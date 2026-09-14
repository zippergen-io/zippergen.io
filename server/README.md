# Live Telegram demo

The static website includes a simulated Telegram approval. This optional
backend runs a separate, real ZipperGen workflow when a visitor chooses the
live path. It uses a fixed draft, so there is no model key or model bill.
Approval releases the example reply. Rejection discards it. No email is sent.

The live workflow is in `live_demo/workflow.py`. Its scope and guarantees are
in `specification.md`. This is a bounded companion to the downloadable mailbox
tutorial, not a deployment of the visitor's simulated shell session.

## What runs on the server

One Gunicorn process serves the small API. ZipperGen's `LocalSupervisor` runs
each session over a separate SQLite store. `TelegramNotifier` sends the real
human task and checks the chat, actor, and answer token. ZipperGen's durable
Telegram inbox preserves received updates before advancing Telegram's cursor.
The small website-specific service associates visitors with their private chats
and expires their sessions.

Use a dedicated bot. Do not run another bot program against the same token.
The service refuses a bot with an active webhook rather than removing it.

The defaults are 12 retained sessions, 30 minutes per session from creation,
and at most 5 starts per client address per hour unless configured otherwise. Completed runs count toward
the limit until expiry. A rejected or approved outcome is reported only after
the workflow has persisted its result. Closing the browser does not stop it.
The URL fragment and optional browser storage let the visitor recover it.
A run's URL grants read access and should be treated as private.

The browser has no approval endpoint. Its simulated buttons cannot answer a
live task. Each temporary Start link can bind to only one private Telegram
user. Bot tokens never enter the static website, API responses, or access logs.
The service deletes expired run directories and session rows, including chat
identifiers. It keeps only hashed rate-limit addresses for up to one hour.
Telegram itself retains the messages according to its own policies.

Notification delivery is at least once. A crash after Telegram accepts a
message but before the receipt is saved can repeat that message. It cannot
change an already recorded approval. Expiry blocks new decisions even before
cleanup has run.

## Review the release before root installation

Do not execute the installer from the SSH account's writable home directory.
Checksums stored beside that directory cannot prevent it changing between
review and privileged execution. The previous home-directory sudo command is
withdrawn.

Use the clean release archive `demo-backend-20260913-v2.tar.gz`, not the whole
staging directory, which also contains a test virtual environment. Copy the
archive into a newly created root-owned directory, verify that root-owned copy
against the SHA-256 digest published with the release, then extract it there.
Inspect the frozen installer, verifier, unit, configuration, and dependencies.
Only then run the frozen installer. See `ROOT-HANDOFF.md` for the sequence.

This freezes the bytes being reviewed. It does not establish that arbitrary
code is safe merely because it has a matching checksum. The installer refuses
non-root-owned, group/world-writable, linked, or special source files as an
additional guard against accidentally using the wrong directory. That guard
is not a substitute for freezing the script before executing it as root.

The runtime account is `zippergen-live`, a separate non-login user. The SSH
staging account is `zippergen-demo`. The runtime account owns only its saved
state, not the application code, deployment unit, or original token file.

The API hostname is `demo-api.zippergen.io`, pointing to `188.68.33.144`.
DNS only is the current deployment policy because the proxy forwards the direct
client address for rate limiting. Caddy can operate behind Cloudflare, but
turning the proxy on requires a reviewed trusted-proxy/client-IP configuration
and a compatible Cloudflare origin TLS mode. Do not toggle it on with the
current direct-client configuration.

The initial netcup config allows `https://zippergen.io` and the local preview
origins `http://127.0.0.1:8765` and `http://localhost:8765`. These origins permit
session creation and observation, not browser approval of a live task.

## Prepare the netcup server

These instructions assume a systemd Linux server with Python 3.11 or newer,
Git, and an existing HTTPS reverse proxy or permission to install one.
The website remains hosted where it is now. Only the API goes on this server.

After freezing and reviewing the release, create a dedicated service account and copy this repository's `server/`
directory to `/opt/zippergen-demo/server`. Keep application code owned by the
administrator, not the service account. For a new installation:

```bash
sudo useradd --system --user-group --no-create-home --home-dir /var/lib/zippergen-demo --shell /usr/sbin/nologin zippergen-live
sudo install -d -m 755 /opt/zippergen-demo
sudo install -d -m 700 /etc/zippergen-demo
sudo python3 -m venv /opt/zippergen-demo/venv
sudo /opt/zippergen-demo/venv/bin/pip install -r /opt/zippergen-demo/server/requirements.txt
sudo install -m 600 /opt/zippergen-demo/server/config.example /etc/zippergen-demo/config
```

