import os
import json
from datetime import datetime
from dataclasses import dataclass

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import LoginManager, login_user, login_required, current_user, logout_user, UserMixin
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, scoped_session
from dotenv import load_dotenv

# --- LLM (Gemini via LangChain) ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage

load_dotenv()

# ----------------- Flask Setup -----------------
app = Flask(__name__, instance_relative_config=True)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Ensure instance folder exists (for SQLite)
os.makedirs(app.instance_path, exist_ok=True)
DB_PATH = os.path.join(app.instance_path, 'app.db')
DB_URI = f"sqlite:///{DB_PATH}"

# ----------------- Database Setup -----------------
Base = declarative_base()
engine = create_engine(DB_URI, echo=False, future=True)
SessionLocal = scoped_session(sessionmaker(
    bind=engine, autoflush=False, autocommit=False))


class User(Base, UserMixin):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_superuser = Column(Boolean, default=False)
    location_id = Column(Integer, ForeignKey('locations.id'),
                         nullable=True)  # local user anchors
    location = relationship('Location', back_populates='users')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Location(Base):
    __tablename__ = 'locations'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    country = Column(String(120), nullable=False)
    lat = Column(String(50), nullable=False)
    lon = Column(String(50), nullable=False)

    devices = relationship(
        'Device', back_populates='location', cascade='all, delete')
    users = relationship('User', back_populates='location')


class Device(Base):
    __tablename__ = 'devices'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    type = Column(String(50), nullable=False)  # light, pump, etc.
    is_on = Column(Boolean, default=False)
    location_id = Column(Integer, ForeignKey('locations.id'))
    location = relationship('Location', back_populates='devices')


class DeviceLog(Base):
    __tablename__ = 'device_logs'
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey('devices.id'))
    action = Column(String(50))  # on/off
    actor_user_id = Column(Integer, ForeignKey('users.id'))
    timestamp = Column(DateTime, default=datetime.utcnow)
    note = Column(Text)


Base.metadata.create_all(engine)

# ----------------- Auth Setup -----------------
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    db = SessionLocal()
    return db.get(User, int(user_id))

# ----------------- Forms -----------------


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
                             DataRequired(), Length(min=4)])
    remember = BooleanField('Remember me')
    submit = SubmitField('Sign in')


class RegisterForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[
                             DataRequired(), Length(min=4)])
    submit = SubmitField('Create account')

# ----------------- Seed Data -----------------


def seed_if_empty():
    db = SessionLocal()
    if db.query(Location).count() == 0:
        dubai = Location(name='Dubai', country='UAE',
                         lat='25.2048', lon='55.2708')
        kollam = Location(name='Kollam', country='India',
                          lat='8.8932', lon='76.6141')
        db.add_all([dubai, kollam])
        db.flush()

        # Dubai devices: 2 lights, 3 pumps
        devices = [
            Device(name='Dubai Light A', type='light', location_id=dubai.id),
            Device(name='Dubai Light B', type='light', location_id=dubai.id),
            Device(name='Dubai Pump 1', type='pump', location_id=dubai.id),
            Device(name='Dubai Pump 2', type='pump', location_id=dubai.id),
            Device(name='Dubai Pump 3', type='pump', location_id=dubai.id),
        ]
        # Kollam devices: 2 lights, 3 pumps
        devices += [
            Device(name='Kollam Light A', type='light', location_id=kollam.id),
            Device(name='Kollam Light B', type='light', location_id=kollam.id),
            Device(name='Kollam Pump 1', type='pump', location_id=kollam.id),
            Device(name='Kollam Pump 2', type='pump', location_id=kollam.id),
            Device(name='Kollam Pump 3', type='pump', location_id=kollam.id),
        ]
        db.add_all(devices)

    if db.query(User).count() == 0:
        # Create a superuser
        admin = User(name='Super Admin',
                     email='admin@example.com', is_superuser=True)
        admin.set_password('admin123')
        db.add(admin)
    db.commit()


seed_if_empty()

# ----------------- Helpers -----------------


def require_superuser():
    if not current_user.is_authenticated or not current_user.is_superuser:
        abort(403)

# simulate an IoT transport (replace with real MQTT/HTTP later)


@dataclass
class IoTResult:
    ok: bool
    message: str


