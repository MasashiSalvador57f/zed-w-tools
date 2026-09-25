#!/usr/bin/env python3
"""Generate and open a vertical-writing (tategaki) HTML preview.

Usage:
    python3 tategaki_preview.py <source.txt> [chars_per_line] [line_spacing] [lines_per_page] [font_size_px] [margin_mm]

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
  --margin: 15mm;
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
#pages { padding: 76px 0 48px; }
.page {
  width: calc(297mm - var(--margin) * 2);
  height: calc(210mm - var(--margin) * 2);
  background: #fff;
  margin: 0 auto 28px;
  box-shadow: 0 2px 10px rgba(0,0,0,.3);
  display: flex;
  flex-direction: row-reverse;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  position: relative;
}
.col {
  writing-mode: vertical-rl;
  text-orientation: upright;
  height: calc(var(--chars) * 1em);
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
  .page { margin: 0; box-shadow: none; page-break-after: always; overflow: hidden; height: calc(210mm - var(--margin) * 2 - 0.5mm); }
  .page:last-child { page-break-after: avoid; }
}
/* @page margin is rewritten by JS; this is the initial value. */
@page { size: A4 landscape; margin: 15mm; }
</style>
</head>
<body>
<div id="controls">
  <strong id="filename"></strong>
  <label>1行の文字数 <input id="in-chars" type="number" min="1"></label>
  <label>行間(文字サイズ比) <input id="in-spacing" type="number" step="0.05" min="1"></label>
  <label>1ページ行数 <input id="in-lines" type="number" min="1"></label>
  <label>文字サイズ(px) <input id="in-fontsize" type="number" min="8"></label>
  <label>余白(mm) <input id="in-margin" type="number" min="0"></label>
  <button id="btn-pdf">PDF出力 (A4横)</button>
  <span id="warning">内容がページに収まりきらない可能性があります（文字サイズ/行数を調整してください）</span>
</div>
<div id="pages"></div>
<script>
const SOURCE = %%SOURCE_JSON%%;
const PARAMS = %%PARAMS_JSON%%;

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
  const marginMm = Math.max(0, parseInt(document.getElementById("in-margin").value, 10) || 0);

  const root = document.documentElement;
  root.style.setProperty("--chars", chars);
  root.style.setProperty("--spacing", spacing);
  root.style.setProperty("--font-size", fontSize + "px");
  root.style.setProperty("--margin", marginMm + "mm");
  document.getElementById("pagestyle").textContent =
    `@page { size: A4 landscape; margin: ${marginMm}mm; }`;

  // Columnize: a column holds at most `chars` cells; newline ends the column.
  const atoms = parse(SOURCE);
  const cols = [];
  let col = [];
  let cells = 0;
  const flush = () => { cols.push(col); col = []; cells = 0; };
  for (const a of atoms) {
    if (a.t === "br") { flush(); continue; }
    if (a.t === "ruby") {
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
    if (cells >= chars) flush();
    col.push(a); cells++;
  }
  if (col.length || cols.length === 0) flush();

  const pagesEl = document.getElementById("pages");
  pagesEl.textContent = "";
  const totalPages = Math.ceil(cols.length / linesPerPage);
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
  const pageHpx = (210 - marginMm * 2) * 3.7795;
  document.getElementById("warning").style.display =
    chars * fontSize > pageHpx ? "inline" : "none";
}

const params = PARAMS;
document.getElementById("filename").textContent = params.name || "";
for (const [id, v] of [["in-chars", params.chars], ["in-spacing", params.spacing],
                       ["in-lines", params.lines], ["in-fontsize", params.fontSize],
                       ["in-margin", params.margin]]) {
  const el = document.getElementById(id);
  el.value = v;
  el.addEventListener("input", render);
}
document.getElementById("btn-pdf").addEventListener("click", () => window.print());
render();
</script>
</body>
</html>
"""


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: tategaki_preview.py <source> [chars] [spacing] [lines] [font_size]")
    src = sys.argv[1]
    chars = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    spacing = float(sys.argv[3]) if len(sys.argv) > 3 else 1.75
    lines = int(sys.argv[4]) if len(sys.argv) > 4 else 30
    font_size = int(sys.argv[5]) if len(sys.argv) > 5 else 16
    margin_mm = int(sys.argv[6]) if len(sys.argv) > 6 else 15

    with open(src, encoding="utf-8") as f:
        text = f.read()

    params = {
        "name": os.path.basename(src),
        "chars": chars,
        "spacing": spacing,
        "lines": lines,
        "fontSize": font_size,
        "margin": margin_mm,
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
