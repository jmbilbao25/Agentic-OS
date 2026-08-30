/* The Activities view, and the live feed.
 *
 * A roster of automations, each one a button, and underneath each one a running
 * account of what it is doing.
 *
 * WHY THIS POLLS INSTEAD OF STREAMING
 * -----------------------------------
 * It used to hold one SSE response open for the whole run. That works on a laptop
 * and fails on a phone: the doctor takes ~80 seconds over three captures, the
 * browser gave up at 50, and the panel reported "network error" for a run the
 * server went on to finish. Heartbeats did not save it — the connection was still
 * the single point of failure, and it was also the only thing reporting.
 *
 * So the server owns the run and this polls its log from an offset. A dropped
 * connection costs one poll. A lock screen costs nothing. A page reload rejoins
 * the run in progress instead of orphaning it, because `load()` asks which run is
 * live before it draws anything.
 *
 * The feed is deliberately verbose for the doctor: it is the one step where the
 * interesting part is what the model *decided* — which capture, which notes, which
 * links it had to drop — and a summary printed afterwards gives you no way to tell
 * a working run from a stuck one.
 */

import { get, post, AuthLost } from './api.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Seconds as something readable at a glance: "15m 12s" beats "912.4s". */
const fmt = (sec) => {
  const n = Math.max(0, Math.round(Number(sec) || 0));
  return n < 60 ? `${n}s` : `${Math.floor(n / 60)}m ${String(n % 60).padStart(2, '0')}s`;
};

/** Steps that cannot work without an inference key. */
const NEEDS_LLM = new Set(['distill', 'doctor']);

/** How often to ask for new log lines. Fast enough to feel live, slow enough that
 *  a forgotten open tab is not a load generator. */
const POLL_MS = 1500;

