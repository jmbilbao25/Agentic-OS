#!/usr/bin/env python3
"""Parsing, dashboard rendering, and the self-check for AgentOS.

Stdlib only, on purpose. The vault is markdown; anything that needs a package to
read it is a vault that will one day be unreadable.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAIN = ROOT / "brain"
LOOPS = BRAIN / "loops"
STEP = re.compile(r"^- \[( |x)\] (.*)$")
WIKILINK = re.compile(r"\[\[([^\]|#]+)")


def frontmatter(text):
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


def section(text, name):
    m = re.search(rf"^#+\s*{re.escape(name)}\s*$(.*?)(?=^#|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def steps(text):
    return [(m.group(1) == "x", m.group(2).strip())
            for m in (STEP.match(l) for l in text.splitlines()) if m]


def loops(status=None):
    for f in sorted(LOOPS.glob("*.md")) if LOOPS.exists() else []:
        text = f.read_text(encoding="utf-8")
        fm = frontmatter(text)
        if status and fm.get("status") != status:
            continue
        yield f, text, fm


def loop_file(name):
    f = LOOPS / f"{name}.md"
    if not f.exists():
        sys.exit(f"os: no loop '{name}' (bin/os loop new {name})")
    return f


def cmd_loop_status(_):
    rows = list(loops("open"))
    if not rows:
        print("(no open loops)")
        return
    for f, text, fm in rows:
        st = steps(text)
        done = sum(1 for d, _ in st if d)
        nxt = next((t for d, t in st if not d), None)
        print(f"* {f.stem}  [{done}/{len(st)}]  next: {nxt or 'ALL DONE — bin/os loop close ' + f.stem}")


def cmd_loop_next(args):
    if not args:
        sys.exit("usage: os loop next <name>")
    text = loop_file(args[0]).read_text(encoding="utf-8")
    st = steps(text)
    nxt = next(((i, t) for i, (d, t) in enumerate(st, 1) if not d), None)
    print(f"=== LOOP {args[0]} ===")
    print(f"\n# Goal\n{section(text, 'Goal')}")
    print(f"\n# Done when\n{section(text, 'Done when')}")
    notes = section(text, "Notes")
    if notes:
        print(f"\n# Notes so far\n{notes}")
    if not nxt:
        print(f"\n>>> every step ticked. Verify 'Done when', then: bin/os loop close {args[0]}")
        return
    i, t = nxt
    print(f"\n>>> NEXT STEP {i}: {t}")
    print(f">>> do only this step, append findings to # Notes, then:")
    print(f">>>   bin/os loop done {args[0]} {i} && bin/os save \"loop {args[0]} step {i}\"")


def cmd_loop_done(args):
    if len(args) < 2:
        sys.exit("usage: os loop done <name> <step-number>")
    f = loop_file(args[0])
    n = int(args[1])
    lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
    seen = 0
    for idx, line in enumerate(lines):
        if STEP.match(line):
            seen += 1
            if seen == n:
                lines[idx] = line.replace("- [ ]", "- [x]", 1)
                f.write_text("".join(lines), encoding="utf-8")
                print(f"ticked {args[0]} step {n}: {STEP.match(line).group(2)}")
                return
    sys.exit(f"os: loop '{args[0]}' has no step {n}")


def cmd_loop_close(args):
    if not args:
        sys.exit("usage: os loop close <name>")
    f = loop_file(args[0])
    text = f.read_text(encoding="utf-8")
    open_steps = [t for d, t in steps(text) if not d]
    if open_steps:
        print(f"warn: {len(open_steps)} step(s) still unchecked — closing anyway")
    f.write_text(re.sub(r"^status:.*$", "status: closed", text, count=1, flags=re.M), encoding="utf-8")
    print(f"closed {args[0]}")


def collect():
    def read(p):
        return p.read_text(encoding="utf-8") if p.exists() else ""
    notes = sorted((BRAIN / "notes").glob("*.md")) if (BRAIN / "notes").exists() else []
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%MZ"),
        "state": read(BRAIN / "STATE.md"),
        "lessons": read(BRAIN / "lessons.md"),
        "loops": [{"name": f.stem, "status": fm.get("status", "open"),
                   "steps": steps(t), "body": t} for f, t, fm in loops()],
        "journal": [{"name": f.stem, "body": f.read_text(encoding="utf-8")}
                    for f in sorted((BRAIN / "journal").glob("*.md"), reverse=True)[:14]],
        "notes": [{"name": f.stem, "body": f.read_text(encoding="utf-8"),
                   "links": sorted(set(WIKILINK.findall(f.read_text(encoding="utf-8"))))}
                  for f in notes],
        "decisions": [{"name": f.stem, "body": f.read_text(encoding="utf-8")}
                      for f in sorted((BRAIN / "decisions").glob("*.md"), reverse=True)],
    }


TEMPLATE = """<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentOS — second brain</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
:root{--bg:#0e1116;--panel:#161b22;--line:#272e38;--fg:#c9d3df;--dim:#7d8896;--acc:#4fd1c5}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.6 ui-sans-serif,-apple-system,Segoe UI,sans-serif}
header{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;gap:14px;
align-items:baseline;flex-wrap:wrap;position:sticky;top:0;background:var(--bg);z-index:2}
h1{font-size:17px;margin:0;letter-spacing:.06em}h1 b{color:var(--acc)}
.meta{color:var(--dim);font-size:12px}
nav{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
nav button{background:var(--panel);color:var(--fg);border:1px solid var(--line);
border-radius:6px;padding:5px 11px;font:inherit;font-size:13px;cursor:pointer}
nav button.on{border-color:var(--acc);color:var(--acc)}
main{max-width:1000px;margin:0 auto;padding:22px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:14px}
.card h3{margin:0 0 8px;font-size:14px;color:var(--acc);letter-spacing:.04em}
.bar{height:5px;background:#0b0e12;border-radius:3px;overflow:hidden;margin:8px 0}
.bar i{display:block;height:100%;background:var(--acc)}
pre{background:#0b0e12;padding:10px;border-radius:6px;overflow:auto}
code{background:#0b0e12;padding:1px 5px;border-radius:4px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid var(--line);padding:5px 8px;text-align:left}
a{color:var(--acc)}.wl{color:var(--acc);cursor:pointer;border-bottom:1px dotted}
.hide{display:none}.dim{color:var(--dim)}h1,h2{line-height:1.3}
details summary{cursor:pointer;color:var(--acc);font-size:14px}
input#q{background:#0b0e12;border:1px solid var(--line);color:var(--fg);border-radius:6px;
padding:5px 10px;font:inherit;font-size:13px}
</style>
<header>
  <h1>Agent<b>OS</b></h1>
  <span class="meta" id="meta"></span>
  <nav id="nav"></nav>
</header>
<main id="app"></main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const md = s => marked.parse((s||'').replace(/^---[\\s\\S]*?\\n---\\n/, '')
  .replace(/\\[\\[([^\\]|]+)\\]\\]/g, (_,n)=>`<span class="wl" data-go="${n}">${n}</span>`));
document.getElementById('meta').textContent =
  `generated ${D.generated} · ${D.notes.length} notes · ${D.decisions.length} decisions · ` +
  `${D.loops.filter(l=>l.status==='open').length} open loops`;

const views = {
  Overview(){
    const open = D.loops.filter(l=>l.status==='open');
    return card('WORKING MEMORY', md(D.state))
      + (open.length ? open.map(loopCard).join('') : card('LOOPS','<p class="dim">no open loops</p>'))
      + card('LESSONS', md(D.lessons))
      + (D.journal[0] ? card('LATEST JOURNAL — '+D.journal[0].name, md(D.journal[0].body)) : '');
  },
  Loops(){ return D.loops.length ? D.loops.map(loopCard).join('') : '<p class="dim">no loops</p>'; },
  Notes(){
    return `<div class="card"><input id="q" placeholder="filter notes…" size="30"></div>`
      + `<div id="notes">` + D.notes.map(n =>
        `<div class="card note" data-n="${n.name.toLowerCase()}" id="n-${cssid(n.name)}">
           <h3>${n.name}</h3>${md(n.body)}
           ${n.links.length?`<p class="dim">links: ${n.links.map(l=>`<span class="wl" data-go="${l}">${l}</span>`).join(', ')}</p>`:''}
         </div>`).join('') + `</div>`;
  },
  Decisions(){ return D.decisions.map(d=>card(d.name, md(d.body))).join('') || '<p class="dim">none</p>'; },
  Journal(){ return D.journal.map(j=>`<details class="card" open><summary>${j.name}</summary>${md(j.body)}</details>`).join('') || '<p class="dim">none</p>'; },
};
function card(t,b){ return `<div class="card"><h3>${t}</h3>${b}</div>`; }
function cssid(s){ return s.replace(/[^a-z0-9]/gi,'-').toLowerCase(); }
function loopCard(l){
  const done = l.steps.filter(s=>s[0]).length, pct = l.steps.length ? done/l.steps.length*100 : 0;
  return `<div class="card"><h3>LOOP · ${l.name} <span class="dim">${l.status} · ${done}/${l.steps.length}</span></h3>
    <div class="bar"><i style="width:${pct}%"></i></div>${md(l.body)}</div>`;
}
let cur = 'Overview';
function render(){
  document.getElementById('nav').innerHTML = Object.keys(views)
    .map(k=>`<button class="${k===cur?'on':''}" data-v="${k}">${k}</button>`).join('');
  document.getElementById('app').innerHTML = views[cur]();
}
document.addEventListener('click', e => {
  const v = e.target.dataset.v, go = e.target.dataset.go;
  if (v) { cur = v; render(); }
  if (go) { cur = 'Notes'; render();
    const el = document.getElementById('n-'+cssid(go));
    el ? el.scrollIntoView({behavior:'smooth'}) : alert('No note yet: '+go); }
});
document.addEventListener('input', e => {
  if (e.target.id !== 'q') return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('.note').forEach(n =>
    n.classList.toggle('hide', !n.dataset.n.includes(q)));
});
render();
</script>
"""


def cmd_dash(_):
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    payload = json.dumps(collect()).replace("</script>", "<\\/script>")
    out.write_text(TEMPLATE.replace("__DATA__", payload), encoding="utf-8")
    print(f"dashboard → docs/index.html ({out.stat().st_size // 1024} KB)")


def cmd_selftest(_):
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    for p in ["STATE.md", "lessons.md"]:
        check((BRAIN / p).exists(), f"missing brain/{p}")
    check((ROOT / ".kiro/steering/00-kernel.md").exists(), "missing kernel steering file")

    kernel = (ROOT / ".kiro/steering/00-kernel.md").read_text(encoding="utf-8")
    check(kernel.startswith("---\ninclusion: always"),
          "kernel must start with 'inclusion: always' frontmatter or it won't load every session")

    for skill in (ROOT / ".kiro/skills").glob("*/SKILL.md"):
        fm = frontmatter(skill.read_text(encoding="utf-8"))
        check(fm.get("name") == skill.parent.name,
              f"{skill}: frontmatter name '{fm.get('name')}' != folder '{skill.parent.name}'")
        check(0 < len(fm.get("description", "")) <= 1024, f"{skill}: description missing or >1024 chars")

    state_lines = len((BRAIN / "STATE.md").read_text(encoding="utf-8").splitlines())
    check(state_lines <= 80, f"brain/STATE.md is {state_lines} lines — prune it, it loads every boot")

    for f, text, fm in loops():
        check(fm.get("status") in ("open", "closed"), f"{f.name}: status must be open|closed")
        check(bool(steps(text)), f"{f.name}: no '- [ ]' steps — a loop without steps can't resume")

    names = {p.stem for p in (BRAIN / "notes").glob("*.md")} if (BRAIN / "notes").exists() else set()
    names |= {p.stem for p in (BRAIN / "decisions").glob("*.md")} if (BRAIN / "decisions").exists() else set()
    for p in list((BRAIN / "notes").glob("*.md")) + [BRAIN / "STATE.md"]:
        # strip fenced blocks and inline code first: notes legitimately discuss the
        # `[[wikilink]]` syntax itself, and that is not a broken link.
        prose = re.sub(r"`[^`]*`", "", re.sub(r"```.*?```", "", p.read_text(encoding="utf-8"), flags=re.S))
        for link in WIKILINK.findall(prose):
            check(link.strip() in names, f"{p.name}: broken wikilink [[{link.strip()}]]")

    print("\n".join(f"FAIL  {m}" for m in fails) if fails else "ok — vault well-formed")
    sys.exit(1 if fails else 0)


CMDS = {"loop-status": cmd_loop_status, "loop-next": cmd_loop_next, "loop-done": cmd_loop_done,
        "loop-close": cmd_loop_close, "dash": cmd_dash, "selftest": cmd_selftest}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        sys.exit(f"osutil: {sorted(CMDS)}")
    CMDS[sys.argv[1]](sys.argv[2:])
