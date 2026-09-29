#!/usr/bin/env bash
# bulk_dir.sh — resolve where the bulk (downloaded) data files live.
#
# Sourced by run_pipeline.sh, make_replication_tar.sh and finalize_replication_data.sh.
# Mirrors ppp_paths.py, which the notebooks use; precedence is the same:
#   1. $PPP_BULK_DIR
#   2. the first non-comment line of bulk_dir.txt next to this script
#   3. ./data/bulk/   (fallback — where the --full replication archive extracts them)
#
# Sets two variables:
#   BULK     as written (may be a Windows drive path, for the notebook Python)
#   BULK_SH  the same location as a path this shell can test and read
#
# run_pipeline.sh exports PPP_BULK_DIR="$BULK" so the notebooks cannot disagree.

_bulk_from_config() {
  local cfg
  cfg="$(dirname "${BASH_SOURCE[0]}")/bulk_dir.txt"
  [ -f "$cfg" ] || return 0
  sed -e 's/[[:space:]]*$//' "$cfg" | grep -v '^[[:space:]]*#' | grep -v '^[[:space:]]*$' | head -1
}

BULK="${PPP_BULK_DIR:-}"
[ -n "$BULK" ] || BULK="$(_bulk_from_config)"
[ -n "$BULK" ] || BULK="./data/bulk"
BULK="${BULK%/}"

# A drive path (D:/ppp_data) is what the Windows notebook Python wants; this shell
# needs /mnt/d/ppp_data (WSL) or /d/ppp_data (Git Bash).
BULK_SH="$BULK"
case "$BULK" in
  [A-Za-z]:[/\\]*)
    if command -v wslpath >/dev/null 2>&1; then BULK_SH=$(wslpath -u "$BULK")
    elif command -v cygpath >/dev/null 2>&1; then BULK_SH=$(cygpath -u "$BULK"); fi ;;
esac
