/* The Activities view.
 *
 * A roster of automations, each one a button. Pressing one streams a frame per
 * step into that activity's own card, so the log stays attached to the thing that
 * produced it rather than accumulating in a shared console — you press two
 * buttons over a morning and you still know which output was which.
 *
 * What a step *writes* is shown before you run it, next to the steps themselves.
 * These recipes append to the vault, and a button whose consequences are only
 * discoverable by pressing it is a button people are right not to trust.
 */

import { get, stream, AuthLost } from './api.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Steps that cannot work without an inference key. */
const NEEDS_LLM = new Set(['distill', 'doctor']);

export class ActivitiesView {
  constructor({ toast, onOpenDoc, onBusy, onWrote }) {
    this.body = $('#activities-body');
    this.phaseEl = $('#act-phase');
    this.stopBtn = $('#act-stop');

    this.toast = toast;
    this.onOpenDoc = onOpenDoc || (() => {});
    this.onBusy = onBusy || (() => {});
    // The map is stale the moment an activity writes a note, so the caller gets
    // told rather than the user being left with a graph that quietly disagrees
    // with the vault.
    this.onWrote = onWrote || (() => {});

    this.data = null;
    this.running = null;      // name of the activity currently running
    this.abort = null;
    this.loaded = false;

    this.body.addEventListener('click', (e) => {
      const run = e.target.closest('[data-run]');
      if (run) { this.run(run.dataset.run).catch((err) => this.fail(err)); return; }
      const open = e.target.closest('[data-doc]');
      if (open) this.onOpenDoc(open.dataset.doc);
    });
  }

  fail(e) {
    if (e instanceof AuthLost) throw e;
    this.toast(e.message || String(e), 'err');
  }

  /* --------------------------------------------------------------- loading */

  async load({ force = false } = {}) {
    if (this.loaded && !force) return;
    try {
      this.data = await get('/api/activities');
      this.loaded = true;
      this.render();
    } catch (e) {
      this.body.innerHTML = `<div class="failed">
        <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg>
        <b>Could not load activities</b><p>${esc(e.message)}</p></div>`;
      throw e;
    }
  }

  /* -------------------------------------------------------------- render */

  render() {
    const { activities = [], steps = {}, will_not_run: broken = [],
            llm_configured: hasKey } = this.data || {};

    const notices = broken.length ? `<div class="notice act-notice">
      <svg class="i" aria-hidden="true"><use href="#i-warn"/></svg>
      <span><b>${broken.length} file${broken.length === 1 ? '' : 's'} in
      config/activities/ will not run.</b> ${broken.map(esc).join(' · ')}</span>
    </div>` : '';

    const empty = `<div class="empty">
      <svg class="i" aria-hidden="true"><use href="#i-empty"/></svg>
      <b>No activities yet</b>
      <p>Ask the agent for one — "make fetching AI news an activity". It writes a
      file into <code>config/activities/</code> and it appears here.</p></div>`;

    this.body.innerHTML = `
      <div class="act-head">
        <h3>Activities</h3>
        <p>Automations this brain can run. Each one is a file in
        <code>config/activities/</code>, so an agent can write you a new button
        and it shows up here.</p>
      </div>
      ${notices}
      <div class="act-list">
        ${activities.length ? activities.map((a) => this.card(a, hasKey)).join('') : empty}
      </div>
      ${this.vocab(steps)}`;
  }

  card(a, hasKey) {
    const verbs = a.steps.map((s) => s.verb);
    const blocked = !hasKey && verbs.some((v) => NEEDS_LLM.has(v));

    const chain = a.steps.map((s) => `<span class="act-step" title="${esc(s.summary)}">
      ${esc(s.render)}</span>`).join('<span class="act-arrow">→</span>');

    const writes = (a.writes || []).length
      ? `<span class="act-writes">writes <b>${a.writes.map(esc).join('</b>, <b>')}</b></span>`
      : '';

    return `<article class="act" id="act-${esc(a.name)}">
      <div class="act-top">
        <div class="act-id">
          <button class="act-name" data-doc="${esc(a.id)}"
                  title="Open the recipe">${esc(a.name)}</button>
          <p>${esc(a.description)}</p>
        </div>
        <button class="btn btn-primary btn-sm act-run" data-run="${esc(a.name)}"
                ${blocked ? 'disabled' : ''}
                title="${blocked ? 'Needs an inference key' : `Run ${esc(a.name)}`}">
          <svg class="i" aria-hidden="true"><use href="#i-run"/></svg> Run
        </button>
      </div>
      <div class="act-meta">${chain}${writes}</div>
      ${blocked ? `<p class="act-blocked">
        <svg class="i" aria-hidden="true"><use href="#i-warn"/></svg>
        This one reasons over your notes, so it needs an inference key. Add one in
        Settings.</p>` : ''}
      <div class="act-log" id="act-log-${esc(a.name)}" hidden></div>
    </article>`;
  }

