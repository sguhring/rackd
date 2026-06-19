# rackd — installable PWA build

A full-screen, installable version of the rackd prototype that **saves your sets on-device**
(localStorage) and works **offline**. No App Store, no Apple Developer account, no Mac.

## files

- `index.html` — the app, full-screen, with on-device persistence
- `manifest.webmanifest` — makes it installable (name, icons, standalone display)
- `sw.js` — service worker; caches the app shell for offline use
- `icon-192.png`, `icon-512.png`, `icon-512-maskable.png` — app icons

## put it on your phone (2 minutes)

A PWA needs to be served over **https** for install + offline to work (opening the file
directly with `file://` won't register the service worker). Easiest free host:

**Option A — Netlify Drop (no account needed to try)**
1. Go to https://app.netlify.com/drop
2. Drag this whole `pwa` folder onto the page.
3. Open the URL it gives you on your iPhone in **Safari**.
4. Share → **Add to Home Screen**. Done — it opens full-screen with its own icon.

**Option B — Vercel**
```bash
npm i -g vercel
cd web/pwa
vercel        # follow prompts; it gives you an https URL
```
Then Add to Home Screen on the phone as above.

## notes

- Your logged sets persist in the browser/app storage on that device. "last time on this
  machine" and PR detection read from that saved history.
- Data is per-device and per-origin: it stays as long as you don't clear site data / delete the
  installed app.
- This is the local-first stage from `docs/ARCHITECTURE.md`. A shared machine catalog synced
  across users would need the `api/` backend hosted too — not required for personal use.
- If you preview `index.html` outside a server (e.g. straight from disk), the UI works but
  persistence and offline caching are disabled until it's served over https.
