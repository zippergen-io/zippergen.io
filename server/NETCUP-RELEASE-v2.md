# Netcup release v2

Archive on the server:
`/home/zippergen-demo/demo-backend-20260913-v2.tar.gz`

Expected SHA-256:
`37e621fc96366797a7c38cc4db97f9968f3aed2aac100820fafdc368ddf70be2`

The old home-directory sudo command is withdrawn. The v1 staging installer now
exits without installing anything. This v2 archive contains a separate
`zippergen-live` runtime account and root-ownership checks.

Read the following block, then paste it into your administrator terminal. It
copies data using system tools and never executes a file from writable staging.
It stops on a digest mismatch and stops after extracting a frozen review copy.
Do not run a staging-owned helper file with sudo.

```bash
# Read this block and paste it into your administrator terminal.
# Do not execute a staging-owned helper file with sudo.
sudo /bin/bash --noprofile --norc <<'ROOT'
set -euo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
umask 077
review=/root/zippergen-demo-install-v2
mkdir -m 700 "$review"
install -o root -g root -m 600 \
  /home/zippergen-demo/demo-backend-20260913-v2.tar.gz \
  "$review/release.tar.gz"
printf '%s  %s\n' \
  '37e621fc96366797a7c38cc4db97f9968f3aed2aac100820fafdc368ddf70be2' \
  "$review/release.tar.gz" | sha256sum --check -
tar --extract --gzip --file "$review/release.tar.gz" \
  --directory "$review" --no-same-owner --no-same-permissions
printf '%s\n' "Frozen for review at $review. Nothing has been installed or started."
ROOT
```

Then inspect the frozen files, including the installer and verifier:

```bash
sudo less /root/zippergen-demo-install-v2/server/install-netcup.sh
sudo less /root/zippergen-demo-install-v2/verify-bundle.py
sudo cat /root/zippergen-demo-install-v2/server/zippergen-demo.service
sudo cat /root/zippergen-demo-install-v2/server/Caddyfile.netcup
sudo cat /root/zippergen-demo-install-v2/server/config.netcup
```

Review any other code and dependencies needed before authorizing installation.
A matching digest provides a stable review target, not a general safety proof.

Only after that review, in your own administrator terminal:

```bash
sudo /bin/bash /root/zippergen-demo-install-v2/server/install-netcup.sh
```

The original Telegram token remains in `/etc/zippergen-demo/telegram-token`,
owned by root with mode 0600 under a root-only directory. `LoadCredential`
provides the runtime with its per-service copy. Enter the dedicated bot token
only in the hidden terminal prompt. No secret belongs in the source archive.

The hostname is `demo-api.zippergen.io`. DNS only is required by this release's
direct-client proxy configuration. Cloudflare can be added with a separately
reviewed proxy-trust and origin-TLS configuration.

This release record is outside the archive to avoid a self-referential hash.
