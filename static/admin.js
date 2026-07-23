const TOKEN_KEY = 'gpm_token';
const USER_KEY = 'gpm_user';

function getToken() { return localStorage.getItem(TOKEN_KEY); }
function authHeaders() { return { 'Authorization': 'Bearer ' + getToken() }; }
function logout() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY); location.href = '/login'; }

// 启动校验登录态
if (!getToken()) { location.href = '/login'; }
else {
  document.getElementById('userBadge').textContent = localStorage.getItem(USER_KEY) || 'admin';
  document.getElementById('logoutBtn').addEventListener('click', logout);
}

function fmtBytes(n) {
  if (n == null) return '—';
  const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(v < 10 ? 1 : 0) + ' ' + u[i];
}
function fmtDuration(sec) {
  if (sec == null) return '—';
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d > 0) return d + '天 ' + h + '时';
  if (h > 0) return h + '时 ' + m + '分';
  return m + '分';
}
function shortId(id) { return id ? id.slice(0, 8) : ''; }

// 401 统一跳登录
async function api(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) { logout(); return null; }
  return res;
}

// ---------- 状态 ----------
async function loadStatus() {
  try {
    const res = await api('/api/v1/status');
    if (!res) return;
    const d = await res.json();
    document.getElementById('statName').textContent = d.server_name;
    document.getElementById('statUptime').textContent = fmtDuration(d.uptime_seconds);
    document.getElementById('statModpacks').textContent = d.modpack_count;
    document.getElementById('statMods').textContent = d.mod_count;
    document.getElementById('statStorage').textContent = fmtBytes(d.storage_used_bytes);
    document.getElementById('serverKind').textContent = d.server_kind;
  } catch (e) { console.error(e); }
}

// ---------- 整合包 ----------
async function loadModpacks() {
  try {
    const res = await api('/api/v1/modpacks');
    if (!res) return;
    const d = await res.json();
    const tbody = document.getElementById('modpackTbody');
    const items = d.modpacks || [];
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="8" class="empty-row">暂无整合包</td></tr>'; return; }
    tbody.innerHTML = items.map(m => `
      <tr>
        <td title="${m.id}">${shortId(m.id)}</td>
        <td>${m.name}</td>
        <td>${m.version}</td>
        <td>${m.game}</td>
        <td>${m.game_version}</td>
        <td>${m.mod_loader}</td>
        <td>${fmtBytes(m.file_size)}</td>
        <td>
          <button class="btn-dl" onclick="dlModpack('${m.id}')">下载</button>
          <button class="btn-del" onclick="delModpack('${m.id}')">删除</button>
        </td>
      </tr>`).join('');
  } catch (e) { console.error(e); }
}
function dlModpack(id) { window.open('/api/v1/modpacks/' + id + '/download', '_blank'); }
async function delModpack(id) {
  if (!confirm('确定删除该整合包？')) return;
  const res = await api('/api/v1/modpacks/' + id, { method: 'DELETE', headers: authHeaders() });
  if (res && res.ok) { loadModpacks(); loadStatus(); } else { alert('删除失败'); }
}

document.getElementById('modpackForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('modpackUploadBtn');
  const msg = document.getElementById('modpackMsg');
  btn.disabled = true; btn.textContent = '上传中...'; msg.className = 'form-msg'; msg.textContent = '';
  const fd = new FormData(e.target);
  try {
    const res = await api('/api/v1/modpacks', { method: 'POST', headers: authHeaders(), body: fd });
    const data = await res.json();
    if (res.ok) { msg.className = 'form-msg ok'; msg.textContent = '上传成功'; e.target.reset(); loadModpacks(); loadStatus(); }
    else { msg.className = 'form-msg err'; msg.textContent = data.error || '上传失败'; }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  btn.disabled = false; btn.textContent = '上传整合包';
});

// ---------- 模组 ----------
async function loadMods() {
  try {
    const res = await api('/api/v1/mods');
    if (!res) return;
    const d = await res.json();
    const tbody = document.getElementById('modTbody');
    const items = d.mods || [];
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="6" class="empty-row">暂无模组</td></tr>'; return; }
    tbody.innerHTML = items.map(m => `
      <tr>
        <td title="${m.id}">${shortId(m.id)}</td>
        <td>${m.name}</td>
        <td>${m.version}</td>
        <td>${m.game}</td>
        <td>${fmtBytes(m.file_size)}</td>
        <td>
          <button class="btn-dl" onclick="dlMod('${m.id}')">下载</button>
          <button class="btn-del" onclick="delMod('${m.id}')">删除</button>
        </td>
      </tr>`).join('');
  } catch (e) { console.error(e); }
}
function dlMod(id) { window.open('/api/v1/mods/' + id + '/download', '_blank'); }
async function delMod(id) {
  if (!confirm('确定删除该模组？')) return;
  const res = await api('/api/v1/mods/' + id, { method: 'DELETE', headers: authHeaders() });
  if (res && res.ok) { loadMods(); loadStatus(); } else { alert('删除失败'); }
}

document.getElementById('modForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('modUploadBtn');
  const msg = document.getElementById('modMsg');
  btn.disabled = true; btn.textContent = '上传中...'; msg.className = 'form-msg'; msg.textContent = '';
  const fd = new FormData(e.target);
  try {
    const res = await api('/api/v1/mods', { method: 'POST', headers: authHeaders(), body: fd });
    const data = await res.json();
    if (res.ok) { msg.className = 'form-msg ok'; msg.textContent = '上传成功'; e.target.reset(); loadMods(); loadStatus(); }
    else { msg.className = 'form-msg err'; msg.textContent = data.error || '上传失败'; }
  } catch (err) { msg.className = 'form-msg err'; msg.textContent = '网络错误：' + err; }
  btn.disabled = false; btn.textContent = '上传模组';
});

// 首次加载 + 定时刷新状态
loadStatus(); loadModpacks(); loadMods();
setInterval(loadStatus, 10000);
