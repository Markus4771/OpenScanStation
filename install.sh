#!/usr/bin/env bash
set -Eeuo pipefail

REPO="Markus4771/OpenScanStation"
REPO_URL="https://github.com/${REPO}.git"
API_URL="https://api.github.com/repos/${REPO}/releases/latest"
PACKAGE="openscanstation"
SERVICE="openscanstation.service"
WEB_PORT="8101"
SOURCE_DIR="/opt/OpenScanStation"
ACTION="${1:-install}"

log() { printf '[OpenScanStation] %s\n' "$*" >&2; }
fail() { printf '[OpenScanStation] FEHLER: %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "${EUID}" -eq 0 ] || fail "Bitte mit sudo ausführen: sudo bash install.sh ${ACTION}"
}

install_base_dependencies() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y ca-certificates curl git python3 dpkg-dev
}

download_latest_release() {
  local temp_dir="$1"
  local metadata asset_url asset_name
  metadata="$temp_dir/release.json"

  local -a args=(-fsSL -H "Accept: application/vnd.github+json")
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    args+=(-H "Authorization: Bearer ${GITHUB_TOKEN}")
  fi

  if ! curl "${args[@]}" "$API_URL" -o "$metadata"; then
    return 1
  fi

  asset_url="$(python3 - "$metadata" <<'PY'
import json, sys
with open(sys.argv[1], encoding='utf-8') as handle:
    release = json.load(handle)
for asset in release.get('assets', []):
    name = asset.get('name', '')
    if name.startswith('openscanstation_') and name.endswith('_all.deb'):
        print(asset.get('browser_download_url', ''))
        break
PY
)"

  [ -n "$asset_url" ] || return 1
  asset_name="${asset_url##*/}"
  log "Lade Release-Paket ${asset_name} herunter ..."
  curl "${args[@]}" -L "$asset_url" -o "$temp_dir/$asset_name"
  printf '%s\n' "$temp_dir/$asset_name"
}

build_from_source() {
  local temp_dir="$1"
  log "Kein passendes Release-Paket gefunden. Baue aus dem aktuellen GitHub-Stand."

  if [ -d "$SOURCE_DIR/.git" ]; then
    git -C "$SOURCE_DIR" fetch --prune origin >&2
    git -C "$SOURCE_DIR" reset --hard origin/main >&2
  else
    rm -rf "$SOURCE_DIR"
    git clone --depth 1 "$REPO_URL" "$SOURCE_DIR" >&2
  fi

  chmod +x "$SOURCE_DIR/scripts/build_deb.sh"
  "$SOURCE_DIR/scripts/build_deb.sh" >&2

  local package_file
  package_file="$(find "$SOURCE_DIR/dist" -maxdepth 1 -type f -name 'openscanstation_*_all.deb' -print | sort -V | tail -n 1)"
  [ -n "$package_file" ] || fail "Beim Build wurde kein Debian-Paket erzeugt."
  cp "$package_file" "$temp_dir/"
  printf '%s\n' "$temp_dir/${package_file##*/}"
}

wait_for_health() {
  local attempt
  for attempt in $(seq 1 15); do
    if curl -fsS --max-time 3 "http://127.0.0.1:${WEB_PORT}/health" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

install_or_update() {
  install_base_dependencies
  local temp_dir package_file
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT

  package_file="$(download_latest_release "$temp_dir" || true)"
  if [ -z "$package_file" ] || [ ! -f "$package_file" ]; then
    package_file="$(build_from_source "$temp_dir")"
  fi

  log "Installiere ${package_file##*/} ..."
  apt-get install -y "$package_file"
  systemctl daemon-reload
  systemctl enable --now "$SERVICE"
  systemctl restart "$SERVICE"

  log "Prüfe Dienst und WebGUI ..."
  if wait_for_health; then
    local address
    address="$(hostname -I 2>/dev/null | awk '{print $1}')"
    log "Installation erfolgreich. WebGUI: http://${address:-SERVER-IP}:${WEB_PORT}"
  else
    systemctl --no-pager --full status "$SERVICE" || true
    log "Paket wurde installiert, aber der Health-Check antwortet nicht."
    log "Diagnose: journalctl -u ${SERVICE} -n 100 --no-pager"
    exit 2
  fi
}

show_status() {
  dpkg-query -W -f='Paket: ${Package}\nVersion: ${Version}\nStatus: ${Status}\n' "$PACKAGE" 2>/dev/null || true
  systemctl --no-pager --full status "$SERVICE" || true
  printf '\nHealth-Check: '
  curl -fsS --max-time 5 "http://127.0.0.1:${WEB_PORT}/health" || printf 'nicht erreichbar'
  printf '\n'
}

uninstall_package() {
  apt-get remove -y "$PACKAGE"
  log "Scandaten unter /var/lib/openscanstation wurden nicht gelöscht."
}

require_root
case "$ACTION" in
  install|update)
    install_or_update
    ;;
  status)
    show_status
    ;;
  uninstall)
    uninstall_package
    ;;
  *)
    fail "Unbekannte Aktion '$ACTION'. Erlaubt: install, update, status, uninstall"
    ;;
esac
