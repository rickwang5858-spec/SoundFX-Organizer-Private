#!/bin/bash
set -euo pipefail
ZIP="${1:?ZIP path required}"
EXPECTED_ARCH="${EXPECTED_ARCH:-$(uname -m)}"
WORK="$(mktemp -d)"
trap '/bin/rm -rf "$WORK"' EXIT
/usr/bin/ditto -x -k "$ZIP" "$WORK"
APP="$WORK/SoundFX Organizer.app"
test -d "$APP"
test -x "$APP/Contents/MacOS/SoundFX Organizer"
test -x "$APP/Contents/Resources/ai_worker/ai_worker"
/usr/bin/lipo "$APP/Contents/MacOS/SoundFX Organizer" -verify_arch "$EXPECTED_ARCH"
/usr/bin/lipo "$APP/Contents/Resources/ai_worker/ai_worker" -verify_arch "$EXPECTED_ARCH"
/usr/bin/codesign --verify --deep --strict "$APP"
if /usr/bin/zipinfo -1 "$ZIP" | /usr/bin/grep -Eqi 'OpenSource|CONTRIBUTING|tests?/|\.py$'; then
  echo "Developer files leaked into final archive." >&2; exit 3
fi
"$APP/Contents/MacOS/SoundFX Organizer" --release-self-test >"$WORK/app-self-test.json"
/usr/bin/grep -q '"python_frozen": true' "$WORK/app-self-test.json"
/usr/bin/grep -q '"architecture": "'"$EXPECTED_ARCH"'"' "$WORK/app-self-test.json"
"$APP/Contents/Resources/ai_worker/ai_worker" </dev/null >"$WORK/ai.out" 2>"$WORK/ai.err" &
AI_PID=$!
for _ in {1..600}; do
  if /usr/bin/grep -q '"ready"' "$WORK/ai.out"; then break; fi
  if ! /bin/kill -0 "$AI_PID" 2>/dev/null; then
    /bin/cat "$WORK/ai.err" >&2; exit 4
  fi
  /bin/sleep 1
done
/bin/kill "$AI_PID" 2>/dev/null || true
/usr/bin/grep -q '"ready"' "$WORK/ai.out"
