export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api/${path}`, {
      credentials: 'include', ...options,
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'grading-web', ...options.headers },
    });
  } catch { throw new Error('Unable to connect. Please try again.'); }
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Invalid input. Please check your details and try again.');
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

export function post(path, data) {
  return api(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) });
}

export function uploadFiles(path, data, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('POST', `/api/${path}`);
    request.withCredentials = true;
    request.setRequestHeader('X-Requested-With', 'grading-web');
    request.upload.onprogress = event => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
    request.onerror = () => reject(new Error('Upload interrupted. Please try again.'));
    request.onload = () => {
      let body;
      try { body = JSON.parse(request.responseText); } catch { reject(new Error('Upload failed. Please try again.')); return; }
      if (request.status >= 200 && request.status < 300) resolve(body);
      else reject(new Error(typeof body.detail === 'string' ? body.detail : 'Upload failed. Check the file type and size.'));
    };
    request.send(data);
  });
}
