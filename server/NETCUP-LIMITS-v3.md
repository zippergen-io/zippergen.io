# Configurable demo limits

This update changes only `live_demo/service.py` and `live_demo/server.py`.
The workflow and database schema are unchanged. The installed workflow hash
was checked against this checkout and matches. Existing saved runs and hourly
counters are retained across restart.

All 20 backend tests passed, including configurable hourly limits, expiry of
hourly counters, distinct capacity errors, both decisions and crash recovery.

The archive is staged at `/home/zippergen-demo/demo-limits-v3.tar.gz`.
SHA-256, independently computed on the Mac:

```text
3979d09a2ccd53eddeafa58d4997549b0c658d043a3926b91528330e535e6f66
```

Run the following commands individually in your **administrator SSH terminal
on Netcup**, not directly on your Mac. They work from fish.

## Freeze and check

```sh
sudo mkdir -m 700 /root/zippergen-demo-limits-v3
```

```sh
sudo install -o root -g root -m 600 /home/zippergen-demo/demo-limits-v3.tar.gz /root/zippergen-demo-limits-v3/release.tar.gz
```

```sh
sudo sha256sum /root/zippergen-demo-limits-v3/release.tar.gz
```

Compare with the checksum above. Stop if it differs. The verified archive
contains exactly two regular files, `service.py` and `server.py`.

```sh
sudo tar --extract --gzip --file /root/zippergen-demo-limits-v3/release.tar.gz --directory /root/zippergen-demo-limits-v3 --no-same-owner --no-same-permissions
```

## Review the changes

```sh
sudo diff -u /opt/zippergen-demo/server/live_demo/service.py /root/zippergen-demo-limits-v3/service.py
```

```sh
sudo diff -u /opt/zippergen-demo/server/live_demo/server.py /root/zippergen-demo-limits-v3/server.py
```

`diff` returns status 1 when files differ. That is expected here. A matching
archive checksum provides a stable review target, not a general safety proof.

## Configure and install after review

```sh
sudoedit /etc/zippergen-demo/config
```

Add or replace this one setting, keeping the other entries:

```ini
DEMO_MAX_STARTS_PER_IP_PER_HOUR=20
```

Keep `DEMO_MAX_SESSIONS=12` initially. The two limits are independent.
The first limits new sessions per public IP address over a rolling hour.
The second bounds retained sessions across all visitors.

Back up both files:

```sh
sudo cp -p /opt/zippergen-demo/server/live_demo/service.py /root/zippergen-demo-limits-v3/service.py.before
```

```sh
sudo cp -p /opt/zippergen-demo/server/live_demo/server.py /root/zippergen-demo-limits-v3/server.py.before
```

This briefly stops the demo while installing the two reviewed files:

```sh
sudo systemctl stop zippergen-demo
```

```sh
sudo install -o root -g root -m 644 /root/zippergen-demo-limits-v3/service.py /opt/zippergen-demo/server/live_demo/service.py
```

```sh
sudo install -o root -g root -m 644 /root/zippergen-demo-limits-v3/server.py /opt/zippergen-demo/server/live_demo/server.py
```

```sh
sudo systemctl start zippergen-demo
```

```sh
sudo systemctl status zippergen-demo --no-pager
```

```sh
curl --fail https://demo-api.zippergen.io/api/config
```

Once Telegram polling is ready, the API should report `"available": true`.
The token file is not changed by this update. No credentials belong in chat.

After this update, future limit changes only need editing the config and
running `sudo systemctl restart zippergen-demo`. Adding the new setting without
updating the two Python files has no effect on the old backend.
