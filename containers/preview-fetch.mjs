// Reviewed container-only HTTP bridge. No redirects, auth forwarding or proxy.
import http from 'node:http';
import { pathToFileURL } from 'node:url';

export const MAX_BODY = 20 * 1024 * 1024;

export function validateRequest(target, query = '') {
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//') ||
      target.length > 4096 || typeof query !== 'string' || query.length > 4096 ||
      /[\x00-\x20\x7f?#]/.test(target) || /[\x00-\x20\x7f#]/.test(query)) throw new Error('Invalid preview request');
  let decoded = target;
  for (let i = 0; i < 4; i++) {
    if (decoded.includes('\\') || /[\x00-\x1f\x7f]/.test(decoded) || decoded.split('/').includes('..')) {
      throw new Error('Invalid preview request');
    }
    const next = decodeURIComponent(decoded);
    if (next === decoded) return target + (query ? '?' + query : '');
    decoded = next;
  }
  throw new Error('Excessive preview path encoding');
}

export function fetchPreview(target, query = '', { port = 3000, maxBytes = MAX_BODY, timeoutMs = 8000 } = {}) {
  const requestPath = validateRequest(target, query);
  return new Promise((resolve, reject) => {
    let settled = false;
    let deadline;
    const finish = (error, result) => {
      if (settled) return;
      settled = true;
      clearTimeout(deadline);
      if (error) reject(error); else resolve(result);
    };
    const request = http.request({ hostname: '127.0.0.1', port, method: 'GET', path: requestPath,
      headers: { Accept: '*/*', 'User-Agent': 'OLYMPUS-Container-Preview' } }, response => {
      const chunks = [];
      let size = 0;
      response.on('data', chunk => {
        size += chunk.length;
        if (size > maxBytes) {
          finish(new Error('Preview response exceeds limit'));
          response.destroy(); request.destroy(); return;
        }
        chunks.push(chunk);
      });
      response.on('error', error => finish(error));
      response.on('aborted', () => finish(new Error('Preview response aborted')));
      response.on('end', () => finish(null, { status: response.statusCode,
        content_type: response.headers['content-type'] || 'application/octet-stream',
        location: response.headers.location || null, body: Buffer.concat(chunks).toString('base64') }));
    });
    request.on('error', error => finish(error));
    deadline = setTimeout(() => { finish(new Error('Preview request exceeded deadline')); request.destroy(); }, timeoutMs);
    request.end();
  });
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  if (process.argv.length !== 4) { console.error('Invalid preview request arguments'); process.exitCode = 1; }
  else {
    try { process.stdout.write(JSON.stringify(await fetchPreview(process.argv[2], process.argv[3]))); }
    catch { console.error('Preview HTTP unavailable'); process.exitCode = 1; }
  }
}
