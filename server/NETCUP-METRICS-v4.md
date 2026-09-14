# Install demo usage counts on Netcup

This update adds `metrics.py` and changes `service.py` and `server.py`.
It uses only existing dependencies. It adds two session columns and two aggregate
measurement tables to the existing database. Pending runs are preserved across
the service restart. The workflow, Telegram token and session limits are unchanged.
Old sessions default to unmeasured. The old backend can still read the database.

The archive is staged at `/home/zippergen-demo/demo-metrics-v4.tar.gz`.
SHA-256, independently computed from the archive on the Mac:

```text
cecc1a7303d6618a1a7d983d3912dc4adda4ec10f2769f4c1e20facafee703a7
```

Read this release record from your Mac checkout or GitHub. Do not obtain the
expected checksum from another file in the writable staging account.

Run every command below individually in your **administrator SSH terminal on
Netcup**, not directly on your Mac. The commands work in fish. If a command fails,
stop before continuing. The assistant has staged the archive but has not run
these privileged installation commands.

## Freeze and inspect

```sh
sudo mkdir -m 700 /root/zippergen-demo-metrics-v4
```

```sh
sudo install -o root -g root -m 600 /home/zippergen-demo/demo-metrics-v4.tar.gz /root/zippergen-demo-metrics-v4/release.tar.gz
```

```sh
sudo sha256sum /root/zippergen-demo-metrics-v4/release.tar.gz
```

Compare with the checksum above. Stop if it differs. The archive was checked on
the Mac and contains exactly three regular files, `service.py`, `server.py` and
`metrics.py`. A matching digest provides a stable review target, not a general
safety proof.

```sh
sudo tar --extract --gzip --file /root/zippergen-demo-metrics-v4/release.tar.gz --directory /root/zippergen-demo-metrics-v4 --no-same-owner --no-same-permissions
```

```sh
sudo diff -u /opt/zippergen-demo/server/live_demo/service.py /root/zippergen-demo-metrics-v4/service.py
```

```sh
sudo diff -u /opt/zippergen-demo/server/live_demo/server.py /root/zippergen-demo-metrics-v4/server.py
```

```sh
sudo less /root/zippergen-demo-metrics-v4/metrics.py
```

A `diff` status of 1 means there are differences, as expected.

## Install after review

Back up the two installed files and configuration before changing them:

```sh
sudo cp -p /opt/zippergen-demo/server/live_demo/service.py /root/zippergen-demo-metrics-v4/service.py.before
```

```sh
sudo cp -p /opt/zippergen-demo/server/live_demo/server.py /root/zippergen-demo-metrics-v4/server.py.before
```

```sh
sudo cp -p /etc/zippergen-demo/config /root/zippergen-demo-metrics-v4/config.before
```

```sh
sudoedit /etc/zippergen-demo/config
```

Add this setting once, keeping the other entries:

```ini
DEMO_METRICS_ENABLED=1
```

The following commands briefly stop the demo while installing the three files:

```sh
sudo systemctl stop zippergen-demo
```

```sh
sudo install -o root -g root -m 644 -t /opt/zippergen-demo/server/live_demo /root/zippergen-demo-metrics-v4/service.py /root/zippergen-demo-metrics-v4/server.py /root/zippergen-demo-metrics-v4/metrics.py
```

```sh
sudo systemctl start zippergen-demo
```

```sh
sudo systemctl status zippergen-demo --no-pager
```

```sh
curl --fail -H 'Origin: https://zippergen.io' https://demo-api.zippergen.io/api/config
```

After Telegram polling starts, expect `"available": true` and
`"metrics_enabled": true`. The Origin header is needed for this check, since
measurement is limited to the production website. Refresh the demo to see its
Usage counts control. The frontend also works with the previous backend, with
counting disabled until this update is installed.

## Read the report

Still in your administrator SSH terminal on Netcup:

```sh
sudo -u zippergen-live /opt/zippergen-demo/venv/bin/python /opt/zippergen-demo/server/live_demo/metrics.py --days 7
```

Counts begin with this release. Use `--days 30` or add `--json` as needed.
[The server README](README.md#demo-usage-counts) explains each counter and its limits.
No public dashboard or reporting route is exposed.

To stop collection, change the setting to `DEMO_METRICS_ENABLED=0` and restart
`zippergen-demo`. Existing aggregates remain available to the private report.

## Roll back the code if needed

Run only if you need to restore the previous backend:

```sh
sudo systemctl stop zippergen-demo
```

```sh
sudo install -o root -g root -m 644 /root/zippergen-demo-metrics-v4/service.py.before /opt/zippergen-demo/server/live_demo/service.py
```

```sh
sudo install -o root -g root -m 644 /root/zippergen-demo-metrics-v4/server.py.before /opt/zippergen-demo/server/live_demo/server.py
```

```sh
sudo install -o root -g root -m 600 /root/zippergen-demo-metrics-v4/config.before /etc/zippergen-demo/config
```

```sh
sudo systemctl start zippergen-demo
```

The old code ignores the added database columns and tables. Leave the state
database in place. The unused `metrics.py` file can remain installed.
