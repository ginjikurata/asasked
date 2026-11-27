#!/bin/sh
# One-time setup on the VPS (Caddy already serves lab.asasked.dev). Run as root:
#   sh server-setup.sh 'ssh-ed25519 AAAA... asasked-lab-deploy' [site folder]
# Creates a user "labdeploy" whose key can only rsync files into the site folder
# (no shell, no sudo, no other folders). Caddy, DNS and HTTPS are left as they are.
set -eu
PUBKEY="${1:?pass the deploy public key in quotes}"
ROOT="${2:-/var/www/lab.asasked.dev}"

command -v rsync >/dev/null || { apt-get update && apt-get install -y rsync; }
RRSYNC=$(command -v rrsync || true)
[ -n "$RRSYNC" ] || { echo "rrsync not found (needs rsync 3.2.4+, e.g. Ubuntu 22.04+ / Debian 12+)"; exit 1; }

id labdeploy >/dev/null 2>&1 || useradd -m -s /bin/sh labdeploy
mkdir -p "$ROOT" /home/labdeploy/.ssh
chown -R labdeploy:labdeploy "$ROOT"
echo "restrict,command=\"$RRSYNC $ROOT\" $PUBKEY" > /home/labdeploy/.ssh/authorized_keys
chown -R labdeploy:labdeploy /home/labdeploy/.ssh
chmod 700 /home/labdeploy/.ssh && chmod 600 /home/labdeploy/.ssh/authorized_keys

echo "labdeploy can now upload into $ROOT"
echo "--- current Caddy block for lab.asasked.dev:"
grep -rn -A12 "lab.asasked.dev" /etc/caddy 2>/dev/null || echo "(not found in /etc/caddy)"
