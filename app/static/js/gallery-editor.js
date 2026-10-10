/* Ordered, bounded drop uploads; existing assets retain their saved order. */
import {initialGallerySlots, nextGallerySlots, sortGalleryFiles} from './gallery-policy.mjs';
import {uploadGalleryFile} from './gallery-upload.mjs';

const root = document.getElementById('gallery-editor');
if (root) {
  const input = document.getElementById('gallery-images-input');
  const files = document.getElementById('gallery-files');
  const previews = document.getElementById('gallery-previews');
  const dropzone = document.getElementById('gallery-dropzone');
  const more = document.getElementById('gallery-more');
  const status = document.getElementById('gallery-status');
  const progress = document.getElementById('gallery-progress');
  const form = root.closest('form');
  const limit = Number(root.dataset.limit);
  const paths = JSON.parse(input.value || '[]');
  let visible = initialGallerySlots(limit, paths.length);
  let busy = false;
  let dragDepth = 0;

  function icon(name) {
    const element = document.createElement('i');
    element.dataset.lucide = name; element.setAttribute('aria-hidden', 'true');
    return element;
  }
  function changed() {
    input.value = JSON.stringify(paths);
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
  function render() {
    input.value = JSON.stringify(paths); previews.replaceChildren();
    visible = Math.max(visible, paths.length);
    for (let index = 0; index < visible; index += 1) {
      const card = document.createElement('div'); card.className = 'gallery-slot';
      const number = document.createElement('span');
      number.className = 'gallery-slot-number'; number.textContent = `${index + 1}`;
      if (paths[index]) {
        const image = document.createElement('img');
        image.src = paths[index]; image.alt = `${root.dataset.image} ${index + 1}`; image.loading = 'lazy';
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'gallery-slot-remove'; remove.disabled = busy;
        remove.setAttribute('aria-label', `${root.dataset.remove} ${index + 1}`);
        remove.title = root.dataset.remove; remove.append(icon('x'));
        remove.addEventListener('click', () => {
          if (busy) return;
          paths.splice(index, 1); changed(); render();
        });
        card.append(image, remove);
      } else {
        const add = document.createElement('button');
        add.type = 'button'; add.className = 'gallery-slot-add'; add.disabled = busy || paths.length >= limit;
        add.setAttribute('aria-label', `${root.dataset.add} ${index + 1}`);
        const label = document.createElement('span'); label.textContent = root.dataset.add;
        add.append(icon('image-plus'), label); add.addEventListener('click', () => files.click());
        card.append(add);
      }
      card.append(number); previews.append(card);
    }
    more.hidden = visible >= limit; more.disabled = busy;
    if (window.lucide) window.lucide.createIcons();
  }
  async function upload(incoming) {
    if (busy) return;
    const selected = sortGalleryFiles(incoming);
    if (!selected.length) return;
    if (paths.length + selected.length > limit) { status.textContent = root.dataset.limitMessage; return; }
    if (selected.some(file => !/\.(png|jpe?g|webp|gif)$/i.test(file.name))) { status.textContent = root.dataset.error; return; }
    busy = true; files.disabled = true; root.setAttribute('aria-busy', 'true'); render();
    const buttons = [...form.querySelectorAll('button[type="submit"], #application-publish-button, #application-preview-button')];
    const prior = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    const totalBytes = selected.reduce((sum, file) => sum + Math.max(1, file.size), 0);
    let completedBytes = 0;
    if (progress) { progress.hidden = false; progress.value = 0; progress.setAttribute('aria-label', root.dataset.uploading); }
    try {
      for (const [index, file] of selected.entries()) {
        status.textContent = `${root.dataset.uploading} ${index + 1} / ${selected.length}`;
        const csrf = document.querySelector('meta[name="csrf-token"]').content;
        const data = await uploadGalleryFile(file, csrf, fraction => {
          const percent = Math.min(99, Math.round(100 * (completedBytes + Math.max(1, file.size) * fraction) / totalBytes));
          if (progress) progress.value = percent;
          status.textContent = `${fraction === 1 ? root.dataset.processing : root.dataset.uploading} ${index + 1} / ${selected.length} · ${percent}%`;
        });
        if (!/^\/static\/uploads\/gallery\/[a-f0-9]{32}\.webp$/.test(data.path)) throw new Error('Invalid image path');
        if (!paths.includes(data.path)) paths.push(data.path);
        completedBytes += Math.max(1, file.size);
        changed(); render();
      }
      if (progress) { progress.value = 100; progress.setAttribute('aria-label', root.dataset.complete); }
      status.textContent = `${root.dataset.complete} · 100%`;
    } catch (_error) { status.textContent = root.dataset.error; }
    finally {
      busy = false; files.disabled = false; root.removeAttribute('aria-busy');
      buttons.forEach((button, index) => { button.disabled = prior[index]; }); render();
    }
  }
  files.addEventListener('change', () => { const selected = [...files.files]; files.value = ''; upload(selected); });
  more.addEventListener('click', () => {
    visible = nextGallerySlots(limit, visible, paths.length); render();
    previews.querySelector('.gallery-slot:last-child button')?.focus();
  });
  form.addEventListener('submit', event => { if (busy) { event.preventDefault(); event.stopImmediatePropagation(); } }, true);
  function draggingFiles(event) { return [...(event.dataTransfer?.types || [])].includes('Files'); }
  dropzone.addEventListener('dragenter', event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); dragDepth += 1;
    if (!busy) dropzone.classList.add('is-dragging');
  });
  dropzone.addEventListener('dragover', event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); event.dataTransfer.dropEffect = busy ? 'none' : 'copy';
  });
  dropzone.addEventListener('dragleave', () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) dropzone.classList.remove('is-dragging');
  });
  dropzone.addEventListener('drop', event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); dragDepth = 0; dropzone.classList.remove('is-dragging'); upload(event.dataTransfer.files);
  });
  render();
}
