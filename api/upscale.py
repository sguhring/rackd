"""AI super-resolution for catalog renders, via Real-ESRGAN (ncnn / Vulkan).

The Watson (and other brochure) renders are tiny — ~250px JPEGs embedded in the
source PDFs, displayed scaled-up. There is no higher-res data to recover, so to
make them look good in Notion we run a genuine super-resolution model that
*invents* plausible detail at 4x.

We deliberately avoid the torch/basicsr stack (no compatible wheels on Python
3.14, and basicsr's `functional_tensor` breakage). Instead we drive the prebuilt
`realesrgan-ncnn-vulkan` binary: the real ESRGAN x4plus model, GPU-accelerated
through Vulkan, with zero Python dependencies. The binary + models are downloaded
once into the gitignored `tools/` dir and cached; every upscale result is cached
by content hash so re-runs are instant and restart-safe.

    python upscale.py <in.jpg|png> <out.jpg>   # one-off, also warms the binary
"""
from __future__ import annotations

import hashlib
import io
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import fitz  # PyMuPDF — already a project dep; used here only to re-encode PNG->JPG

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools" / "realesrgan-ncnn-vulkan"
CACHE = ROOT / "tools" / "_upscale_cache"
EXE = TOOLS / "realesrgan-ncnn-vulkan.exe"

# Official Real-ESRGAN ncnn-vulkan Windows release (exe + bundled models).
RELEASE_ZIP = ("https://github.com/xinntao/Real-ESRGAN/releases/download/"
               "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip")
MODEL = "realesrgan-x4plus"   # general-purpose photo model (not the anime one)
SCALE = 4


def ensure_binary() -> Path:
    """Download + unzip the realesrgan binary into tools/ on first use."""
    if EXE.exists():
        return EXE
    TOOLS.mkdir(parents=True, exist_ok=True)
    print(f"downloading Real-ESRGAN ncnn binary -> {TOOLS} …")
    with urllib.request.urlopen(RELEASE_ZIP, timeout=120) as r:
        blob = r.read()
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(TOOLS)
    if not EXE.exists():
        raise SystemExit(f"binary missing after extract; check contents of {TOOLS}")
    print("  done.")
    return EXE


def _to_jpg(png_bytes: bytes, quality: int = 92) -> bytes:
    """Re-encode the model's PNG output to JPEG (smaller, Notion-friendly)."""
    pix = fitz.Pixmap(io.BytesIO(png_bytes))
    if pix.alpha:                                   # flatten any alpha onto opaque
        pix = fitz.Pixmap(pix, 0)
    if pix.colorspace and pix.colorspace.n == 4:    # CMYK -> RGB
        pix = fitz.Pixmap(fitz.csRGB, pix)
    return pix.tobytes("jpg", jpg_quality=quality)


def upscale_jpeg(raw: bytes, *, model: str = MODEL, scale: int = SCALE) -> bytes:
    """Super-resolve image bytes by `scale`x; return JPEG bytes. Content-cached."""
    key = hashlib.sha1(raw + f"|{model}|{scale}".encode()).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.jpg"
    if cached.exists():
        return cached.read_bytes()

    ensure_binary()
    with tempfile.TemporaryDirectory() as td:
        ip, op = Path(td) / "in.png", Path(td) / "out.png"
        ip.write_bytes(raw)
        subprocess.run(
            [str(EXE), "-i", str(ip), "-o", str(op),
             "-n", model, "-s", str(scale), "-m", str(TOOLS / "models")],
            check=True, capture_output=True,
        )
        jpg = _to_jpg(op.read_bytes())
    cached.write_bytes(jpg)
    return jpg


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python upscale.py <in.(jpg|png)> <out.jpg>")
    src = Path(sys.argv[1]).read_bytes()
    out = upscale_jpeg(src)
    Path(sys.argv[2]).write_bytes(out)
    print(f"upscaled -> {sys.argv[2]} ({len(out) // 1024} KB)")
