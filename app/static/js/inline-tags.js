/* Owned tag creation and reversible application associations. */
(function () {
  'use strict';
  const toggle = document.getElementById('tag-add-toggle');
  if (!toggle) return;
  const controls = document.getElementById('tag-add-controls');
  const input = document.getElementById('inline-tag-name');
  const save = document.getElementById('tag-add-save');
  const status = document.getElementById('tag-add-status');
  const tags = document.getElementById('application-tags');
  toggle.addEventListener('click', function () {
    const open = controls.classList.toggle('hidden') === false;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) input.focus();
  });
  tags.addEventListener('click', function (event) {
    const remove = event.target.closest('.tag-remove');
    if (!remove) return;
    event.preventDefault();
    const checkbox = remove.closest('.choice-card').querySelector('input');
    checkbox.checked = false;
    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    checkbox.focus();
  });
  async function add() {
    const name = input.value.trim();
    if (!name || save.disabled) return;
    save.disabled = true;
    status.textContent = '';
    try {
      const body = new FormData(); body.append('name', name);
      const response = await fetch('/panel/tags/inline', { method: 'POST', body,
        headers: { 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content, Accept: 'application/json' } });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : controls.dataset.error);
      let checkbox = [...tags.querySelectorAll('input[name="tag_ids"]')].find(item => item.value === String(data.id));
      if (!checkbox) {
        const label = document.createElement('label'); label.className = 'choice-card inline-flex items-center px-2.5 py-1.5 select-none';
        checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.name = 'tag_ids'; checkbox.value = String(data.id); checkbox.className = 'choice-input';
        const text = document.createElement('span'); text.className = 'text-sm'; text.textContent = '#' + data.name;
        const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'tag-remove ml-2'; remove.setAttribute('aria-label', controls.dataset.remove); remove.textContent = '×';
        label.append(checkbox, text, remove); tags.append(label);
      }
      checkbox.checked = true; checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      input.value = ''; input.focus();
    } catch (error) { status.textContent = error.message || controls.dataset.error; }
    finally { save.disabled = false; }
  }
  save.addEventListener('click', add);
  input.addEventListener('keydown', function (event) { if (event.key === 'Enter') { event.preventDefault(); add(); } });
})();
