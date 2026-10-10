/* Shared editor policy: preserve structure, inherit the site's typography and colors. */
(function () {
  'use strict';

  window.createRichTextEditor = function (element, options, initialHtml) {
    const Delta = Quill.import('delta');
    const editor = new Quill(element, {
      ...options,
      formats: [
        'header', 'size', 'bold', 'italic', 'underline', 'strike', 'script',
        'list', 'indent', 'blockquote', 'code-block', 'code', 'link', 'image', 'align', 'direction',
      ],
    });
    const labels = window.richTextLabels || {};
    const toolbar = editor.getModule('toolbar');
    if (toolbar) {
      function labelButtons() {
        toolbar.container.querySelectorAll('button').forEach(function (button) {
          const format = [...button.classList].find(name => name.startsWith('ql-'));
          const key = format === 'ql-code-block' ? 'code' : format && format.slice(3);
          if (!labels[key]) return;
          button.title = labels[key];
          if (button.getAttribute('aria-label') !== labels[key]) button.setAttribute('aria-label', labels[key]);
        });
      }
      labelButtons();
      // Quill refreshes accessible labels as the selection changes.
      new MutationObserver(labelButtons).observe(toolbar.container, { attributes: true, attributeFilter: ['aria-label'], subtree: true });
      toolbar.container.querySelectorAll('.ql-picker').forEach(function (picker) {
        const heading = picker.classList.contains('ql-header');
        const size = picker.classList.contains('ql-size');
        if (!heading && !size) {
          const format = [...picker.classList].find(name => name !== 'ql-picker' && name.startsWith('ql-'));
          const label = format && labels[format.slice(3)];
          if (label) picker.querySelector('.ql-picker-label')?.setAttribute('aria-label', label);
          return;
        }
        function update() {
          picker.querySelectorAll('.ql-picker-label, .ql-picker-item').forEach(function (item) {
            const value = item.dataset.value;
            const label = heading ? (value ? labels.heading + ' ' + value : labels.normal) : (labels[value] || labels.normal);
            if (label) { item.dataset.label = label; item.setAttribute('aria-label', label); }
          });
        }
        update();
        new MutationObserver(update).observe(picker, { attributes: true, attributeFilter: ['data-value'], subtree: true });
      });
    }
    if (editor.theme.tooltip) {
      const tooltip = editor.theme.tooltip.root;
      ['link', 'save', 'edit', 'remove'].forEach(function (key) {
        if (labels[key]) tooltip.style.setProperty('--rt-' + key, JSON.stringify(labels[key]));
      });
    }
    // Keep sizes deliberately saved through the toolbar, not sizes from the clipboard.
    if (initialHtml && initialHtml.trim()) editor.clipboard.dangerouslyPasteHTML(initialHtml);
    editor.clipboard.addMatcher(Node.ELEMENT_NODE, function (_node, delta) {
      return new Delta(delta.ops.map(function (operation) {
        const attributes = { ...operation.attributes };
        ['color', 'background', 'font', 'size'].forEach(function (name) {
          delete attributes[name];
        });
        return { ...operation, attributes };
      }));
    });
    return editor;
  };
})();
