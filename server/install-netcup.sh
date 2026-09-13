#!/usr/bin/env bash
# First installation only. Run in your own SSH terminal with sudo.
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 022

bundle=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app=/opt/zippergen-demo
config=/etc/zippergen-demo
host=demo-api.zippergen.io

if [[ ${1:-} == --check ]]; then
    printf '%s\n' "Install the tested backend from $bundle into $app." \
        "Install Caddy and Python venv support from Ubuntu packages." \
        "Configure HTTPS for $host and the zippergen-demo system service." \
        'Ask for the dedicated bot token privately if none is saved.'
    exit 0
fi
if [[ $EUID -ne 0 ]]; then
    printf '%s\n' 'First freeze and inspect a root-owned release. See ROOT-HANDOFF.md.' >&2
    exit 1
fi
# This catches accidental use of writable staging. It cannot make an altered
# script safe to run as root. The archive must be frozen and reviewed FIRST.
/usr/bin/python3 -I - "$bundle" <<'CHECK'
from pathlib import Path
import stat, sys
base = Path(sys.argv[1])
for path in [*reversed(base.parents), base, *base.rglob('*')]:
    info = path.lstat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit(f'Refusing non-root-owned or writable installation source: {path}')
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise SystemExit(f'Refusing links or special files: {path}')
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise SystemExit(f'Refusing multiply-linked files: {path}')
CHECK
if getent passwd zippergen-live >/dev/null || getent group zippergen-live >/dev/null; then
    printf '%s\n' 'The runtime account already exists. Inspect it before installing.' >&2
    exit 1
fi
if [[ -e $app || -e /etc/systemd/system/zippergen-demo.service ]]; then
    printf '%s\n' 'An installation already exists. Stop here rather than overwrite it.' >&2
    exit 1
fi
if ! getent ahostsv4 "$host" | awk '{print $1}' | sort -u | grep -Fxq 188.68.33.144; then
    printf '%s\n' "Set the DNS record for $host to DNS only and 188.68.33.144 first." >&2
    exit 1
fi
/usr/bin/python3 -I "$bundle/verify-bundle.py"
install -d -m 700 "$config"
if [[ ! -e $config/config ]]; then
    install -m 600 "$bundle/server/config.netcup" "$config/config"
fi
if [[ ! -s $config/telegram-token ]]; then
    /usr/bin/python3 -I - "$config/telegram-token" <<'PY'
import getpass, os, re, sys
from pathlib import Path
path = Path(sys.argv[1])
token = getpass.getpass('Dedicated Telegram demo bot token (hidden): ').strip()
if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
    raise SystemExit('The token format looks wrong. Nothing was saved.')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as output:
    output.write(token + '\n')
print('Bot token saved privately.')
PY
fi
apt-get update
apt-get install -y python3-venv caddy
install -d -m 755 "$app"
cp -R "$bundle/server" "$app/server"
chown -R root:root "$app/server"
find "$app/server" -type d -exec chmod 755 {} +
find "$app/server" -type f -exec chmod 644 {} +
/usr/bin/python3 -I -m venv "$app/venv"
"$app/venv/bin/python" -I -m pip install --no-index --find-links "$bundle/wheelhouse" zippergen==0.1.0a3 gunicorn==26.2.0
useradd --system --user-group --no-create-home --home-dir /var/lib/zippergen-demo --shell /usr/sbin/nologin zippergen-live
# Keep existing Caddy sites. Import only this demo's site block.
install -m 644 "$app/server/Caddyfile.netcup" /etc/caddy/zippergen-demo.caddy
if ! grep -Fxq 'import /etc/caddy/zippergen-demo.caddy' /etc/caddy/Caddyfile; then
    printf '\nimport /etc/caddy/zippergen-demo.caddy\n' >> /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
install -m 644 "$app/server/zippergen-demo.service" /etc/systemd/system/zippergen-demo.service
systemd-analyze verify /etc/systemd/system/zippergen-demo.service
systemctl daemon-reload
systemctl enable --now zippergen-demo.service
systemctl enable --now caddy.service
systemctl reload caddy.service
printf '\n%s\n' 'Installed. Check the service and HTTPS endpoint:' \
    'sudo systemctl status zippergen-demo --no-pager' \
    'curl --fail https://demo-api.zippergen.io/api/config'
