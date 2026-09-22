(function () {
  const focusableSelector = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(',');
  const dialogState = new WeakMap();

  function isHidden(element) {
    return element.classList.contains('hidden') || element.getAttribute('aria-hidden') === 'true';
  }

  function focusableElements(container) {
    return Array.from(container.querySelectorAll(focusableSelector)).filter((element) => {
      return !element.hidden
        && element.getAttribute('aria-hidden') !== 'true'
        && element.getClientRects().length > 0;
    });
  }

  function visibleDialogs() {
    return Array.from(document.querySelectorAll('[data-accessible-dialog]')).filter(
      (dialog) => !isHidden(dialog),
    );
  }

  function syncPageLock() {
    document.body.classList.toggle('dialog-open', visibleDialogs().length > 0);
  }

  function syncDialog(dialog) {
    const state = dialogState.get(dialog);
    const open = !dialog.classList.contains('hidden');
    dialog.setAttribute('aria-hidden', open ? 'false' : 'true');

    if (open && !state.open) {
      state.returnFocus = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      window.requestAnimationFrame(() => {
        const initial = dialog.querySelector('[data-dialog-initial-focus]')
          || focusableElements(dialog)[0]
          || dialog;
        initial.focus();
      });
    } else if (!open && state.open && state.returnFocus && state.returnFocus.isConnected) {
      state.returnFocus.focus();
    }
    state.open = open;
    syncPageLock();
  }

  function prepareDialog(dialog, index) {
    dialog.dataset.accessibleDialog = '';
    if (!dialog.hasAttribute('role')) dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('tabindex', '-1');

    const heading = dialog.querySelector('h1, h2, h3');
    if (heading && !dialog.hasAttribute('aria-labelledby')) {
      if (!heading.id) heading.id = `dialog-title-${index + 1}`;
      dialog.setAttribute('aria-labelledby', heading.id);
    }

    dialogState.set(dialog, { open: false, returnFocus: null });
    const observer = new MutationObserver(() => syncDialog(dialog));
    observer.observe(dialog, { attributes: true, attributeFilter: ['class'] });
    syncDialog(dialog);
  }

  function syncDisclosure(button, target) {
    button.setAttribute('aria-expanded', target.classList.contains('hidden') ? 'false' : 'true');
  }

  function prepareDisclosure(button) {
    const target = document.getElementById(button.getAttribute('aria-controls') || '');
    if (!target) return;
    syncDisclosure(button, target);
    const observer = new MutationObserver(() => syncDisclosure(button, target));
    observer.observe(target, { attributes: true, attributeFilter: ['class'] });

    button.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowDown') return;
      event.preventDefault();
      if (target.classList.contains('hidden')) button.click();
      window.requestAnimationFrame(() => {
        const first = focusableElements(target)[0];
        if (first) first.focus();
      });
    });
  }

  function init() {
    document.querySelectorAll('[id$="-modal"], [data-dialog]').forEach(prepareDialog);
    document.querySelectorAll('[data-disclosure-button][aria-controls]').forEach(prepareDisclosure);
  }

  document.addEventListener('keydown', (event) => {
    const dialogs = visibleDialogs();
    const dialog = dialogs[dialogs.length - 1];
    if (dialog) {
      if (event.key === 'Escape') {
        const close = dialog.querySelector('[data-dialog-close]');
        if (close) {
          event.preventDefault();
          close.click();
        }
        return;
      }
      if (event.key === 'Tab') {
        const focusable = focusableElements(dialog);
        if (!focusable.length) {
          event.preventDefault();
          dialog.focus();
          return;
        }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (!dialog.contains(document.activeElement)) {
          event.preventDefault();
          first.focus();
        } else if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
      return;
    }

    if (event.key !== 'Escape') return;
    document.querySelectorAll('[data-disclosure-button][aria-expanded="true"]').forEach((button) => {
      const target = document.getElementById(button.getAttribute('aria-controls') || '');
      if (!target) return;
      target.classList.add('hidden');
      button.setAttribute('aria-expanded', 'false');
      if (target.contains(document.activeElement) || button === document.activeElement) button.focus();
    });
  }, true);

  document.addEventListener('DOMContentLoaded', init);
})();