  /** The step vocabulary, shown because it is also the answer to "what can I ask
   *  the agent to build?" — and because it is the honest list of what a button
   *  here is able to do. */
  vocab(steps) {
    const rows = Object.entries(steps).map(([verb, v]) => `<tr>
      <td><code>${esc(verb)}${v.arg ? `: &lt;${esc(v.arg)}&gt;` : ''}</code></td>
      <td>${esc(v.summary)}</td>
      <td>${v.writes ? `<code>${esc(v.writes)}</code>` : '—'}</td></tr>`).join('');
    return `<details class="act-vocab">
      <summary>The steps an activity can be made of (${Object.keys(steps).length})</summary>
      <table><thead><tr><th>Step</th><th>Does</th><th>Writes</th></tr></thead>
      <tbody>${rows}</tbody></table>
      <p>There is deliberately no step that runs a shell command: captures in
      <code>brain/raw/</code> come from the internet, and activities are written by
      an agent that reads them.</p>
    </details>`;
  }

  /* ------------------------------------------------------------------ run */

  stop() {
    if (this.abort) {
      this.abort.abort();
      this.abort = null;
      this.toast('Activity stopped');
    }
  }

  setPhase(text) {
    this.phaseEl.innerHTML = text
      ? `<span class="spin"></span>${esc(text)}` : '';
  }

  async run(name) {
    if (this.running) {
      this.toast(`${this.running} is still running`, 'err');
      return;
    }
    const log = document.getElementById(`act-log-${name}`);
    const btn = this.body.querySelector(`[data-run="${name}"]`);
    if (!log) return;

    this.running = name;
    this.abort = new AbortController();
    this.onBusy(true);
    if (btn) btn.disabled = true;
    this.stopBtn.hidden = false;
    log.hidden = false;
    log.innerHTML = '';

    let failed = null;
    let wrote = false;

    try {
      for await (const { event, data } of stream('/api/activities/run', { name },
                                                 { signal: this.abort.signal })) {
        switch (event) {
          case 'start':
            this.setPhase(`${name} · ${data.of} step${data.of === 1 ? '' : 's'}`);
            break;
          case 'step':
            this.setPhase(`${name} · step ${data.n}/${data.of} · ${data.summary}`);
            log.insertAdjacentHTML('beforeend', `<div class="act-line running"
              id="act-${name}-${data.n}">
              <span class="spin"></span>
              <span class="act-line-t"><b>${esc(data.render)}</b>
              <span>${esc(data.summary)}</span></span></div>`);
            break;
          case 'step_done': {
            const row = document.getElementById(`act-${name}-${data.n}`);
            if (row) {
              // The tail of the output, not the head: a module's last lines are
              // its result, where its first are startup noise.
              const detail = ((data.ok ? data.output : data.error) || '')
                .trim().split('\n').filter(Boolean).slice(-3).join(' ');
              row.classList.remove('running');
              row.classList.add(data.ok ? 'ok' : 'bad');
              row.innerHTML = `<svg class="i" aria-hidden="true"><use href="#${
                data.ok ? 'i-check' : 'i-alert'}"/></svg>
                <span class="act-line-t"><b>${esc(data.verb)}</b>
                <span>${esc(detail.slice(0, 400)) || (data.ok ? 'done' : 'failed')}</span>
                </span>`;
            }
            if (data.ok) wrote = true;
            break;
          }
          case 'reindexed':
            log.insertAdjacentHTML('beforeend', `<div class="act-line ok">
              <svg class="i" aria-hidden="true"><use href="#i-sync"/></svg>
              <span class="act-line-t"><b>reindexed</b>
              <span>${data.chunks ?? '?'} chunks — what it wrote is searchable now</span>
              </span></div>`);
            break;
          case 'error': failed = data.message; break;
          case 'done':
            log.insertAdjacentHTML('beforeend', `<div class="act-done ${
              data.ok ? 'ok' : 'bad'}">${esc(data.message)}</div>`);
            if (data.ok) this.toast(data.message, 'ok');
            break;
          default: break;
        }
      }
    } catch (e) {
      if (e instanceof AuthLost) { this.cleanup(name); throw e; }
      if (e.name !== 'AbortError') failed = e.message;
    }

    if (failed) {
      log.insertAdjacentHTML('beforeend', `<div class="act-done bad">${esc(failed)}</div>`);
      this.toast(failed, 'err');
    }
    if (wrote) this.onWrote();
    this.cleanup(name);
  }

  cleanup(name) {
    this.running = null;
    this.abort = null;
    this.onBusy(false);
    this.stopBtn.hidden = true;
    this.setPhase('');
    const btn = this.body.querySelector(`[data-run="${name}"]`);
    if (btn) btn.disabled = false;
  }
}
