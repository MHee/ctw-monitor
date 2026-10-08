---
name: preview-live
description: Look at the ctw-monitor web app locally with the live site's real data before Martin does - download the deployed products, optionally recompute events/stations with local code, build, vite preview, and check panels in Chrome. Use after any web or product-format change, or when Martin reports something on the live page.
---

# Preview the web app with live data

Synthetic data (`cli synthetic`) hides real-data problems: clutter from 30+ events, a dead
gauge, label collisions, huge interval bounds. Check UI changes against the live products.

## Steps

1. Products into `web/public/data/` (gitignored; overwritten):
   ```bash
   python scripts/preview_live.py                       # live products as deployed
   python scripts/preview_live.py --recompute-events    # local events code is ahead of the site
   python scripts/preview_live.py --restations          # new fields in stations.json
   ```
   Run it with the conda env set up as in the conda-env memory (PATH prefix, `< /dev/null`).
   It prints `validate: ok` or the schema problems.
2. **Build, then preview.** `vite preview` serves `web/dist`, and the build copies `data/`
   at build time. Without a rebuild you see whatever data the last build had (once it was
   the synthetic set, which looked like a bug in the new code):
   ```bash
   cd web && npm run build && (npx vite preview --port 4173 --strictPort > /dev/null 2>&1 &)
   ```
3. Chrome (load the claude-in-chrome tools in one ToolSearch call): new tab,
   `http://localhost:4173/`, wait about 2.5 s for the data, scroll the panel into view, screenshot.
   For numbers, read the DOM with `javascript_tool`. Two tables carry class `events`: the
   status details and the events table; select the events table by its `caption`.
   After a rebuild, `location.reload()` in its own call (a long wait in the same call
   fails when the page navigates).
4. Clean up: close the tab, `pkill -f "vite preview"`. Leave `web/public/data` as it is,
   or run `python -m ctw_monitor.cli synthetic --out web/public/data` before
   `npm run build` if you need the synthetic set again.

## What to look at

- Distance-time panel: event overlay readable, speed labels inside the plot.
- NEPTUNE panels: both time ranges, event-marker labels not colliding.
- Events table: ranges and minus signs, the per-segment line, greyed rows.
- Status panel: the stale-stations line matches `meta.last_valid` in the products.
- Dark and light themes when colours changed.
