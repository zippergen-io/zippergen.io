# Root installation handoff

The old command that executed a file in `/home/zippergen-demo` with sudo is
withdrawn. Do not execute a staging-owned shell or Python file as root.

From your administrator terminal:

1. Create a fresh directory under `/root` with mode 0700.
2. Use the system `install` command to copy the release archive there, owned by
   root with mode 0600. Do not copy the whole staging directory.
3. Compare the copied archive's SHA-256 against the digest provided separately
   with this release. Do not read the expected digest from writable staging.
   Stop on any mismatch.
4. Extract that verified root-owned archive with the system `tar`, using
   `--no-same-owner --no-same-permissions`. The release builder admits only
   relative directories and regular files, with no symbolic or hard links.
5. Inspect the frozen `server/install-netcup.sh`, `verify-bundle.py`, service
   unit, Caddy site, environment configuration, and any other code or dependency
   you need to review. A frozen copy is a stable review target, not a proof of
   code safety.
6. Run `/bin/bash` on the installer inside that root-owned copy. It installs
   a new, separate `zippergen-live` runtime account and refuses an existing
   installation. It asks for the bot token only in your own hidden terminal
   prompt.

The release-specific freeze command and SHA-256 are provided with the v2
archive. Read that command, then paste it into your administrator terminal.
Do not run a purported freeze helper directly from the staging account.

The unit uses `LoadCredential=telegram-token:/etc/zippergen-demo/telegram-token`.
systemd reads the root-only original and exposes a per-service file at
`$CREDENTIALS_DIRECTORY/telegram-token`. The application reads that file.
It does not need permission to read the original under `/etc`.

The `User` and `Group` are `zippergen-live`, not root and not the SSH account.
`ProtectSystem=strict` and `ProtectHome=true` restrict filesystem access.
`StateDirectory=zippergen-demo` provides the writable state directory with
mode 0700. These settings do not sandbox application code from its own bot
credential, which it necessarily needs to contact Telegram.

References: [systemd credentials](https://systemd.io/CREDENTIALS/) and
[Caddy proxy trust](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
