/* Progressive disclosure: descriptions stay fully readable without JavaScript. */
document.addEventListener('DOMContentLoaded', () => {
  const content = document.getElementById('application-description');
  const button = document.getElementById('description-toggle');
  if (!content || !button) return;
  let expanded = false;
  function refresh() {
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
});
