"""Description disclosure preserves accessible content and handles short text."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_description_disclosure_and_keyboard_access():
    node = os.environ.get("BACKUP_TEST_NODE") or shutil.which("node")
    if not node:
        pytest.skip("Node.js is optional for description DOM regression checks")
    script = r"""
const fs = require('fs');
const assert = require('node:assert/strict');
class Element {
  constructor() {
    this.classes = new Set(); this.events = {}; this.attributes = {};
    this.dataset = { more: 'Read more', less: 'Show less' };
    this.classList = {
      add: c => this.classes.add(c), remove: c => this.classes.delete(c),
      contains: c => this.classes.has(c),
      toggle: (c, on) => on ? this.classes.add(c) : this.classes.delete(c),
    };
  }
  addEventListener(k, fn) { this.events[k] = fn; }
  setAttribute(k, v) { this.attributes[k] = v; }
  getBoundingClientRect() { return { top: -10 }; }
  closest() { return null; }
  scrollIntoView() { this.scrolled = true; }
}
const content = new Element(), button = new Element();
content.style = {setProperty: (key, value) => { content.attributes[key] = value; }};
const facts = new Element(), tabBar = new Element();
facts.getBoundingClientRect = () => ({height: 360});
tabBar.getBoundingClientRect = () => ({height: 56});
content.scrollHeight = 1000; content.clientHeight = 512;
let resized;
global.document = {
  addEventListener: (k, fn) => fn(),
  getElementById: id => id === 'application-description' ? content : id === 'description-toggle' ? button : id === 'detail-facts-content' ? facts : null,
  querySelectorAll: selector => selector === '.detail-tabs' ? [tabBar] : [],
};
global.window = { innerWidth: 1200, addEventListener: (k, fn) => { resized = fn; } };
eval(fs.readFileSync('app/static/js/download-detail.js', 'utf8'));
assert(content.classes.has('is-collapsed'));
assert(!button.classes.has('hidden'));
assert.equal(content.attributes['--detail-collapse-height'], '248px');
content.scrollHeight = 350; content.clientHeight = 248; resized();
assert(content.classes.has('is-collapsed')); // Below the old 512px threshold.
button.events.click();
assert(!content.classes.has('is-collapsed'));
assert.equal(button.attributes['aria-expanded'], 'true');
assert.equal(button.textContent, 'Show less');
resized(); assert(!content.classes.has('is-collapsed'));
button.events.click();
assert(content.classes.has('is-collapsed'));
assert.equal(button.attributes['aria-expanded'], 'false');
assert(content.scrolled);
content.events.focusin(); assert(!content.classes.has('is-collapsed'));
button.events.click();
content.scrollHeight = 100; content.clientHeight = 100; resized();
assert(!content.classes.has('is-collapsed'));
assert(button.classes.has('hidden'));
content.scrollHeight = 1000; resized();
assert(content.classes.has('is-collapsed'));
assert(!button.classes.has('hidden'));
"""
    result = subprocess.run(
        [node], input=script, text=True, capture_output=True,
        cwd=Path(__file__).resolve().parents[1], timeout=10,
    )
    assert result.returncode == 0, result.stderr
