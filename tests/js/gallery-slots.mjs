import assert from 'node:assert/strict';
import {initialGallerySlots, nextGallerySlots, sortGalleryFiles} from '../../app/static/js/gallery-policy.mjs';

for (const [limit, count] of [[3, 3], [5, 5], [10, 10], [15, 10], [20, 10], [25, 10]]) {
  assert.equal(initialGallerySlots(limit, 0), count);
}
assert.equal(initialGallerySlots(3, 5), 5); // Existing images survive a lowered policy.
assert.equal(nextGallerySlots(25, 10, 0), 11);
assert.equal(nextGallerySlots(25, 25, 25), 25);
assert.deepEqual(sortGalleryFiles([{name:'media-10.png'}, {name:'media-2.png'}, {name:'media-1.png'}]).map(file => file.name), ['media-1.png', 'media-2.png', 'media-10.png']);

// A minimal DOM double tests behavior without controlling a real browser.
class Element {
  constructor() { this.children = []; this.events = {}; this.disabled = false; this.value = ''; this.dataset = {}; this.classes = new Set(); this.classList = {add:name => this.classes.add(name), remove:name => this.classes.delete(name)}; }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  setAttribute(name, value) { this[name] = value; }
  removeAttribute(name) { delete this[name]; }
  addEventListener(name, callback) { this.events[name] = callback; }
  dispatchEvent() {}
  querySelectorAll() { return []; }
  querySelector() { return null; }
  closest() { return form; }
}
const form = new Element();
const ids = Object.fromEntries(['gallery-editor', 'gallery-images-input', 'gallery-files', 'gallery-previews', 'gallery-dropzone', 'gallery-more', 'gallery-status'].map(id => [id, new Element()]));
const root = ids['gallery-editor'];
root.dataset = {limit:'25', add:'Add photo', image:'Gallery', remove:'Remove', error:'Failed', limitMessage:'Too many', uploading:'Uploading'};
ids['gallery-images-input'].value = '[]';
globalThis.document = {getElementById:id => ids[id], createElement:() => new Element(), querySelector:() => ({content:'csrf'})};
globalThis.window = {};
const uploaded = [];
let rejectAt = -1;
globalThis.fetch = async (_url, options) => {
  uploaded.push(options.body.get('file').name);
  const okay = uploaded.length !== rejectAt;
  return {ok:okay, headers:{get:() => 'application/json'}, json:async () => ({path:`/static/uploads/gallery/${uploaded.length.toString(16).padStart(32,'0')}.webp`})};
};
await import('../../app/static/js/gallery-editor.js');
assert.equal(ids['gallery-previews'].children.length, 10);
ids['gallery-more'].events.click();
assert.equal(ids['gallery-previews'].children.length, 11);
const drop = ids['gallery-dropzone'];
function event(files=[]) { return {preventDefault(){}, dataTransfer:{types:['Files'], files}}; }
drop.events.dragenter(event()); assert.ok(drop.classes.has('is-dragging'));
drop.events.dragleave(); assert.ok(!drop.classes.has('is-dragging'));
const files = ['media-10.png', 'media-2.png', 'media-1.png'].map(name => new File(['test'], name, {type:'image/png'}));
drop.events.drop(event(files));
assert.equal(root['aria-busy'], 'true');
let blocked = false;
form.events.submit({preventDefault(){blocked=true;}, stopImmediatePropagation(){}}); assert.ok(blocked);
await new Promise(resolve => setImmediate(resolve));
assert.deepEqual(uploaded, ['media-1.png', 'media-2.png', 'media-10.png']);
assert.equal(JSON.parse(ids['gallery-images-input'].value).length, 3);
assert.equal(root['aria-busy'], undefined);
drop.events.drop(event(Array(23).fill(files[0])));
assert.equal(ids['gallery-status'].textContent, 'Too many'); assert.equal(uploaded.length, 3);
rejectAt = 5;
drop.events.drop(event(files));
await new Promise(resolve => setImmediate(resolve));
assert.equal(JSON.parse(ids['gallery-images-input'].value).length, 4); // Keep successful uploads on later failure.
assert.equal(ids['gallery-status'].textContent, 'Failed'); assert.equal(root['aria-busy'], undefined);
