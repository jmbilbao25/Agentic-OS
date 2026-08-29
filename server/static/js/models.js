/* Model picker.
 *
 * A native <select> holding 400 options is unusable, and a plain text input makes
 * you remember exact provider ids. So: a text input that filters the live
 * catalogue, showing context length and price per million tokens next to each id,
 * because those are the two things that actually decide the choice.
 *
 * The catalogue is fetched once by app.js and handed to every picker, so opening
 * three of them costs one request.
 */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const money = (v) => {
  if (v === null || v === undefined) return null;
  if (v === 0) return 'free';
  return v < 1 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`;
};

const ctx = (n) => {
  if (!n) return null;
  return n >= 1000 ? `${Math.round(n / 1000)}K ctx` : `${n} ctx`;
};

let catalogue = [];
const pickers = new Set();

/** Called once when /api/models lands; refreshes every open picker. */
export function setCatalogue(models) {
  catalogue = Array.isArray(models) ? models : [];
  for (const p of pickers) p.refresh();
}

export function getCatalogue() { return catalogue; }

export class ModelPicker {
  constructor(host, { value = '', blank = '', onChange = () => {} } = {}) {
    this.host = host;
    this.blank = blank;                 // label shown for the empty value
    this.onChange = onChange;
    this._value = value;
    this.sel = 0;
    this.open = false;

    host.classList.add('combo');
    host.innerHTML = `
      <input type="text" class="mono" spellcheck="false" autocomplete="off"
             role="combobox" aria-expanded="false" aria-autocomplete="list">
      <div class="combo-list" role="listbox"></div>`;
    this.input = host.querySelector('input');
    this.list = host.querySelector('.combo-list');

    this.input.placeholder = blank || 'provider/model-id';
    this.input.value = value;

    this.input.addEventListener('focus', () => { this.show(); this.input.select(); });
    this.input.addEventListener('input', () => { this.show(); });
    this.input.addEventListener('keydown', (e) => this.key(e));
    this.input.addEventListener('blur', () => {
      // Let a click on an option land before the list disappears.
      setTimeout(() => this.hide(), 130);
    });
    this.list.addEventListener('mousedown', (e) => {
      const b = e.target.closest('[data-id]');
      if (!b) return;
      e.preventDefault();
      this.commit(b.dataset.id);
    });

    pickers.add(this);
  }

  destroy() { pickers.delete(this); }

  get value() { return this._value; }

  set value(v) {
    this._value = v || '';
    this.input.value = this._value;
  }

  matches() {
    const q = this.input.value.trim().toLowerCase();
    const all = catalogue;
    if (!q) return all.slice(0, 60);
    // Rank exact-ish matches first: typing "haiku" should not bury
    // claude-3.5-haiku under twenty ids that merely contain the letters.
    const scored = [];
    for (const m of all) {
      const id = m.id.toLowerCase();
      const name = (m.name || '').toLowerCase();
      let s = -1;
      if (id === q) s = 0;
      else if (id.startsWith(q)) s = 1;
      else if (id.includes(q)) s = 2;
      else if (name.includes(q)) s = 3;
      if (s >= 0) scored.push([s, m]);
    }
    scored.sort((a, b) => a[0] - b[0] || a[1].id.length - b[1].id.length);
    return scored.slice(0, 60).map((x) => x[1]);
  }

  show() {
    const rows = this.matches();
    this.sel = 0;

    if (!catalogue.length) {
      this.list.innerHTML =
        `<div class="empty"><b>No catalogue</b><p>Add an API key in Settings, or
         type the model id directly — it is used as given.</p></div>`;
    } else if (!rows.length) {
      this.list.innerHTML =
        `<div class="empty"><b>No model matches</b><p>It will still be sent as
         typed, in case the catalogue is stale.</p></div>`;
    } else {
      const head = this.blank
        ? `<button type="button" class="combo-opt" data-id="">
             <span class="mid">${esc(this.blank)}</span></button>` : '';
      this.list.innerHTML = head + rows.map((m, i) => {
        const meta = [ctx(m.context),
                      m.free ? null : money(m.prompt_per_m) &&
                        `${money(m.prompt_per_m)}/M in`,
                      m.free ? null : money(m.completion_per_m) &&
                        `${money(m.completion_per_m)}/M out`,
                      m.reasoning ? 'reasoning' : null].filter(Boolean);
        return `<button type="button" class="combo-opt${i === 0 && !head ? ' sel' : ''}"
                  data-id="${esc(m.id)}" role="option">
            <span class="mid">${esc(m.id)}${m.free ? ' <span class="free">·free</span>' : ''}</span>
            ${meta.length ? `<span class="meta">${meta.map(esc).join(' · ')}</span>` : ''}
          </button>`;
      }).join('');
    }

    this.host.classList.add('open');
    this.input.setAttribute('aria-expanded', 'true');
    this.open = true;
  }

  hide() {
    this.host.classList.remove('open');
    this.input.setAttribute('aria-expanded', 'false');
    this.open = false;
    // Whatever is in the box is the value, catalogue or not. A model id the
    // catalogue has never heard of is a normal thing to want.
    if (this.input.value.trim() !== this._value) this.commit(this.input.value.trim());
  }

  refresh() { if (this.open) this.show(); }

  move(d) {
    const opts = [...this.list.querySelectorAll('.combo-opt')];
    if (!opts.length) return;
    opts[this.sel]?.classList.remove('sel');
    this.sel = (this.sel + d + opts.length) % opts.length;
    const el = opts[this.sel];
    el.classList.add('sel');
    el.scrollIntoView({ block: 'nearest' });
  }

  key(e) {
    if (e.key === 'ArrowDown') { e.preventDefault(); this.open ? this.move(1) : this.show(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); this.move(-1); }
    else if (e.key === 'Enter') {
      const el = this.list.querySelectorAll('.combo-opt')[this.sel];
      if (this.open && el) { e.preventDefault(); this.commit(el.dataset.id); }
      else this.hide();
    } else if (e.key === 'Escape') {
      if (this.open) { e.stopPropagation(); this.input.value = this._value; this.hide(); }
    }
  }

  commit(id) {
    const next = (id ?? '').trim();
    const changed = next !== this._value;
    this._value = next;
    this.input.value = next;
    this.host.classList.remove('open');
    this.open = false;
    if (changed) this.onChange(next);
  }
}
