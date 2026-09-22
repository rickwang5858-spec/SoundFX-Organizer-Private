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
set_plist_string CFBundleShortVersionString 5.0.2
set_plist_string CFBundleVersion 102
set_plist_string CFBundleDisplayName "SoundFX Organizer"
/usr/libexec/PlistBuddy -c "Delete :LSUIElement" "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool false" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :LSBackgroundOnly" "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :LSBackgroundOnly bool false" "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Delete :NSHighResolutionCapable" "$APP/Contents/Info.plist" >/dev/null 2>&1 || true
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$APP/Contents/Info.plist"
BIN="$APP/Contents/MacOS/SoundFX Organizer"
/usr/bin/lipo "$BIN" -verify_arch "$ARCH"
/usr/bin/lipo "$APP/Contents/Resources/ai_worker/ai_worker" -verify_arch "$ARCH"
/usr/bin/codesign --force --deep --sign - "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"
ARCHIVE="dist/SoundFX_Organizer_5.0.2_M1_macOS26_${ARCH}.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ARCHIVE"
archive_has_project_sources() {
  /usr/bin/zipinfo -1 "$1" | /usr/bin/awk '
    !/^SoundFX Organizer\.app(\/|$)/ && !/^__MACOSX\/SoundFX Organizer\.app(\/|$)/ { bad=1 }
    /Contents\/Resources\/(OpenSource|src|tests|scripts|\.github)(\/|$)/ { bad=1 }
    /Contents\/Resources\/(ai_worker|audio_ai|categories|custom_rules|engine|gui|i18n|legacy|low_quality|metadata_text|taxonomy)\.py$/ { bad=1 }
    END { exit bad ? 0 : 1 }
  '
}
if archive_has_project_sources "$ARCHIVE"; then
  echo "Project source or developer files leaked into final archive." >&2; exit 3
fi
