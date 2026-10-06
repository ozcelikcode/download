/* Progressive disclosure: descriptions stay fully readable without JavaScript. */
document.addEventListener('DOMContentLoaded', () => {
  const tabs = [...document.querySelectorAll('[data-detail-tab]')];
  function activate(tab) {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.dataset.detailTab).hidden = !selected;
    });
    window.dispatchEvent(new Event('resize'));
  }
  if (tabs.length) {
    tabs[0].parentElement.setAttribute('role', 'tablist');
    tabs.forEach((tab, index) => {
      tab.setAttribute('role', 'tab');
      const panel = document.getElementById(tab.dataset.detailTab);
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', tab.id);
      tab.addEventListener('click', () => activate(tab));
      tab.addEventListener('keydown', event => {
        let next = index;
        if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
        else if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
        else if (event.key === 'Home') next = 0;
        else if (event.key === 'End') next = tabs.length - 1;
        else return;
        event.preventDefault(); activate(tabs[next]); tabs[next].focus();
      });
    });
    activate(tabs[0]);
  }
  function disclosure(contentId, buttonId) {
  const content = document.getElementById(contentId);
  const button = document.getElementById(buttonId);
  if (!content || !button) return;
  let expanded = false;
  function refresh() {
    if (content.closest('[hidden]')) return;
    if (expanded) return;
    content.classList.add('is-collapsed');
    const overflows = content.scrollHeight > content.clientHeight + 1;
    content.classList.toggle('is-collapsed', overflows);
    button.classList.toggle('hidden', !overflows);
  }
  function open() {
    expanded = true;
    content.classList.remove('is-collapsed');
    button.setAttribute('aria-expanded', 'true');
    button.textContent = button.dataset.less;
  }
  button.addEventListener('click', () => {
    if (!expanded) { open(); return; }
    expanded = false;
    button.setAttribute('aria-expanded', 'false');
    button.textContent = button.dataset.more;
    refresh();
    if (content.getBoundingClientRect().top < 0) content.scrollIntoView({ block: 'start' });
  });
  content.addEventListener('focusin', () => { if (content.classList.contains('is-collapsed')) open(); });
  content.addEventListener('load', refresh, true);
  window.addEventListener('resize', refresh);
  if (window.ResizeObserver) new ResizeObserver(refresh).observe(content);
  if (document.fonts) document.fonts.ready.then(refresh);
  refresh();
  }
  disclosure('application-description', 'description-toggle');
  disclosure('version-history-content', 'history-toggle');
});
