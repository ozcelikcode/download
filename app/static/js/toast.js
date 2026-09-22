(function () {
  'use strict';

  var ALLOWED_TYPES = ['success', 'warning', 'error', 'info'];
  var ICONS = {
    success: 'circle-check',
    warning: 'triangle-alert',
    error: 'circle-x',
    info: 'info'
  };
  var timers = new Map();
  var sequence = 0;

  function getRegion() {
    var region = document.querySelector('[data-toast-region]');
    if (region) return region;
    region = document.createElement('div');
    region.className = 'app-toast-region';
    region.dataset.toastRegion = '';
    region.setAttribute('aria-live', 'polite');
    region.setAttribute('aria-atomic', 'false');
    document.body.appendChild(region);
    return region;
  }

  function dismiss(target) {
    var toast = typeof target === 'string'
      ? Array.from(getRegion().children).find(function (item) {
        return item.dataset.toastId === target;
      })
      : target;
    if (!toast) return;
    var id = toast.dataset.toastId;
    if (timers.has(id)) {
      window.clearTimeout(timers.get(id));
      timers.delete(id);
    }
    toast.classList.add('is-leaving');
    window.setTimeout(function () { toast.remove(); }, 160);
  }

  function schedule(toast, duration) {
    var id = toast.dataset.toastId;
    if (timers.has(id)) window.clearTimeout(timers.get(id));
    if (duration > 0) {
      timers.set(id, window.setTimeout(function () { dismiss(toast); }, duration));
    }
  }

  function show(message, options) {
    options = options || {};
    var type = ALLOWED_TYPES.includes(options.type) ? options.type : 'info';
    var id = String(options.id || ('toast-' + (++sequence)));
    var duration = Number.isFinite(options.duration) ? Math.max(0, options.duration) : 4000;
    var region = getRegion();
    var toast = Array.from(region.children).find(function (item) {
      return item.dataset.toastId === id;
    });

    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'app-toast';
      toast.dataset.toastId = id;
      toast.innerHTML = '<i class="app-toast-icon" aria-hidden="true"></i>'
        + '<p class="app-toast-message"></p>'
        + '<button type="button" class="app-toast-close"><span aria-hidden="true">×</span></button>';
      toast.querySelector('.app-toast-close').addEventListener('click', function () { dismiss(toast); });
      region.appendChild(toast);
    }

    toast.className = 'app-toast app-toast-' + type;
    toast.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toast.querySelector('.app-toast-message').textContent = String(message || '');
    var previousIcon = toast.querySelector('.app-toast-icon');
    var icon = document.createElement('i');
    icon.className = 'app-toast-icon';
    icon.setAttribute('data-lucide', ICONS[type]);
    icon.setAttribute('aria-hidden', 'true');
    previousIcon.replaceWith(icon);
    toast.querySelector('.app-toast-close').setAttribute(
      'aria-label',
      options.closeLabel || region.dataset.toastCloseLabel || 'Dismiss'
    );
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
    schedule(toast, duration);

    return {
      dismiss: function () { dismiss(toast); },
      update: function (nextMessage, nextOptions) {
        return show(nextMessage, Object.assign({}, options, nextOptions || {}, { id: id }));
      }
    };
  }

  window.AppToast = { show: show, dismiss: dismiss };

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-toast-message]').forEach(function (source) {
      show(source.dataset.toastMessage, {
        id: source.dataset.toastId || undefined,
        type: source.dataset.toastType || 'info',
        duration: Number(source.dataset.toastDuration || 4000)
      });
      source.remove();
    });
  });
})();
