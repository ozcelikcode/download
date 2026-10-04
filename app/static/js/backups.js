/* Client-held recovery keys: no private key or recovery password leaves this browser. */
(function () {
  'use strict';
  const root = document.getElementById('backup-app');
  if (!root) return;
  const messages = JSON.parse(document.getElementById('backup-messages').textContent);
  const notice = document.getElementById('backup-notice');
  const show = message => { notice.textContent = message; notice.classList.remove('hidden'); };
  const secure = window.isSecureContext && window.crypto && window.crypto.subtle;
  const encoder = new TextEncoder();
  const encode = bytes => { let value = ''; for (const byte of new Uint8Array(bytes)) value += String.fromCharCode(byte); return btoa(value); };
  const decode = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
  async function passwordKey(password, salt) {
    const material = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name: 'PBKDF2', salt, iterations: 600000, hash: 'SHA-256'}, material, {name: 'AES-GCM', length: 256}, false, ['encrypt', 'decrypt']);
  }
  async function fingerprint(publicKey) {
    return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', publicKey)), b => b.toString(16).padStart(2, '0')).join('');
  }
  const generate = document.getElementById('backup-generate');
  if (generate) generate.addEventListener('click', async () => {
    if (!secure) { show(messages.secure); return; }
    const password = document.getElementById('recovery-password');
    const repeat = document.getElementById('recovery-repeat');
    if (password.value.length < 12 || password.value !== repeat.value) { show(messages.invalid); return; }
    generate.disabled = true; show(messages.working);
    try {
      const pair = await crypto.subtle.generateKey({name: 'RSA-OAEP', modulusLength: 4096, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256'}, true, ['encrypt', 'decrypt']);
      const publicBytes = await crypto.subtle.exportKey('spki', pair.publicKey);
      const privateBytes = await crypto.subtle.exportKey('pkcs8', pair.privateKey);
      const salt = crypto.getRandomValues(new Uint8Array(16));
      const iv = crypto.getRandomValues(new Uint8Array(12));
      const key = await passwordKey(password.value, salt);
      const encrypted = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, key, privateBytes);
      const id = await fingerprint(publicBytes);
      const recovery = {format: 1, key_id: id, public_key: encode(publicBytes), salt: encode(salt), iv: encode(iv), iterations: 600000, encrypted_private_key: encode(encrypted)};
      const url = URL.createObjectURL(new Blob([JSON.stringify(recovery)], {type: 'application/json'}));
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'site-recovery-' + id.slice(0, 12) + '.json'; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      new Uint8Array(privateBytes).fill(0); password.value = ''; repeat.value = '';
      document.getElementById('backup-public-key').value = '-----BEGIN PUBLIC KEY-----\n' + encode(publicBytes).match(/.{1,64}/g).join('\n') + '\n-----END PUBLIC KEY-----\n';
      document.getElementById('backup-save-key').disabled = false;
      notice.classList.add('hidden');
    } catch (_) { show(messages.failed); }
    finally { generate.disabled = false; }
  });
  const form = document.getElementById('backup-import-form');
  if (form) form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!secure) { show(messages.secure); return; }
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true; show(messages.working);
    let plain;
    try {
      const file = document.getElementById('backup-input').files[0];
      const recoveryFile = document.getElementById('recovery-input').files[0];
      if (file.size > Number(root.dataset.limit) + 16384) throw new Error(messages.large);
      if (recoveryFile.size > 16384) throw new Error(messages.invalid);
      const bytes = new Uint8Array(await file.arrayBuffer());
      if (bytes.length < 28 || new TextDecoder().decode(bytes.slice(0, 8)) !== 'DLBACK01') throw new Error(messages.invalid);
      const length = new DataView(bytes.buffer).getUint32(8, false);
      if (length > 8192 || 12 + length + 16 >= bytes.length) throw new Error(messages.invalid);
      const header = JSON.parse(new TextDecoder().decode(bytes.slice(12, 12 + length)));
      const recovery = JSON.parse(await recoveryFile.text());
      if (header.format !== 1 || recovery.format !== 1 || recovery.iterations !== 600000 || header.key_id !== recovery.key_id || await fingerprint(decode(recovery.public_key)) !== header.key_id) throw new Error(messages.invalid);
      const salt = decode(recovery.salt), iv = decode(recovery.iv);
      if (salt.length !== 16 || iv.length !== 12 || decode(header.iv).length !== 12) throw new Error(messages.invalid);
      const password = document.getElementById('import-recovery-password');
      const key = await passwordKey(password.value, salt);
      const privateBytes = await crypto.subtle.decrypt({name: 'AES-GCM', iv}, key, decode(recovery.encrypted_private_key));
      const privateKey = await crypto.subtle.importKey('pkcs8', privateBytes, {name: 'RSA-OAEP', hash: 'SHA-256'}, false, ['unwrapKey']);
      new Uint8Array(privateBytes).fill(0); password.value = '';
      const contentKey = await crypto.subtle.unwrapKey('raw', decode(header.wrapped_key), privateKey, 'RSA-OAEP', {name: 'AES-GCM', length: 256}, false, ['decrypt']);
      plain = await crypto.subtle.decrypt({name: 'AES-GCM', iv: decode(header.iv), additionalData: bytes.slice(0, 12 + length)}, contentKey, bytes.slice(12 + length));
      if (plain.byteLength > Number(root.dataset.limit)) throw new Error(messages.large);
      const data = new FormData(form); data.set('file', new Blob([plain], {type: 'application/zip'}), 'incoming.zip');
      const response = await fetch(form.action, {method: 'POST', body: data, credentials: 'same-origin'});
      const result = await response.json();
      if (!response.ok || !result.redirect_url) {
        const error = new Error(messages.failed);
        error.publicMessage = typeof result.error === 'string' ? result.error.slice(0, 512) : messages.failed;
        throw error;
      }
      window.location.assign(result.redirect_url);
    } catch (error) { show(error.publicMessage || (Object.values(messages).includes(error.message) ? error.message : messages.invalid)); }
    finally { if (plain) new Uint8Array(plain).fill(0); button.disabled = false; }
  });
  if (!secure && (generate || form)) show(messages.secure);
  if (root.dataset.queued === 'true') {
    const timer = setInterval(async () => {
      try {
        const response = await fetch('/panel/backups/status', {credentials: 'same-origin'});
        if (!response.ok) { clearInterval(timer); return; }
        const data = await response.json();
        if (data.latest !== (root.dataset.latest || null) || data.error) { clearInterval(timer); window.location.reload(); }
      } catch (_) { clearInterval(timer); }
    }, 10000);
  }
})();