def iot_send(device: Device, target_state: bool) -> IoTResult:
    # Mocked call to real device edge function
    # In production, integrate your MQTT/HTTP call here
    # Simulate success always for demo
    return IoTResult(True, f"Simulated send to {device.name}: set {'ON' if target_state else 'OFF'}")

# ----------------- Routes -----------------


@app.route('/')
@login_required
def index():
    db = SessionLocal()
    if current_user.is_superuser:
        locations = db.query(Location).all()
        devices = db.query(Device).all()
    else:
        # Local user: limited to their location
        if current_user.location_id:
            locations = db.query(Location).filter(
                Location.id == current_user.location_id).all()
            devices = db.query(Device).filter(
                Device.location_id == current_user.location_id).all()
        else:
            locations, devices = [], []
    return render_template('dashboard.html', locations=locations, devices=devices, user=current_user)


@app.route('/admin')
@login_required
def admin():
    require_superuser()
    db = SessionLocal()
    locations = db.query(Location).all()
    users = db.query(User).all()
    return render_template('admin.html', locations=locations, users=users)


@app.route('/api/admin/users')
@login_required
def list_users_admin():
    # superuser only
    if not current_user.is_superuser:
        return jsonify({'ok': False, 'error': 'Forbidden'}), 403
    db = SessionLocal()
    users = db.query(User).all()
    return jsonify({
        'ok': True,
        'users': [
            {
                'id': u.id,
                'name': u.name,
                'email': u.email,
                'is_superuser': bool(u.is_superuser),
                'location_id': u.location_id
            }
            for u in users
        ]
    })


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if request.method == 'POST':  # bypass strict validate_on_submit for debugging
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        db = SessionLocal()
        user = db.query(User).filter(User.email == email).first()
        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get('remember')))
            return redirect(url_for('index'))
        flash('Invalid credentials', 'error')
    return render_template('login.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        db = SessionLocal()
        if db.query(User).filter(User.email == form.email.data.lower()).first():
            flash('Email already registered', 'error')
            return render_template('register.html', form=form)
        # default normal user not superuser; unassigned location initially
        user = User(name=form.name.data, email=form.email.data.lower())
        user.set_password(form.password.data)
        db.add(user)
        db.commit()
        flash('Account created. You can log in now.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ------------- Admin APIs -------------


@app.route('/api/admin/assign_user_location', methods=['POST'])
@login_required
def assign_user_location():
    require_superuser()
    payload = request.get_json(force=True)
    user_id = payload.get('user_id')
    location_id = payload.get('location_id')
    db = SessionLocal()
    user = db.get(User, user_id)
    loc = db.get(Location, location_id)
    if not user or not loc:
        return jsonify({'ok': False, 'error': 'User or Location not found'}), 404
    user.location_id = loc.id
    db.commit()
    return jsonify({'ok': True})


@app.route('/api/admin/create_location', methods=['POST'])
@login_required
def create_location():
    require_superuser()
    payload = request.get_json(force=True)
    name = payload.get('name')
    country = payload.get('country')
    lat = payload.get('lat')
    lon = payload.get('lon')
    if not all([name, country, lat, lon]):
        return jsonify({'ok': False, 'error': 'Missing fields'}), 400
    db = SessionLocal()
    loc = Location(name=name, country=country, lat=str(lat), lon=str(lon))
    db.add(loc)
    db.commit()
    return jsonify({'ok': True, 'location_id': loc.id})


@app.route('/api/admin/create_device', methods=['POST'])
@login_required
def create_device():
    require_superuser()
    payload = request.get_json(force=True)
    name = payload.get('name')
    dtype = payload.get('type')
    location_id = payload.get('location_id')
    if not all([name, dtype, location_id]):
        return jsonify({'ok': False, 'error': 'Missing fields'}), 400
    db = SessionLocal()
    dev = Device(name=name, type=dtype, location_id=int(location_id))
    db.add(dev)
    db.commit()
    return jsonify({'ok': True, 'device_id': dev.id})

# ------------- Device APIs -------------


@app.route('/api/devices')
@login_required
def list_devices():
    db = SessionLocal()
    q = db.query(Device)
    if not current_user.is_superuser and current_user.location_id:
        q = q.filter(Device.location_id == current_user.location_id)
    devices = q.all()
    return jsonify([
        {'id': d.id, 'name': d.name, 'type': d.type,
            'is_on': d.is_on, 'location_id': d.location_id}
        for d in devices
    ])


@app.route('/api/device/<int:device_id>/toggle', methods=['POST'])
@login_required
def toggle_device(device_id):
    db = SessionLocal()
    dev = db.get(Device, device_id)
    if not dev:
        return jsonify({'ok': False, 'error': 'Device not found'}), 404
    # authorization: local users can only control their location
    if not current_user.is_superuser:
        if not current_user.location_id or current_user.location_id != dev.location_id:
            return jsonify({'ok': False, 'error': 'Forbidden'}), 403

    target_state = not dev.is_on
    send_res = iot_send(dev, target_state)
    if not send_res.ok:
        return jsonify({'ok': False, 'error': 'IoT send failed', 'detail': send_res.message}), 502

    dev.is_on = target_state
    log = DeviceLog(device_id=dev.id, action='on' if target_state else 'off', actor_user_id=current_user.id,
                    note=send_res.message)
    db.add(log)
    db.commit()
    return jsonify({'ok': True, 'device_id': dev.id, 'is_on': dev.is_on})


@app.route('/api/locations')
@login_required
def list_locations():
    db = SessionLocal()
    if current_user.is_superuser:
        locs = db.query(Location).all()
    else:
        locs = db.query(Location).filter(
            Location.id == current_user.location_id).all()
    return jsonify([
        {'id': l.id, 'name': l.name, 'country': l.country, 'lat': float(l.lat), 'lon': float(l.lon),
         'device_count': len(l.devices)} for l in locs
    ])

# ------------- Support (Gemini) -------------


def get_support_context_json():
    db = SessionLocal()
    locs = db.query(Location).all()
    payload = {
        'locations': [
            {
                'id': l.id,
                'name': l.name,
                'country': l.country,
                'lat': l.lat,
                'lon': l.lon,
                'devices': [
                    {'id': d.id, 'name': d.name, 'type': d.type, 'is_on': d.is_on}
                    for d in l.devices
                ]
            }
            for l in locs
        ]
    }
    return json.dumps(payload, indent=2)

# === DEBUG: whoami, users, create_admin (remove after use) ===


@app.route('/debug/whoami')
def debug_whoami():
    if current_user.is_authenticated:
        return {
            "auth": True,
            "id": current_user.id,
            "email": current_user.email,
            "is_superuser": current_user.is_superuser,
            "location_id": current_user.location_id
        }
    return {"auth": False}


@app.route('/debug/users')
def debug_users():
    db = SessionLocal()
    users = db.query(User).all()
    return {
        "count": len(users),
        "users": [{"id": u.id, "email": u.email, "is_superuser": u.is_superuser} for u in users]
    }


@app.route('/debug/create_admin')
def debug_create_admin():
    db = SessionLocal()
    u = db.query(User).filter_by(email="admin@example.com").first()
    if not u:
        u = User(name="Super Admin",
                 email="admin@example.com", is_superuser=True)
        u.set_password("admin123")
        db.add(u)
        db.commit()
        return {"created": True}
    return {"created": False, "message": "Admin already exists"}


@app.route('/api/support', methods=['POST'])
@login_required
def support():
    data = request.get_json(force=True)
    user_msg = data.get('message', '')
    if not user_msg:
        return jsonify({'ok': False, 'error': 'Empty message'}), 400

    sys_prompt = (
        "You are an IoT Customer Support Agent. Be concise and actionable. "
        "When applicable, use the provided JSON context of locations and devices to answer. "
        "NEVER invent devices or locations that are not in context."
    )

    context_json = get_support_context_json()

    try:
        gemini = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash", google_api_key=os.getenv('GEMINI_API_KEY'))
        messages = [
            SystemMessage(content=sys_prompt +
                          "\n\nContext JSON:\n" + context_json),
            HumanMessage(content=user_msg)
        ]
        resp = gemini(messages)
        answer = resp.content
        return jsonify({'ok': True, 'answer': answer})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

# ----------------- Views -----------------


@app.route('/health')
def health():
    return {'ok': True, 'time': datetime.utcnow().isoformat()}

# ----------------- CLI -----------------


@app.cli.command('seed')
def cli_seed():
    seed_if_empty()
    print('Seeded.')


if __name__ == '__main__':
    app.run(debug=True)
