#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/version.txt")"
DEB_FILE="$ROOT_DIR/dist/openscanstation_${VERSION}_all.deb"
WORK_DIR="$(mktemp -d)"
NEW_DEB="$ROOT_DIR/dist/openscanstation_${VERSION}_all.new.deb"

cleanup() {
  rm -r "$WORK_DIR" 2>/dev/null || true
  rm -f "$NEW_DEB" 2>/dev/null || true
}
trap cleanup EXIT

chmod +x "$ROOT_DIR/scripts/build_deb.sh"
"$ROOT_DIR/scripts/build_deb.sh"

test -f "$DEB_FILE"
dpkg-deb -R "$DEB_FILE" "$WORK_DIR/package"
install -D -m 0755 "$ROOT_DIR/scripts/backup.sh" "$WORK_DIR/package/usr/bin/openscanstation-backup"
install -d -m 0750 "$WORK_DIR/package/var/backups/openscanstation"
dpkg-deb --root-owner-group --build "$WORK_DIR/package" "$NEW_DEB"
mv "$NEW_DEB" "$DEB_FILE"

echo "Release-Paket erstellt: $DEB_FILE"
echo "Enthalten: /usr/bin/openscanstation-backup"
