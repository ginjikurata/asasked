#!/bin/sh
# Monthly re-check of published stores, started by launchd (scripts/dev.asasked.lab.recheck.plist).
# Runs `node scripts/discover.mjs recheck`, keeps a dated log in research/recheck-logs/ and shows a macOS
# notification with the result. It only updates research/recheck.csv: it never builds or deploys the site.
# Extra arguments go to discover.mjs (for a test: sh scripts/recheck-monthly.sh --limit 1).
set -u
LAB="$(cd "$(dirname "$0")/.." && pwd)"
LOGS="$LAB/../research/recheck-logs"
LOG="$LOGS/$(date +%Y-%m-%d).log"
NODE=/opt/homebrew/bin/node
mkdir -p "$LOGS"
cd "$LAB" || exit 1

"$NODE" scripts/discover.mjs recheck "$@" > "$LOG" 2>&1
code=$?

# "78 published stores: ok 42, manual 36, review 0 -> ..." -> "ok 42, manual 36, review 0"
counts=$(sed -n 's/^[0-9]* published stores: \(.*\) -> .*/\1/p' "$LOG")
hidden=$(grep -c 'hidden until a person checks' "$LOG")
if [ "$code" -ne 0 ] || [ -z "$counts" ]; then
  text="Перепроверка не прошла, смотрите лог $(basename "$LOG")"
elif [ "$hidden" -gt 0 ]; then
  text="Скрыто магазинов: $hidden. $counts. Нужна ручная проверка, потом сборка и выкладка."
else
  text="$counts. Даты обновлены, нужна сборка и выкладка."
fi
osascript -e "display notification \"$text\" with title \"AsAsked lab: перепроверка магазинов\"" >/dev/null 2>&1
exit "$code"
