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
  "$BUILD_DIR/lib/systemd/system" \
  "$BUILD_DIR/usr/share/doc/openscanstation" \
  "$BUILD_DIR/usr/share/it-projektzentrale/projects" \
  "$BUILD_DIR/var/lib/openscanstation/scans" \
  "$BUILD_DIR/var/lib/openscanstation/network-inbox"

cp -a "$ROOT_DIR/openscanstation" "$BUILD_DIR/opt/openscanstation/"
cp -a "$ROOT_DIR/plugins" "$BUILD_DIR/opt/openscanstation/"
cp "$ROOT_DIR/version.txt" "$BUILD_DIR/opt/openscanstation/version.txt"
cp "$ROOT_DIR/README.md" "$BUILD_DIR/usr/share/doc/openscanstation/README.md"
cp "$ROOT_DIR/INSTALLATION.md" "$BUILD_DIR/usr/share/doc/openscanstation/INSTALLATION.md"
cp "$ROOT_DIR/CHANGELOG.md" "$BUILD_DIR/usr/share/doc/openscanstation/CHANGELOG.md"
cp "$ROOT_DIR/packaging/60-openscanstation-kodak.rules" "$BUILD_DIR/lib/udev/rules.d/60-openscanstation-kodak.rules"
cp "$ROOT_DIR/packaging/openscanstation-brother-buttons" "$BUILD_DIR/usr/bin/openscanstation-brother-buttons"
cp "$ROOT_DIR/packaging/openscanstation-brother-buttons.service" "$BUILD_DIR/lib/systemd/system/openscanstation-brother-buttons.service"
cp "$ROOT_DIR/packaging/openscanstation-brother-network" "$BUILD_DIR/usr/bin/openscanstation-brother-network"
cp "$ROOT_DIR/packaging/openscanstation-brother-network.service" "$BUILD_DIR/lib/systemd/system/openscanstation-brother-network.service"
chmod 0755 "$BUILD_DIR/usr/bin/openscanstation-brother-buttons"
chmod 0755 "$BUILD_DIR/usr/bin/openscanstation-brother-network"

if [ -f "$ROOT_DIR/integration/it-projektzentrale.json" ]; then
  cp "$ROOT_DIR/integration/it-projektzentrale.json" "$BUILD_DIR/usr/share/it-projektzentrale/projects/openscanstation.json"
fi

cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3, python3-usb, python3-pil, sane-utils, sane-airscan, usbutils, tesseract-ocr, tesseract-ocr-deu, poppler-utils, zbar-tools, snmp, samba
Maintainer: Markus Ach
Description: Zentrale Scannerplattform mit einheitlicher WebGUI
 OpenScanStation erkennt Scanner über Plugins und bietet Scanprofile,
 Dokumentenkatalog, OCR, Volltextsuche, Barcode-/QR-Erkennung,
 Kopieren, Hardwareverwaltung und REST-API.
EOF

cat > "$BUILD_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if ! getent group openscanstation >/dev/null 2>&1; then
    addgroup --system openscanstation
fi
if ! getent passwd openscanstation >/dev/null 2>&1; then
    adduser --system --ingroup openscanstation --home /var/lib/openscanstation --no-create-home --shell /usr/sbin/nologin openscanstation
fi
for group in scanner lp; do
    if getent group "$group" >/dev/null 2>&1; then
        adduser openscanstation "$group" >/dev/null 2>&1 || true
    fi
done
mkdir -p /var/lib/openscanstation/scans /var/lib/openscanstation/network-inbox
chown -R openscanstation:openscanstation /var/lib/openscanstation
chmod 0750 /var/lib/openscanstation /var/lib/openscanstation/scans
if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=usb || true
fi
if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
    systemctl enable openscanstation.service || true
    systemctl restart openscanstation.service || true
    systemctl enable openscanstation-brother-buttons.service || true
    systemctl restart openscanstation-brother-buttons.service || true
    systemctl enable openscanstation-brother-network.service || true
    systemctl restart openscanstation-brother-network.service || true
fi
exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"

cat > "$BUILD_DIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
    systemctl stop openscanstation-brother-buttons.service || true
    systemctl disable openscanstation-brother-buttons.service || true
    systemctl stop openscanstation-brother-network.service || true
    systemctl disable openscanstation-brother-network.service || true
    systemctl stop openscanstation.service || true
    systemctl disable openscanstation.service || true
fi
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

cat > "$BUILD_DIR/usr/bin/openscanstation-web" <<'EOF'
#!/bin/sh
set -e
cd /opt/openscanstation
exec /usr/bin/python3 -m openscanstation.web_runtime "$@"
EOF
chmod 0755 "$BUILD_DIR/usr/bin/openscanstation-web"

cat > "$BUILD_DIR/lib/systemd/system/openscanstation.service" <<'EOF'
[Unit]
Description=OpenScanStation Internal Web and Scanner Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/openscanstation
ExecStart=/usr/bin/openscanstation-web --host 127.0.0.1 --port 8111
Restart=on-failure
RestartSec=3
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/openscanstation

[Install]
WantedBy=multi-user.target
EOF

find "$BUILD_DIR" -type d -exec chmod 0755 {} +
chmod 0750 "$BUILD_DIR/var/lib/openscanstation" "$BUILD_DIR/var/lib/openscanstation/scans"
chmod 0770 "$BUILD_DIR/var/lib/openscanstation/network-inbox"
mkdir -p "$OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"

echo "Paket erstellt: $OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
echo "Einheitliche WebGUI nach Installation: http://<VM-IP>:8101"
