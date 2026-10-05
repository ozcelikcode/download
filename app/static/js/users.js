/* Accessible account controls without nested accordion menus. */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-user-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const panel = document.getElementById(button.getAttribute('aria-controls'));
      if (!panel) return;
      const opening = panel.classList.contains('hidden');
      document.querySelectorAll('[data-user-toggle]').forEach((other) => {
        const target = document.getElementById(other.getAttribute('aria-controls'));
        if (target) target.classList.add('hidden');
        other.setAttribute('aria-expanded', 'false');
      });
      panel.classList.toggle('hidden', !opening);
      button.setAttribute('aria-expanded', String(opening));
    });
  });
});
