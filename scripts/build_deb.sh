#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/version.txt")"
PACKAGE="openscanstation"
ARCH="all"
BUILD_DIR="$ROOT_DIR/build/${PACKAGE}_${VERSION}_${ARCH}"
OUTPUT_DIR="$ROOT_DIR/dist"

rm -rf "$BUILD_DIR"
mkdir -p \
  "$BUILD_DIR/DEBIAN" \
  "$BUILD_DIR/opt/openscanstation" \
  "$BUILD_DIR/usr/bin" \
  "$BUILD_DIR/lib/udev/rules.d" \
  "$BUILD_DIR/usr/share/doc/openscanstation"

cp -a "$ROOT_DIR/openscanstation" "$BUILD_DIR/opt/openscanstation/"
cp -a "$ROOT_DIR/plugins" "$BUILD_DIR/opt/openscanstation/"
cp "$ROOT_DIR/version.txt" "$BUILD_DIR/opt/openscanstation/version.txt"
cp "$ROOT_DIR/README.md" "$BUILD_DIR/usr/share/doc/openscanstation/README.md"
cp "$ROOT_DIR/INSTALLATION.md" "$BUILD_DIR/usr/share/doc/openscanstation/INSTALLATION.md"
cp "$ROOT_DIR/CHANGELOG.md" "$BUILD_DIR/usr/share/doc/openscanstation/CHANGELOG.md"
cp "$ROOT_DIR/packaging/60-openscanstation-kodak.rules" "$BUILD_DIR/lib/udev/rules.d/60-openscanstation-kodak.rules"

cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3, python3-usb, sane-utils, sane-airscan
Maintainer: Markus Ach
Description: Modulare Scannerplattform für Linux und Raspberry Pi
 OpenScanStation erkennt Scanner über austauschbare Plugins. Version 0.1.1
 unterstützt die Erkennung des Kodak i2600 über USB und von Samsung-AirScan-
 Geräten über SANE/AirScan.
EOF

cat > "$BUILD_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=usb || true
fi

exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"

cat > "$BUILD_DIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/prerm"

cat > "$BUILD_DIR/usr/bin/openscanstation" <<'EOF'
#!/bin/sh
set -e
cd /opt/openscanstation
exec /usr/bin/python3 -m openscanstation "$@"
EOF
chmod 0755 "$BUILD_DIR/usr/bin/openscanstation"

find "$BUILD_DIR" -type d -exec chmod 0755 {} +
mkdir -p "$OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"

echo "Paket erstellt: $OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
