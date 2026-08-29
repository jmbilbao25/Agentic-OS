/* Talking to the server.
 *
 * Two jobs: turn a failed fetch into an Error carrying the server's own message,
 * and turn an SSE response into an async iterator of parsed events. Both exist so
 * that no caller has to write framing or error-shape logic again.
 */

/** A 401 means the session went away while the tab stayed open. */
export class AuthLost extends Error {}

async function detail(r) {
  const body = await r.text();
  try {
    const j = JSON.parse(body);
    return j.error || j.detail || body;
  } catch { return body; }
}

export async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, { credentials: 'same-origin', ...opts });
  } catch {
    // fetch only rejects on transport failure, which is the one case where the
    // server has no message to offer.
    throw new Error('Cannot reach the server. Is it still running?');
  }
  if (r.status === 401) throw new AuthLost('Session expired');
  if (!r.ok) throw new Error(await detail(r));
  if (r.status === 204) return null;
  return r.json();
}

export const get = (p) => api(p);

export const post = (p, body) => api(p, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body ?? {}),
});

export const put = (p, body) => api(p, {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body ?? {}),
});

/**
 * POST a body and yield parsed SSE events as { event, data }.
 *
 * Written as an async generator so a caller can `for await` and keep its state in
 * local variables instead of a callback soup of half-finished buffers. The
 * trailing partial frame is deliberately held back until the next chunk: SSE
 * frames are split on a blank line and a chunk boundary lands mid-frame often
 * enough that not doing this drops tokens.
 */
export async function* stream(path, body, { signal } = {}) {
  const r = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (r.status === 401) throw new AuthLost('Session expired');
  if (!r.ok) throw new Error(await detail(r));
  if (!r.body) throw new Error('This browser cannot read a streaming response.');

  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let pending = '';

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      pending += dec.decode(value, { stream: true });

      const frames = pending.split('\n\n');
      pending = frames.pop() ?? '';

      for (const frame of frames) {
        if (!frame.trim()) continue;
        let event = 'message';
        const dataLines = [];
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
        }
        if (!dataLines.length) continue;
        let data;
        try { data = JSON.parse(dataLines.join('\n')); } catch { continue; }
        yield { event, data };
      }
    }
  } finally {
    // Abandoning a stream without cancelling leaves the connection open and the
    // server generating tokens nobody will read.
    try { await reader.cancel(); } catch { /* already closed */ }
  }
}
