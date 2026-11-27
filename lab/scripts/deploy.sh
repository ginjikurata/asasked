#!/bin/sh
# Builds the static site and uploads it to the VPS over SSH.
# Usage: sh scripts/deploy.sh  (LAB_HOST defaults to the ssh alias "asasked-lab")
# Uses your own SSH key/agent; the script never asks for or stores a password.
set -eu
cd "$(dirname "$0")/.."
LAB_HOST="${LAB_HOST:-asasked-lab}"
# The server key is locked by rrsync to /var/www/lab.asasked.dev, so "." is that folder.
DEST="${LAB_DEST:-.}"

npm run build
test -s out/index.html && test -s out/products.json
node -e 'const d=require("./out/products.json"); if(!d.products.length) { console.error("empty product list, not deploying"); process.exit(1) } console.log(d.products.length + " products")'

# macOS ships openrsync, which the server-side rrsync rejects; use real rsync (brew install rsync).
RSYNC=$(command -v /opt/homebrew/bin/rsync || command -v rsync)
"$RSYNC" -az --delete out/ "$LAB_HOST:$DEST/"
echo "uploaded to $LAB_HOST:$DEST"
