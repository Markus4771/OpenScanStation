#!/usr/bin/env bash
set -Eeuo pipefail

DATA_DIR="/var/lib/openscanstation"
BACKUP_DIR="/var/backups/openscanstation"
SERVICE="openscanstation.service"
ACTION="${1:-create}"
ARGUMENT="${2:-}"

log() { printf '[OpenScanStation Backup] %s\n' "$*"; }
fail() { printf '[OpenScanStation Backup] FEHLER: %s\n' "$*" >&2; exit 1; }

require_root() {
  [ "${EUID}" -eq 0 ] || fail "Bitte mit sudo ausführen."
}

ensure_directories() {
  install -d -m 0750 "$DATA_DIR" "$BACKUP_DIR"
}

create_backup() {
  ensure_directories
  local stamp host target temp_manifest
  stamp="$(date +%Y%m%d-%H%M%S)"
  host="$(hostname -s | tr -cd 'A-Za-z0-9._-')"
  target="$BACKUP_DIR/openscanstation-${host:-host}-${stamp}.tar.gz"
  temp_manifest="$(mktemp)"
  trap 'rm -f "$temp_manifest"' RETURN

  {
    printf 'format_version=1\n'
    printf 'created_at=%s\n' "$(date --iso-8601=seconds)"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'package_version=%s\n' "$(dpkg-query -W -f='${Version}' openscanstation 2>/dev/null || echo unknown)"
  } > "$temp_manifest"

  log "Erstelle Sicherung ..."
  tar --create --gzip --file "$target" \
      --owner=0 --group=0 \
      --transform='s,^,data/,' \
      -C "$DATA_DIR" . \
      --transform='s,^,metadata/,' \
      -C "$(dirname "$temp_manifest")" "$(basename "$temp_manifest")"
  chmod 0640 "$target"
  sha256sum "$target" > "${target}.sha256"
  chmod 0640 "${target}.sha256"
  log "Sicherung erstellt: $target"
  log "Prüfsumme: ${target}.sha256"
}

list_backups() {
  ensure_directories
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'openscanstation-*.tar.gz' \
    -printf '%TY-%Tm-%Td %TH:%TM  %10s Byte  %p\n' | sort -r
}

validate_archive() {
  local archive="$1" entry
  [ -f "$archive" ] || fail "Sicherungsdatei nicht gefunden: $archive"
  case "$archive" in *.tar.gz|*.tgz) ;; *) fail "Nur .tar.gz- oder .tgz-Sicherungen sind erlaubt." ;; esac

  while IFS= read -r entry; do
    case "$entry" in
      data/*|metadata/*) ;;
      *) fail "Ungültiger Pfad im Archiv: $entry" ;;
    esac
    [[ "$entry" != /* ]] || fail "Absolute Pfade im Archiv sind nicht erlaubt."
    [[ "$entry" != *"../"* && "$entry" != ".." ]] || fail "Pfadnavigation im Archiv ist nicht erlaubt."
  done < <(tar -tzf "$archive")
}

restore_backup() {
  local archive="$ARGUMENT" temp_dir safety_backup
  [ -n "$archive" ] || fail "Aufruf: openscanstation-backup restore /pfad/sicherung.tar.gz"
  archive="$(readlink -f "$archive")"
  validate_archive "$archive"
  ensure_directories

  if [ -f "${archive}.sha256" ]; then
    log "Prüfe SHA256-Prüfsumme ..."
    (cd "$(dirname "$archive")" && sha256sum -c "$(basename "${archive}.sha256")")
  else
    log "Hinweis: Keine SHA256-Datei gefunden; Archivstruktur wurde geprüft."
  fi

  safety_backup="$BACKUP_DIR/pre-restore-$(date +%Y%m%d-%H%M%S).tar.gz"
  if [ -d "$DATA_DIR" ] && [ -n "$(find "$DATA_DIR" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    log "Erstelle Rückfallsicherung: $safety_backup"
    tar -czf "$safety_backup" -C "$DATA_DIR" .
    chmod 0640 "$safety_backup"
  fi

  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' RETURN
  tar -xzf "$archive" -C "$temp_dir"
  [ -d "$temp_dir/data" ] || fail "Archiv enthält keinen Datenbereich."

  log "Stoppe Dienst und stelle Daten wieder her ..."
  systemctl stop "$SERVICE" 2>/dev/null || true
  find "$DATA_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
  cp -a "$temp_dir/data/." "$DATA_DIR/"
  chown -R root:root "$DATA_DIR"
  chmod 0750 "$DATA_DIR"
  find "$DATA_DIR" -type d -exec chmod 0750 {} +
  systemctl start "$SERVICE" 2>/dev/null || true
  log "Wiederherstellung abgeschlossen."
}

show_help() {
  cat <<'EOF'
OpenScanStation Sicherung

  openscanstation-backup create
  openscanstation-backup list
  openscanstation-backup restore /pfad/sicherung.tar.gz

Gesichert werden alle Daten unter /var/lib/openscanstation,
insbesondere Scans, Dokumentendatenbank und Scanprofile.
EOF
}

require_root
case "$ACTION" in
  create) create_backup ;;
  list) list_backups ;;
  restore) restore_backup ;;
  help|-h|--help) show_help ;;
  *) fail "Unbekannte Aktion '$ACTION'. Erlaubt: create, list, restore, help" ;;
esac
