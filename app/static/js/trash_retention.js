/* The server enforces expiry; this display never deletes anything. */
(function () {
  const timers = document.querySelectorAll('[data-trash-expires]');
  function update() {
    timers.forEach(timer => {
      const remaining = Date.parse(timer.dataset.trashExpires) - Date.now();
      const days = Math.max(0, Math.ceil(remaining / 86400000));
      timer.textContent = days ? timer.dataset.template.replace('{days}', String(days)) : timer.dataset.due;
    });
  }
  update();
  if (timers.length) setInterval(update, 60000);
})();
