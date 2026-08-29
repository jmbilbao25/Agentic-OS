/* The Gauntlet view.
 *
 * Renders the loop as a ledger: one card per round, the builder's artifact, then
 * the critic's forced choice and the single gap it named. You are watching a
 * quality argument play out, so the verdict is the loudest thing on each card —
 * not the prose.
 *
 * The blind side (which of A/B was ours) is shown *after* the verdict, because
 * seeing it beforehand would let you second-guess a judgement the critic made
 * without it.
 */

import { post, stream, AuthLost } from './api.js';
import { md } from './md.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export class GauntletView {
  constructor({ builderPicker, criticPicker, toast, onOpenDoc, onBusy }) {
    this.log = $('#g-rounds-log');
    this.phaseEl = $('#g-phase');
    this.runBtn = $('#g-run');
    this.stopBtn = $('#g-stop');
    this.goalEl = $('#g-goal');
    this.barEl = $('#g-bar');
    this.urlEl = $('#g-url');
    this.fetchBtn = $('#g-fetch');
    this.barStatus = $('#g-bar-status');
    this.roundsEl = $('#g-rounds');
    this.roundsOut = $('#g-rounds-out');

    this.builderPicker = builderPicker;
    this.criticPicker = criticPicker;
    this.toast = toast;
    this.onOpenDoc = onOpenDoc;
    this.onBusy = onBusy || (() => {});

    this.busy = false;
    this.abort = null;
    this.cards = new Map();          // round -> { artifact, verdict }

    this.roundsEl.addEventListener('input', () => {
      this.roundsOut.textContent = this.roundsEl.value;
    });

    this.log.addEventListener('click', (e) => {
      const b = e.target.closest('[data-doc]');
      if (b) this.onOpenDoc(b.dataset.doc);
      const c = e.target.closest('[data-copy-final]');
      if (c) {
        navigator.clipboard?.writeText(this.final || '')
          .then(() => this.toast('Final artifact copied'))
          .catch(() => this.toast('The browser blocked the clipboard', 'err'));
      }
    });
  }

  setDefaults(g) {
    if (!g) return;
    if (g.ceiling) { this.roundsEl.value = g.ceiling; this.roundsOut.textContent = g.ceiling; }
  }

  /* ------------------------------------------------------------- the bar */

  async fetchBar() {
    const url = this.urlEl.value.trim();
    if (!url) { this.urlEl.focus(); return; }
    this.fetchBtn.disabled = true;
    this.barStatus.textContent = 'Fetching…';
    try {
      const r = await post('/api/gauntlet/bar', { url });
      this.barEl.value = r.text;
      this.barStatus.innerHTML =
        `Got <b>${r.chars.toLocaleString()}</b> characters from ${esc(r.title)}. `
        + 'Check it reads like the real thing before running.';
      this.toast(`Bar loaded — ${r.chars.toLocaleString()} characters`, 'ok');
    } catch (e) {
      if (e instanceof AuthLost) throw e;
      this.barStatus.textContent = e.message;
      this.toast(e.message, 'err');
    } finally {
      this.fetchBtn.disabled = false;
    }
  }

  /* ---------------------------------------------------------------- run */

  stop() {
    if (this.abort) {
      this.abort.abort();
      this.abort = null;
      this.toast('Gauntlet stopped');
    }
  }

  async run() {
    if (this.busy) return;
    const goal = this.goalEl.value.trim();
    const bar = this.barEl.value.trim();

    if (!goal) { this.goalEl.focus(); return this.toast('Give it a goal', 'err'); }
    if (bar.length < 200) {
      this.barEl.focus();
      return this.toast('The bar needs to be a real artifact — at least a few '
        + 'paragraphs', 'err');
    }

    this.busy = true;
    this.onBusy(true);
    this.runBtn.disabled = true;
    this.stopBtn.hidden = false;
    this.abort = new AbortController();
    this.log.innerHTML = '';
    this.cards.clear();
    this.final = '';

    let round = 0;
    let failed = null;

    try {
      for await (const { event, data } of stream('/api/gauntlet', {
        goal,
        bar,
        builder_model: this.builderPicker?.value || '',
        critic_model: this.criticPicker?.value || '',
        max_rounds: Number(this.roundsEl.value) || undefined,
      }, { signal: this.abort.signal })) {
        switch (event) {
          case 'start': this.renderStart(data); break;
          case 'bar': this.barStatus.textContent =
            `Bar: ${data.title} (${data.chars} characters)`; break;
          case 'round': round = data.n; this.addCard(data.n, data.of); break;
          case 'phase': this.setPhase(data); break;
          case 'builder_delta': this.appendArtifact(round, data.text); break;
          case 'builder_done': this.finishArtifact(round, data.chars); break;
          case 'verdict': this.renderVerdict(round, data); break;
          case 'inconclusive': this.renderInconclusive(round, data); break;
          case 'usage': this.renderUsage(round, data); break;
          case 'notice': this.toast(data.message); break;
          case 'error': failed = data.message; break;
          case 'done': this.renderDone(data); break;
          default: break;
        }
      }
    } catch (e) {
      if (e instanceof AuthLost) { this.cleanup(); throw e; }
      if (e.name !== 'AbortError') failed = e.message;
    }

    if (failed) {
      this.log.insertAdjacentHTML('beforeend', `<div class="failed">
        <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg>
        <b>The gauntlet stopped</b><p>${esc(failed)}</p></div>`);
      this.toast(failed, 'err');
    }
    this.setPhase(null);
    this.cleanup();
  }

  cleanup() {
    this.busy = false;
    this.onBusy(false);
    this.runBtn.disabled = false;
    this.stopBtn.hidden = true;
    this.abort = null;
  }

  /* -------------------------------------------------------------- render */

  setPhase(p) {
    if (!p) { this.phaseEl.innerHTML = ''; return; }
    const label = { fetching: 'Fetching the bar', building: 'Builder drafting',
                    judging: 'Critic comparing blind' }[p.phase] || p.phase;
    this.phaseEl.innerHTML = `<span class="spin"></span>${esc(label)}${
      p.model ? ` · ${esc(p.model)}` : ''}`;
  }

  renderStart(d) {
    const sources = d.sources?.length
      ? `<div class="sources"><h4>Building from · ${d.sources.length}</h4>${
          d.sources.map((s) => `<button class="src" data-doc="${esc(s.doc_id)}">
            <span class="n">${s.n}</span><span class="t"><b>${esc(s.title)}</b>
            <span>${esc(s.path)}</span></span></button>`).join('')}</div>`
      : `<div class="empty"><svg class="i" aria-hidden="true"><use href="#i-empty"/></svg>
         <b>No vault context matched</b><p>The builder will work from the brief and
         the bar alone.</p></div>`;

    this.log.insertAdjacentHTML('beforeend', `
      <div class="round">
        <div class="round-head">Setup<span class="who">${esc(d.bar_label)} ·
          ${d.bar_chars.toLocaleString()} chars</span></div>
        <div class="round-body">
          <div class="telemetry">
            <span>builder <b>${esc(d.builder)}</b></span>
            <span>critic <b>${esc(d.critic)}</b></span>
            <span>ceiling <b>${d.ceiling}</b></span>
          </div>
          ${sources}
        </div>
      </div>`);
  }

  addCard(n, of) {
    this.log.insertAdjacentHTML('beforeend', `
      <div class="round" id="g-round-${n}">
        <div class="round-head">Round ${n}<span class="who">of ${of}</span></div>
        <div class="round-body">
          <div class="artifact md" id="g-art-${n}"></div>
        </div>
      </div>`);
    this.cards.set(n, { text: '' });
    const el = document.getElementById(`g-round-${n}`);
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  appendArtifact(n, text) {
    const card = this.cards.get(n);
    if (!card) return;
    card.text += text;
    const el = document.getElementById(`g-art-${n}`);
    if (el) {
      el.innerHTML = md(card.text);
      el.scrollTop = el.scrollHeight;
    }
  }

  finishArtifact(n, chars) {
    const head = document.querySelector(`#g-round-${n} .who`);
    if (head) head.textContent = `${chars.toLocaleString()} chars`;
  }

  renderUsage(n, u) {
    const card = document.getElementById(`g-round-${n}`);
    if (!card) return;
    const bits = [
      u.phase ? `${u.phase}` : null,
      u.total_tokens ? `${u.total_tokens} tokens` : null,
      u.cost !== undefined ? `$${Number(u.cost).toFixed(5)}` : null,
    ].filter(Boolean).join(' · ');
    if (!bits) return;
    let strip = card.querySelector('.usage');
    if (!strip) {
      card.querySelector('.round-body')
        ?.insertAdjacentHTML('beforeend', '<div class="usage"></div>');
      strip = card.querySelector('.usage');
    }
    strip.insertAdjacentHTML('beforeend', `<span>${esc(bits)}</span>`);
  }

  renderVerdict(n, v) {
    const card = document.getElementById(`g-round-${n}`);
    if (!card) return;
    card.insertAdjacentHTML('beforeend', `
      <div class="verdict ${v.won ? 'won' : 'lost'}">
        <span class="badge">${v.won ? 'ours won' : 'bar won'}</span>
        <span class="why">
          <b>${esc(v.reason)}</b>
          ${v.gap ? `<span class="gap">Next: ${esc(v.gap)}</span>` : ''}
          <span class="gap">Ours was shown as <b>${esc(v.ours_was)}</b>; the critic
          picked <b>${esc(v.picked)}</b>.</span>
        </span>
      </div>`);
  }

  renderInconclusive(n, d) {
    const card = document.getElementById(`g-round-${n}`);
    if (!card) return;
    card.insertAdjacentHTML('beforeend', `
      <div class="verdict tie">
        <span class="badge">no verdict</span>
        <span class="why"><b>${esc(d.message)}</b>
        ${d.raw ? `<span class="gap">It said: ${esc(d.raw.slice(0, 200))}</span>` : ''}
        </span>
      </div>`);
  }

  renderDone(d) {
    this.final = d.final || '';
    this.log.insertAdjacentHTML('beforeend', `
      <div class="round">
        <div class="round-head">${d.won ? 'Won' : 'Stopped'}
          <span class="who">${d.rounds} round${d.rounds === 1 ? '' : 's'}</span></div>
        <div class="round-body">
          <p>${esc(d.message)}</p>
          ${this.final ? `<button class="btn btn-sm" data-copy-final>
            <svg class="i" aria-hidden="true"><use href="#i-copy"/></svg>
            Copy the final artifact</button>` : ''}
        </div>
      </div>`);
    this.toast(d.message, d.won ? 'ok' : 'err');
  }
}
