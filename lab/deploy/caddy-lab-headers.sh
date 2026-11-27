#!/bin/sh
# Adds to the existing lab.asasked.dev Caddy block (run as root on the VPS):
#   - caching: /_next/static/* for a year (file names change with every build), /products.json for 5 minutes
#   - the "Page not found" page (404) gets the same security headers as every other page, and no "Server: Caddy"
# Needs the 404 page from deploy/caddy-lab-extras.sh. Keeps everything else in the block. Safe to run twice.
# From the Mac:  ssh concord sh -s < deploy/caddy-lab-headers.sh
set -eu
# Backups (*.bak*) hold the same block; skip them, and stop if more than one live file has it.
FILE=$(grep -rlE --exclude='*.bak*' "^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{" /etc/caddy 2>/dev/null || true)
[ -n "$FILE" ] || { echo "lab.asasked.dev block not found in /etc/caddy"; exit 1; }
[ "$(printf '%s\n' "$FILE" | wc -l)" -eq 1 ] || { echo "lab.asasked.dev block found in more than one file:"; echo "$FILE"; exit 1; }
if grep -q "AsAsked Lab headers" "$FILE"; then echo "== already added ($FILE)"; exit 0; fi

# Lines go in as they are; kept here (not inside awk) because the CSP has single quotes.
LAB_CACHE=$(cat <<'EOF'
	# AsAsked Lab headers: caching
	header /_next/static/* Cache-Control "public, max-age=31536000, immutable"
	header /products.json Cache-Control "public, max-age=300"
EOF
)
LAB_ERR=$(cat <<'EOF'
		# AsAsked Lab headers: the 404 page gets the same headers as other pages
		header {
			Content-Security-Policy "frame-ancestors 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; script-src 'self' 'unsafe-inline'; worker-src 'self' blob:"
			Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()"
			Referrer-Policy strict-origin-when-cross-origin
			Strict-Transport-Security "max-age=31536000; includeSubDomains"
			X-Content-Type-Options nosniff
			-Server
		}
EOF
)
export LAB_CACHE LAB_ERR

cp -p "$FILE" "$FILE.bak-lab-headers"
# Cache lines right after the block's first line; the 404 headers inside the block's "handle_errors 404 {".
# Braces are counted so a handle_errors of another site in the same file is left alone.
if ! awk '
  function depth_of(s,  o, c) { o = gsub(/[{]/, "", s); c = gsub(/[}]/, "", s); return o - c }
  !opened && /^[[:space:]]*lab\.asasked\.dev[[:space:]]*\{/ {
    print; print ENVIRON["LAB_CACHE"]
    opened = 1; depth = 1; next
  }
  opened && depth > 0 && !errs && /^[[:space:]]*handle_errors[[:space:]]+404[[:space:]]*\{/ {
    print; print ENVIRON["LAB_ERR"]
    errs = 1; depth += depth_of($0); next
  }
  opened && depth > 0 { depth += depth_of($0) }
  { print }
  END { if (!errs) exit 3 }
' "$FILE.bak-lab-headers" > "$FILE"; then
  cp -p "$FILE.bak-lab-headers" "$FILE"
  echo "No \"handle_errors 404 {\" in the lab.asasked.dev block. Run deploy/caddy-lab-extras.sh first. Nothing changed."
  exit 1
fi

if caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 && systemctl reload caddy; then
  echo "== Caddy updated ($FILE, backup $FILE.bak-lab-headers)"
else
  cp -p "$FILE.bak-lab-headers" "$FILE"
  systemctl reload caddy || true
  echo "Caddy rejected the change; the old file is back."
  exit 1
fi

sleep 1
echo "-- check: 404 page (expect content-security-policy and strict-transport-security, no server)"
curl -sI --max-time 10 https://lab.asasked.dev/no-such-page | grep -iE "^(HTTP|content-security-policy|strict-transport-security|server):?" || true
echo "-- check: /products.json (expect cache-control: public, max-age=300)"
curl -sI --max-time 10 https://lab.asasked.dev/products.json | grep -iE "^(HTTP|cache-control):?" || true
