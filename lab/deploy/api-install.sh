#!/bin/sh
# Puts the lab server on the VPS. Run it yourself on the Mac (it uses your root SSH alias):
#   sh deploy/api-install.sh            (ROOT_HOST defaults to the ssh alias "concord")
# Copies only the server code (no local data/lab.db), then runs deploy/api-remote.sh there as root.
# Safe to run again after server changes. The static pages still go up with scripts/deploy.sh.
set -eu
cd "$(dirname "$0")/.."
ROOT_HOST="${ROOT_HOST:-concord}"
RSYNC=$(command -v /opt/homebrew/bin/rsync || command -v rsync)

"$RSYNC" -a --relative \
  server/main.mjs server/mcp.mjs server/catalog.mjs server/store.mjs \
  server/woo.mjs server/invoice.mjs server/orders.mjs server/chat.mjs extension/guard.js \
  lib/intent.ts lib/products.ts lib/merchants.json package.json \
  "$ROOT_HOST:/opt/asasked-lab/"
ssh "$ROOT_HOST" sh -s < deploy/api-remote.sh
