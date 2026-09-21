"""Render the recovered HBP catalog to PDF (HTML -> headless Chrome).

    python catalog/build_hbp_pdf.py            # -> docs/hbp-catalog.pdf

Source is catalog/hbp_from_wayback.json (see scrapers/wayback_hbp.py) plus the
German->English/taxonomy gloss in catalog/hbp_map.py. Photos come from
catalog/hbp_images/ — only 38 of 199 survive in the archive, so most rows show a
placeholder rather than a picture.

Chrome exits 0 even when it fails to write the PDF (e.g. the file is open in a
viewer), so the output mtime is checked explicitly.
"""
from __future__ import annotations

import collections
import html
import json
import shutil
import struct
import subprocess
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hbp_map import classify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "catalog" / "hbp_from_wayback.json"
IMG = ROOT / "catalog" / "hbp_images"
OUT_HTML = ROOT / "docs" / "hbp-catalog.html"
OUT_PDF = ROOT / "docs" / "hbp-catalog.pdf"

e = html.escape
LINE_ORDER = ["StandardLine", "Avantgarde", "ExclusiveLine", "FitnessLine",
              "DynamicLineDS", "DynamicLineDG", "ActiveLine"]

# The archive only ever captured two sizes: ~256px "full" images and ~102px "_kl"
# thumbnails. Printing either past its native resolution just prints blur, so the
# gallery shows the 256px ones large and keeps the 102px survivors in a small strip.
FULL_MIN_PX = 200


