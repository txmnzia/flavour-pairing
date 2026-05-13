#!/usr/bin/env python3
"""
Ingredient curation tool — Tinder-style card swipe interface.
Usage: python pipeline/curate.py [--db PATH] [--port PORT]

  ← arrow / swipe left  →  Delete ingredient
  → arrow / swipe right →  Keep (validate) ingredient
  ↑ arrow / swipe up    →  Merge into another ingredient
"""
import argparse
import json
import os
import sqlite3
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

DEFAULT_DB = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'pairings.db')

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ingredient Curation</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*, *::before, *::after { box-sizing: border-box; }
body {
  margin: 0; background: #0d0d1a; color: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  height: 100dvh; display: flex; flex-direction: column; overflow: hidden;
  -webkit-tap-highlight-color: transparent;
}

/* Header */
#hdr {
  padding: 12px 20px; display: flex; justify-content: space-between;
  align-items: center; flex-shrink: 0;
}
#progress { font-size: 0.88rem; color: #94a3b8; font-weight: 500; }
#session  { font-size: 0.75rem; color: #475569; }

/* Progress bar */
#pbar { height: 2px; background: #1e293b; flex-shrink: 0; }
#pfill { height: 100%; background: #6366f1; transition: width 0.4s; width: 0%; }

/* Card stage */
#stage {
  flex: 1; display: flex; align-items: center; justify-content: center;
  position: relative; overflow: hidden;
}

/* Card */
#card {
  background: white; color: #1e293b; border-radius: 20px;
  width: min(340px, 86vw); padding: 40px 28px 32px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.55);
  position: relative; cursor: grab; select: none;
  will-change: transform;
}
#card:active { cursor: grabbing; }
#card.validated { border-top: 4px solid #22c55e; }

#cname { font-size: clamp(1.5rem, 6vw, 2.1rem); font-weight: 700;
         text-align: center; margin-bottom: 10px; line-height: 1.2;
         word-break: break-word; }
#cfreq { text-align: center; font-size: 0.82rem; color: #94a3b8; }
#cstatus { text-align: center; font-size: 0.72rem; color: #22c55e;
           font-weight: 600; margin-top: 4px; min-height: 16px; }

/* Direction hint labels on card */
.hint-lbl {
  position: absolute; font-size: 1rem; font-weight: 800;
  letter-spacing: 0.08em; padding: 5px 12px; border-radius: 6px;
  border: 3px solid; opacity: 0; pointer-events: none;
}
#lbl-del  { top: 18px; right: 16px; color: #ef4444; border-color: #ef4444;
            transform: rotate(12deg); }
#lbl-keep { top: 18px; left:  16px; color: #22c55e; border-color: #22c55e;
            transform: rotate(-12deg); }
#lbl-mrg  { bottom: 18px; left: 50%; transform: translateX(-50%);
            color: #60a5fa; border-color: #60a5fa; }

/* Action buttons */
#actions {
  display: flex; justify-content: center; align-items: center;
  gap: 22px; padding: 18px 20px; flex-shrink: 0;
}
.abtn {
  border: none; border-radius: 50%; cursor: pointer; display: flex;
  align-items: center; justify-content: center;
  box-shadow: 0 4px 18px rgba(0,0,0,0.4);
  transition: transform 0.12s, box-shadow 0.12s;
  font-size: 1.4rem; flex-shrink: 0;
}
.abtn:hover  { transform: scale(1.1); box-shadow: 0 6px 24px rgba(0,0,0,0.5); }
.abtn:active { transform: scale(0.92); }
#btn-del { width: 62px; height: 62px; background: #ef4444; }
#btn-mrg { width: 50px; height: 50px; background: #3b82f6; font-size: 1.1rem; }
#btn-kep { width: 62px; height: 62px; background: #22c55e; }

#kbhint {
  text-align: center; font-size: 0.7rem; color: #1e293b;
  padding-bottom: 14px; flex-shrink: 0; letter-spacing: 0.03em;
}

