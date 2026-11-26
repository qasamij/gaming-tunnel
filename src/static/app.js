'use strict';

const csrf = document.querySelector('meta[name="csrf"]').content;
const $ = (id) => document.getElementById(id);
const rate = (v) => v == null ? '—' : (v / 1e6).toFixed(3) + ' Mbps';
const size = (v) => v == null ? '—' : (v / 1048576).toFixed(2) + ' MiB';
const elapsed = (ts, now) => !ts ? '—' : Math.max(0, Math.round(now - ts)) + ' s';
const num = (v, digits = 2) => v == null ? '—' : Number(v).toFixed(digits);

let latest = null;
let refreshing = false;

function toast(message, ok = true) {
  const box = $('toast-box');
  const node = document.createElement('div');
  node.className = 'toast' + (ok ? '' : ' bad');
  node.textContent = message || (ok ? 'انجام شد' : 'خطا');
  box.append(node);
  setTimeout(() => node.remove(), 3500);
}

function cell(row, value) {
  const td = document.createElement('td');
  td.textContent = value;
  row.append(td);
  return td;
}

function button(label, action, extra = {}, cls = '') {
  const b = document.createElement('button');
  b.type = 'button';
  b.textContent = label;
  b.dataset.action = action;
  Object.entries(extra).forEach(([k, v]) => { b.dataset[k] = v; });
  if (cls) b.className = cls;
  return b;
}

function drawHistory(history) {
  const canvas = $('traffic');
  if (!canvas) return;
  const width = canvas.clientWidth || 320;
  const height = 190;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = width * ratio;
  canvas.height = height * ratio;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const usable = history.filter((h) => h.up != null && h.down != null);
  const max = Math.max(1000, ...usable.flatMap((h) => [h.up, h.down]));
  ctx.fillStyle = '#a8b8cc';
  ctx.font = '12px Tahoma, sans-serif';
  ctx.fillText('max ' + rate(max), 8, 16);

  const plot = (key, color) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    let started = false;
    history.forEach((h, i) => {
      if (h[key] == null) { started = false; return; }
      const x = (i * width) / Math.max(1, history.length - 1);
      const y = height - 14 - (h[key] / max) * (height - 34);
      if (started) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      started = true;
    });
    ctx.stroke();
  };
  plot('down', '#76e0c0');
  plot('up', '#60a5fa');
}

function renderUsers(data) {
  const body = $('users-table').querySelector('tbody');
  body.replaceChildren();
  const names = Object.values(data.users).map((u) => u.name || 'Peer');
  $('active-users').textContent = Object.values(data.users).filter((u) => u.enabled).length + ' / ' + names.length;

  Object.entries(data.interfaces.omclient0 || []).forEach((row) => {
    const u = data.users[row.pub] || {};
    const tr = document.createElement('tr');
    cell(tr, u.name || 'Peer');
    cell(tr, row.ip || '—');
    const badge = document.createElement('td');
    const span = document.createElement('span');
    span.className = 'badge ' + (u.enabled ? 'on' : 'off');
    span.textContent = u.enabled ? 'فعال' : 'قطع';
    badge.append(span);
    tr.append(badge);
    cell(tr, rate(row.down));
    cell(tr, rate(row.up));
    cell(tr, size(u.used));
    const limit = u.quota ? size(u.quota) + ' سهمیه' : 'نامحدود';
    const expiry = u.expires ? new Date(u.expires * 1000).toLocaleDateString('fa-IR') : 'نامحدود';
    cell(tr, expiry + ' • ' + limit);
    const actions = document.createElement('td');
    const name = u.name;
    if (name) {
      const link = document.createElement('a');
      link.href = '/download/' + encodeURIComponent(name);
      link.textContent = 'کانفیگ';
      link.style.color = '#76e0c0';
      link.style.marginLeft = '8px';
      actions.append(link);
      const qr = document.createElement('a');
      qr.href = '/qr/' + encodeURIComponent(name);
      qr.textContent = 'QR';
      qr.style.color = '#60a5fa';
      qr.style.marginLeft = '8px';
      actions.append(qr);
      actions.append(button(u.enabled ? 'قطع' : 'فعال', u.enabled ? 'disable' : 'enable', { name }));
      actions.append(button('حذف', 'delete', { name }, 'del'));
    }
    tr.append(actions);
    body.append(tr);
  });
}

