#!/bin/bash
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  echo "Final macOS builds must be produced on macOS." >&2; exit 2
fi
ARCH="$(uname -m)"
case "$ARCH" in arm64|x86_64) ;; *) echo "Unsupported architecture: $ARCH" >&2; exit 2;; esac
python3 -c 'import tkinter,PyInstaller'
python3 -m PyInstaller --noconfirm --clean --onedir \
  --name ai_worker --paths src --collect-all transformers --collect-all torch src/ai_worker.py
python3 -m PyInstaller --noconfirm --clean --windowed \
  --name "SoundFX Organizer" \
  --osx-bundle-identifier "tw.snowmanmusic.soundfx-organizer" \
  --add-data "src/locales:locales" --paths src src/gui.py
APP="dist/SoundFX Organizer.app"
/bin/cp -R "dist/ai_worker" "$APP/Contents/Resources/ai_worker"
set_plist_string() {
  local key="$1" value="$2"
  if /usr/libexec/PlistBuddy -c "Print :${key}" "$APP/Contents/Info.plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :${key} ${value}" "$APP/Contents/Info.plist"
  else
    /usr/libexec/PlistBuddy -c "Add :${key} string ${value}" "$APP/Contents/Info.plist"
  fi
}
set_plist_string CFBundleShortVersionString 5.0
set_plist_string CFBundleVersion 100
BIN="$APP/Contents/MacOS/SoundFX Organizer"
/usr/bin/lipo -verify_arch "$ARCH" "$BIN"
/usr/bin/lipo -verify_arch "$ARCH" "$APP/Contents/Resources/ai_worker/ai_worker"
/usr/bin/codesign --force --deep --options runtime --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "dist/SoundFX_Organizer_5.0_macOS_${ARCH}.zip"
if /usr/bin/zipinfo -1 "dist/SoundFX_Organizer_5.0_macOS_${ARCH}.zip" | grep -Eqi 'OpenSource|CONTRIBUTING|tests?/|\.py$'; then
  echo "Developer files leaked into final archive." >&2; exit 3
fi