/* Done screen */
#done {
  display: none; flex: 1; flex-direction: column;
  align-items: center; justify-content: center; text-align: center; padding: 24px;
}
#done h2 { font-size: 2rem; margin: 12px 0 8px; }
#done p  { color: #64748b; line-height: 1.9; margin-bottom: 28px; }
#done b  { color: #e2e8f0; }
#restart {
  padding: 10px 28px; border: none; border-radius: 8px; cursor: pointer;
  background: #6366f1; color: white; font-size: 0.9rem; font-weight: 600;
}

/* Merge overlay */
#overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.75); z-index: 50;
  align-items: center; justify-content: center;
}
#overlay.open { display: flex; }
#modal {
  background: #1e293b; border-radius: 18px; padding: 24px;
  width: min(420px, 92vw); box-shadow: 0 24px 64px rgba(0,0,0,0.6);
}
#modal h3 { margin: 0 0 16px; font-size: 1rem; font-weight: 600; color: #e2e8f0; }
#modal h3 span { color: #60a5fa; }
#msearch {
  width: 100%; padding: 10px 14px; background: #0f172a; color: #e2e8f0;
  border: 1px solid #334155; border-radius: 8px; font-size: 0.88rem; outline: none;
}
#msearch:focus { border-color: #6366f1; box-shadow: 0 0 0 2px rgba(99,102,241,0.2); }
#mresults { margin-top: 6px; max-height: 230px; overflow-y: auto; }
.mitem {
  padding: 9px 14px; border-radius: 6px; cursor: pointer;
  font-size: 0.85rem; color: #cbd5e1;
}
.mitem:hover, .mitem.hi { background: #334155; color: white; }
#mcancel {
  display: block; text-align: center; margin-top: 14px;
  font-size: 0.78rem; color: #475569; cursor: pointer;
}
#mcancel:hover { color: #94a3b8; }
</style>
</head>
<body>

<div id="hdr">
  <span id="progress">Loading…</span>
  <span id="session"></span>
</div>
<div id="pbar"><div id="pfill"></div></div>

<div id="stage">
  <div id="card">
    <span class="hint-lbl" id="lbl-del">DELETE</span>
    <span class="hint-lbl" id="lbl-keep">KEEP</span>
    <span class="hint-lbl" id="lbl-mrg">MERGE</span>
    <div id="cname"></div>
    <div id="cfreq"></div>
    <div id="cstatus"></div>
  </div>
</div>

<div id="done">
  <div style="font-size:3rem">✓</div>
  <h2>All done!</h2>
  <p id="done-stats"></p>
  <button id="restart" onclick="restart()">Start over</button>
</div>

<div id="actions">
  <button class="abtn" id="btn-del" title="Delete  ←" onclick="go('left')">✕</button>
  <button class="abtn" id="btn-mrg" title="Merge   ↑" onclick="go('up')">↑</button>
  <button class="abtn" id="btn-kep" title="Keep    →" onclick="go('right')">♥</button>
</div>
<div id="kbhint">← delete &nbsp;·&nbsp; ↑ merge &nbsp;·&nbsp; → keep</div>

<!-- Merge overlay -->
<div id="overlay">
  <div id="modal">
    <h3>Merge <span id="mfrom"></span> into…</h3>
    <input id="msearch" placeholder="Type ingredient name…" autocomplete="off"
           oninput="filterM()" onkeydown="keyM(event)">
    <div id="mresults"></div>
    <span id="mcancel" onclick="closeM()">Cancel (Esc)</span>
  </div>
</div>

<script>
let queue = [];   // ingredients still to review
let idx   = 0;
let busy  = false;
let stats = { kept: 0, deleted: 0, merged: 0 };

// merge overlay state
let mhits = [];
let msel  = -1;

// ── Bootstrap ──────────────────────────────────────────────────────────────
async function load() {
  const r = await fetch('/api/ingredients');
  queue = await r.json();
  idx   = 0;
  stats = { kept: 0, deleted: 0, merged: 0 };
  showCard();
}

function restart() { load(); }

