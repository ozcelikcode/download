/* Yalnızca aynı kaynaktaki durum değiştiren isteklere CSRF jetonu ekler. */
window.csrfFetch = function (input, options) {
  options = options || {};
  const url = new URL(input, window.location.href);
  const method = (options.method || 'GET').toUpperCase();
  if (url.origin === window.location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const headers = new Headers(options.headers || {});
    headers.set('X-CSRF-Token', document.querySelector('meta[name="csrf-token"]').content);
    options = Object.assign({}, options, { headers: headers });
  }
  return fetch(input, options);
};