def jpeg_size(b: bytes) -> tuple[int, int] | None:
    """Width/height straight from the JPEG header (no Pillow dependency)."""
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        if m in (0xD8, 0xD9, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None
LINE_NOTE = {
    "StandardLine": "the core selectorized range — the bulk of the catalog",
    "Avantgarde": "the premium range, still resold today as complete gym fit-outs",
    "ExclusiveLine": "heavier-framed selectorized machines",
    "FitnessLine": "lighter studio range",
    "DynamicLineDS": "dual-station units",
    "DynamicLineDG": "dual-station units, larger frames",
    "ActiveLine": "hydraulic circuit stations — the only line with English/French names on the plate",
}


def spec_bits(r: dict) -> str:
    out = []
    if d := r.get("dims_mm"):
        out.append(f"{d['l']}×{d['w']}×{d['h']} mm")
    if v := r.get("total_kg"):
        out.append(f"{v:g} kg total")
    if v := r.get("stack_kg"):
        out.append(f"<b>{v:g} kg stack</b>")
    if v := r.get("price_eur"):
        out.append(f"€{v:,.0f}".replace(",", " "))
    return " · ".join(out)


def row(r: dict) -> str:
    img = r.get("image") or ""
    have = img and (IMG / img).exists()
    thumb = (f'<img src="{(IMG / img).resolve().as_uri()}">' if have
             else '<span class="nopic">no photo<br>archived</span>')
    gloss = f'<div class="gloss">{e(r["english"])}</div>' if r.get("english") else ""
    trans = (f'<div class="trans">plate reads: {e(r["translation"])}</div>'
             if r.get("translation") else "")
    mus = e(r["muscle"]) if r.get("muscle") else "—"
    if r.get("secondary"):
        mus += f'<span class="sec">+ {e(", ".join(r["secondary"]))}</span>'
    return (
        f'<tr><td class="thumb">{thumb}</td>'
        f'<td class="art">{e(r.get("article") or "—")}</td>'
        f'<td class="model"><div class="de">{e(r["name"])}</div>{gloss}{trans}</td>'
        f'<td class="mech">{e(r["mechanism"] or "—")}</td>'
        f'<td class="reg"><span class="r">{e(r["region"])}</span></td>'
        f'<td class="mus">{mus}</td>'
        f'<td class="spec">{spec_bits(r)}</td></tr>')


HEAD = ("<th></th><th>art. no</th><th>machine</th><th>mechanism</th>"
        "<th>region</th><th>muscle</th><th>specifications</th>")

CSS = """
@page { size:A4; margin:13mm 11mm 15mm; } @page :first { margin:0; }
* { box-sizing:border-box; }
body { font:8.6pt/1.42 "Inter","Segoe UI",system-ui,sans-serif; color:#16181d; margin:0;
       -webkit-print-color-adjust:exact; print-color-adjust:exact; }
h1,h2 { margin:0; font-weight:650; letter-spacing:-.02em; }
.cover { height:297mm; padding:26mm 24mm; display:flex; flex-direction:column;
         background:#0d0f13; color:#f4f5f7; break-after:page; }
.cover .mark { font-size:54pt; font-weight:750; letter-spacing:-.045em; color:#fff; line-height:1; }
.cover .dot { color:#d7ff3e; }
.cover .kicker { margin-top:9mm; font-size:8pt; letter-spacing:.16em; text-transform:uppercase; color:#d7ff3e; }
.cover h1 { font-size:27pt; font-weight:700; margin-top:2mm; letter-spacing:-.035em; }
.cover .sub { margin-top:5mm; font-size:12pt; font-weight:350; color:#9aa1ad; max-width:128mm; line-height:1.55; }
.cover .spacer { flex:1; }
.cover .stats { display:flex; gap:11mm; border-top:1px solid #2a2f39; padding-top:7mm; flex-wrap:wrap; }
.cover .stat b { display:block; font-size:24pt; font-weight:700; color:#d7ff3e; letter-spacing:-.03em; }
.cover .stat span { font-size:8pt; color:#8b93a1; }
.sec-head { margin:0 0 3mm; padding-bottom:2mm; border-bottom:2px solid #16181d;
            display:flex; align-items:baseline; gap:4mm; break-after:avoid; }
.sec-head h2 { font-size:15pt; letter-spacing:-.03em; }
.sec-head .n { font-size:8pt; color:#6b7280; }
.sec-head .note { font-size:8pt; color:#6b7280; font-style:italic; margin-left:auto; }
section { break-before:page; }
section:first-of-type { break-before:auto; }
table { width:100%; border-collapse:collapse; }
th { text-align:left; font-size:6.6pt; text-transform:uppercase; letter-spacing:.09em;
     color:#8b93a1; font-weight:600; padding:0 4px 1.5mm; border-bottom:1px solid #d7dae0; }
td { padding:1.6mm 4px; border-bottom:1px solid #eceef1; vertical-align:top; }
tr { break-inside:avoid; }
.thumb { width:30mm; }
.thumb img { width:28mm; height:28mm; object-fit:contain; background:#f4f5f7; border-radius:2px; }
.nopic { display:flex; align-items:center; justify-content:center; width:28mm; height:11mm;
         background:#f7f8fa; border:1px dashed #d7dae0; border-radius:2px; color:#b6bcc6;
         font-size:5.4pt; text-align:center; line-height:1.25; }
/* gallery — the 38 machines whose photography survived */
.gal { display:flex; flex-wrap:wrap; gap:5mm; }
.gal figure { width:54mm; margin:0; break-inside:avoid; }
.gal img { width:54mm; height:54mm; object-fit:contain; background:#f4f5f7; border-radius:3px; }
.gal figcaption { margin-top:1.5mm; font-size:7.2pt; line-height:1.35; }
.gal .a { font-family:"SF Mono",Consolas,monospace; color:#8b93a1; font-size:6.6pt; }
.gal .n { font-weight:600; }
.gal .g { color:#6b7280; }
.galsm { display:flex; flex-wrap:wrap; gap:4mm; margin-top:4mm; }
.galsm figure { width:26mm; margin:0; break-inside:avoid; }
.galsm img { width:26mm; height:26mm; object-fit:contain; background:#f4f5f7; border-radius:3px; }
.galsm figcaption { margin-top:1mm; font-size:6.2pt; line-height:1.3; color:#6b7280; }
.subhead { margin:7mm 0 3mm; font-size:7pt; text-transform:uppercase; letter-spacing:.1em; color:#8b93a1; }
.art { width:14mm; font-family:"SF Mono",Consolas,monospace; font-size:7.6pt; color:#6b7280; white-space:nowrap; }
.model { width:52mm; }
.model .de { font-weight:600; }
.model .gloss { color:#4b5563; font-size:7.8pt; }
.model .trans { color:#9aa1ad; font-size:6.8pt; font-style:italic; }
.mech { width:26mm; font-size:7.8pt; }
.reg { width:19mm; }
.r { display:inline-block; padding:.6mm 1.6mm; border-radius:2px; background:#eef1f5;
     font-size:6.8pt; letter-spacing:.02em; }
.mus { width:26mm; font-size:7.8pt; }
.sec { display:block; color:#9aa1ad; font-size:6.8pt; }
.spec { font-size:7.4pt; color:#4b5563; }
.intro { margin-bottom:6mm; font-size:9pt; color:#4b5563; max-width:150mm; line-height:1.6; }
.grid { display:flex; gap:8mm; margin-bottom:7mm; flex-wrap:wrap; }
.card { flex:1; min-width:60mm; }
.card h3 { margin:0 0 2mm; font-size:7pt; text-transform:uppercase; letter-spacing:.1em; color:#8b93a1; }
.bar { display:flex; align-items:center; gap:2mm; margin-bottom:1mm; font-size:7.6pt; }
.bar .lbl { width:30mm; color:#374151; }
.bar .fill { height:3mm; background:#16181d; border-radius:1px; }
.bar .v { color:#8b93a1; font-size:7pt; }
"""


def bars(counts, total, width_mm=34):
    out = []
    top = max(counts.values()) if counts else 1
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        out.append(f'<div class="bar"><span class="lbl">{e(str(k))}</span>'
                   f'<span class="fill" style="width:{v / top * width_mm:.1f}mm"></span>'
                   f'<span class="v">{v}</span></div>')
    return "".join(out)


def main() -> None:
    recs = json.loads(SRC.read_text(encoding="utf-8"))
    for r in recs:
        r.update(classify(r["name"]))

    by_line = collections.defaultdict(list)
    for r in recs:
        by_line[r["line"]].append(r)
    for v in by_line.values():
        v.sort(key=lambda r: (r["region"], r["name"]))

    photos = sum(1 for r in recs if r.get("image") and (IMG / r["image"]).exists())
    priced = [r["price_eur"] for r in recs if r.get("price_eur")]
    stacks = [r["stack_kg"] for r in recs if r.get("stack_kg")]

    cover = f"""
    <div class="cover">
      <div class="mark">hbp<span class="dot">.</span></div>
      <div class="kicker">recovered catalog · hefele borenski gmbh</div>
      <h1>the complete HBP equipment range</h1>
      <div class="sub">Health Beauty Power, Grenzach-Wyhlen. {len(recs)} machines across
        {len(by_line)} product lines, reconstructed from the Internet Archive after the
        manufacturer's website went offline. No brochure survives — this is rebuilt from
        the archived product database itself.</div>
      <div class="spacer"></div>
      <div class="stats">
        <div class="stat"><b>{len(recs)}</b><span>machines</span></div>
        <div class="stat"><b>{len(by_line)}</b><span>product lines</span></div>
        <div class="stat"><b>{photos}</b><span>photos recovered</span></div>
        <div class="stat"><b>{len(recs) - photos}</b><span>photos lost</span></div>
        <div class="stat"><b>0</b><span>brochures archived</span></div>
      </div>
    </div>"""

    overview = f"""
    <section style="break-before:auto">
      <div class="sec-head"><h2>overview</h2><span class="n">{len(recs)} machines</span></div>
      <div class="intro">
        Every record carries an article number, the German machine name and full dimensions.
        Stack weights are on {len(stacks)} of {len(recs)}; {len(priced)} still carry their
        original price{f' (median €{sorted(priced)[len(priced) // 2]:,.0f})'.replace(",", " ") if priced else ''},
        in euros, from the 2003–2007 snapshot. Mechanism, region and muscle are mapped from
        the German names — see <i>catalog/hbp_map.py</i> — not stated by the manufacturer.
      </div>
      <div class="grid">
        <div class="card"><h3>by product line</h3>
          {bars({k: len(v) for k, v in by_line.items()}, len(recs))}</div>
        <div class="card"><h3>by body region</h3>
          {bars(collections.Counter(r["region"] for r in recs), len(recs))}</div>
      </div>
      <div class="grid">
        <div class="card"><h3>by mechanism (top 12)</h3>
          {bars(dict(collections.Counter(r["mechanism"] or "—" for r in recs).most_common(12)), len(recs))}</div>
      </div>
    </section>"""

    # ---- gallery: split by what each source image can actually carry ----
    shot = [r for r in recs if r.get("image") and (IMG / r["image"]).exists()]
    for r in shot:
        r["_px"] = jpeg_size((IMG / r["image"]).read_bytes()) or (0, 0)
    big = [r for r in shot if r["_px"][0] >= FULL_MIN_PX]
    small = [r for r in shot if r["_px"][0] < FULL_MIN_PX]

    def fig(r: dict, cls: str = "") -> str:
        uri = (IMG / r["image"]).resolve().as_uri()
        gloss = f'<div class="g">{e(r["english"])}</div>' if r.get("english") else ""
        return (f'<figure><img src="{uri}">'
                f'<figcaption><span class="a">{e(r.get("article") or "")}</span> '
                f'<span class="n">{e(r["name"])}</span>{gloss}</figcaption></figure>')

    gallery = f"""
    <section>
      <div class="sec-head"><h2>surviving photography</h2>
        <span class="n">{len(shot)} of {len(recs)} machines</span>
        <span class="note">everything else was never captured before the site went down</span></div>
      <div class="intro">
        The archive holds two sizes and no more: {len(big)} machines at 256&nbsp;px and
        {len(small)} that survive only as 102&nbsp;px thumbnails. These are printed at the
        largest size each still holds — pushing them further would only enlarge the blur.
      </div>
      <div class="gal">{"".join(fig(r) for r in big)}</div>
      <div class="subhead">thumbnail-only survivals — no full-size capture exists</div>
      <div class="galsm">{"".join(fig(r) for r in small)}</div>
    </section>"""

    sections = []
    for line in LINE_ORDER + [k for k in by_line if k not in LINE_ORDER]:
        rows = by_line.get(line)
        if not rows:
            continue
        sections.append(
            f'<section><div class="sec-head"><h2>{e(line)}</h2>'
            f'<span class="n">{len(rows)} machines</span>'
            f'<span class="note">{e(LINE_NOTE.get(line, ""))}</span></div>'
            f'<table><thead><tr>{HEAD}</tr></thead><tbody>'
            + "".join(row(r) for r in rows) + "</tbody></table></section>")

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(f"<!doctype html><meta charset='utf-8'><style>{CSS}</style>"
                        + cover + overview + gallery + "".join(sections), encoding="utf-8")

    chrome = next((p for p in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ) if Path(p).exists()), shutil.which("chrome") or shutil.which("chromium"))
    if not chrome:
        raise SystemExit("no Chrome found")

    before = OUT_PDF.stat().st_mtime if OUT_PDF.exists() else 0
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={OUT_PDF}", OUT_HTML.resolve().as_uri()],
                   check=False, capture_output=True, timeout=300)
    time.sleep(0.5)
    after = OUT_PDF.stat().st_mtime if OUT_PDF.exists() else 0
    if after <= before:
        raise SystemExit(f"Chrome reported success but did not write {OUT_PDF.name} "
                         f"— is it open in a viewer?")
    print(f"wrote {OUT_PDF.relative_to(ROOT)}  "
          f"({OUT_PDF.stat().st_size // 1024} KB · {len(recs)} machines · {photos} photos)")


if __name__ == "__main__":
    main()