export class ActivitiesView {
  constructor({ toast, onOpenDoc, onBusy, onWrote }) {
    this.body = $('#activities-body');
    this.phaseEl = $('#act-phase');
    this.stopBtn = $('#act-stop');

    this.toast = toast;
    this.onOpenDoc = onOpenDoc || (() => {});
    this.onBusy = onBusy || (() => {});
    this.onWrote = onWrote || (() => {});

    this.data = null;
    this.loaded = false;
    this.watch = null;          // { runId, name, cursor, timer, wrote }

    this.body.addEventListener('click', (e) => {
      const run = e.target.closest('[data-run]');
      if (run) { this.start(run.dataset.run).catch((err) => this.fail(err)); return; }
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
    if (this.loaded && !force) { this.rejoin().catch(() => {}); return; }
    try {
      this.data = await get('/api/activities');
      this.loaded = true;
      this.render();
      await this.rejoin();
    } catch (e) {
      this.body.innerHTML = `<div class="failed">
        <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg>
        <b>Could not load activities</b><p>${esc(e.message)}</p></div>`;
      throw e;
    }
  }

  /** Reattach to a run already in progress. This is what makes a reload safe. */
  async rejoin() {
    if (this.watch) return;
    const { active } = await get('/api/activities/runs');
    if (!active) return;
    const head = await get(`/api/activities/runs/${active}`);
    this.attach(head.run_id, head.name, 0);
    this.toast(`Rejoined ${head.name} — already running`, 'ok');
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
        and it shows up here. A run keeps going if you close this tab.</p>
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

  /** Stop *watching*. The run itself continues server-side, on purpose: killing
   *  work halfway through a git-committing routine is worse than losing sight of
   *  it, and you can rejoin by reopening the panel. */
  stop() {
    if (!this.watch) return;
    const { name } = this.watch;
    this.detach();
    this.toast(`Stopped watching ${name} — it is still running on the server`);
  }

  setPhase(text) {
    this.phaseEl.innerHTML = text ? `<span class="spin"></span>${esc(text)}` : '';
  }

  async start(name) {
    if (this.watch) {
      this.toast(`${this.watch.name} is still running`, 'err');
      return;
    }
    const r = await post('/api/activities/run', { name });
    if (r.already_running) this.toast(`${name} was already running — watching it`);
    this.attach(r.run_id, name, 0);
  }

  attach(runId, name, cursor) {
    const log = document.getElementById(`act-log-${name}`);
    if (log && !cursor) { log.hidden = false; log.innerHTML = ''; }
    else if (log) log.hidden = false;

    const btn = this.body.querySelector(`[data-run="${name}"]`);
    if (btn) btn.disabled = true;
    this.stopBtn.hidden = false;
    this.onBusy(true);

    this.watch = { runId, name, cursor: cursor || 0, wrote: false, timer: null };
    this.tick();
  }

  detach() {
    if (!this.watch) return;
    const { name, timer, wrote } = this.watch;
    if (timer) clearTimeout(timer);
    this.watch = null;
    this.onBusy(false);
    this.stopBtn.hidden = true;
    this.setPhase('');
    const btn = this.body.querySelector(`[data-run="${name}"]`);
    if (btn) btn.disabled = false;
    if (wrote) this.onWrote();
  }

  async tick() {
    if (!this.watch) return;
    const { runId, name, cursor } = this.watch;
    let head;
    try {
      head = await get(`/api/activities/runs/${runId}?after=${cursor}`);
    } catch (e) {
      if (e instanceof AuthLost) { this.detach(); this.fail(e); return; }
      // A failed poll is not a failed run. Say so, and try again — this is the
      // whole point of not streaming.
      this.setPhase(`${name} · reconnecting…`);
      this.watch.timer = setTimeout(() => this.tick().catch(() => {}), POLL_MS * 2);
      return;
    }

    const log = document.getElementById(`act-log-${name}`);
    for (const ev of head.events || []) this.line(log, ev);
    this.watch.cursor = head.next;
    if ((head.events || []).some((e) => e.type === 'note' || e.type === 'doctor_note'
                                        || e.type === 'step_done')) {
      this.watch.wrote = true;
    }

    if (head.running) {
      this.setPhase(`${name} · ${fmt(head.elapsed)}`);
      this.watch.timer = setTimeout(() => this.tick().catch(() => {}), POLL_MS);
      return;
    }

    if (head.ok) this.toast(head.message || `${name} finished`, 'ok');
    else if (head.message) this.toast(head.message, 'err');
    this.detach();
  }

  /* ----------------------------------------------------------- the feed */

  line(log, ev) {
    if (!log) return;
    const row = (cls, icon, head, detail, right) => {
      log.insertAdjacentHTML('beforeend', `<div class="act-line ${cls}">
        ${icon ? `<svg class="i" aria-hidden="true"><use href="#${icon}"/></svg>`
               : '<span class="spin"></span>'}
        <span class="act-line-t"><b>${head}</b>${
          detail ? `<span>${detail}</span>` : ''}</span>${
          right ? `<span class="act-el">${esc(right)}</span>` : ''}</div>`);
      log.lastElementChild?.scrollIntoView({ block: 'nearest' });
    };

    switch (ev.type) {
      case 'start':
        row('', 'i-run', esc(ev.name),
            `${ev.of} step${ev.of === 1 ? '' : 's'}: ${esc((ev.steps || []).join(' → '))}`);
        break;
      case 'step':
        row('running', '', esc(ev.render), esc(ev.summary));
        break;
      case 'ping':
        // Liveness only; the phase line already carries the clock.
        break;
      case 'step_done':
        row(ev.ok ? 'ok' : 'bad', ev.ok ? 'i-check' : 'i-alert', esc(ev.verb),
            esc(((ev.ok ? ev.output : ev.error) || '').trim().split('\n')
              .filter(Boolean).slice(-2).join(' ').slice(0, 300)) || (ev.ok ? 'done' : 'failed'),
            ev.elapsed ? fmt(ev.elapsed) : '');
        break;
      case 'reindexed':
        row('ok', 'i-sync', 'reindexed',
            `${ev.chunks ?? '?'} chunks across ${ev.docs ?? '?'} documents — searchable now`);
        break;

      /* ---- the doctor narrating itself ---- */
      case 'doctor_start':
        row('', 'i-doc', 'reading captures',
            `${ev.captures} to promote, ${ev.targets} existing notes to link into${
              ev.deferred ? `, ${ev.deferred} left for next run` : ''}`);
        break;
      case 'doctor_capture':
        row('sub', 'i-doc', esc(ev.capture), `capture ${ev.n} of ${ev.of}`);
        break;
      case 'doctor_thinking':
        row('sub running', '', 'asking the model',
            `${ev.chars.toLocaleString()} characters of capture, ${ev.targets} link targets`);
        break;
      case 'doctor_proposed':
        row('sub', 'i-ask', `${ev.count} note${ev.count === 1 ? '' : 's'} proposed`,
            `${esc(ev.model || '')}${ev.titles?.length ? ` — ${esc(ev.titles.join('; '))}` : ''}`);
        break;
      case 'doctor_note':
        row('sub ok', 'i-check', esc(ev.title),
            `written · links to ${esc((ev.links || []).join(', ')) || 'nothing'}${
              ev.dropped?.length ? ` · dropped ${esc(ev.dropped.join(', '))}` : ''}`);
        break;
      case 'doctor_links_dropped':
        row('sub warn', 'i-warn', 'unresolvable links removed',
            `${esc(ev.title)} → ${esc((ev.dropped || []).join(', '))}`);
        break;
      case 'doctor_skipped':
        row('sub', 'i-empty', esc(ev.title), `skipped — ${esc(ev.why)}`);
        break;
      case 'doctor_orphan':
        row('sub warn', 'i-warn', esc(ev.title), `dropped — ${esc(ev.why)}`);
        break;
      case 'doctor_capture_done':
        row('sub', ev.ok ? 'i-check' : 'i-alert', esc(ev.capture),
            ev.ok ? `${(ev.written || []).length} written, ${(ev.skipped || []).length} skipped, ${(ev.orphans || []).length} orphaned`
                  : esc(ev.error || 'failed'));
        break;

      case 'error':
        row('bad', 'i-alert', 'stopped', esc(ev.message));
        break;
      case 'notice':
        row('', 'i-doc', 'note', esc(ev.message));
        break;
      case 'done':
        log.insertAdjacentHTML('beforeend',
          `<div class="act-done ${ev.ok ? 'ok' : 'bad'}">${esc(ev.message || '')}</div>`);
        break;
      default:
        break;
    }
  }
}