// ── Card display ───────────────────────────────────────────────────────────
function showCard() {
  busy = false;
  setLabels(0, 0, 0);

  if (idx >= queue.length) {
    document.getElementById('stage').style.display   = 'none';
    document.getElementById('actions').style.display = 'none';
    document.getElementById('kbhint').style.display  = 'none';
    document.getElementById('done').style.display    = 'flex';
    document.getElementById('done-stats').innerHTML  =
      '<b>' + stats.kept    + '</b> kept &nbsp;·&nbsp; ' +
      '<b>' + stats.deleted + '</b> deleted &nbsp;·&nbsp; ' +
      '<b>' + stats.merged  + '</b> merged';
    document.getElementById('progress').textContent = 'Complete!';
    document.getElementById('pfill').style.width = '100%';
    return;
  }

  document.getElementById('stage').style.display   = 'flex';
  document.getElementById('actions').style.display = 'flex';
  document.getElementById('kbhint').style.display  = 'block';
  document.getElementById('done').style.display    = 'none';

  const item = queue[idx];
  const card = document.getElementById('card');
  card.style.transition = 'none';
  card.style.transform  = '';
  card.style.opacity    = '1';
  card.className        = item.validated ? 'validated' : '';

  document.getElementById('cname').textContent   = item.name;
  document.getElementById('cfreq').textContent   = item.freq.toLocaleString() + ' recipes';
  document.getElementById('cstatus').textContent = item.validated ? '✓ previously validated' : '';

  const total = queue.length + stats.kept + stats.deleted + stats.merged;
  const done  = stats.kept + stats.deleted + stats.merged;
  document.getElementById('progress').textContent = (done + 1) + ' / ' + total;
  document.getElementById('pfill').style.width   = (done / total * 100) + '%';
  const parts = [];
  if (stats.kept)    parts.push(stats.kept    + ' kept');
  if (stats.deleted) parts.push(stats.deleted + ' deleted');
  if (stats.merged)  parts.push(stats.merged  + ' merged');
  document.getElementById('session').textContent = parts.join(' · ');
}

// ── Direction trigger (keyboard / button) ──────────────────────────────────
function go(dir) {
  if (busy || idx >= queue.length) return;
  if (dir === 'up') { openM(); return; }
  busy = true;
  setLabels(dir === 'left' ? 1 : 0, dir === 'right' ? 1 : 0, 0);
  flyOut(dir, dir === 'left' ? doDelete : doKeep);
}

// ── Fly-out animation ──────────────────────────────────────────────────────
function flyOut(dir, cb) {
  const card = document.getElementById('card');
  card.style.transition = 'transform 0.34s ease, opacity 0.34s ease';
  if (dir === 'left')  card.style.transform = 'translateX(-130vw) rotate(-28deg)';
  if (dir === 'right') card.style.transform = 'translateX(130vw)  rotate(28deg)';
  if (dir === 'up')    card.style.transform = 'translateY(-110vh)';
  card.style.opacity = '0';
  setTimeout(cb, 350);
}

// ── Actions ────────────────────────────────────────────────────────────────
async function doDelete() {
  const item = queue[idx];
  await fetch('/api/delete/' + item.id, { method: 'POST' });
  stats.deleted++;
  queue.splice(idx, 1);   // remove; idx now points to next card
  showCard();
}

async function doKeep() {
  const item = queue[idx];
  if (!item.validated) {
    await fetch('/api/validate/' + item.id, { method: 'POST' });
    item.validated = 1;
  }
  stats.kept++;
  idx++;
  showCard();
}

// ── Merge overlay ──────────────────────────────────────────────────────────
function openM() {
  const item = queue[idx];
  document.getElementById('mfrom').textContent   = '"' + item.name + '"';
  document.getElementById('msearch').value       = '';
  document.getElementById('mresults').innerHTML  = '';
  mhits = []; msel = -1;
  document.getElementById('overlay').classList.add('open');
  setTimeout(() => document.getElementById('msearch').focus(), 40);
}

function closeM() {
  document.getElementById('overlay').classList.remove('open');
  busy = false;
}

