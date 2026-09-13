# ZipperGen Website

Official project website for ZipperGen.

Live site: https://zippergen.io

## Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

## Interactive demo

`public/demo/` is a simulated shell using plain JavaScript and CSS.
JetBrains Mono is served locally with its SIL Open Font License.
The simulated shell does not execute commands, call a model, or start a service.
At approval, a Telegram preview lets visitors click Approve or Reject. The
optional live path starts a separate workflow on a demo server.
The old visualization is preserved at `/demo/legacy/`.

Suggested commands guide visitors from `zg init` through a simulated coding
agent session, code inspection, configuration, and deployment. Visitors can
inspect either participant, stop and restart, or choose either approval
outcome. They can also type supported commands. The dispatcher handles a
fixed set of commands and never evaluates shell input.

The command row stays in place, with underlined command suggestions directly
below it. Text uses a high-contrast palette and locally served JetBrains Mono.
The output has a separate, subtly shaded area and a consistent text hierarchy.
Desktop milestone labels align right, with the circles on their right.
Each command replaces the current output,
while arrow keys retain access to command history. A small milestone line
tracks achieved steps without forcing a route. On phones it sits above the
terminal. Skipped inspection stays marked as not explored.

Versioned browser storage keeps progress when available. Start over clears the
simulation and forgets the current live session, so the next live attempt asks
for a new approval. Earlier server sessions expire after 30 minutes.
The downloadable project contains the real workflow.

The setup summary distinguishes the fixed browser draft and simulated Telegram
approval from the downloadable project's mock model and terminal approval.
“Setup in your project” shows how to configure a Telegram provider and connector
without collecting credentials in the browser.

The optional live backend and netcup deployment instructions are in
[server/README.md](server/README.md). It uses a fixed draft and real durable
ZipperGen approval. `public/demo/live-config.json` points to the checked backend
at `https://demo-api.zippergen.io`. Set `api_base` to `null` to hide the live
option. Live runs disable simulated approval controls and display the Telegram
decision. An optional QR code is generated locally in the browser.

The command output, code views, and downloadable project must stay aligned.
Refresh the generated artifacts from a clean framework checkout:

```bash
../zippergen/.venv/bin/python scripts/prepare-demo.py --framework ../zippergen
```

This validates the workflow, checks both projections, records the source
revision and hash in `content.json`, and builds `approval-example.zip`.
The workflow source is copied from `examples/email_approval.py` without edits.
The ZIP contains its own installation and run instructions pinned to that
framework revision. Regenerate and check the download when updating the source.

For browser checks, use a separate Python environment with Playwright:

```bash
python3 -m venv /tmp/zippergen-browser-check
/tmp/zippergen-browser-check/bin/pip install playwright
/tmp/zippergen-browser-check/bin/playwright install chromium
npm run build
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

In a second terminal:

```bash
/tmp/zippergen-browser-check/bin/python scripts/test-demo.py
```

Pass `--browser /path/to/chrome` to use an existing Chrome installation, or
`--screenshots /tmp/zippergen-demo-screenshots` to save desktop and mobile views.
The checks cover both coding agents, global and participant views, both
decisions, stop and restart, refresh, reset, typed commands and history,
unsupported input, the ZIP download, narrow screens, local font loading, and
unavailable storage or content. They do not contact a live provider.

Before publishing, also extract the ZIP into a temporary directory and follow
its README. Exercise yes, no, and Ctrl-C followed by `zg run --resume` at the
approval prompt. Keep this real runtime check separate from the simulation.
