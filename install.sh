#!/usr/bin/env bash
set -Eeuo pipefail

REPO="Markus4771/OpenScanStation"
REPO_URL="https://github.com/${REPO}.git"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
PACKAGE="openscanstation"
WEB_PORT="8101"
SOURCE_DIR="/opt/OpenScanStation"
ACTION="${1:-install}"
CLEANUP_DIR=""
SERVICES=(
  openscanstation.service
  openscanstation-device-settings.service
  openscanstation-storage-settings.service
  openscanstation-workflows.service
  openscanstation-classification.service
  openscanstation-copy.service
  openscanstation-hardware.service
)

log() { printf '[OpenScanStation] %s\n' "$*" >&2; }
fail() { printf '[OpenScanStation] FEHLER: %s\n' "$*" >&2; exit 1; }
require_root() { [ "${EUID}" -eq 0 ] || fail "Bitte mit sudo ausführen: sudo bash install.sh ${ACTION}"; }
cleanup() { [ -n "${CLEANUP_DIR:-}" ] && rm -rf -- "$CLEANUP_DIR" || true; }
trap cleanup EXIT

install_base_dependencies() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y \
    ca-certificates curl git python3 python3-pil python3-usb dpkg-dev \
    sane-utils sane-airscan usbutils \
    tesseract-ocr tesseract-ocr-deu poppler-utils zbar-tools \
    cups cups-client printer-driver-all
  systemctl enable --now cups.service || true
}

curl_github() {
  local -a args=(-fsSL -H "Accept: application/vnd.github+json")
  if [ -n "${GITHUB_TOKEN:-}" ]; then args+=(-H "Authorization: Bearer ${GITHUB_TOKEN}"); fi
  curl "${args[@]}" "$@"
}

download_latest_release() {
  local temp_dir="$1" metadata asset_url asset_name
  metadata="$temp_dir/release.json"
  curl_github "$API_URL" -o "$metadata" || return 1
  asset_url="$(python3 - "$metadata" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    release = json.load(handle)
for asset in release.get('assets', []):
    name = asset.get('name', '')
    if name.startswith('openscanstation_') and name.endswith('_all.deb'):
        print(asset.get('browser_download_url', '')); break
PY
)"
  [ -n "$asset_url" ] || return 1
  asset_name="${asset_url##*/}"
  log "Lade Release-Paket ${asset_name} herunter ..."
  curl_github -L "$asset_url" -o "$temp_dir/$asset_name"
  printf '%s\n' "$temp_dir/$asset_name"
}

configure_clone_url() {
  if [ -n "${GITHUB_TOKEN:-}" ]; then printf 'https://Markus4771:%s@github.com/%s.git\n' "$GITHUB_TOKEN" "$REPO"; else printf '%s\n' "$REPO_URL"; fi
}

build_from_source() {
  local temp_dir="$1" clone_url package_file
  clone_url="$(configure_clone_url)"
  log "Kein passendes Release-Paket gefunden. Baue das vollständige Release aus dem aktuellen GitHub-Stand."
  if [ -d "$SOURCE_DIR/.git" ]; then
    git -C "$SOURCE_DIR" remote set-url origin "$clone_url"
    git -C "$SOURCE_DIR" fetch --prune origin >&2
    git -C "$SOURCE_DIR" reset --hard origin/main >&2
    git -C "$SOURCE_DIR" remote set-url origin "$REPO_URL"
  else
    rm -rf "$SOURCE_DIR"
    git clone --depth 1 "$clone_url" "$SOURCE_DIR" >&2 || fail "Repository konnte nicht geladen werden."
    git -C "$SOURCE_DIR" remote set-url origin "$REPO_URL"
  fi
  chmod +x "$SOURCE_DIR/scripts/build_deb.sh" "$SOURCE_DIR/scripts/build_release.sh"
  "$SOURCE_DIR/scripts/build_release.sh" >&2
  package_file="$(find "$SOURCE_DIR/dist" -maxdepth 1 -type f -name 'openscanstation_*_all.deb' -print | sort -V | tail -n 1)"
  [ -n "$package_file" ] || fail "Beim Release-Build wurde kein Debian-Paket erzeugt."
  cp "$package_file" "$temp_dir/"
  printf '%s\n' "$temp_dir/${package_file##*/}"
}

start_services() {
  systemctl daemon-reload
  for service in "${SERVICES[@]}"; do
    if systemctl list-unit-files "$service" --no-legend 2>/dev/null | grep -q "^${service}"; then
      if ! systemctl enable --now "$service"; then
        log "WARNUNG: ${service} konnte nicht gestartet werden."
        systemctl --no-pager --full status "$service" || true
        continue
      fi
      systemctl restart "$service" || true
    else
      log "Hinweis: ${service} ist im Paket nicht vorhanden."
    fi
  done
  systemctl enable --now openscanstation-watchdog.timer 2>/dev/null || true
}

wait_for_health() {
  for attempt in $(seq 1 20); do curl -fsS --max-time 3 "http://127.0.0.1:${WEB_PORT}/health" >/dev/null && return 0; sleep 1; done
  return 1
}

show_addresses() {
  local address
  address="$(hostname -I 2>/dev/null | awk '{print $1}')"; address="${address:-SERVER-IP}"
  log "Hauptoberfläche:       http://${address}:8101"
  log "Geräteeinstellungen:  http://${address}:8102"
  log "Speicherziele:        http://${address}:8103"
  log "Workflows:            http://${address}:8104"
  log "Dokumenterkennung:    http://${address}:8105"
  log "Kopieren:             http://${address}:8106"
  log "Hardware-Zentrale:    http://${address}:8107"
}

install_or_update() {
  install_base_dependencies
  local package_file
  CLEANUP_DIR="$(mktemp -d)"
  package_file="$(download_latest_release "$CLEANUP_DIR" || true)"
  if [ -z "$package_file" ] || [ ! -f "$package_file" ]; then package_file="$(build_from_source "$CLEANUP_DIR")"; fi
  chmod 0644 "$package_file"
  log "Installiere ${package_file##*/} ..."
  apt-get install -y "$package_file"
  start_services
  log "Prüfe Dienst und Haupt-WebGUI ..."
  if wait_for_health; then log "Installation erfolgreich."; show_addresses; else systemctl --no-pager --full status openscanstation.service || true; fail "Health-Check antwortet nicht. Diagnose: journalctl -u openscanstation.service -n 100 --no-pager"; fi
}

show_status() {
  dpkg-query -W -f='Paket: ${Package}\nVersion: ${Version}\nStatus: ${Status}\n' "$PACKAGE" 2>/dev/null || true
  for service in "${SERVICES[@]}"; do printf '\n=== %s ===\n' "$service"; systemctl --no-pager --full status "$service" 2>/dev/null || true; done
  printf '\nHealth-Checks:\n'
  for port in 8101 8102 8103 8104 8105 8106 8107; do printf 'Port %s: ' "$port"; curl -fsS --max-time 3 "http://127.0.0.1:${port}/health" || printf 'nicht erreichbar'; printf '\n'; done
}

uninstall_package() { apt-get remove -y "$PACKAGE"; log "Scandaten und Einstellungen unter /var/lib/openscanstation wurden nicht gelöscht."; }

require_root
case "$ACTION" in
  install|update) install_or_update ;;
  status) show_status ;;
  uninstall) uninstall_package ;;
  *) fail "Unbekannte Aktion '$ACTION'. Erlaubt: install, update, status, uninstall" ;;
esac
