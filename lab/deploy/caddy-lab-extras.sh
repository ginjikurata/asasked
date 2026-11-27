#!/bin/sh
# Adds to the existing lab.asasked.dev Caddy block (run as root on the VPS):
#   - /products -> /search, and addresses ending in "/" -> the same address without it
#   - our own "Page not found" page (/404.html) for missing addresses
# Keeps everything already in the block (/api, /mcp, X-Robots-Tag). Safe to run twice.
# From the Mac:  ssh concord sh -s < deploy/caddy-lab-extras.sh
set -eu
# Backups (*.bak*) hold the same block; skip them, and stop if more than one live file has it.
FILE=$(grep -rlE --exclude='*.bak*' "^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{" /etc/caddy 2>/dev/null || true)
[ -n "$FILE" ] || { echo "lab.asasked.dev block not found in /etc/caddy"; exit 1; }
[ "$(printf '%s\n' "$FILE" | wc -l)" -eq 1 ] || { echo "lab.asasked.dev block found in more than one file:"; echo "$FILE"; exit 1; }
if grep -q "AsAsked Lab extras" "$FILE"; then echo "== already added ($FILE)"; exit 0; fi
cp -p "$FILE" "$FILE.bak-lab-extras"
awk '
  !done && /^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{/ {
    print
    print "\t# AsAsked Lab extras: redirects and 404 page"
    print "\tredir /products /search permanent"
    print "\t@slash path_regexp slash ^(/.+)/$"
    print "\tredir @slash {re.slash.1} permanent"
    print "\thandle_errors 404 {"
    print "\t\trewrite * /404.html"
    print "\t\tfile_server"
    print "\t}"
    done = 1; next
  }
  { print }
' "$FILE.bak-lab-extras" > "$FILE"
if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 && systemctl reload caddy; then
  echo "== Caddy updated ($FILE, backup $FILE.bak-lab-extras)"
else
  cp -p "$FILE.bak-lab-extras" "$FILE"
  systemctl reload caddy || true
  echo "Caddy rejected the change; the old file is back."
  exit 1
fi
