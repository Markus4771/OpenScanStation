#!/usr/bin/env bash
set -u

BASE_URL="${1:-http://127.0.0.1:8107}"
FAILED=0
ROUTES=(/ /monitor /setup /scanners /profiles /printers /network /usb /brother /maintenance /drivers /diagnostics /support)

printf 'OpenScanStation Hardware-Selbsttest: %s\n' "$BASE_URL"
for route in "${ROUTES[@]}"; do
  code="$(curl -sS --max-time 45 -o /tmp/openscanstation-hardware-selftest.out -w '%{http_code}' "${BASE_URL}${route}" 2>/dev/null || printf '000')"
  if [[ "$code" == "200" ]]; then
    printf 'OK      %-16s HTTP %s\n' "$route" "$code"
  else
    printf 'FEHLER  %-16s HTTP %s\n' "$route" "$code"
    head -c 300 /tmp/openscanstation-hardware-selftest.out 2>/dev/null || true
    printf '\n'
    FAILED=1
  fi
done

exit "$FAILED"
