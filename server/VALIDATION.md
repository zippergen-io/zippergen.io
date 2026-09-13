# Local validation, 13 September 2026

Framework revision: `0346b490d72699228031eee8349528a77ac389ba`.

- Workflow validation passed. Inspected the communication view, full workflow,
  and exact Mailbox and Writer projections.
- Twelve backend tests passed, including both branches, duplicate and foreign
  answers, private-chat binding, expiry and cleanup, admission limits, a broken
  chat, fresh-process recovery, and recovery after a killed process.
- Existing browser journeys passed at desktop, tablet, and 390/320-pixel widths.
- Browser integration passed through the real HTTP API and SQLite workflow
  runner, with only Telegram transport faked. Both answers completed while the
  browser page was closed. Reopening the URL restored the saved outcome.
  Simulated approval did not change the live result.
- Gunicorn 26.2.0 started the production application factory and served session
  creation and status with a fake bot. No live Telegram calls were made.
- A separate macOS process holding twelve pending workflows peaked at 34.5 MiB
  RSS. During a three-second idle sample it used 10.8% of one CPU. This is a
  local runtime measurement, excluding Gunicorn and network traffic. It is not
  a netcup load benchmark or a production capacity guarantee.

The backend and offline wheel bundle have now also been staged on netcup at
`/home/zippergen-demo/demo-backend-20260913`. All twelve backend tests passed
there under Python 3.12.3, as did the Gunicorn production-factory smoke test
with fake Telegram transport.

On netcup, a separate runtime-only check with twelve pending workflows peaked
at 43.6 MiB RSS and used 15.6% of one CPU during a three-second idle sample.
This excludes Gunicorn and real network traffic. It supports starting with the
current server, but does not establish a production capacity guarantee.

The root-install handoff was revised before privileged installation. Release v2
separates the SSH staging user from the non-login runtime user and uses a
root-owned review copy. The old staging installer is withdrawn. Release checks
cover link exclusion, archive-copy stability after staging changes, modified
files, and unexpected installable files.

## Production readiness

The administrator installed release v2 on netcup. The supplied systemd status
showed the service active with 29.4 MiB memory use. Public HTTPS now returns
`{"available": true, "lifetime_seconds": 1800}`. DNS points directly to netcup.
The browser API accepts the public origin `https://zippergen.io`.

The user confirmed receiving and approving a real Telegram request. Subsequent
browser fixes clear the saved live session on Start over and disable simulated
approval controls when a live run is active. Those fixes were checked against
an isolated API and the real workflow runner with fake Telegram transport,
including both decisions, closing and reopening the browser, a fresh session
after reset, and expiry. They do not require a backend update.

The optional QR code was independently decoded and compared with the session's
Telegram link at desktop and mobile widths. The QR image is generated in the
browser and disappears after connection, reset, or expiry.

The static live configuration is enabled for publication. Automated browser
checks do not send Telegram messages to users.
