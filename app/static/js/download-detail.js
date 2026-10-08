/* Progressive disclosure: descriptions stay fully readable without JavaScript. */
document.addEventListener('DOMContentLoaded', () => {
  const gallery = [...document.querySelectorAll('[data-gallery-item]')];
  const lightbox = document.getElementById('gallery-lightbox');
  if (lightbox && typeof lightbox.showModal === 'function') {
    let selected = 0;
    let previousOverflow = '';
    const image = document.getElementById('gallery-full-image');
    function show(index) {
      selected = (index + gallery.length) % gallery.length;
      image.src = gallery[selected].getAttribute('href');
      image.alt = gallery[selected].querySelector('img').alt;
      document.getElementById('gallery-position').textContent = `${selected + 1} / ${gallery.length}`;
    }
    gallery.forEach((item, index) => item.addEventListener('click', event => {
      event.preventDefault(); show(index); previousOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden'; lightbox.showModal();
    }));
    lightbox.querySelector('[data-gallery-close]').addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('click', event => { if (event.target === lightbox) lightbox.close(); });
    lightbox.addEventListener('close', () => { document.body.style.overflow = previousOverflow; });
    lightbox.querySelector('[data-gallery-previous]').addEventListener('click', () => show(selected - 1));
    lightbox.querySelector('[data-gallery-next]').addEventListener('click', () => show(selected + 1));
    lightbox.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); show(selected + (event.key === 'ArrowLeft' ? -1 : 1)); }
    });
  }
  const moreMenu = document.querySelectorAll('.detail-more')[0];
  if (moreMenu) {
    document.addEventListener('click', event => {
      if (!moreMenu.contains(event.target)) moreMenu.open = false;
    });
    moreMenu.addEventListener('keydown', event => {
      if (event.key === 'Escape') {
        moreMenu.open = false;
        moreMenu.querySelector('summary').focus();
      }
    });
  }
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
    const facts = document.getElementById('detail-facts-content');
    const tabBar = document.querySelectorAll('.detail-tabs')[0];
    if (contentId === 'application-description' && facts && tabBar) {
      // Measure intrinsic facts, not the stretched card, to avoid a size loop.
      const available = facts.getBoundingClientRect().height - tabBar.getBoundingClientRect().height - 56;
      const limit = window.innerWidth >= 768 ? Math.max(160, Math.min(384, available)) : 320;
      content.style.setProperty('--detail-collapse-height', `${limit}px`);
    }
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
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(refresh);
    observer.observe(content);
    const facts = document.getElementById('detail-facts-content');
    if (facts) observer.observe(facts);
  }
  if (document.fonts) document.fonts.ready.then(refresh);
  refresh();
  }
  disclosure('application-description', 'description-toggle');
  disclosure('version-history-content', 'history-toggle');
});