function filterM() {
  const q = document.getElementById('msearch').value.toLowerCase().trim();
  const fromId = queue[idx].id;
  msel = -1;
  if (!q) { document.getElementById('mresults').innerHTML = ''; mhits = []; return; }
  mhits = queue.filter((x, i) => i !== idx && x.name.toLowerCase().includes(q)).slice(0, 12);
  document.getElementById('mresults').innerHTML = mhits.map((m, i) =>
    '<div class="mitem" data-i="' + i + '" onclick="pickM(' + i + ')">' + esc(m.name) + '</div>'
  ).join('');
}

function keyM(e) {
  const items = document.getElementById('mresults').querySelectorAll('.mitem');
  if (e.key === 'Escape') { closeM(); return; }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    msel = Math.min(msel + 1, items.length - 1);
    items.forEach((el, i) => el.classList.toggle('hi', i === msel));
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    msel = Math.max(msel - 1, 0);
    items.forEach((el, i) => el.classList.toggle('hi', i === msel));
  } else if (e.key === 'Enter' && msel >= 0) {
    pickM(msel);
  }
}

async function pickM(hitIdx) {
  const from = queue[idx];
  const into = mhits[hitIdx];
  if (!into) return;
  closeM();
  busy = true;
  setLabels(0, 0, 1);
  flyOut('up', async () => {
    await fetch('/api/merge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_id: from.id, into_id: into.id })
    });
    stats.merged++;
    queue.splice(idx, 1);
    showCard();
  });
}

// ── Hint labels ────────────────────────────────────────────────────────────
function setLabels(del, keep, mrg) {
  document.getElementById('lbl-del').style.opacity  = del;
  document.getElementById('lbl-keep').style.opacity = keep;
  document.getElementById('lbl-mrg').style.opacity  = mrg;
}

// ── Keyboard ───────────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (document.getElementById('overlay').classList.contains('open')) return;
  if (e.key === 'ArrowLeft')  { e.preventDefault(); go('left');  }
  if (e.key === 'ArrowRight') { e.preventDefault(); go('right'); }
  if (e.key === 'ArrowUp')    { e.preventDefault(); go('up');    }
});

// ── Drag / swipe ───────────────────────────────────────────────────────────
let ox, oy, dragging = false;
const card = document.getElementById('card');

function startDrag(cx, cy) {
  if (busy || idx >= queue.length) return;
  ox = cx; oy = cy; dragging = true;
}
function moveDrag(cx, cy) {
  if (!dragging) return;
  const dx = cx - ox, dy = cy - oy;
  card.style.transition = 'none';
  card.style.transform  = 'translate(' + dx + 'px,' + dy + 'px) rotate(' + dx * 0.07 + 'deg)';
  const th = 60;
  const dr = Math.min(Math.max(-dx, 0) / th, 1);
  const kr = Math.min(Math.max( dx, 0) / th, 1);
  const mr = Math.min(Math.max(-dy, 0) / th, 1);
  setLabels(dr, kr, mr);
}
function endDrag(cx, cy) {
  if (!dragging) return;
  dragging = false;
  const dx = cx - ox, dy = cy - oy, th = 80;
  if      (dx < -th) go('left');
  else if (dx >  th) go('right');
  else if (dy < -th) go('up');
  else {
    card.style.transition = 'transform 0.28s ease';
    card.style.transform  = '';
    setLabels(0, 0, 0);
  }
}

card.addEventListener('mousedown',  e => startDrag(e.clientX, e.clientY));
document.addEventListener('mousemove', e => { if (dragging) moveDrag(e.clientX, e.clientY); });
document.addEventListener('mouseup',   e => endDrag(e.clientX, e.clientY));

