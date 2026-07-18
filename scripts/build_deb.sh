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
  "$BUILD_DIR/usr/share/it-projektzentrale/projects"

cp -a "$ROOT_DIR/openscanstation" "$BUILD_DIR/opt/openscanstation/"
cp -a "$ROOT_DIR/plugins" "$BUILD_DIR/opt/openscanstation/"
cp "$ROOT_DIR/version.txt" "$BUILD_DIR/opt/openscanstation/version.txt"
cp "$ROOT_DIR/README.md" "$BUILD_DIR/usr/share/doc/openscanstation/README.md"
cp "$ROOT_DIR/INSTALLATION.md" "$BUILD_DIR/usr/share/doc/openscanstation/INSTALLATION.md"
cp "$ROOT_DIR/CHANGELOG.md" "$BUILD_DIR/usr/share/doc/openscanstation/CHANGELOG.md"
cp "$ROOT_DIR/packaging/60-openscanstation-kodak.rules" "$BUILD_DIR/lib/udev/rules.d/60-openscanstation-kodak.rules"

if [ -f "$ROOT_DIR/integration/it-projektzentrale.json" ]; then
  cp "$ROOT_DIR/integration/it-projektzentrale.json" \
    "$BUILD_DIR/usr/share/it-projektzentrale/projects/openscanstation.json"
fi

cat > "$BUILD_DIR/DEBIAN/control" <<EOF
Package: $PACKAGE
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: python3, python3-usb, python3-pil, sane-utils, sane-airscan, usbutils
Maintainer: Markus Ach
Description: Modulare Scannerplattform mit WebGUI auf Port 8101
 OpenScanStation erkennt Scanner über Plugins, bietet Kodak-i2600-Diagnose,
 SANE-Scans sowie eine WebGUI und REST-Endpunkte auf TCP-Port 8101.
EOF

cat > "$BUILD_DIR/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e

if command -v udevadm >/dev/null 2>&1; then
    udevadm control --reload-rules || true
    udevadm trigger --subsystem-match=usb || true
fi

if command -v systemctl >/dev/null 2>&1; then
    systemctl daemon-reload || true
    systemctl enable openscanstation.service || true
    systemctl restart openscanstation.service || true
fi

exit 0
EOF
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"

cat > "$BUILD_DIR/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if command -v systemctl >/dev/null 2>&1; then
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
exec /usr/bin/python3 -m openscanstation.web "$@"
EOF
chmod 0755 "$BUILD_DIR/usr/bin/openscanstation-web"

cat > "$BUILD_DIR/lib/systemd/system/openscanstation.service" <<'EOF'
[Unit]
Description=OpenScanStation WebGUI and Scanner Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/openscanstation
ExecStart=/usr/bin/openscanstation-web --host 0.0.0.0 --port 8101
Restart=on-failure
RestartSec=3
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/tmp /var/tmp

[Install]
WantedBy=multi-user.target
EOF

find "$BUILD_DIR" -type d -exec chmod 0755 {} +
mkdir -p "$OUTPUT_DIR"
dpkg-deb --root-owner-group --build "$BUILD_DIR" "$OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"

echo "Paket erstellt: $OUTPUT_DIR/${PACKAGE}_${VERSION}_${ARCH}.deb"
echo "WebGUI nach Installation: http://<VM-IP>:8101"
