// Exercise the shipped browser code with Web Crypto, without sending recovery secrets.
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto, createHash} = require('node:crypto');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {value: '', files: [], dataset: {}, classList: {add() {}, remove() {}},
    addEventListener(name, callback) { this[name] = callback; }, querySelector() { return element('button'); }});
  return elements.get(id);
}
element('backup-app').dataset = {limit: '1073741824', queued: 'false'};
element('backup-messages').textContent = JSON.stringify({invalid: 'invalid', working: 'working', secure: 'secure', large: 'large', failed: 'failed'});
const document = {getElementById(id) {
  if (input.mode === 'generate' && id === 'backup-import-form') return null;
  if (input.mode === 'import' && id === 'backup-generate') return null;
  return element(id);
}, createElement() { return {click() {}}; }};
let generated, uploaded;
const context = {document, window: {isSecureContext: true, crypto: webcrypto, location: {assign() {}}}, crypto: webcrypto,
  TextEncoder, TextDecoder, Uint8Array, DataView, Blob, atob, btoa,
  URL: {createObjectURL(blob) { generated = blob; return 'blob:test'; }, revokeObjectURL() {}},
  setTimeout() {}, setInterval() {}, clearInterval() {},
  FormData: class {constructor() { this.data = new Map([['current_password', 'admin-only'], ['csrf_token', 'test-csrf']]); } set(key, value) { this.data.set(key, value); }},
  async fetch(url, options) { uploaded = options.body.data; return {ok: true, json: async () => ({redirect_url: '/admin/backups?stage=test'})}; }};
vm.runInNewContext(fs.readFileSync('app/static/js/backups.js', 'utf8'), context);
(async () => {
  if (input.mode === 'generate') {
    element('recovery-password').value = input.password;
    element('recovery-repeat').value = input.password;
    await element('backup-generate').click();
    if (!generated) throw new Error(element('backup-notice').textContent);
    process.stdout.write(JSON.stringify({recovery: JSON.parse(await generated.text()), publicKey: element('backup-public-key').value}));
  } else {
    element('backup-input').files = [new Blob([Buffer.from(input.backup, 'base64')])];
    element('recovery-input').files = [new Blob([JSON.stringify(input.recovery)])];
    element('import-recovery-password').value = input.password;
    element('backup-import-form').action = '/admin/backups/import';
    await element('backup-import-form').submit({preventDefault() {}});
    if (!uploaded) throw new Error(element('backup-notice').textContent);
    const bytes = Buffer.from(await uploaded.get('file').arrayBuffer());
    process.stdout.write(JSON.stringify({digest: createHash('sha256').update(bytes).digest('hex'), fields: [...uploaded.keys()]}));
  }
})().catch(error => { process.stderr.write(error.message); process.exitCode = 1; });