The dependency file pins the framework revision that this backend was tested
against. It does not require a new PyPI release. The backend uses framework
store and Telegram modules as well as the public runner API, so recheck its
tests before changing that pin.

Create a dedicated demo bot through Telegram's BotFather. Save its token in
`/etc/zippergen-demo/telegram-token` using your own terminal:

```bash
sudoedit /etc/zippergen-demo/telegram-token
sudo chmod 600 /etc/zippergen-demo/telegram-token
```

Put only the bot token in that file. Do not paste it into a coding-agent chat,
shell command argument, project file, or the browser. systemd passes a private
copy to the service through `LoadCredential`.

Edit `/etc/zippergen-demo/config` if the website origin differs from
`https://zippergen.io`. Origins must match exactly, without a trailing slash.
Multiple origins are separated by spaces. The default lifetime is 1800 seconds.

Review and install the provided service definition:

```bash
sudo install -m 644 /opt/zippergen-demo/server/zippergen-demo.service /etc/systemd/system/zippergen-demo.service
sudo systemctl daemon-reload
sudo systemctl enable --now zippergen-demo
sudo systemctl status zippergen-demo
curl --fail http://127.0.0.1:8787/api/config
```

After the first successful Telegram poll, the last command should report
`"available": true`. The service binds only to localhost. It has a 512 MB
memory limit and a private persistent state directory. Start with these
settings and measure the live server under several concurrent sessions.

Point an API subdomain at the server. Add a reverse-proxy site following
`Caddyfile.example`, using your actual hostname. Keep existing sites intact.
Caddy terminates HTTPS and overwrites `X-Real-IP`, which the backend uses for
rate limiting only when the connection comes from localhost. If using Nginx,
apply the same rules: HTTPS, proxy to localhost:8787, overwrite X-Real-IP with
the connecting client address, and limit request bodies to 1 KB.
Do not expose port 8787 directly to the internet.

The static website should retain its existing HTTPS configuration. Set
`public/demo/live-config.json` to the API origin, for example:

```json
{"api_base": "https://demo-api.example.org"}
```

Rebuild the site. With `api_base` set to `null`, the live action is hidden and
the simulated journey works on its own.

## Check the actual Telegram path before publishing

1. Open the demo, create and inspect the workflow, then run `zg config` and
   `zg deploy` in the simulation.
2. Open its pending task and choose the real Telegram step.
3. Open the bot link, press Start, and confirm that the message arrives.
4. Close the browser page and approve in Telegram. Reopen the saved demo URL.
   It should report that the real workflow completed.
5. Repeat with Reject.
6. On a pending run, restart this service with `sudo systemctl restart
   zippergen-demo`. Confirm that the same approval remains usable.
7. Check expiry and monitor memory with `systemctl status zippergen-demo`.

The live button opens a normal Telegram deep link. The optional “Scan with your
phone” panel encodes that same link in the browser using a vendored QR generator.
It disappears once connected, on expiry, or when starting over. There is no
external QR image service and no request that sends the private session URL to one.

Do not deploy changed workflow code over pending runs. Stop accepting new
sessions by hiding the live action, allow the 30-minute retention period to
elapse, then restart with the new code. The runtime rejects incompatible saved
workflow identities. Use `systemctl restart`, not a Gunicorn graceful reload,
because a single owner holds the state-directory lock.

## Automated checks

From the website checkout, with the framework checkout next to it:

```bash
PYTHONPATH=server ../zippergen/.venv/bin/python -m pytest server/tests -q
../zippergen/.venv/bin/zg validate server/live_demo/workflow.py:telegram_approval
../zippergen/.venv/bin/zg show server/live_demo/workflow.py:telegram_approval --communications
../zippergen/.venv/bin/zg show server/live_demo/workflow.py:telegram_approval --detail full
../zippergen/.venv/bin/zg show server/live_demo/workflow.py:telegram_approval --agent Mailbox
../zippergen/.venv/bin/zg show server/live_demo/workflow.py:telegram_approval --agent Writer
```

The browser integration check needs Playwright and ZipperGen importable in
one Python environment. Serve `public/` or the built site first:

