/* Shared unread counts; pending workflow totals remain independent of reading. */
document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('panel-messages');
  if (!root) return;
  const menu = document.getElementById('panel-messages-menu');
  const button = document.getElementById('panel-messages-toggle');
  const list = document.getElementById('panel-message-list');
  const unread = document.getElementById('panel-unread');
  const readAll = document.getElementById('panel-notice-read-all');
  const paths = { contact: '/panel/contact', registrations: '/panel/registrations', review: '/panel/review', trash: '/panel/downloads/trash', users: '/panel/users', content: '/panel/downloads', reports: '/panel/links' };
  let previous = null;
  let loading = false;
  let acknowledging = false;
  let revision = 0;
  button.addEventListener('click', () => {
    menu.classList.toggle('hidden');
    button.setAttribute('aria-expanded', String(!menu.classList.contains('hidden')));
  });
  document.addEventListener('click', (event) => {
    if (!root.contains(event.target)) { menu.classList.add('hidden'); button.setAttribute('aria-expanded', 'false'); }
  });
  function render(data) {
    if (!Array.isArray(data.items)) return;
    const counters = data.unread_counters || {};
    const signature = data.items.filter(item => item.unread > 0).map(item => item.kind + ':' + item.latest).join('|');
    if (previous !== null && signature && signature !== previous && window.AppToast) window.AppToast.show(root.dataset.update, { type: 'info', id: 'panel-updates' });
    previous = signature;
    unread.textContent = String(data.unread);
    unread.classList.toggle('is-read', !data.unread);
    unread.setAttribute('aria-label', root.dataset.unread + ': ' + data.unread);
    if (readAll) readAll.querySelector('button').disabled = !data.unread;
    list.replaceChildren();
    if (!data.items.length) {
      const empty = document.createElement('p'); empty.className = 'p-3 text-sm text-slate-500';
      empty.textContent = root.dataset.empty; list.appendChild(empty);
    }
    data.items.forEach(item => {
      if (!(item.kind in paths)) return;
      const form = document.createElement('form'); form.method = 'post'; form.action = '/panel/notifications/open';
      const kind = document.createElement('input'); kind.type = 'hidden'; kind.name = 'kind'; kind.value = item.kind;
      const token = document.createElement('input'); token.type = 'hidden'; token.name = 'csrf_token'; token.value = document.querySelector('meta[name="csrf-token"]').content;
      const link = document.createElement('button'); link.type = 'submit'; link.className = 'panel-message-link';
      const label = document.createElement('span'); label.textContent = item.label;
      const state = document.createElement('small'); state.className = 'panel-notice-state'; state.textContent = item.unread ? root.dataset.new : root.dataset.read;
      label.appendChild(state);
      const count = document.createElement('span'); count.className = 'panel-count' + (item.unread ? '' : ' is-read'); count.textContent = String(item.unread || item.count);
      link.append(label, count); form.append(kind, token, link); list.appendChild(form);
    });
    Object.entries(paths).forEach(([kind, path]) => {
      document.querySelectorAll('.admin-nav-link[href="' + path + '"]').forEach(link => {
        let badge = link.querySelector('[data-panel-count]');
        if (!badge) { badge = document.createElement('span'); badge.dataset.panelCount = kind; badge.className = 'panel-count'; link.appendChild(badge); }
        const count = Number(counters[kind] || 0); badge.textContent = String(count); badge.classList.toggle('hidden', !count);
      });
    });
    document.querySelectorAll('summary[data-panel-group]').forEach(summary => {
      const links = new Set(Array.from(summary.parentElement.querySelectorAll('.admin-nav-link')).map(link => link.getAttribute('href')));
      const total = Object.entries(paths).reduce((sum, [kind, path]) => sum + (links.has(path) ? Number(counters[kind] || 0) : 0), 0);
      let badge = summary.querySelector('[data-panel-total]');
      if (!badge) { badge = document.createElement('span'); badge.dataset.panelTotal = ''; badge.className = 'panel-count'; summary.insertBefore(badge, summary.lastElementChild); }
      badge.textContent = String(total); badge.classList.toggle('hidden', !total);
    });
    document.querySelectorAll('.dashboard-update-card[data-notice-kind]').forEach(card => {
      const isUnread = Number(counters[card.dataset.noticeKind] || 0) > 0;
      card.querySelector('.panel-notice-state').textContent = isUnread ? root.dataset.new : root.dataset.read;
      card.querySelector('.panel-count').classList.toggle('is-read', !isUnread);
    });
  }
  async function refresh() {
    if (document.hidden || loading || acknowledging) return;
    loading = true;
    const observedRevision = revision;
    try {
      const response = await fetch('/panel/notifications', { headers: { Accept: 'application/json' }, redirect: 'error', cache: 'no-store' });
      if (response.ok) {
        const data = await response.json();
        if (observedRevision === revision) render(data);
      }
    } catch (_) { /* Keep the server-rendered counts on transient failures. */ }
    finally { loading = false; }
  }
  if (readAll) readAll.addEventListener('submit', async event => {
    event.preventDefault();
    if (acknowledging) return;
    acknowledging = true;
    revision += 1;
    readAll.querySelector('button').disabled = true;
    try {
      const response = await fetch(readAll.action, { method: 'POST', body: new FormData(readAll), headers: { Accept: 'application/json' }, redirect: 'error', cache: 'no-store' });
      if (!response.ok) throw new Error('Notification acknowledgment failed');
      render(await response.json());
      if (window.AppToast) window.AppToast.show(root.dataset.readAllDone, { type: 'success', id: 'notices-read' });
    } catch (_) {
      readAll.querySelector('button').disabled = false;
      if (window.AppToast) window.AppToast.show(root.dataset.readFailed, { type: 'error', id: 'notices-read' });
    }
    finally { acknowledging = false; }
  });
  const seed = document.getElementById('panel-notice-data');
  if (seed) { try { render(JSON.parse(seed.textContent)); } catch (_) { /* Fetch a fresh snapshot below. */ } }
  refresh();
  setInterval(refresh, 30000);
  document.addEventListener('visibilitychange', refresh);
});
