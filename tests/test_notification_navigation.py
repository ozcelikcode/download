"""Exercise notification DOM updates without a network or browser account."""

import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest


def test_asset_version_changes_without_process_restart(monkeypatch):
    from app import templating

    version = 100
    monkeypatch.setattr(templating, "Path", lambda name: SimpleNamespace(
        stat=lambda: SimpleNamespace(st_mtime_ns=version), glob=lambda pattern: [],
    ))
    assert templating.templates.env.globals["css_asset_v"]() == 100
    version = 101
    assert templating.templates.env.globals["css_asset_v"]() == 101


def test_parent_badges_are_scoped_compact_and_reset():
    node = os.environ.get("BACKUP_TEST_NODE") or shutil.which("node")
    if not node:
        pytest.skip("Node.js is optional for notification DOM regression checks")
    script = r"""
const fs = require('fs');
const assert = require('node:assert/strict');
class Element {
  constructor() { this.children = []; this.dataset = {}; this.textContent = ''; this.attributes = {}; this.classes = new Set(); this.classList = { add: c => this.classes.add(c), toggle: (c, on) => { if (on) this.classes.add(c); else this.classes.delete(c); }, contains: c => this.classes.has(c) }; }
  append(...elements) { this.children.push(...elements); }
  appendChild(element) { this.append(element); }
  insertBefore(element, before) { this.children.splice(this.children.indexOf(before), 0, element); }
  replaceChildren() { this.children = []; }
  querySelector(selector) { return this.children.find(c => selector === '[data-panel-total]' ? 'panelTotal' in c.dataset : 'panelCount' in c.dataset); }
  get lastElementChild() { return this.children.at(-1); }
  addEventListener() {}
  setAttribute(k, v) { this.attributes[k] = v; }
  getAttribute(k) { return this.attributes[k]; }
}
const root = new Element(); root.dataset.update = 'Updated'; root.dataset.empty = 'Empty';
const elements = { 'panel-messages': root, 'panel-messages-menu': new Element(), 'panel-messages-toggle': new Element(), 'panel-message-list': new Element(), 'panel-unread': new Element() };
const registration = new Element(); registration.attributes.href = '/panel/registrations';
const contact = new Element(); contact.attributes.href = '/panel/contact';
const unrelated = new Element(); unrelated.attributes.href = '/panel/review';
const summary = new Element(); summary.children = [new Element(), new Element()]; summary.parentElement = { querySelectorAll: () => [registration, registration, contact] };
const content = new Element(); content.children = [new Element()]; content.parentElement = { querySelectorAll: () => [unrelated] };
let empty = false;
global.document = {
  hidden: false, getElementById: id => elements[id], createElement: () => new Element(),
  addEventListener: (event, fn) => { if (event === 'DOMContentLoaded') fn(); },
  querySelector: () => ({ content: 'test-token' }),
  querySelectorAll: selector => selector === 'summary[data-panel-group]' ? [summary, content] : selector.includes('registrations') ? [registration] : selector.includes('contact') ? [contact] : [],
};
global.window = {};
global.fetch = async () => ({ ok: true, json: async () => empty ? { items: [], counters: {}, unread: 0 } : { items: [{ kind: 'registrations', label: '<unsafe label>', count: 2, unread: 2, latest: '2026-10-06' }], counters: { registrations: 2, contact: 1, review: 9 }, unread: 2 } });
let refresh; global.setInterval = fn => { refresh = fn; };
eval(fs.readFileSync('app/static/js/panel-notifications.js', 'utf8'));
setImmediate(async () => {
  assert.equal(summary.querySelector('[data-panel-total]').textContent, '3');
  assert.equal(content.querySelector('[data-panel-total]').textContent, '9');
  const action = elements['panel-message-list'].children[0].children[2];
  assert.equal(action.children[0].textContent, '<unsafe label>');
  assert.equal(action.children[1].textContent, '2');
  empty = true; await refresh();
  assert(summary.querySelector('[data-panel-total]').classList.contains('hidden'));
  assert(registration.querySelector('[data-panel-count]').classList.contains('hidden'));
});
"""
    result = subprocess.run([node], input=script, text=True, capture_output=True,
                            cwd=Path(__file__).resolve().parents[1], timeout=10)
    assert result.returncode == 0, result.stderr
