#!/bin/sh
# Launch: removes the X-Robots-Tag "noindex, nofollow" line from the lab.asasked.dev Caddy block (run as root on the VPS),
# so search engines may index the site. Goes with LAUNCHED = true in lib/site.ts. Keeps everything else. Safe to run twice.
# From the Mac:  ssh concord sh -s < deploy/caddy-lab-launch.sh
set -eu
FILE=$(grep -rlE --exclude='*.bak*' "^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{" /etc/caddy 2>/dev/null || true)
[ -n "$FILE" ] || { echo "lab.asasked.dev block not found in /etc/caddy"; exit 1; }
[ "$(printf '%s\n' "$FILE" | wc -l)" -eq 1 ] || { echo "lab.asasked.dev block found in more than one file:"; echo "$FILE"; exit 1; }

# Only lines inside the lab block; braces are counted so other sites in the same file are left alone.
COUNT=$(awk '
  function depth_of(s,  o, c) { o = gsub(/[{]/, "", s); c = gsub(/[}]/, "", s); return o - c }
  !opened && /^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{/ { opened = 1; depth = 1; next }
  opened && depth > 0 { if ($0 ~ /^[[:space:]]*header[[:space:]]+X-Robots-Tag/) n++; depth += depth_of($0) }
  END { print n + 0 }
' "$FILE")
if [ "$COUNT" -eq 0 ]; then echo "== already removed ($FILE)"; exit 0; fi

cp -p "$FILE" "$FILE.bak-lab-launch"
awk '
  function depth_of(s,  o, c) { o = gsub(/[{]/, "", s); c = gsub(/[}]/, "", s); return o - c }
  !opened && /^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{/ { print; opened = 1; depth = 1; next }
  opened && depth > 0 {
    if ($0 ~ /^[[:space:]]*header[[:space:]]+X-Robots-Tag/) next
    if ($0 ~ /^[[:space:]]*# Not open to search engines until launch\./) next
    depth += depth_of($0)
  }
  { print }
' "$FILE.bak-lab-launch" > "$FILE"

if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 && systemctl reload caddy; then
  echo "== Caddy updated ($FILE, backup $FILE.bak-lab-launch)"
else
  cp -p "$FILE.bak-lab-launch" "$FILE"
  systemctl reload caddy || true
  echo "Caddy rejected the change; the old file is back."
  exit 1
fi

sleep 1
echo "-- check: home page (expect no x-robots-tag)"
curl -sI --max-time 10 https://lab.asasked.dev/ | grep -iE "^(HTTP|x-robots-tag):?" || true
