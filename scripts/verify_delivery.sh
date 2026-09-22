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
archive_has_project_sources() {
  /usr/bin/zipinfo -1 "$1" | /usr/bin/awk '
    !/^SoundFX Organizer\.app(\/|$)/ && !/^__MACOSX\/SoundFX Organizer\.app(\/|$)/ { bad=1 }
    /Contents\/Resources\/(OpenSource|src|tests|scripts|\.github)(\/|$)/ { bad=1 }
    /Contents\/Resources\/(ai_worker|audio_ai|categories|custom_rules|engine|gui|i18n|legacy|low_quality|metadata_text|taxonomy)\.py$/ { bad=1 }
    END { exit bad ? 0 : 1 }
  '
}
if archive_has_project_sources "$ZIP"; then
  echo "Project source or developer files leaked into final archive." >&2; exit 3
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

# Launch through LaunchServices, create a real Tk window, and require proof that
# it became viewable. This catches windowed apps that pass CLI self-tests but
# silently exit when opened from Finder.
GUI_MARKER="$WORK/gui-smoke.json"
/usr/bin/open -n "$APP" --args --gui-smoke-test "$GUI_MARKER"
for _ in {1..60}; do
  test -s "$GUI_MARKER" && break
  /bin/sleep 1
done
test -s "$GUI_MARKER"
python3 - "$GUI_MARKER" <<'PY'
import json, pathlib, sys
result=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert result["visible"] is True, result
assert result["width"] >= 980 and result["height"] >= 700, result
print({"gui_smoke": "passed", **result})
PY
