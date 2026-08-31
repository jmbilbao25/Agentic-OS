/* The Note and Ask views.
 *
 * Both render into the dock. Both have the same three states — loading, loaded,
 * failed — and say so out loud, because a panel that stays blank is
 * indistinguishable from a panel that broke.
 */

import { get, stream, AuthLost } from './api.js';
import { md } from './md.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const skeleton = `<div class="skel"><i></i><i></i><i></i><i></i></div>`;

const failure = (msg) => `<div class="failed">
  <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg>
  <b>That did not load</b><p>${esc(msg)}</p></div>`;

function when(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const days = Math.floor((Date.now() - d) / 86400000);
  const stamp = d.toISOString().slice(0, 10);
  if (days <= 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  return stamp;
}

/* ------------------------------------------------------------------- note */

export class DocView {
  constructor({ onJump, titles, toast }) {
    this.body = $('#doc-body');
    this.onJump = onJump;
    this.titles = titles;              // () => Set of lowercase titles
    this.toast = toast;
    this.current = null;

    this.body.addEventListener('click', (e) => {
      const wl = e.target.closest('[data-wl]');
      if (wl) return this.onJump({ title: wl.dataset.wl });
      const jump = e.target.closest('[data-doc]');
      if (jump) return this.onJump({ id: jump.dataset.doc });
      const copy = e.target.closest('[data-copy]');
      if (copy) {
        navigator.clipboard?.writeText(copy.dataset.copy)
          .then(() => this.toast('Path copied'))
          .catch(() => this.toast('The browser blocked the clipboard', 'err'));
      }
    });
  }

  async load(id) {
    if (!id) return;
    this.current = id;
    this.body.innerHTML = skeleton;
    try {
      const doc = await get(`/api/doc?id=${encodeURIComponent(id)}`);
      if (this.current !== id) return;            // a newer click won
      this.render(doc);
    } catch (e) {
      if (e instanceof AuthLost) throw e;
      this.body.innerHTML = failure(e.message);
    }
  }

  render(doc) {
    // A chip is for a short value. Skill files carry a multi-sentence
    // `description:` in frontmatter, and putting that in a pill produced a
    // paragraph wearing a border-radius. Long values get their own block.
    const fm = Object.entries(doc.fm || {})
      .filter(([k]) => !['tags', 'title'].includes(k));
    const shortFm = fm.filter(([, v]) => String(v).length <= 48);
    const longFm = fm.filter(([, v]) => String(v).length > 48);

    const chips = [
      `<span class="chip layer">${esc(doc.layer)}</span>`,
      `<span class="chip ring-${esc(doc.ring)}">${esc(doc.ring)}</span>`,
      ...(doc.tags || []).map((t) => `<span class="chip">#${esc(t)}</span>`),
      ...shortFm.map(([k, v]) => `<span class="chip">${esc(k)}: ${esc(v)}</span>`),
    ].join('');

    const notes = longFm.map(([k, v]) => `<p class="fm-long">
      <span>${esc(k)}</span>${esc(v)}</p>`).join('');

    const links = (label, list) => (!list?.length ? '' : `
      <div class="linkcol">
        <h4>${label} · ${list.length}</h4>
        <ul>${list.map((b) => `<li><button class="jump" data-doc="${esc(b.id)}">
          ${esc(b.title)}</button></li>`).join('')}</ul>
      </div>`);

    const linkbar = (doc.backlinks?.length || doc.outgoing?.length)
      ? `<div class="linkbar">
           ${links('Linked from', doc.backlinks)}
           ${links('Links to', doc.outgoing)}
         </div>`
      : '';

    // `links` is every [[wikilink]] written in the file; `outgoing` is the subset
    // that resolves to a note that exists. Reporting the raw count as "links out"
    // next to a resolved list of a different length just looks like a bug, so name
    // the difference: a dangling link is a real thing to know about.
    const out = (doc.outgoing || []).length;
    const dangling = Math.max(0, (doc.links || []).length - out);

    this.body.innerHTML = `
      <div class="doc-head">
        <h2>${esc(doc.title)}</h2>
        <div class="chips">${chips}</div>
        ${notes}
      </div>
      <div class="well">
        <code>${esc(doc.path)}</code>
        <button class="btn btn-ghost btn-icon btn-sm" data-copy="${esc(doc.path)}"
                title="Copy path" aria-label="Copy path">
          <svg class="i" aria-hidden="true"><use href="#i-copy"/></svg>
        </button>
        ${doc.repo_url ? `<a class="btn btn-ghost btn-icon btn-sm"
            href="${esc(doc.repo_url)}" target="_blank" rel="noopener"
            title="Open on GitHub" aria-label="Open on GitHub">
          <svg class="i" aria-hidden="true"><use href="#i-external"/></svg></a>` : ''}
      </div>
      <div class="telemetry">
        <span><b>${doc.words}</b> words</span>
        <span><b>${out}</b> out${dangling ? ` <span class="warnish">+${dangling} dangling</span>` : ''}</span>
        <span><b>${(doc.backlinks || []).length}</b> in</span>
        <span>edited <b>${when(doc.mtime)}</b></span>
      </div>
      ${linkbar}
      <div class="md">${md(doc.body, {
        exists: (n) => this.titles().has(n.toLowerCase()),
      })}</div>`;
    this.body.scrollTop = 0;
  }
}

/* -------------------------------------------------------------------- ask */

export class AskView {
  constructor({ onOpenDoc, modelPicker, toast, onBusy }) {
    this.answerEl = $('#ask-answer');
    this.sourcesEl = $('#ask-sources');
    this.inputEl = $('#ask-q');
    this.sendEl = $('#ask-send');
    this.onOpenDoc = onOpenDoc;
    this.modelPicker = modelPicker;
    this.toast = toast;
    this.onBusy = onBusy || (() => {});
    this.busy = false;
    this.abort = null;

    this.sourcesEl.addEventListener('click', (e) => {
      const b = e.target.closest('[data-doc]');
      if (b) this.onOpenDoc(b.dataset.doc);
    });
    this.answerEl.addEventListener('click', (e) => {
      const c = e.target.closest('[data-copy-answer]');
      if (c) {
        navigator.clipboard?.writeText(this.text || '')
          .then(() => this.toast('Answer copied'))
          .catch(() => this.toast('The browser blocked the clipboard', 'err'));
      }
    });
  }

  focus() { this.inputEl.focus(); }

  setQuestion(q) { this.inputEl.value = q; }

  stop() {
    if (this.abort) { this.abort.abort(); this.abort = null; }
  }

  async ask(question) {
    const q = (question ?? this.inputEl.value).trim();
    if (!q) { this.inputEl.focus(); return; }
    if (this.busy) return;

    this.inputEl.value = q;
    this.busy = true;
    this.onBusy(true);
    this.sendEl.disabled = true;
    this.abort = new AbortController();

    this.text = '';
    this.think = '';
    this.usage = null;
    this.modelUsed = null;
    this.answerEl.className = 'answer md streaming';
    this.answerEl.innerHTML = '';
    this.sourcesEl.innerHTML = `<h4>Sources</h4>${skeleton}`;

    let failed = null;
    const notices = [];

    try {
      const body = { q };
      const m = this.modelPicker?.value;
      if (m) body.model = m;

      for await (const { event, data } of
                 stream('/api/ask', body, { signal: this.abort.signal })) {
        switch (event) {
          case 'sources': this.renderSources(data); break;
          case 'retrieval': this.retrieval = data; break;
          case 'model': this.modelUsed = data.id; break;
          case 'reasoning': this.think += data.text; this.paint(); break;
          case 'delta': this.text += data.text; this.paint(); break;
          case 'usage': this.usage = data; break;
          case 'notice': notices.push(data.message); this.toast(data.message); break;
          case 'error': failed = data.message; break;
          default: break;
        }
      }
    } catch (e) {
      if (e instanceof AuthLost) { this.cleanup(); throw e; }
      if (e.name !== 'AbortError') failed = e.message;
    }

    this.answerEl.classList.remove('streaming');

    if (failed) {
      this.answerEl.innerHTML = failure(failed);
    } else if (!this.text.trim()) {
      this.answerEl.innerHTML = `<div class="empty">
        <svg class="i" aria-hidden="true"><use href="#i-empty"/></svg>
        <b>No answer came back</b>
        <p>The model returned nothing. Try a different model in the picker below.</p>
        </div>`;
    } else {
      this.paint(true);
    }
    this.cleanup();
  }

  cleanup() {
    this.busy = false;
    this.onBusy(false);
    this.sendEl.disabled = false;
    this.abort = null;
    // A queued repaint outlives an aborted stream otherwise, and lands one frame
    // later on top of whatever replaced the answer.
    if (this._paintRaf) {
      cancelAnimationFrame(this._paintRaf);
      this._paintRaf = null;
    }
  }

  /* Streaming calls this once per token, and it used to rebuild everything each
     time: a full markdown parse of the whole answer so far, an innerHTML
     teardown of the entire subtree, then `scrollTop = scrollHeight`, which
     forces a synchronous layout. That is O(N^2) work for an N-token answer, and
     it got slower exactly as the answer got longer — the thing you are watching.
     It had two visible costs beyond speed: the open <details> collapsed on every
     token, and any text you tried to select was destroyed under the cursor.

     So coalesce: at most one repaint per animation frame, no matter how fast the
     tokens arrive. The frame budget is the natural rate limit here because
     repainting faster than the display refreshes is work nobody can see. The
     final paint is never coalesced and never dropped. */
  paint(final = false) {
    if (final) {
      if (this._paintRaf) {
        cancelAnimationFrame(this._paintRaf);
        this._paintRaf = null;
      }
      this._paintNow(true);
      return;
    }
    if (this._paintRaf) return;          // a repaint is already queued
    this._paintRaf = requestAnimationFrame(() => {
      this._paintRaf = null;
      this._paintNow(false);
    });
  }

  _paintNow(final = false) {
    const think = this.think.trim() ? `<details class="think">
      <summary>Reasoning</summary>
      <div class="think-body">${esc(this.think)}</div></details>` : '';

    const foot = final ? `<div class="usage">
      ${this.modelUsed ? `<span><b>${esc(this.modelUsed)}</b></span>` : ''}
      ${this.retrieval?.mode ? `<span>retrieval <b>${esc(this.retrieval.mode)}</b></span>` : ''}
      ${this.usage?.total_tokens ? `<span><b>${this.usage.total_tokens}</b> tokens</span>` : ''}
      ${this.usage?.prompt_tokens ? `<span>${this.usage.prompt_tokens} in / ${this.usage.completion_tokens ?? '?'} out</span>` : ''}
      ${this.usage?.cost !== undefined ? `<span>cost <b>$${Number(this.usage.cost).toFixed(5)}</b></span>` : ''}
      <button class="btn btn-ghost btn-sm" data-copy-answer>
        <svg class="i" aria-hidden="true"><use href="#i-copy"/></svg>Copy</button>
    </div>` : '';

    // Carry the disclosure state across the rebuild. Reasoning arrives before the
    // answer does, so this <details> is usually the thing you opened first and
    // the thing that got slammed shut on the next token.
    const wasOpen = this.answerEl.querySelector('details.think')?.open;

    // Read scroll position BEFORE the write. Sticking to the bottom is right only
    // while the reader is already there; scrolling up mid-answer is a deliberate
    // act and yanking them back down fights them.
    const b = this.answerEl.closest('.view-body');
    const pinned = b
      ? b.scrollHeight - b.scrollTop - b.clientHeight < 48
      : false;

    this.answerEl.innerHTML = think + md(this.text) + foot;

    if (wasOpen !== undefined) {
      const d = this.answerEl.querySelector('details.think');
      if (d) d.open = wasOpen;
    }
    if (b && !final && pinned) b.scrollTop = b.scrollHeight;
  }

  renderSources(list) {
    if (!list.length) {
      this.sourcesEl.innerHTML = `<h4>Sources</h4>
        <div class="empty"><svg class="i" aria-hidden="true"><use href="#i-empty"/></svg>
        <b>Nothing retrieved</b><p>No note in the vault matched this question, so
        the answer would be unfounded. Try different words.</p></div>`;
      return;
    }
    this.sourcesEl.innerHTML = `<h4>Sources · ${list.length}</h4>` + list.map((s) => `
      <button class="src" data-doc="${esc(s.doc_id)}" title="${esc(s.text || '')}">
        <span class="n">${s.n}</span>
        <span class="t"><b>${esc(s.title)}</b>${s.heading && s.heading !== s.title
          ? ` — ${esc(s.heading)}` : ''}
          <span>${esc(s.path)}</span></span>
      </button>`).join('');
  }
}
