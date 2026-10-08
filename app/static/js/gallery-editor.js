/* Upload compressed gallery assets; their ordered paths follow normal draft saving. */
document.addEventListener('DOMContentLoaded', () => {
  const root = document.getElementById('gallery-editor');
  if (!root) return;
  const input = document.getElementById('gallery-images-input');
  const files = document.getElementById('gallery-files');
  const previews = document.getElementById('gallery-previews');
  const status = document.getElementById('gallery-status');
  let paths = JSON.parse(input.value || '[]');
  function render() {
    input.value = JSON.stringify(paths);
    previews.replaceChildren();
    paths.forEach((path, index) => {
      const card = document.createElement('div');
      const image = document.createElement('img');
      const remove = document.createElement('button');
      card.className = 'gallery-editor-card';
      image.src = path; image.alt = `${index + 1}`; image.loading = 'lazy';
      remove.type = 'button'; remove.className = 'btn-secondary';
      remove.textContent = root.dataset.remove;
      remove.addEventListener('click', () => {
        paths.splice(index, 1); render(); input.dispatchEvent(new Event('change', {bubbles:true}));
      });
      card.append(image, remove); previews.append(card);
    });
  }
  files.addEventListener('change', async () => {
    const selected = [...files.files];
    if (paths.length + selected.length > Number(root.dataset.limit)) {
      status.textContent = root.dataset.limitMessage; files.value = ''; return;
    }
    files.disabled = true;
    // Prevent form submission while assets are still being prepared.
    const buttons = [...root.closest('form').querySelectorAll('button[type="submit"], #application-publish-button, #application-preview-button')];
    const prior = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    try {
      for (const [index, file] of selected.entries()) {
        status.textContent = `${index + 1} / ${selected.length}`;
        const body = new FormData(); body.append('file', file);
        const csrf = document.querySelector('meta[name="csrf-token"]').content;
        const response = await fetch('/panel/upload/gallery-image', {method:'POST', body, headers:{'X-CSRF-Token':csrf}, credentials:'same-origin'});
        if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Upload rejected');
        const data = await response.json();
        if (!/^\/static\/uploads\/gallery\/[a-f0-9]{32}\.webp$/.test(data.path)) throw new Error('Invalid image path');
        paths.push(data.path); render(); input.dispatchEvent(new Event('change', {bubbles:true}));
      }
      status.textContent = '';
    } catch (_error) { status.textContent = root.dataset.error; }
    finally { files.disabled = false; files.value = ''; buttons.forEach((button, index) => { button.disabled = prior[index]; }); }
  });
  render();
});