card.addEventListener('touchstart', e => startDrag(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
card.addEventListener('touchmove',  e => { if (dragging) moveDrag(e.touches[0].clientX, e.touches[0].clientY); }, { passive: true });
card.addEventListener('touchend',   e => endDrag(e.changedTouches[0].clientX, e.changedTouches[0].clientY));

// Backdrop click closes merge overlay
document.getElementById('overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('overlay')) closeM();
});

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

load();
</script>
</body>
</html>
"""


def open_db(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "ALTER TABLE ingredients ADD COLUMN validated INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Column already exists
    return conn


class Handler(BaseHTTPRequestHandler):
    db_path = None

    def log_message(self, fmt, *args):
        print(" ", args[0], args[1])

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/ingredients":
            conn = open_db(self.db_path)
            rows = conn.execute(
                "SELECT id, name, freq, COALESCE(validated, 0) AS validated "
                "FROM ingredients ORDER BY name"
            ).fetchall()
            conn.close()
            self.send_json([dict(r) for r in rows])
        else:
            self.send_error(404)

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        conn = open_db(self.db_path)
        try:
            if parts[:2] == ["api", "validate"] and len(parts) == 3:
                iid = int(parts[2])
                row = conn.execute(
                    "SELECT COALESCE(validated,0) AS v FROM ingredients WHERE id=?", (iid,)
                ).fetchone()
                new_val = 0 if (row and row["v"]) else 1
                conn.execute(
                    "UPDATE ingredients SET validated=? WHERE id=?", (new_val, iid)
                )
                conn.commit()
                self.send_json({"ok": True, "validated": new_val})

            elif parts[:2] == ["api", "delete"] and len(parts) == 3:
                iid = int(parts[2])
                conn.execute(
                    "DELETE FROM pairings WHERE ingredient_a=? OR ingredient_b=?",
                    (iid, iid),
                )
                conn.execute("DELETE FROM ingredients WHERE id=?", (iid,))
                conn.commit()
                self.send_json({"ok": True})

            elif parts == ["api", "merge"]:
                body = self.read_body()
                from_id = int(body["from_id"])
                into_id = int(body["into_id"])
                if from_id == into_id:
                    self.send_json({"error": "Cannot merge with itself"}, 400)
                    return
                # Transfer pairings where from_id is side A
                conn.execute(
                    """INSERT OR IGNORE INTO pairings
                         (ingredient_a, ingredient_b, cuisine_id, npmi, cooccurrence)
                       SELECT ?, ingredient_b, cuisine_id, npmi, cooccurrence
                       FROM pairings
                       WHERE ingredient_a=? AND ingredient_b!=?""",
                    (into_id, from_id, into_id),
                )
                # Transfer pairings where from_id is side B
                conn.execute(
                    """INSERT OR IGNORE INTO pairings
                         (ingredient_a, ingredient_b, cuisine_id, npmi, cooccurrence)
                       SELECT ingredient_a, ?, cuisine_id, npmi, cooccurrence
                       FROM pairings
                       WHERE ingredient_b=? AND ingredient_a!=?""",
                    (into_id, from_id, into_id),
                )
                # Remove from_id entirely
                conn.execute(
                    "DELETE FROM pairings WHERE ingredient_a=? OR ingredient_b=?",
                    (from_id, from_id),
                )
                conn.execute("DELETE FROM ingredients WHERE id=?", (from_id,))
                conn.commit()
                self.send_json({"ok": True})

            else:
                self.send_error(404)

        except Exception as exc:
            conn.rollback()
            self.send_json({"error": str(exc)}, 500)
        finally:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Ingredient curation server")
    parser.add_argument("--db",   default=DEFAULT_DB, help="Path to pairings.db")
    parser.add_argument("--port", type=int, default=8765, help="HTTP port (default 8765)")
    args = parser.parse_args()

    db_path = os.path.abspath(args.db)
    if not os.path.exists(db_path):
        print(f"Error: database not found at {db_path}")
        print("Generate it first: python pipeline/generate_demo.py")
        raise SystemExit(1)

    Handler.db_path = db_path

    server = HTTPServer(("localhost", args.port), Handler)
    url = f"http://localhost:{args.port}"
    print(f"Curation server → {url}")
    print(f"Database        → {db_path}")
    print("Press Ctrl+C to stop.")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
