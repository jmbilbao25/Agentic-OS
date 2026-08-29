/* A small markdown renderer.
 *
 * Deliberately not a dependency: this UI must work on a locked-down box with no
 * CDN reachable, and the vault only uses a predictable subset of markdown. Code
 * fences are extracted first and reinserted last so that no inline rule can
 * corrupt code, and all HTML is escaped before any tag is generated — the vault
 * is trusted, but "trusted input" is how XSS happens.
 */

const esc = (s) => s.replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function inline(s, opts) {
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g, (_, c) => `<code>${c}</code>`);
  // wikilinks before other links so [[X]] never parses as a nested bracket
  t = t.replace(/\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/g, (_, target, label) => {
    const name = target.trim();
    const dead = opts.exists && !opts.exists(name);
    return `<span class="wl${dead ? ' dead' : ''}" data-wl="${esc(name)}"` +
           `${dead ? ' title="no note with this name yet"' : ''}>` +
           `${esc(label || name)}</span>`;
  });
  // Sized by a class, not a style attribute: the app ships a CSP without
  // 'unsafe-inline', which blocks inline style attributes outright.
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g,
                (_, a, u) => `<img alt="${a}" src="${u}" class="md-img" loading="lazy">`);
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_, a, u) => {
    const safe = /^(https?:|mailto:|#|\/)/i.test(u);
    return safe ? `<a href="${u}" target="_blank" rel="noopener">${a}</a>` : a;
  });
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  t = t.replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  t = t.replace(/(^|[\s(])_([^_\n]+)_/g, '$1<em>$2</em>');
  t = t.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  return t;
}

function table(rows, opts) {
  const cells = (r) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
  const head = cells(rows[0]);
  const body = rows.slice(2).map(cells);
  let h = '<table><thead><tr>' +
    head.map((c) => `<th>${inline(c, opts)}</th>`).join('') + '</tr></thead><tbody>';
  for (const r of body) {
    h += '<tr>' + r.map((c) => `<td>${inline(c, opts)}</td>`).join('') + '</tr>';
  }
  return h + '</tbody></table>';
}

export function md(src, opts = {}) {
  if (!src) return '';
  let text = String(src).replace(/\r\n?/g, '\n');

  // strip YAML frontmatter — it is metadata, shown separately in the UI
  text = text.replace(/^---\n[\s\S]*?\n---\n?/, '');

  // pull code fences out of harm's way
  const fences = [];
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    fences.push(`<pre><code class="lang-${lang}">${esc(code.replace(/\n$/, ''))}</code></pre>`);
    return `\u0000FENCE${fences.length - 1}\u0000`;
  });

  const out = [];
  const lines = text.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) { i++; continue; }

    if (/^\u0000FENCE\d+\u0000$/.test(line.trim())) {
      out.push(line.trim()); i++; continue;
    }

    let m = line.match(/^(#{1,6})\s+(.*)$/);
    if (m) {
      const lv = m[1].length;
      out.push(`<h${lv}>${inline(m[2], opts)}</h${lv}>`);
      i++; continue;
    }

    if (/^\s*([-*_])\s*\1\s*\1[\s\1]*$/.test(line)) { out.push('<hr>'); i++; continue; }

    // table: header row followed by a separator row
    if (line.includes('|') && /^\s*\|?[\s:-]*-[\s:|-]*\|?\s*$/.test(lines[i + 1] || '')) {
      const rows = [];
      while (i < lines.length && lines[i].includes('|')) rows.push(lines[i++]);
      out.push(table(rows, opts)); continue;
    }

    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        buf.push(lines[i++].replace(/^\s*>\s?/, ''));
      }
      out.push(`<blockquote>${md(buf.join('\n'), opts)}</blockquote>`);
      continue;
    }

    if (/^\s*([-*+]|\d+\.)\s/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s/.test(lines[i])) {
        let body = lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, '');
        i++;
        // continuation lines belonging to this item
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) &&
               !/^\s*([-*+]|\d+\.)\s/.test(lines[i])) {
          body += ' ' + lines[i].trim(); i++;
        }
        const task = body.match(/^\[([ xX])\]\s*(.*)$/);
        if (task) {
          const done = task[1].toLowerCase() === 'x';
          items.push(`<li><input type="checkbox" disabled${done ? ' checked' : ''}>` +
                     `${inline(task[2], opts)}</li>`);
        } else {
          items.push(`<li>${inline(body, opts)}</li>`);
        }
      }
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${items.join('')}</${tag}>`);
      continue;
    }

    const buf = [];
    while (i < lines.length && lines[i].trim() &&
           !/^(#{1,6}\s|\s*>|\s*([-*+]|\d+\.)\s|\u0000FENCE)/.test(lines[i])) {
      buf.push(lines[i++]);
    }
    if (buf.length) out.push(`<p>${inline(buf.join('\n'), opts)}</p>`);
    else i++;
  }

  return out.join('\n').replace(/\u0000FENCE(\d+)\u0000/g, (_, n) => fences[+n]);
}
