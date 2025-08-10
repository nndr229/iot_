async function fetchJSON(url, opts = {}) {
  const r = await fetch(
    url,
    Object.assign({ headers: { 'Content-Type': 'application/json' } }, opts)
  );
  if (!r.ok) {
    const t = await r.text().catch(() => String(r.status));
    throw new Error(`HTTP ${r.status}: ${t}`);
  }
  return r.json();
}

let _leafletMap = null;

// --------- Map (Leaflet) ---------
async function initMap() {
  const el = document.getElementById('map');
  if (!el) {
    console.warn('Map element #map not found on this page.');
    return;
  }

  // Ensure the container has height
  if (!el.style.height && !el.classList.contains('map')) {
    el.style.height = '420px';
  }

  if (!_leafletMap) {
    try {
      _leafletMap = L.map(el).setView([20, 0], 2);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap',
      }).addTo(_leafletMap);
      // Invalidate after layout settles so tiles render correctly
      setTimeout(() => _leafletMap.invalidateSize(), 150);
    } catch (e) {
      console.error('Leaflet init failed:', e);
      return;
    }
  }

  try {
    const locs = await fetchJSON('/api/locations');
    locs.forEach((l) => {
      const m = L.marker([Number(l.lat), Number(l.lon)]).addTo(_leafletMap);
      m.bindPopup(
        `<b>${l.name}, ${l.country}</b><br/>Devices: ${l.device_count}`
      );
    });
  } catch (e) {
    console.error('Failed loading /api/locations:', e);
  }
}

// --------- Devices ---------
async function renderDevices() {
  const box = document.getElementById('device-list');
  if (!box) return;
  try {
    const devices = await fetchJSON('/api/devices');
    box.innerHTML = '';
    devices.forEach((d) => {
      const el = document.createElement('div');
      el.className = 'device';
      el.innerHTML = `
        <div class="meta">
          <span class="badge">#${d.id}</span>
          <div>
            <div><strong>${d.name}</strong></div>
            <div class="muted">${d.type} • location ${d.location_id}</div>
          </div>
        </div>
        <button class="toggle ${d.is_on ? 'on' : ''}" onclick="toggleDevice(${
        d.id
      })">${d.is_on ? 'ON' : 'OFF'}</button>
      `;
      box.appendChild(el);
    });
  } catch (e) {
    console.error('Failed loading /api/devices:', e);
    box.innerHTML =
      '<div class="muted">Failed to load devices. Check console.</div>';
  }
}

async function toggleDevice(id) {
  try {
    await fetchJSON(`/api/device/${id}/toggle`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    await renderDevices();
  } catch (e) {
    alert('Toggle failed: ' + e.message);
  }
}

// --------- Admin helpers ---------
async function createLocation(e) {
  e.preventDefault();
  const f = e.target;
  await fetchJSON('/api/admin/create_location', {
    method: 'POST',
    body: JSON.stringify({
      name: f.name.value,
      country: f.country.value,
      lat: f.lat.value,
      lon: f.lon.value,
    }),
  });
  location.reload();
  return false;
}

async function createDevice(e) {
  e.preventDefault();
  const f = e.target;
  await fetchJSON('/api/admin/create_device', {
    method: 'POST',
    body: JSON.stringify({
      name: f.name.value,
      type: f.type.value,
      location_id: f.location_id.value,
    }),
  });
  alert('Device created');
  return false;
}

async function assignUser(e) {
  e.preventDefault();
  const f = e.target;
  await fetchJSON('/api/admin/assign_user_location', {
    method: 'POST',
    body: JSON.stringify({
      user_id: Number(f.user_id.value),
      location_id: Number(f.location_id.value),
    }),
  });
  alert('Assigned');
  return false;
}

// --------- Support Chat (Gemini) ---------
async function sendSupport() {
  const input = document.getElementById('support-text');
  const log = document.getElementById('support-log');
  if (!input || !log) return;
  const text = input.value.trim();
  if (!text) return;
  log.insertAdjacentHTML(
    'beforeend',
    `<div class='bubble me'>${escapeHtml(text)}</div>`
  );
  input.value = '';
  try {
    const res = await fetchJSON('/api/support', {
      method: 'POST',
      body: JSON.stringify({ message: text }),
    });
    if (res.ok) {
      log.insertAdjacentHTML(
        'beforeend',
        `<div class='bubble bot'>${escapeHtml(res.answer)}</div>`
      );
      log.scrollTop = log.scrollHeight;
    } else {
      log.insertAdjacentHTML(
        'beforeend',
        `<div class='bubble bot'>Error: ${escapeHtml(
          res.error || 'Unknown'
        )}</div>`
      );
    }
  } catch (e) {
    log.insertAdjacentHTML(
      'beforeend',
      `<div class='bubble bot'>${escapeHtml(e.message)}</div>`
    );
  }
}

function escapeHtml(s) {
  return s.replace(
    /[&<>'"]/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[
        c
      ])
  );
}

