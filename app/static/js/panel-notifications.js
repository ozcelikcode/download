/* Coalesced actionable updates; no private message bodies reach this feed. */
document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('panel-messages');
  if (!root) return;
  const menu = document.getElementById('panel-messages-menu');
  const button = document.getElementById('panel-messages-toggle');
  const list = document.getElementById('panel-message-list');
  const unread = document.getElementById('panel-unread');
  const paths = { contact: '/panel/contact', registrations: '/panel/registrations', review: '/panel/review', trash: '/panel/downloads/trash', users: '/panel/users', content: '/panel/downloads' };
  let previous = null;
  let loading = false;
  button.addEventListener('click', () => {
    menu.classList.toggle('hidden');
    button.setAttribute('aria-expanded', String(!menu.classList.contains('hidden')));
  });
  document.addEventListener('click', (event) => {
    if (!root.contains(event.target)) { menu.classList.add('hidden'); button.setAttribute('aria-expanded', 'false'); }
  });
  async function refresh() {
    if (document.hidden || loading) return;
    loading = true;
    try {
      const response = await fetch('/panel/notifications', { headers: { Accept: 'application/json' }, redirect: 'error', cache: 'no-store' });
      if (!response.ok) return;
      const data = await response.json();
      if (!Array.isArray(data.items)) return;
      const signature = data.items.filter((item) => item.unread > 0).map((item) => item.kind + ':' + item.latest).join('|');
      if (previous !== null && signature && signature !== previous && window.AppToast) window.AppToast.show(root.dataset.update, { type: 'info', id: 'panel-updates' });
      previous = signature;
      unread.textContent = String(data.unread);
      unread.classList.toggle('hidden', !data.unread);
      list.replaceChildren();
      if (!data.items.length) { const empty = document.createElement('p'); empty.className = 'p-3 text-sm text-slate-500'; empty.textContent = root.dataset.empty; list.appendChild(empty); }
      data.items.forEach((item) => {
        if (!(item.kind in paths)) return;
        const form = document.createElement('form'); form.method = 'post'; form.action = '/panel/notifications/open';
        const kind = document.createElement('input'); kind.type = 'hidden'; kind.name = 'kind'; kind.value = item.kind;
        const token = document.createElement('input'); token.type = 'hidden'; token.name = 'csrf_token'; token.value = document.querySelector('meta[name="csrf-token"]').content;
        const link = document.createElement('button'); link.type = 'submit'; link.className = 'panel-message-link';
        link.textContent = item.label + ' · ' + item.count;
        form.append(kind, token, link); list.appendChild(form);
      });
      Object.entries(paths).forEach(([kind, path]) => {
        document.querySelectorAll('a[href="' + path + '"]').forEach((link) => {
          let badge = link.querySelector('[data-panel-count]');
          if (!badge) { badge = document.createElement('span'); badge.dataset.panelCount = kind; badge.className = 'panel-count'; link.appendChild(badge); }
          const count = Number(data.counters[kind] || 0); badge.textContent = String(count); badge.classList.toggle('hidden', !count);
        });
      });
    } catch (_) { /* A transient failure does not disrupt the current page. */ }
    finally { loading = false; }
  }
  refresh();
  setInterval(refresh, 30000);
  document.addEventListener('visibilitychange', refresh);
});
