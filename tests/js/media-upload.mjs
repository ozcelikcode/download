import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const template = fs.readFileSync(new URL('../../app/templates/admin/media.html', import.meta.url), 'utf8');
const start = template.indexOf('    function uploadOne(');
const end = template.indexOf('\n    async function uploadQueue', start);
assert.ok(start > 0 && end > start);
let xhr;
let progress;
class FakeXHR {
  constructor() { xhr = this; this.upload = {}; this.status = 200; this.responseText = '{"path":"/fixture.png"}'; }
  open(method, url) { this.method = method; this.url = url; }
  setRequestHeader(name, value) { this.header = [name, value]; }
  send(body) { this.body = body; }
}
const context = {
  XMLHttpRequest: FakeXHR,
  FormData: class { append() {} },
  document: {querySelector: () => ({content: 'test-token'})},
  window: {mediaMessages: {imageCompressing: 'Processing', actionFailed: 'Rejected', networkUploadFailed: 'Network failed'}},
  uploadLabel: {},
  showUploadProgress: () => { progress = 0; },
  setUploadProgress: value => { progress = value; },
};
vm.createContext(context);
vm.runInContext(template.slice(start, end), context);
let upload = context.uploadOne('/panel/upload/icon-image', {}, 'Uploading');
assert.equal(xhr.timeout, 120000);
assert.deepEqual(xhr.header, ['X-CSRF-Token', 'test-token']);
xhr.upload.onprogress({lengthComputable: true, loaded: 100, total: 100});
assert.equal(progress, 95);
assert.equal(context.uploadLabel.textContent, 'Processing');
xhr.onload();
assert.equal((await upload).path, '/fixture.png');
assert.equal(progress, 100);
for (const event of ['onerror', 'onabort', 'ontimeout']) {
  upload = context.uploadOne('/panel/media/upload-file', {}, 'Uploading');
  xhr[event]();
  await assert.rejects(upload, /Network failed/);
  assert.notEqual(progress, 100);
}
for (const status of [403, 413, 500]) {
  upload = context.uploadOne('/panel/media/upload-file', {}, 'Uploading');
  xhr.status = status;
  xhr.onload();
  await assert.rejects(upload, /Rejected/);
  assert.notEqual(progress, 100);
}
upload = context.uploadOne('/panel/media/upload-file', {}, 'Uploading');
xhr.responseText = 'invalid JSON';
xhr.onload();
await assert.rejects(upload);
assert.notEqual(progress, 100);
console.log('Media upload completion, bounded timeout and failures passed');