// Auto-run once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  if (document.getElementById('map')) initMap();
  if (document.getElementById('device-list')) renderDevices();
});

// ===== Admin: Users table =====
let __usersCache = [];

async function loadUsers() {
  const box = document.getElementById('users');
  if (!box) return;
  box.innerHTML = '<div class="muted">Loading users…</div>';

  try {
    const res = await fetchJSON('/api/admin/users');
    if (!res.ok) throw new Error(res.error || 'Failed to load users');
    __usersCache = res.users || [];
    renderUsersTable(__usersCache);
  } catch (e) {
    console.error(e);
    box.innerHTML = '<div class="muted">Failed to load users.</div>';
  }
}

function renderUsersTable(users) {
  const box = document.getElementById('users');
  if (!box) return;

  const rows = users
    .map(
      (u) => `
    <tr>
      <td style="padding:.35rem .4rem;">${u.id}</td>
      <td style="padding:.35rem .4rem;">${escapeHtml(u.name || '')}</td>
      <td style="padding:.35rem .4rem;">${escapeHtml(u.email)}</td>
      <td style="padding:.35rem .4rem;">${
        u.is_superuser ? 'SUPER' : 'LOCAL'
      }</td>
      <td style="padding:.35rem .4rem;">${u.location_id ?? '—'}</td>
      <td style="padding:.35rem .4rem;">
        <button class="btn" onclick="fillUser(${u.id})">Pick ID ${u.id}</button>
      </td>
    </tr>
  `
    )
    .join('');

  box.innerHTML = `
    <div style="overflow:auto;">
      <table style="width:100%; border-collapse: collapse;">
        <thead>
          <tr>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">ID</th>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">Name</th>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">Email</th>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">Role</th>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">Location</th>
            <th style="text-align:left;padding:.4rem;border-bottom:1px solid #1b222c;">Pick</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function filterUsers() {
  const q = (document.getElementById('user-search')?.value || '')
    .toLowerCase()
    .trim();
  if (!q) return renderUsersTable(__usersCache);
  const filtered = __usersCache.filter(
    (u) =>
      String(u.id).includes(q) ||
      (u.name || '').toLowerCase().includes(q) ||
      (u.email || '').toLowerCase().includes(q)
  );
  renderUsersTable(filtered);
}

function fillUser(id) {
  const el = document.getElementById('assign_user_id');
  if (el) el.value = String(id);
}

function fillLocation(id) {
  const el1 = document.getElementById('assign_location_id');
  const el2 = document.getElementById('device_location_id');
  if (el1) el1.value = String(id);
  if (el2) el2.value = String(id);
}

// --- Support Chat (Gemini) ---
async function sendSupport() {
  const input = document.getElementById('support-text');
  const log = document.getElementById('support-log');
  if (!input || !log) return;

  const text = input.value.trim();
  if (!text) return;

  // Show my message
  log.insertAdjacentHTML(
    'beforeend',
    `<div class='bubble me'>${escapeHtml(text)}</div>`
  );
  input.value = '';

  // Optional: typing indicator
  const typingId = `t${Date.now()}`;
  log.insertAdjacentHTML(
    'beforeend',
    `<div id="${typingId}" class='bubble bot'>Thinking…</div>`
  );
  log.scrollTop = log.scrollHeight;

  try {
    const res = await fetch('/api/support', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    document.getElementById(typingId)?.remove();

    if (data.ok) {
      log.insertAdjacentHTML(
        'beforeend',
        `<div class='bubble bot'>${escapeHtml(data.answer)}</div>`
      );
    } else {
      log.insertAdjacentHTML(
        'beforeend',
        `<div class='bubble bot'>Error: ${escapeHtml(
          data.error || 'Unknown'
        )}</div>`
      );
    }
    log.scrollTop = log.scrollHeight;
  } catch (e) {
    document.getElementById(typingId)?.remove();
    log.insertAdjacentHTML(
      'beforeend',
      `<div class='bubble bot'>${escapeHtml(e.message)}</div>`
    );
  }
}

function escapeHtml(s) {
  return s.replace(
    /[&<>'"]/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[
        c
      ])
  );
}

// Auto-run once DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  // Existing initializers
  if (document.getElementById('map')) initMap?.();
  if (document.getElementById('device-list')) renderDevices?.();

  // Wire up Support send button + Enter key
  const sendBtn = document.getElementById('support-send');
  const input = document.getElementById('support-text');
  if (sendBtn) sendBtn.addEventListener('click', sendSupport);
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendSupport();
      }
    });
  }
});

// ---------- Global Support Chat (floating) ----------
function chatAppend(where, who, text) {
  const log = document.getElementById(where);
  if (!log) return;
  const cls = who === 'me' ? 'bubble me' : 'bubble bot';
  log.insertAdjacentHTML(
    'beforeend',
    `<div class="${cls}">${escapeHtml(text)}</div>`
  );
  log.scrollTop = log.scrollHeight;
}

async function sendSupportFloating() {
  const input = document.getElementById('chat-input');
  const logId = 'chat-log';
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  chatAppend(logId, 'me', text);
  input.value = '';

  const typingId = `t${Date.now()}`;
  chatAppend(logId, 'bot', `<span id="${typingId}">Thinking…</span>`);

  try {
    const r = await fetch('/api/support', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await r.json();
    const typing = document.getElementById(typingId);
    if (typing) typing.parentElement.remove();

    if (data.ok) {
      chatAppend(logId, 'bot', data.answer);
    } else {
      chatAppend(logId, 'bot', 'Error: ' + (data.error || 'Unknown'));
    }
  } catch (e) {
    const typing = document.getElementById(typingId);
    if (typing) typing.parentElement.remove();
    chatAppend(logId, 'bot', e.message || String(e));
  }
}

function toggleChatDrawer(open) {
  const drawer = document.getElementById('chat-drawer');
  if (!drawer) return;
  if (open === undefined) drawer.classList.toggle('open');
  else drawer.classList.toggle('open', !!open);
}

document.addEventListener('DOMContentLoaded', () => {
  // Existing initializers: keep yours
  if (document.getElementById('map')) initMap?.();
  if (document.getElementById('device-list')) renderDevices?.();

  // Floating chat bindings
  const fab = document.getElementById('chat-fab');
  const close = document.getElementById('chat-close');
  const send = document.getElementById('chat-send');
  const input = document.getElementById('chat-input');

  if (fab) fab.addEventListener('click', () => toggleChatDrawer());
  if (close) close.addEventListener('click', () => toggleChatDrawer(false));
  if (send) send.addEventListener('click', sendSupportFloating);
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendSupportFloating();
      }
    });
  }
});