```bash
PYTHONPATH=server:../zippergen/src /path/to/browser-env/bin/python scripts/test-live-demo.py \
  --url http://127.0.0.1:8765/demo/ \
  --browser /path/to/chrome \
  --state /tmp/zippergen-live-check-unique \
  --screenshots /tmp/zippergen-live-screenshots
```

This uses the real HTTP API, real SQLite-backed workflow, and real notifier
logic with an in-memory Telegram transport. It closes the page before each
answer, then reopens it to verify the persisted outcome. It does not send
Telegram messages. Use a fresh state path for each invocation.

Protocol references: [Telegram bot features](https://core.telegram.org/bots/features),
[Telegram Bot API](https://core.telegram.org/bots/api),
[Gunicorn configuration](https://gunicorn.org/reference/settings/), and
[Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

## Session limits

In `/etc/zippergen-demo/config`, configure:

```ini
DEMO_MAX_STARTS_PER_IP_PER_HOUR=20
DEMO_MAX_SESSIONS=12
DEMO_SESSION_SECONDS=1800
```

The hourly limit accepts 1–1000 and defaults to 5. The netcup example uses 20
for repeated testing. The retained-session limit accepts 1–32 and defaults to
12. Session lifetime accepts 60–3600 seconds and defaults to 1800.

The service reads these values on startup. The hourly setting requires the
updated backend, it is ignored by release v2. Restart the service after changing
configuration. Existing saved runs and hourly counters are preserved. Raising
the hourly limit does not increase the number of retained sessions. Visitors
sharing a public IP address share the hourly allowance.

Limit messages distinguish the hourly allowance from full session capacity
and give an estimated retry interval. Another visitor may take an available
slot before that retry.


## Demo usage counts

The optional measurement service keeps daily totals in the existing private
SQLite database. It is disabled by default. For an existing Netcup installation,
follow [the metrics update](NETCUP-METRICS-v4.md). For a new installation, set
`DEMO_METRICS_ENABLED=1` in the service environment and restart.

On Netcup, from your administrator SSH terminal:

```sh
sudo -u zippergen-live /opt/zippergen-demo/venv/bin/python /opt/zippergen-demo/server/live_demo/metrics.py --days 7
```

Use `--days 30` for a longer period and `--json` for daily totals in JSON.
There is no public reporting endpoint.

| Count | Meaning |
| --- | --- |
| `demo_opened` | A measured attempt opened the walkthrough |
| `first_command` | The attempt submitted its first nonempty shell command |
| `deployment_reached` | The attempt started the simulated service |
| `simulation_completed` | The attempt approved or rejected in the simulation |
| `telegram_requested` | The attempt tried to create a live session |
| `telegram_created` | A measured live session was created |
| `telegram_connected` | Its visitor connected the Telegram bot |
| `telegram_approved`, `telegram_rejected` | Its persisted workflow reached that outcome |
| `github_clicked` | The attempt followed a GitHub link from the demo |
| `live_capacity_refused`, `live_rate_refused`, `live_unavailable` | Requests refused for each reason |

Browser milestones count once per attempt. Reloading keeps the attempt.
Start over, a new tab or the 24-hour expiry starts another attempt. These are
not unique people. Live counts use a separate session unit, so repeated live
attempts can produce more sessions than browser attempts. Server completion is
counted even if the page is closed. Events fall on the UTC day they occur.
Do not treat ratios across a date boundary as exact cohort conversion rates.

Only the production origin participates. Local previews and the browser test
harness opt out. Visitors can use the footer control to opt out. Do Not Track
and Global Privacy Control are respected. Counts can therefore understate use.
Browser reports are untrusted and can also be spoofed. The limits reduce abuse,
but these totals are a practical usage signal, not audited statistics.

The browser sends a fixed event name and a temporary random attempt ID.
Commands, prompts, live-session tokens and Telegram identities are not sent to
the measurement endpoint. Event-specific receipt hashes expire after 24 hours.
Daily aggregates expire after 90 days. Short-lived session flags prevent duplicate
server counts across restarts and are removed with the existing session.
No pre-update sessions are counted retroactively. Cleanup runs during normal
service maintenance. See the website legal notice for the full disclosure.

An unavailable counting endpoint does not block the walkthrough. Disabling the
setting stops collection and hides the footer control after a reload. Existing
aggregates remain in the private database. Avoid repeatedly enabling collection
for tests on the public site, since completed counts cannot be attributed back
to an individual visitor for removal.
