---
name: website-screenshot
description: Take real screenshots of websites using headless Chromium on this machine. Use when investigating a website's layout, verifying scrape targets, checking what a page actually renders (JS-heavy sites, Cloudflare challenges), auditing web UI/UX, or documenting a site for the InStockachu catalogue. Produces PNG files you can view with the read tool.
---

# Website Screenshot

Take a screenshot of any URL with headless Chromium:

```bash
~/.pi/agent/skills/website-screenshot/shot.sh <url> [output.png] [width] [height]
```

Examples:

```bash
~/.pi/agent/skills/website-screenshot/shot.sh https://example.com
~/.pi/agent/skills/website-screenshot/shot.sh https://example.com /tmp/example.png 390 844
```

- Default output: `/tmp/shot-<domain>-<timestamp>.png` (path printed on stdout)
- Default viewport: 1440x2400 (tall, captures most of the page). Use 390x844 for iPhone-ish mobile view.
- JS gets ~8s of virtual time to render before capture.
- View the result with the read tool on the printed path.

For full-page DOM inspection after JS rendering, dump HTML instead:

```bash
chromium --headless=new --disable-gpu --dump-dom --virtual-time-budget=8000 <url> > /tmp/page.html
```

Local apps (e.g. `http://localhost:8020`) work too — useful for auditing our own frontends.
