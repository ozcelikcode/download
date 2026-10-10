/* XHR exposes actual upload progress; fetch does not provide upload progress. */
export function uploadGalleryFile(file, csrf, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/panel/upload/gallery-image');
    xhr.setRequestHeader('X-CSRF-Token', csrf);
    xhr.timeout = 120000;
    xhr.upload.addEventListener('progress', event => {
      if (event.lengthComputable && event.total > 0) onProgress(Math.min(1, event.loaded / event.total));
    });
    xhr.addEventListener('load', () => {
      try {
        if (xhr.status < 200 || xhr.status >= 300 || !xhr.getResponseHeader('content-type')?.includes('application/json')) throw new Error('Upload rejected');
        resolve(JSON.parse(xhr.responseText));
      } catch (error) { reject(error); }
    });
    for (const event of ['error', 'abort', 'timeout']) xhr.addEventListener(event, () => reject(new Error('Upload interrupted')));
    const body = new FormData(); body.append('file', file); xhr.send(body);
  });
}
