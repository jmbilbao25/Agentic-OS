/* The Settings view.
 *
 * The form is generated from the schema the server ships, not hand-written. That
 * is the whole reason settings.py carries labels, help text, ranges and flags:
 * adding a knob is one entry in Python and it appears here, correctly typed, with
 * its own validation and its own "needs a reindex" warning. A hand-maintained
 * form drifts from its backend within one change.
 *
 * Only changed fields are sent. The server validates all-or-nothing, so a single
 * bad value returns per-field errors and applies none of them, and this view
 * shows them against the fields they belong to rather than as one opaque banner.
 */

import { get, put, post, AuthLost } from './api.js';
import { ModelPicker } from './models.js';

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export class SettingsView {
  constructor({ toast, onSaved }) {
    this.body = $('#settings-body');
    this.statusEl = $('#settings-status');
    this.saveBtn = $('#settings-save');
    this.toast = toast;
    this.onSaved = onSaved || (() => {});
    this.data = null;
    this.dirty = new Map();
    this.pickers = [];
    this.loaded = false;
  }

  async load(force = false) {
    if (this.loaded && !force) return;
    this.body.innerHTML = '<div class="skel"><i></i><i></i><i></i><i></i></div>';
    try {
      this.data = await get('/api/settings');
      this.loaded = true;
      this.render();
    } catch (e) {
      if (e instanceof AuthLost) throw e;
      this.body.innerHTML = `<div class="failed">
        <svg class="i" aria-hidden="true"><use href="#i-alert"/></svg>
        <b>Could not load settings</b><p>${esc(e.message)}</p></div>`;
    }
  }

  /* ------------------------------------------------------------- rendering */

  render() {
    const { schema, groups, values, sources, secrets } = this.data;
    this.dirty.clear();
    for (const p of this.pickers) p.destroy();
    this.pickers = [];

    this.body.innerHTML = groups.map((g) => {
      const fields = schema.filter((f) => f.group === g.id);
      if (!fields.length) return '';
      return `<section class="group">
        <h3>${esc(g.label)}</h3>
        <p>${esc(g.help)}</p>
        ${fields.map((f) => this.field(f, values[f.key], sources[f.key],
                                       secrets[f.key])).join('')}
      </section>`;
    }).join('') + `
      <section class="group">
        <h3>Where these live</h3>
        <p>Saved values are written to <code>${esc(this.data.store)}</code>, which is
        gitignored because it holds an API key. Anything marked <b>env</b> came from
        <code>server/.env</code>; anything marked <b>saved</b> was set here and wins
        over both.</p>
      </section>`;

    // Mount the model comboboxes and wire every control's change handler.
    for (const f of schema) {
      const host = this.body.querySelector(`[data-mount="${f.key}"]`);
      if (host) {
        const p = new ModelPicker(host, {
          value: values[f.key] || '',
          blank: f.key.startsWith('GAUNTLET_') ? 'Use the main model' : '',
          onChange: (v) => this.change(f.key, v),
        });
        this.pickers.push(p);
        continue;
      }
      const el = this.body.querySelector(`[data-key="${f.key}"]`);
      if (!el) continue;
      const evt = (f.kind === 'bool' || f.kind === 'choice') ? 'change' : 'input';
      el.addEventListener(evt, () => {
        let v;
        if (f.kind === 'bool') v = el.checked;
        else v = el.value;
        this.change(f.key, v);
        const out = this.body.querySelector(`[data-out="${f.key}"]`);
        if (out) out.textContent = v;
      });
    }
    this.status();
  }

  field(f, value, source, secret) {
    const flags = [
      f.reindex ? '<span class="flag reindex">reindex</span>' : '',
      f.restart ? '<span class="flag restart">restart</span>' : '',
    ].join('');

    const tag = source === 'default' ? '' :
      `<span class="src-tag ${esc(source)}">${esc(source)}</span>`;

    let control;
    switch (f.kind) {
      case 'bool':
        control = `<label class="switch">
          <input type="checkbox" data-key="${esc(f.key)}"${value ? ' checked' : ''}>
          <span class="track"></span>
          <span>${value ? 'On' : 'Off'}</span></label>`;
        break;

      case 'choice':
        control = `<select data-key="${esc(f.key)}">${
          (f.choices || []).map((c) => `<option value="${esc(c)}"${
            c === value ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
        break;

      case 'model':
        control = `<div data-mount="${esc(f.key)}"></div>`;
        break;

      case 'text':
        control = `<textarea data-key="${esc(f.key)}" rows="${
          String(value || '').length > 160 ? 7 : 3}"
          spellcheck="false">${esc(value)}</textarea>`;
        break;

      case 'secret':
        control = `<input type="password" data-key="${esc(f.key)}" class="mono"
          autocomplete="new-password" spellcheck="false"
          placeholder="${secret?.set
            ? `set — ends ${esc(secret.hint)}. Leave blank to keep it.`
            : esc(f.placeholder || 'not set')}">`;
        break;

      case 'csv':
        control = `<input type="text" data-key="${esc(f.key)}" class="mono"
          spellcheck="false" value="${esc((value || []).join(', '))}"
          placeholder="${esc(f.placeholder)}">`;
        break;

      case 'int':
      case 'float': {
        const span = (f.hi ?? 0) - (f.lo ?? 0);
        // A slider is only honest over a range you can actually aim inside. Past
        // a couple of hundred steps the pixel is worth more than the value.
        if (span > 0 && span <= 200) {
          control = `<div class="slider-row">
            <input type="range" data-key="${esc(f.key)}" min="${f.lo}" max="${f.hi}"
              step="${f.step || (f.kind === 'int' ? 1 : 0.05)}" value="${esc(value)}">
            <output data-out="${esc(f.key)}">${esc(value)}</output></div>`;
        } else {
          control = `<input type="number" data-key="${esc(f.key)}" class="mono"
            min="${f.lo ?? ''}" max="${f.hi ?? ''}"
            step="${f.step || (f.kind === 'int' ? 1 : 'any')}" value="${esc(value)}">`;
        }
        break;
      }

      default:
        control = `<input type="${f.kind === 'url' ? 'url' : 'text'}"
          data-key="${esc(f.key)}" class="mono" spellcheck="false"
          value="${esc(value)}" placeholder="${esc(f.placeholder)}">`;
    }

    return `<div class="field" data-field="${esc(f.key)}">
      <label>${esc(f.label)}${tag}
        ${flags ? `<span class="flags">${flags}</span>` : ''}</label>
      ${control}
      ${f.help ? `<p class="hint">${esc(f.help)}</p>` : ''}
      <p class="err" hidden></p>
    </div>`;
  }

  /* ---------------------------------------------------------------- state */

  change(key, value) {
    this.dirty.set(key, value);
    const wrap = this.body.querySelector(`[data-field="${key}"]`);
    wrap?.classList.remove('invalid');
    const err = wrap?.querySelector('.err');
    if (err) err.hidden = true;
    // Keep the switch's own label honest as it flips.
    const sw = this.body.querySelector(`[data-key="${key}"]`);
    if (sw?.type === 'checkbox') {
      const span = sw.closest('.switch')?.querySelector('span:last-child');
      if (span) span.textContent = sw.checked ? 'On' : 'Off';
    }
    this.status();
  }

  status() {
    const n = this.dirty.size;
    this.saveBtn.disabled = n === 0;
    const pending = this.data?.reindex_pending
      ? ' · index is stale, reindex to apply' : '';
    this.statusEl.textContent = n
      ? `${n} unsaved change${n === 1 ? '' : 's'}${pending}`
      : (pending ? pending.slice(3) : 'Everything saved');
  }

  async save() {
    if (!this.dirty.size) return;
    const patch = Object.fromEntries(this.dirty);
    this.saveBtn.disabled = true;
    try {
      const r = await put('/api/settings', patch);
      this.data = r.settings;
      this.render();
      const bits = [`Saved ${r.changed.length} setting${r.changed.length === 1 ? '' : 's'}`];
      if (r.restart_required?.length) {
        bits.push(`${r.restart_required.join(', ')} needs a restart`);
      }
      if (r.reindex_pending) bits.push('reindex to apply');
      this.toast(bits.join(' · '), 'ok');
      this.onSaved(r);
    } catch (e) {
      if (e instanceof AuthLost) throw e;
      // A 422 body is {errors: {KEY: message}, changed: []}. api() hands us the
      // raw body as the message because there is no top-level `error` key, so
      // unwrap `errors` rather than iterating the envelope.
      let errs = null;
      try {
        const parsed = JSON.parse(e.message);
        errs = parsed?.errors ?? parsed;
      } catch { /* not a field map — fall through to a plain toast */ }
      if (errs && typeof errs === 'object' && !Array.isArray(errs)) {
        for (const [k, msg] of Object.entries(errs)) {
          const wrap = this.body.querySelector(`[data-field="${k}"]`);
          wrap?.classList.add('invalid');
          const el = wrap?.querySelector('.err');
          if (el) { el.textContent = msg; el.hidden = false; }
        }
        this.toast('Nothing was saved — fix the highlighted fields', 'err');
        wrapScroll(this.body);
      } else {
        this.toast(e.message, 'err');
      }
      this.saveBtn.disabled = false;
    }
  }

  async resetAll() {
    if (!confirm('Forget every saved setting and fall back to server/.env and the '
                 + 'shipped defaults?\n\nThis also clears the stored API key.')) return;
    try {
      const r = await post('/api/settings/reset', {});
      this.data = r.settings;
      this.render();
      this.toast(`Cleared ${r.cleared.length} saved value${
        r.cleared.length === 1 ? '' : 's'}`, 'ok');
      this.onSaved(r);
    } catch (e) {
      if (e instanceof AuthLost) throw e;
      this.toast(e.message, 'err');
    }
  }
}

/* Errors are useless if they are scrolled off. */
function wrapScroll(root) {
  root.querySelector('.field.invalid')?.scrollIntoView({
    block: 'center', behavior: 'smooth',
  });
}
