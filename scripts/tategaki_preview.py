#!/usr/bin/env python3
"""Generate and open a vertical-writing (tategaki) HTML preview.

Usage:
    python3 tategaki_preview.py <source.txt> [chars_per_line] [line_spacing] [lines_per_page] [font_size_px] [margin_x_mm] [margin_y_mm]

Reads the source text, embeds it in a self-contained HTML file (vertical
writing, Kakuyomu ruby notation support, A4-landscape print layout),
writes it to the system temp directory, and opens it in the default browser.
The path of the generated file is printed to stdout.
"""

import json
import os
import sys
import tempfile
import webbrowser

TEMPLATE = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>縦書きプレビュー</title>
<style id="pagestyle"></style>
<style>
:root {
  --font-size: 16px;
  --spacing: 1.75;
  --chars: 40;
  --margin-x: 15mm;
  --margin-y: 15mm;
}
body {
  margin: 0;
  background: #e8e8e8;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif CJK JP", "Source Han Serif JP", serif;
}
#controls {
  position: fixed;
  top: 0; left: 0; right: 0;
  background: #fff;
  padding: 8px 14px;
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  box-shadow: 0 1px 4px rgba(0,0,0,.25);
  z-index: 10;
  font-family: system-ui, sans-serif;
  font-size: 13px;
}
#controls label { display: flex; gap: 5px; align-items: center; }
#controls input { width: 58px; padding: 2px 4px; }
#controls button { padding: 4px 14px; cursor: pointer; }
#warning { color: #b00; display: none; }
#stats { color: #555; }
#pages { padding: 76px 0 48px; }
.page {
  width: 297mm;
  height: 210mm;
  padding: var(--margin-y) var(--margin-x);
  background: #fff;
  margin: 0 auto 28px;
  box-shadow: 0 2px 10px rgba(0,0,0,.3);
  display: flex;
  flex-direction: row-reverse;
  align-items: center;
  justify-content: flex-start;
  box-sizing: border-box;
  position: relative;
}
.col {
  writing-mode: vertical-rl;
  text-orientation: upright;
  /* One extra cell leaves room for hanging punctuation (ぶら下げ). */
  height: calc((var(--chars) + 1) * 1em);
  width: calc(var(--font-size) * var(--spacing));
  font-size: var(--font-size);
  line-height: 1;
  overflow: hidden;
}
rt { font-size: .52em; line-height: 1; }
.bten { text-emphasis: sesame; }
.pnum {
  position: absolute;
  bottom: 3mm; left: 0; right: 0;
  text-align: center;
  font-size: 9px;
  color: #999;
  font-family: system-ui, sans-serif;
}
@media print {
  #controls { display: none; }
  body { background: #fff; }
  #pages { padding: 0; }
  /* Chrome enforces a minimum printable margin even when @page margin is 0; shave extra. */
  .page { margin: 0; box-shadow: none; page-break-after: always; overflow: hidden; padding: 0; height: calc(210mm - var(--margin-y) * 2 - 4mm); width: calc(297mm - var(--margin-x) * 2 - 4mm); }
  .page:last-child { page-break-after: avoid; }
}
/* @page margin is rewritten by JS; this is the initial value. */
@page { size: A4 landscape; margin: 15mm; }
</style>
</head>
<body>
<div id="controls">
  <strong id="filename"></strong>
  <span id="stats" title="空白・改行・ルビ（読み）・記法記号を除いた文字数"></span>
  <label>1行の文字数 <input id="in-chars" type="number" min="1"></label>
  <label>行間(文字サイズ比) <input id="in-spacing" type="number" step="0.05" min="1"></label>
  <label>1ページ行数 <input id="in-lines" type="number" min="1"></label>
  <label>文字サイズ(px) <input id="in-fontsize" type="number" min="8"></label>
  <label>余白左右(mm) <input id="in-margin-x" type="number" min="0"></label>
  <label>余白上下(mm) <input id="in-margin-y" type="number" min="0"></label>
  <button id="btn-pdf">PDF出力 (A4横)</button>
  <span id="warning">内容がページに収まりきらない可能性があります（文字サイズ/行数を調整してください）</span>
</div>
<div id="pages"></div>
<script>
const SOURCE = %%SOURCE_JSON%%;
const PARAMS = %%PARAMS_JSON%%;

// Kinsoku shori (Japanese line-breaking rules), after JIS X 4051.
// Characters that must not start a column.
const HEAD_NG = new Set("、。，．,.・：；？！?!‼⁇⁈⁉ー）」』】〕〉》］｝〙〗｠”’)]}ヽヾゝゞ々〻" +
                        "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ");
// Characters that must not end a column.
const TAIL_NG = new Set("（「『【〔〈《［｛〘〖｟“‘([{");
// Punctuation allowed to hang one cell past the column end (ぶら下げ).
const HANG = new Set("、。，．,.");
// Characters that must not be split when doubled (――, ……).
const INSEP = new Set("―…‥");

const firstCh = (a) => a.t === "ruby" ? a.base[0] : a.ch;
const lastCh = (a) => a.t === "ruby" ? a.base[a.base.length - 1] : a.ch;
const cellsOf = (a) => a.t === "ruby" ? a.base.length : 1;
function badBreak(before, after) {
  const b = lastCh(before), f = firstCh(after);
  return HEAD_NG.has(f) || TAIL_NG.has(b) || (b === f && INSEP.has(f));
}

// Parse Kakuyomu-style notation into atoms.
//  ｜base《ruby》        explicit ruby
//  base《ruby》         ruby over the preceding character run
//  《《text》》          emphasis dots (bouten)
//  \n                  column break (blank line = empty column)
const RE = /｜([^《》\n]+)《([^《》\n]+)》|《《(.+?)》》|([一-龯々〆ヵヶ]+)《(?!《)([^《》\n]+)》/g;

function parse(text) {
  const atoms = [];
  let last = 0;
  const pushChars = (s) => { for (const ch of s) atoms.push(ch === "\n" ? {t:"br"} : {t:"char", ch}); };
  let m;
  while ((m = RE.exec(text)) !== null) {
    pushChars(text.slice(last, m.index));
    if (m[1] !== undefined) atoms.push({t:"ruby", base:[...m[1]], rt:m[2]});
    else if (m[3] !== undefined) { for (const ch of m[3]) atoms.push(ch === "\n" ? {t:"br"} : {t:"bten", ch}); }
    else atoms.push({t:"ruby", base:[...m[4]], rt:m[5]});
    last = m.index + m[0].length;
  }
  pushChars(text.slice(last));
  return atoms;
}

function render() {
  const chars = Math.max(1, parseInt(document.getElementById("in-chars").value, 10) || 1);
  const spacing = Math.max(1, parseFloat(document.getElementById("in-spacing").value) || 1);
  const linesPerPage = Math.max(1, parseInt(document.getElementById("in-lines").value, 10) || 1);
  const fontSize = Math.max(8, parseInt(document.getElementById("in-fontsize").value, 10) || 8);
  const marginXmm = Math.max(0, parseInt(document.getElementById("in-margin-x").value, 10) || 0);
  const marginYmm = Math.max(0, parseInt(document.getElementById("in-margin-y").value, 10) || 0);
  // Chrome falls back to ~1in margins when @page margin is too small; clamp the effective margin.
  const effXmm = Math.max(marginXmm, 14);
  const effYmm = Math.max(marginYmm, 14);

  const root = document.documentElement;
  root.style.setProperty("--chars", chars);
  root.style.setProperty("--spacing", spacing);
  root.style.setProperty("--font-size", fontSize + "px");
  root.style.setProperty("--margin-x", effXmm + "mm");
  root.style.setProperty("--margin-y", effYmm + "mm");
  document.getElementById("pagestyle").textContent =
    `@page { size: A4 landscape; margin: ${effYmm}mm ${effXmm}mm; }`;

  // Columnize: a column holds at most `chars` cells; newline ends the column.
  const cols = [];
  let col = [];
  let cells = 0;
  const flush = () => { cols.push(col); col = []; cells = 0; };
  // Break the column before `next`. If that break violates kinsoku, push trailing
  // atoms out to the next column (追い出し) until the break point is legal.
  const breakBefore = (next) => {
    const carry = [];
    let carried = 0;
    while (col.length > 1 && badBreak(col[col.length - 1], carry[0] || next)) {
      const n = cellsOf(col[col.length - 1]);
      if (carried + n >= chars) break;
      carry.unshift(col.pop());
      carried += n;
    }
    // No legal break point nearby: keep the original break rather than a huge gap.
    if (col.length && badBreak(col[col.length - 1], carry[0] || next)) {
      col.push(...carry);
      carry.length = 0;
      carried = 0;
    }
    flush();
    col = carry;
    cells = carried;
  };
  for (const a of ATOMS) {
    if (a.t === "br") { flush(); continue; }
    if (a.t === "ruby" && a.base.length > chars) {
      // Split oversized ruby bases across columns; the reading stays on the first segment.
      let base = a.base, rt = a.rt;
      while (base.length) {
        if (cells >= chars) flush();
        const take = Math.min(chars - cells, base.length);
        col.push({t:"ruby", base: base.slice(0, take), rt});
        rt = "";
        cells += take; base = base.slice(take);
      }
      continue;
    }
    const n = cellsOf(a);
    if (cells + n > chars) {
      // Hang one punctuation mark past the column end instead of breaking.
      if (n === 1 && cells === chars && col.length && HANG.has(a.ch)) {
        col.push(a); cells++;
        continue;
      }
      // Short ruby words move to the next column whole instead of being split.
      breakBefore(a);
    }
    col.push(a); cells += n;
  }
  if (col.length || cols.length === 0) flush();

  const pagesEl = document.getElementById("pages");
  pagesEl.textContent = "";
  const totalPages = Math.ceil(cols.length / linesPerPage);
  document.getElementById("stats").textContent =
    `${CHAR_COUNT.toLocaleString()}字 / ${totalPages}ページ`;
  for (let p = 0; p < totalPages; p++) {
    const pageEl = document.createElement("div");
    pageEl.className = "page";
    for (const c of cols.slice(p * linesPerPage, (p + 1) * linesPerPage)) {
      const colEl = document.createElement("div");
      colEl.className = "col";
      for (const a of c) {
        if (a.t === "ruby") {
          const r = document.createElement("ruby");
          r.textContent = a.base.join("");
          const rt = document.createElement("rt");
          rt.textContent = a.rt;
          r.appendChild(rt);
          colEl.appendChild(r);
        } else {
          const s = document.createElement("span");
          if (a.t === "bten") s.className = "bten";
          s.textContent = a.ch;
          colEl.appendChild(s);
        }
      }
      pageEl.appendChild(colEl);
    }
    const num = document.createElement("div");
    num.className = "pnum";
    num.textContent = (p + 1) + " / " + totalPages;
    pageEl.appendChild(num);
    pagesEl.appendChild(pageEl);
  }

  // Warn if a column is taller than the printable page height.
  const pageHpx = (210 - effYmm * 2) * 3.7795;
  document.getElementById("warning").style.display =
    (chars + 1) * fontSize > pageHpx ? "inline" : "none";
}

const ATOMS = parse(SOURCE);
// Count visible characters: ruby bases count, readings/notation/whitespace do not.
let CHAR_COUNT = 0;
for (const a of ATOMS) {
  if (a.t === "ruby") CHAR_COUNT += a.base.length;
  else if (a.t !== "br" && !/\s/.test(a.ch)) CHAR_COUNT++;
}

const params = PARAMS;
const STORAGE_KEY = "tategaki-preview-settings";
let saved = {};
try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch (e) {}
document.getElementById("filename").textContent = params.name || "";
const fields = [["in-chars", "chars"], ["in-spacing", "spacing"],
                ["in-lines", "lines"], ["in-fontsize", "fontSize"],
                ["in-margin-x", "marginX"], ["in-margin-y", "marginY"]];
for (const [id, key] of fields) {
  const el = document.getElementById(id);
  // Fall back to the pre-split single "margin" value for stored settings.
  el.value = saved[key] !== undefined ? saved[key]
           : (saved.margin !== undefined ? saved.margin : params[key]);
  el.addEventListener("input", () => {
    const values = {};
    for (const [fid, fkey] of fields) {
      const v = parseFloat(document.getElementById(fid).value);
      if (isFinite(v)) values[fkey] = v;
    }
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(values)); } catch (e) {}
    render();
  });
}
document.getElementById("btn-pdf").addEventListener("click", () => window.print());
render();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: tategaki_preview.py <source> [chars] [spacing] [lines] [font_size] [margin_x] [margin_y]")
    src = sys.argv[1]
    chars = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    spacing = float(sys.argv[3]) if len(sys.argv) > 3 else 1.75
    lines = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    font_size = int(sys.argv[5]) if len(sys.argv) > 5 else 16
    margin_x_mm = int(sys.argv[6]) if len(sys.argv) > 6 else 15
    margin_y_mm = int(sys.argv[7]) if len(sys.argv) > 7 else margin_x_mm

    with open(src, encoding="utf-8") as f:
        text = f.read()

    params = {
        "name": os.path.basename(src),
        "chars": chars,
        "spacing": spacing,
        "lines": lines,
        "fontSize": font_size,
        "marginX": margin_x_mm,
        "marginY": margin_y_mm,
    }
    # Escape '<' so the serialized text can never close the inline <script>.
    source_json = json.dumps(text, ensure_ascii=False).replace("<", "\\u003c")
    # Replace PARAMS first: source text must never be scanned for placeholders.
    html = TEMPLATE.replace("%%PARAMS_JSON%%", json.dumps(params)).replace(
        "%%SOURCE_JSON%%", source_json
    )

    out_dir = os.path.join(tempfile.gettempdir(), "tategaki-preview")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(params["name"])[0]
    fd, out = tempfile.mkstemp(dir=out_dir, prefix=stem + "-", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)

    print(out)
    webbrowser.open("file://" + out)


if __name__ == "__main__":
    main()
