"""Point in-gym Life Fitness machines at official lifefitness.com catalog images.

Life Fitness isn't Shopify, so we scrape the catalog page's product cards
(title -> templated CDN url) and resolve {width} to a real CDN width (960).
Only one Life Fitness machine is currently in a gym (Insignia Shoulder Press).

Usage:  python lifefitness_images.py
"""
from __future__ import annotations

import re
import ssl
import urllib.request

from sqlmodel import Session

from database import engine
from models import Machine

PAGE = ("https://www.lifefitness.com/en-eu/catalog/strength-training/"
        "selectorized/insignia-series")

# in-gym Life Fitness machine.id -> catalog product title
MAP = {876: "Insignia Series Shoulder Press"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=30, context=_CTX).read()


def title_images(html: str) -> dict[str, str]:
    """title -> CDN url, resolving {width} to 960 (a valid CDN width)."""
    titles = [(m.start(), m.group(1))
              for m in re.finditer(r'title="(Insignia Series [^"]+)"', html)]
    imgs = [(m.start(), m.group(1))
            for m in re.finditer(r'(https://production-[^"\' ]+)', html)]
    out: dict[str, str] = {}
    for pos, t in titles:
        near = sorted((abs(ip - pos), u) for ip, u in imgs)
        if near and t not in out:
            out[t] = near[0][1].replace("{width}", "960")
    return out


def run() -> None:
    table = title_images(fetch(PAGE).decode("utf-8", "ignore"))
    print(f"catalog: {len(table)} Insignia products")

    with Session(engine) as s:
        for mid, title in MAP.items():
            src = table.get(title)
            machine = s.get(Machine, mid)
            if not src or not machine:
                print(f"  [skip] id={mid} title={title!r} src={bool(src)}")
                continue
            machine.image_url = src
            s.add(machine)
            print(f"  [ok] {mid} {machine.model} <- {title}")
        s.commit()
    print("done.")


if __name__ == "__main__":
    run()
