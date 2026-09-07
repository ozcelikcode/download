(function () {
  const storageKey = 'theme';
  const media = window.matchMedia('(prefers-color-scheme: dark)');

  function currentMode() {
    const value = localStorage.getItem(storageKey);
    return value === 'light' || value === 'dark' ? value : 'system';
  }

  function applyTheme(mode, persist) {
    document.documentElement.classList.toggle(
      'dark',
      mode === 'dark' || (mode === 'system' && media.matches),
    );
    if (persist) localStorage.setItem(storageKey, mode);

    document.querySelectorAll('[data-theme-icon]').forEach((icon) => {
      icon.classList.toggle('hidden', icon.dataset.themeIcon !== mode);
    });
    document.querySelectorAll('.theme-option-btn').forEach((option) => {
      const active = option.dataset.themeOption === mode;
      option.classList.toggle('text-blue-600', active);
      option.classList.toggle('dark:text-blue-400', active);
      option.classList.toggle('bg-blue-50', active);
      option.classList.toggle('dark:bg-blue-500/10', active);
    });
  }

  function init() {
    const wrap = document.getElementById('theme-menu-wrap');
    const button = document.getElementById('theme-toggle-btn');
    const menu = document.getElementById('theme-menu');
    applyTheme(currentMode(), false);
    if (!wrap || !button || !menu) return;

    button.addEventListener('click', (event) => {
      event.stopPropagation();
      menu.classList.toggle('hidden');
    });
    document.addEventListener('click', (event) => {
      if (!wrap.contains(event.target)) menu.classList.add('hidden');
    });
    document.querySelectorAll('.theme-option-btn').forEach((option) => {
      option.addEventListener('click', () => {
        applyTheme(option.dataset.themeOption, true);
        menu.classList.add('hidden');
      });
    });
  }

  media.addEventListener('change', () => {
    if (currentMode() === 'system') applyTheme('system', false);
  });
  window.addEventListener('storage', (event) => {
    if (event.key === storageKey) applyTheme(currentMode(), false);
  });
  document.addEventListener('DOMContentLoaded', init);
})();
