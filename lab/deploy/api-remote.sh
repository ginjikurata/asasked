#!/bin/sh
# Runs on the VPS as root (started by deploy/api-install.sh). Safe to run again.
# 1) Node 24+ from the NodeSource apt repo (signed), if node is missing or older.
# 2) systemd service "asasked-lab": code in /opt/asasked-lab, data in /var/lib/asasked-lab (0700),
#    no own user (DynamicUser), listens on 127.0.0.1:3103 only.
#    The chat model's settings and key live in /etc/asasked-lab/llm.env (root, 0600), which the owner
#    writes by hand; this script never creates or reads it. Without that file the chat runs on rules.
# 3) Caddy: forwards /api/* and /mcp of lab.asasked.dev to it. Backup first, validate, roll back on error.
set -eu
CODE=/opt/asasked-lab
SITE=/var/www/lab.asasked.dev

# --- 1. Node
major=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$major" -lt 24 ]; then
  echo "== installing Node 24 (now: $major)"
  apt-get update && apt-get install -y ca-certificates curl gnupg
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_24.x nodistro main" > /etc/apt/sources.list.d/nodesource.list
  apt-get update && apt-get install -y nodejs
fi
node -e 'require("node:sqlite")' || { echo "node:sqlite missing"; exit 1; }
echo "== node $(node -v)"

# --- 2. Service
chown -R root:root "$CODE" && chmod -R go-w "$CODE"
cat > /etc/systemd/system/asasked-lab.service <<EOF
[Unit]
Description=AsAsked Lab server (wallet sign-in, profile, MCP)
After=network.target

[Service]
ExecStart=$(command -v node) $CODE/server/main.mjs
Environment=LAB_PORT=3103
Environment=LAB_ORIGIN=https://lab.asasked.dev
Environment=LAB_DATA=/var/lib/asasked-lab
Environment=LAB_PRODUCTS=$SITE/products.json
Environment=LAB_MERCHANTS=$CODE/lib/merchants.json
Environment=LAB_TRUST_PROXY=1
EnvironmentFile=-/etc/asasked-lab/llm.env
DynamicUser=yes
StateDirectory=asasked-lab
StateDirectoryMode=0700
UMask=0077
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable asasked-lab >/dev/null 2>&1
systemctl restart asasked-lab
for i in 1 2 3 4 5 6 7 8 9 10; do curl -fs http://127.0.0.1:3103/api/health >/dev/null && break; sleep 1; done
curl -fs http://127.0.0.1:3103/api/health || { echo "server did not start:"; journalctl -u asasked-lab -n 30 --no-pager; exit 1; }
echo
echo "== service is up"

# --- 3. Caddy
# Backups (*.bak*) hold the same block; skip them, and stop if more than one live file has it.
FILE=$(grep -rlE --exclude='*.bak*' "^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{" /etc/caddy 2>/dev/null || true)
[ -n "$FILE" ] || { echo "lab.asasked.dev block not found in /etc/caddy; add the /api and /mcp lines by hand"; exit 1; }
[ "$(printf '%s\n' "$FILE" | wc -l)" -eq 1 ] || { echo "lab.asasked.dev block found in more than one file:"; echo "$FILE"; exit 1; }
if grep -q "127.0.0.1:3103" "$FILE"; then
  echo "== Caddy already forwards to 3103 ($FILE)"
else
  cp -p "$FILE" "$FILE.bak-asasked-lab"
  awk '
    !done && /^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{/ {
      print
      print "\t# AsAsked Lab server (sign-in, profile, MCP)"
      print "\thandle /api/* {"
      print "\t\treverse_proxy 127.0.0.1:3103"
      print "\t}"
      print "\thandle /mcp {"
      print "\t\treverse_proxy 127.0.0.1:3103"
      print "\t}"
      done = 1; next
    }
    { print }
  ' "$FILE.bak-asasked-lab" > "$FILE"
  if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 && systemctl reload caddy; then
    echo "== Caddy updated ($FILE, backup $FILE.bak-asasked-lab)"
  else
    cp -p "$FILE.bak-asasked-lab" "$FILE"
    systemctl reload caddy || true
    echo "Caddy rejected the change; the old file is back. Nothing else was changed in Caddy."
    exit 1
  fi
fi
echo "== done"
