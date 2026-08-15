#!/bin/bash

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "Fehler: Dieser Build muss auf macOS ausgeführt werden."
    exit 1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
    echo "Fehler: Dieser Build ist für Apple Silicon (arm64) vorgesehen."
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv-macos"
ICONSET_DIR="$PROJECT_DIR/build/macos/Transkript.iconset"
ICNS_PATH="$PROJECT_DIR/build/macos/transkript-logo.icns"
SOURCE_ICON="$PROJECT_DIR/transkript-logo.png"
DMG_DIR="$PROJECT_DIR/build/macos/dmg"
DMG_PATH="$PROJECT_DIR/dist/Transkript-macOS-Apple-Silicon.dmg"

cd "$PROJECT_DIR"

if [[ ! -f "$SOURCE_ICON" ]]; then
    echo "Fehler: transkript-logo.png wurde nicht gefunden."
    exit 1
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r requirement.txt

if ! "$VENV_DIR/bin/python" -c "import tkinter" >/dev/null 2>&1; then
    echo "Fehler: Die verwendete Python-Installation enthält kein Tkinter."
    echo "Installiere Python inklusive Tk-Unterstützung und starte den Build erneut."
    exit 1
fi

mkdir -p "$ICONSET_DIR"

make_icon() {
    local size="$1"
    local filename="$2"
    sips -z "$size" "$size" "$SOURCE_ICON" --out "$ICONSET_DIR/$filename" >/dev/null
}

make_icon 16 icon_16x16.png
make_icon 32 icon_16x16@2x.png
make_icon 32 icon_32x32.png
make_icon 64 icon_32x32@2x.png
make_icon 128 icon_128x128.png
make_icon 256 icon_128x128@2x.png
make_icon 256 icon_256x256.png
make_icon 512 icon_256x256@2x.png
make_icon 512 icon_512x512.png
make_icon 1024 icon_512x512@2x.png

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

"$VENV_DIR/bin/pyinstaller" \
    --noconfirm \
    --clean \
    --windowed \
    --onedir \
    --target-arch arm64 \
    --osx-bundle-identifier app.transkript.desktop \
    --name Transkript \
    --icon "$ICNS_PATH" \
    --collect-data ttkbootstrap \
    --collect-all imageio_ffmpeg \
    --add-data "transkript-logo.png:." \
    gui.py

ditto -c -k --sequesterRsrc --keepParent \
    "$PROJECT_DIR/dist/Transkript.app" \
    "$PROJECT_DIR/dist/Transkript-macOS-Apple-Silicon.zip"

rm -rf "$DMG_DIR"
mkdir -p "$DMG_DIR"
ditto "$PROJECT_DIR/dist/Transkript.app" "$DMG_DIR/Transkript.app"
ln -s /Applications "$DMG_DIR/Applications"
hdiutil create \
    -volname "Transkript" \
    -srcfolder "$DMG_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo
echo "Fertig:"
echo "  $PROJECT_DIR/dist/Transkript.app"
echo "  $PROJECT_DIR/dist/Transkript-macOS-Apple-Silicon.zip"
echo "  $DMG_PATH"
