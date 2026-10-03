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