function renderLatency(data) {
  const l = data.latency || {};
  $('rtt').textContent = num(l.avg == null ? l.rtt : l.avg) + ' ms';
  $('jitter').textContent = num(l.jitter) + ' ms';
  $('loss').textContent = num(l.loss, 1) + ' %';

  const tiles = $('latency-tiles');
  tiles.replaceChildren();
  const values = [
    ['آخرین RTT', num(l.rtt) + ' ms'],
    ['میانگین', num(l.avg) + ' ms'],
    ['کمینه / بیشینه', num(l.min) + ' / ' + num(l.max) + ' ms'],
    ['Jitter', num(l.jitter) + ' ms'],
    ['اتلاف', num(l.loss, 1) + ' %'],
    ['روش', l.mode === 'udp' ? 'UDP echo' : 'ICMP'],
  ];
  values.forEach(([label, value]) => {
    const tile = document.createElement('div');
    tile.className = 'tile';
    const span = document.createElement('span');
    span.textContent = label;
    const strong = document.createElement('strong');
    strong.textContent = value;
    tile.append(span, strong);
    tiles.append(tile);
  });
  const detail = $('latency-detail');
  detail.replaceChildren();
  const p = document.createElement('p');
  p.textContent = 'هدف: ' + (l.target || '—') +
    ' • UDP تک بسته هر چند ثانیه، بدون نیاز به هماهنگی ساعت دو سرور.';
  detail.append(p);
  const note = document.createElement('small');
  note.textContent = 'این عدد لتنسی تانل است؛ لتنسی واقعی بازی به مسیر exit و ISP بستگی دارد.';
  detail.append(note);
}

function renderInterfaces(data) {
  const host = $('interfaces');
  host.replaceChildren();
  Object.entries(data.interfaces).forEach(([iface, rows]) => {
    const card = document.createElement('section');
    card.className = 'card';
    const title = document.createElement('h3');
    title.textContent = 'اینترفیس ' + iface;
    card.append(title);
    if (rows === null) {
      const warning = document.createElement('p');
      warning.className = 'msg';
      warning.textContent = 'داده در دسترس نیست';
      card.append(warning);
      host.append(card);
      return;
    }
    const table = document.createElement('table');
    const thead = document.createElement('thead');
    const hrow = document.createElement('tr');
    ['Peer / IP', 'Handshake', 'دانلود', 'آپلود', 'دریافت / ارسال', 'مصرف ثبت شده'].forEach((h) => {
      const th = document.createElement('th');
      th.textContent = h;
      hrow.append(th);
    });
    thead.append(hrow);
    table.append(thead);
    const tbody = document.createElement('tbody');
    rows.forEach((row) => {
      const u = data.users[row.pub] || {};
      const tr = document.createElement('tr');
      cell(tr, ((u.name || 'Peer') + ' ' + (row.ip || '')).trim());
      cell(tr, elapsed(row.handshake, data.now));
      cell(tr, rate(row.down));
      cell(tr, rate(row.up));
      cell(tr, size(row.tx) + ' / ' + size(row.rx));
      cell(tr, size(u.used));
      tbody.append(tr);
    });
    table.append(tbody);
    card.append(table);
    host.append(card);
  });
}

function render(data) {
  latest = data;
  if (data.endpoint && document.activeElement !== $('endpoint-input')) {
    $('endpoint-input').value = data.endpoint;
  }
  const h = data.history[data.history.length - 1] || {};
  $('total-down').textContent = rate(h.down);
  $('total-up').textContent = rate(h.up);
  $('updated').textContent = 'به\u200cروزرسانی ' + new Date(data.now * 1000).toLocaleTimeString('fa-IR');
  drawHistory(data.history);
  renderUsers(data);
  renderLatency(data);
  renderInterfaces(data);
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  try {
    const response = await fetch('/metrics', { cache: 'no-store' });
    if (!response.ok) throw new Error('status');
    render(await response.json());
  } catch (error) {
    toast('دریافت آمار ناموفق؛ نشت یا اتصال را بررسی کنید.', false);
  } finally {
    refreshing = false;
  }
}

async function post(payload) {
  const body = new URLSearchParams({ csrf, ...payload });
  try {
    const response = await fetch('/action', {
      method: 'POST',
      body,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    const result = await response.json();
    toast(result.msg, result.ok !== false);
    if (result.ok !== false) await refresh();
    return result;
  } catch (error) {
    toast('ارسال درخواست ناموفق', false);
    return { ok: false };
  }
}

document.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-tab]');
  if (tab) {
    document.querySelectorAll('[data-tab]').forEach((n) => n.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.tab').forEach((s) => s.classList.add('hidden'));
    $('tab-' + tab.dataset.tab).classList.remove('hidden');
    if (tab.dataset.tab === 'overview') drawHistory((latest || {}).history || []);
    return;
  }
  const action = event.target.closest('[data-action]');
  if (!action) return;
  const name = action.dataset.name;
  if (action.dataset.action === 'delete' && !confirm('حذف این کاربر؟')) return;
  const payload = { action: action.dataset.action };
  if (name) payload.name = name;
  post(payload).then((result) => {
    if (result.ok && ['diagnose', 'repair', 'probe', 'test'].includes(payload.action)) {
      $('tool-output').textContent = result.msg;
    }
  });
});

document.addEventListener('submit', (event) => {
  const form = event.target;
  if (form.id === 'logout-form') return;
  event.preventDefault();
  const data = new FormData(form);
  const payload = { action: form.id.replace('-form', '') };
  data.forEach((value, key) => { payload[key] = value; });
  if (form.id === 'create-form') form.reset();
  post(payload).then((result) => {
    if (result.ok && payload.action === 'test') $('tool-output').textContent = result.msg;
  });
});

refresh();
setInterval(refresh, 2000);
