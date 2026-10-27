"""Export the whole machine catalog into a real Notion database — with photos.

Creates a Notion database (under a parent page you own) with one row per machine
and these properties — so you can filter/group natively in Notion:

    Machine (title) · Photo (files) · Brand (select) · Body part (select)
    Mechanism (select) · Exercise (select) · Muscle (text) · Gym floor (multi-select)
    Source (select) · Machine ID (number)

Body-part and mechanism options are created up-front with colours; brand/exercise/
source options Notion fills in automatically as rows are written.

Photos: the renders live on your local API (localhost), which Notion can't fetch —
so each render is uploaded straight to Notion via the file-upload API and attached
as the page icon (thumbnail in the table) + a Photo file. That's 3 API calls per
machine, so the full run is rate-limited to ~30-40 min.

Setup (one time):
  1. https://www.notion.so/my-integrations → New integration → copy the secret.
  2. Open the Notion page you want this under → ••• → Connections → add your integration.
  3. Copy that page's id from its URL (the 32-hex chunk).

Run:
  export NOTION_TOKEN=secret_xxx
  export NOTION_PARENT_PAGE_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  python export_notion.py --dry          # show schema + first rows, no API calls
  python export_notion.py --limit 20     # push only the first 20 (sanity check)
  python export_notion.py                # push all ~1954 (with photos)
  python export_notion.py --no-photos    # skip uploads (fast, ~12 min, no images)

Update photos of rows already in the database (AI super-resolution, in place):
  python export_notion.py --update-photos <db_id> --source watson-brochure
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

from sqlmodel import Session, select

from database import engine
from models import Brand, Exercise, Gym, GymMachine, Machine

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
THROTTLE = 0.34  # seconds between calls — stay under Notion's ~3 req/s

BP_COLOR = {"legs": "orange", "push": "blue", "pull": "purple", "core": "yellow",
            "unmapped": "default"}
TYPE_COLOR = {"plate-loaded": "brown", "selectorized": "green", "cable": "blue",
              "functional": "pink", "rack": "gray", "bench": "gray",
              "storage": "gray", "smith": "gray"}


def fetch_rows() -> list[dict]:
    """Same flat shape as GET /catalog/all (plus image_url), read from the DB."""
    with Session(engine) as s:
        gyms_by_machine: dict[int, list[str]] = {}
        for mid, gname in s.exec(
            select(GymMachine.machine_id, Gym.name).where(Gym.id == GymMachine.gym_id)
        ).all():
            gyms_by_machine.setdefault(mid, []).append(gname)
        rows = s.exec(
            select(Machine, Brand, Exercise)
            .where(Brand.id == Machine.brand_id)
            .join(Exercise, isouter=True)
            .order_by(Brand.name, Machine.model)
        ).all()
        return [{
            "machine_id": m.id, "brand": b.name, "model": m.model,
            "machine_type": m.machine_type, "muscle_label": m.muscle_label,
            "muscle_group": ex.muscle_group if ex else None,
            "exercise": ex.name if ex else None, "source": m.source,
            "gyms": sorted(set(gyms_by_machine.get(m.id, []))),
            "image_url": m.image_url,
        } for m, b, ex in rows]


def api(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """One Notion JSON API call, with 429 back-off + throttle."""
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(6):
        req = urllib.request.Request(f"{NOTION_API}{path}", data=data, method=method, headers={
            "Authorization": f"Bearer {token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req) as r:
                out = json.loads(r.read())
            time.sleep(THROTTLE)
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(float(e.headers.get("Retry-After", 1)) + 0.5)
                continue
            raise SystemExit(f"Notion API {e.code} on {method} {path}:\n{e.read().decode()}")
    raise SystemExit("rate-limited repeatedly; giving up.")


EXT = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
       "image/webp": "webp", "image/gif": "gif"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 rackd-export"


def image_bytes(image_url: str | None) -> tuple[bytes, str, str] | None:
    """Resolve a machine's image to (raw, mime, filename). Decodes base64 data URIs
    and downloads http(s) URLs (the marketplace renders). None on any failure."""
    if not image_url:
        return None
    try:
        if image_url.startswith("data:"):
            mime = image_url[5:].split(";")[0] or "image/jpeg"
            raw = base64.b64decode(image_url.partition(",")[2])
        elif image_url.startswith("http"):
            req = urllib.request.Request(image_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                mime = (r.headers.get("Content-Type", "") or "").split(";")[0].strip()
            if not mime.startswith("image/"):
                mime = "image/" + (image_url.rsplit(".", 1)[-1].split("?")[0].lower() or "jpeg")
        else:
            return None
    except Exception:                       # noqa: BLE001 — network/decode, just skip the photo
        return None
    if not raw:
        return None
    return raw, mime, f"render.{EXT.get(mime, 'jpg')}"


def upload_bytes(token: str, raw: bytes, mime: str, fname: str) -> str | None:
    """Upload raw image bytes to Notion; return file_upload id or None."""
    try:
        fu = api("POST", "/file_uploads", token, {})
        boundary = "----rackd" + uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
            f"filename=\"{fname}\"\r\nContent-Type: {mime}\r\n\r\n".encode()
            + raw + f"\r\n--{boundary}--\r\n".encode()
        )
        req = urllib.request.Request(
            f"{NOTION_API}/file_uploads/{fu['id']}/send", data=body, method="POST",
            headers={"Authorization": f"Bearer {token}", "Notion-Version": NOTION_VERSION,
                     "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req):
            pass
        time.sleep(THROTTLE)
        return fu["id"]
    except (urllib.error.HTTPError, KeyError, ValueError):
        return None


def upload_render(token: str, image_url: str | None) -> str | None:
    """Upload a render (base64 or remote URL) to Notion; return file_upload id or None."""
    got = image_bytes(image_url)
    if not got:
        return None
    raw, mime, fname = got
    return upload_bytes(token, raw, mime, fname)


def db_schema() -> dict:
    return {
        "Machine": {"title": {}},
        "Photo": {"files": {}},
        "Brand": {"select": {}},
        "Body part": {"select": {"options": [{"name": k, "color": c} for k, c in BP_COLOR.items()]}},
        "Mechanism": {"select": {"options": [{"name": k, "color": c} for k, c in TYPE_COLOR.items()]}},
        "Exercise": {"select": {}},
        "Muscle": {"rich_text": {}},
        "Gym floor": {"multi_select": {}},
        "Source": {"select": {}},
        "Machine ID": {"number": {}},
    }


def page_props(r: dict) -> dict:
    p: dict = {
        "Machine": {"title": [{"text": {"content": r["model"][:2000]}}]},
        "Body part": {"select": {"name": r["muscle_group"] or "unmapped"}},
        "Machine ID": {"number": r["machine_id"]},
    }
    if r["brand"]:
        p["Brand"] = {"select": {"name": r["brand"][:100]}}
    if r["machine_type"]:
        p["Mechanism"] = {"select": {"name": r["machine_type"][:100]}}
    if r["exercise"]:
        p["Exercise"] = {"select": {"name": r["exercise"][:100]}}
    if r["muscle_label"]:
        p["Muscle"] = {"rich_text": [{"text": {"content": r["muscle_label"][:2000]}}]}
    if r["gyms"]:
        p["Gym floor"] = {"multi_select": [{"name": g.replace(",", " ")[:100]} for g in r["gyms"]]}
    if r["source"]:
        p["Source"] = {"select": {"name": r["source"][:100]}}
    return p


def existing_machine_ids(token: str, db_id: str) -> set[int]:
    """Machine IDs already present in the Notion database (so append stays idempotent)."""
    ids: set[int] = set()
    cursor = None
    while True:
        body = {"page_size": 100, "filter": {"property": "Machine ID", "number": {"is_not_empty": True}}}
        if cursor:
            body["start_cursor"] = cursor
        res = api("POST", f"/databases/{db_id}/query", token, body)
        for pg in res["results"]:
            v = pg["properties"].get("Machine ID", {}).get("number")
            if v is not None:
                ids.add(int(v))
        if not res.get("has_more"):
            return ids
        cursor = res["next_cursor"]


def append(db_id: str, source: str, photos: bool) -> None:
    """Add rows of a single catalog source to an EXISTING database, skipping any
    Machine IDs already there. Select/multi-select options Notion creates on the fly."""
    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise SystemExit("set NOTION_TOKEN env var first.")
    rows = [r for r in fetch_rows() if r["source"] == source]
    have = existing_machine_ids(token, db_id)
    todo = [r for r in rows if r["machine_id"] not in have]
    print(f"{source}: {len(rows)} rows, {len(have)} already in DB, appending {len(todo)}"
          f"{'' if photos else ' (no photos)'}.")

    done = with_photo = 0
    for r in todo:
        props = page_props(r)
        body = {"parent": {"database_id": db_id}, "properties": props}
        if photos:
            fid = upload_render(token, r["image_url"])
            if fid:
                with_photo += 1
                body["icon"] = {"type": "file_upload", "file_upload": {"id": fid}}
                props["Photo"] = {"files": [
                    {"type": "file_upload", "file_upload": {"id": fid}, "name": "render.jpg"}]}
        api("POST", "/pages", token, body)
        done += 1
        if done % 25 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)} rows… ({with_photo} with photo)")
    print(f"\ndone — {done} machines appended to {db_id}, {with_photo} with photos.")


def source_pages(token: str, db_id: str, source: str) -> list[tuple[str, int]]:
    """(page_id, machine_id) for every row of one source already in the database."""
    out: list[tuple[str, int]] = []
    cursor = None
    while True:
        body = {"page_size": 100, "filter": {"property": "Source", "select": {"equals": source}}}
        if cursor:
            body["start_cursor"] = cursor
        res = api("POST", f"/databases/{db_id}/query", token, body)
        for pg in res["results"]:
            mid = pg["properties"].get("Machine ID", {}).get("number")
            if mid is not None:
                out.append((pg["id"], int(mid)))
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def update_photos(db_id: str, source: str) -> None:
    """Re-render every existing row of `source` with an AI-upscaled photo: super-
    resolve its render 4x, upload the result, and PATCH the page's icon + Photo
    file in place. Idempotent — the upscaler caches by content hash, and each run
    simply overwrites the photo, so re-running is safe."""
    from upscale import ensure_binary, upscale_jpeg

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        raise SystemExit("set NOTION_TOKEN env var first.")
    ensure_binary()

    by_id = {r["machine_id"]: r for r in fetch_rows() if r["source"] == source}
    pages = source_pages(token, db_id, source)
    print(f"{source}: {len(pages)} rows in Notion, {len(by_id)} in DB; upscaling photos.")

    done = updated = skipped = 0
    for page_id, mid in pages:
        done += 1
        r = by_id.get(mid)
        got = image_bytes(r["image_url"]) if r else None
        if not got:
            skipped += 1
            continue
        raw, _, _ = got
        try:
            big = upscale_jpeg(raw)
        except Exception as e:                  # noqa: BLE001 — model/subprocess hiccup, skip one
            print(f"  ! upscale failed for machine {mid}: {e}")
            skipped += 1
            continue
        fid = upload_bytes(token, big, "image/jpeg", "render.jpg")
        if not fid:
            skipped += 1
            continue
        api("PATCH", f"/pages/{page_id}", token, {
            "icon": {"type": "file_upload", "file_upload": {"id": fid}},
            "properties": {"Photo": {"files": [
                {"type": "file_upload", "file_upload": {"id": fid}, "name": "render.jpg"}]}},
        })
        updated += 1
        if done % 10 == 0 or done == len(pages):
            print(f"  {done}/{len(pages)}… ({updated} upscaled, {skipped} skipped)")
    print(f"\ndone — {updated} {source} photos upscaled + updated, {skipped} skipped.")


def run(dry: bool, limit: int | None, photos: bool) -> None:
    rows = fetch_rows()
    if limit:
        rows = rows[:limit]
    print(f"{len(rows)} machines to export{'' if photos else ' (no photos)'}.")

    if dry:
        print("\nDatabase properties:")
        for name, spec in db_schema().items():
            print(f"  · {name}: {list(spec)[0]}")
        print("\nFirst rows:")
        for r in rows[:8]:
            print(f"  {r['brand']} — {r['model']}  [{r['muscle_group'] or 'unmapped'} · "
                  f"{r['machine_type'] or '—'}]  photo={bool(r['image_url'])}")
        print("\n(dry run — no Notion calls.)")
        return

    token = os.environ.get("NOTION_TOKEN")
    parent = os.environ.get("NOTION_PARENT_PAGE_ID")
    if not token or not parent:
        raise SystemExit("set NOTION_TOKEN and NOTION_PARENT_PAGE_ID env vars first (see docstring).")

    db = api("POST", "/databases", token, {
        "parent": {"type": "page_id", "page_id": parent},
        "title": [{"type": "text", "text": {"content": "rackd · machine catalog"}}],
        "icon": {"type": "emoji", "emoji": "🏋"},
        "properties": db_schema(),
    })
    db_id = db["id"]
    print(f"created database {db_id}\n  {db.get('url', '')}\n")

    done = with_photo = 0
    for r in rows:
        props = page_props(r)
        body = {"parent": {"database_id": db_id}, "properties": props}
        if photos:
            fid = upload_render(token, r["image_url"])
            if fid:
                with_photo += 1
                body["icon"] = {"type": "file_upload", "file_upload": {"id": fid}}
                props["Photo"] = {"files": [
                    {"type": "file_upload", "file_upload": {"id": fid}, "name": "render.jpg"}]}
        api("POST", "/pages", token, body)
        done += 1
        if done % 50 == 0 or done == len(rows):
            print(f"  {done}/{len(rows)} rows… ({with_photo} with photo)")

    print(f"\ndone — {done} machines pushed, {with_photo} with photos.\n  open: {db.get('url', '(see Notion)')}")


if __name__ == "__main__":
    photos = "--no-photos" not in sys.argv
    if "--update-photos" in sys.argv:
        db_id = sys.argv[sys.argv.index("--update-photos") + 1]
        source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else "watson-brochure"
        update_photos(db_id, source)
    elif "--append" in sys.argv:
        db_id = sys.argv[sys.argv.index("--append") + 1]
        source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv else "watson-brochure"
        append(db_id, source, photos)
    else:
        lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        run(dry="--dry" in sys.argv, limit=lim, photos=photos)
