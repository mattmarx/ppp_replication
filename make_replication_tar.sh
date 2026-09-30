#!/usr/bin/env bash
# make_replication_tar.sh — bundle this directory into a distributable replication archive.
#
# Runs from within the package directory (invoke from anywhere; it cd's itself).
# Writes the tar ONE LEVEL UP by default so the archive never contains itself.
#
# Usage:
#   bash make_replication_tar.sh                    # slim archive (<1 GB) -> ../ppp_replication_<date>.tar
#   bash make_replication_tar.sh --full             # include the bulk data files too (~82 GB)
#   bash make_replication_tar.sh --out /e/archives  # write the tar somewhere else (e.g. non-synced disk)
#
# The archive extracts to a single top-level folder: ppp_replication/
#
# data/conf is NEVER included in ANY build — it holds confidential Web of Science
# extracts and author-validation responses collected under a promise of
# confidentiality. Those are shared privately, case by case, by the authors only.
#
# SLIM (default): ships only what cannot be re-downloaded — hand-coded files,
# Grok-4 assessment CSVs, prompt, WoS/CPC crosswalks, code, docs.
# All of that is data/raw, which is now small (~7 MB). run_pipeline.sh auto-downloads
# the remaining ~79 GB (MAG files, USPTO/PatentsView files, PQR files) from public
# Zenodo records on first run, into the bulk directory — which lives OUTSIDE this
# package (see bulk_dir.txt / ppp_paths.py) and is therefore never in a slim archive.
#
# FULL: also bundles the bulk directory, as data/bulk/ — exactly the fallback location
# ppp_paths.py uses when no bulk_dir.txt or PPP_BULK_DIR is set, so an extracted --full
# archive runs offline with no configuration.
#
# data/int and data/fin ship as empty directories (run_pipeline.sh recreates them anyway).
# If this folder syncs to Dropbox, prefer --out to a non-synced location.

set -u
cd "$(dirname "$0")"

FULL=0
OUTDIR=".."
while [ $# -gt 0 ]; do
  case "$1" in
    --full)   FULL=1; shift ;;
    --out)    OUTDIR="$2"; shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# The Zenodo-refetchable bulk files (~79 GB) live outside this package; a --full
# build appends them as data/bulk/. downloadFiles002.ipynb re-fetches them otherwise
# (records 3936556, 4845629, 11374125, 11461587, 14170964, 15783125, 23048170).
. ./bulk_dir.sh

STAMP=$(date +%Y%m%d)
NAME="ppp_replication"
TARBASE="${NAME}_${STAMP}$([ $FULL -eq 1 ] && echo _full).tar"
TARPATH="$OUTDIR/$TARBASE"
[ -e "$TARPATH" ] && { echo "FAIL: $TARPATH already exists; remove it or pick --out elsewhere."; exit 1; }
mkdir -p "$OUTDIR" || { echo "FAIL: cannot create $OUTDIR"; exit 1; }

# ---------------------------------------------------------------- manifest
# Code + docs at root (explicit list — nothing stray gets in).
ROOT_FILES=(
  run_pipeline.sh
  finalize_replication_data.sh
  REPLICATION.md
  REPLICATION_README.md
  requirements.txt
  requirements_wsl_batch_env.txt
  README.md
  QUICKSTART.md
  BATCH_CLASSIFY_README.md
  ppp_paths.py
  bulk_dir.sh
  compute_plagiarism_metrics001.py
  classify_ppp_claude_batch.py
  merge_ppp_data.py
  validate_batch_output.py
)

NOTEBOOKS=( *.ipynb )

# ---------------------------------------------------------------- preflight
FAIL=0
for f in "${ROOT_FILES[@]}" "${NOTEBOOKS[@]}"; do
  [ -e "$f" ] || { echo "MISSING: $f"; FAIL=1; }
done
if [ $FULL -eq 1 ]; then
  [ -d "$BULK_SH" ] && [ -n "$(ls -A "$BULK_SH" 2>/dev/null)" ] \
    || { echo "MISSING/EMPTY bulk data directory: $BULK_SH"; FAIL=1; }
fi
[ -d data/raw ] && [ -n "$(ls -A data/raw)" ] || { echo "MISSING/EMPTY: data/raw"; FAIL=1; }
[ -d woscpcxwalk ] || { echo "MISSING: woscpcxwalk/"; FAIL=1; }
[ "$FAIL" -ne 0 ] && { echo "FAIL: manifest incomplete; fix the items above."; exit 1; }

# Refuse to package Dropbox placeholders (0 bytes on disk -> corrupt archive).
# Only the paths that actually go INTO the archive are checked: data/raw, plus the
# bulk directory on --full. data/conf is never packaged, and data/int / data/fin
# ship as empty stubs, so placeholders there are irrelevant here.
if command -v powershell.exe >/dev/null 2>&1; then
  ROOT_WIN=$(command -v wslpath >/dev/null 2>&1 && wslpath -w "$PWD" || cygpath -w "$PWD")
  # A --full build also packages the bulk directory, so check it too.
  BULK_TARGET=""
  if [ $FULL -eq 1 ]; then
    BULK_WIN=$(command -v wslpath >/dev/null 2>&1 && wslpath -w "$BULK_SH" || cygpath -w "$BULK_SH")
    BULK_TARGET=", \"$BULK_WIN\""
  fi
  PS='
$root = "__ROOT__"
Add-Type -MemberDefinition "[DllImport(`"kernel32.dll`", SetLastError=true, CharSet=CharSet.Unicode)] public static extern uint GetCompressedFileSizeW(string lpFileName, out uint lpFileSizeHigh);" -Name K -Namespace W
$bad = 0
Get-ChildItem -LiteralPath @("$root\data\raw"__BULK__) -Recurse -File | ForEach-Object {
  $high = [uint32]0
  $low = [W.K]::GetCompressedFileSizeW($_.FullName, [ref]$high)
  $ondisk = ([uint64]$high * 4294967296) + $low
  if ($_.Length -gt 0 -and $ondisk -lt ($_.Length * 0.9)) { $_.FullName; $script:bad++ }
}
"PLACEHOLDERS=$bad"'
  PS=${PS//__ROOT__/$ROOT_WIN}
  PS=${PS//__BULK__/$BULK_TARGET}
  ENC=$(printf '%s' "$PS" | iconv -f utf-8 -t utf-16le | base64 -w0)
  HOUT=$(powershell.exe -NoProfile -EncodedCommand "$ENC" 2>/dev/null | tr -d '\r')
  echo "$HOUT" | grep -v '^PLACEHOLDERS=' | head -20
  if ! echo "$HOUT" | grep -q 'PLACEHOLDERS=0'; then
    echo "FAIL: the files above are cloud placeholders (not on disk). Hydrate them first."
    exit 1
  fi
fi

# ---------------------------------------------------------------- build
echo "Building $TARPATH $([ $FULL -eq 1 ] && echo '(full: incl. Zenodo-refetchable files)')"
[ $FULL -eq 1 ] && echo "Full build is ~82 GB (incl. bulk data from $BULK_SH) and will take a while..." || echo "Slim build (<1 GB; run_pipeline.sh auto-downloads ~79 GB from Zenodo on first run)"
echo "data/conf is NOT included (confidential) in any build."

DIRNAME_REAL=$(basename "$PWD")
TAR_ARGS=(
  --transform "s|^$DIRNAME_REAL|$NAME|"
  -C ..
)
INCLUDE=()
for f in "${ROOT_FILES[@]}" "${NOTEBOOKS[@]}"; do INCLUDE+=("$DIRNAME_REAL/$f"); done
INCLUDE+=("$DIRNAME_REAL/woscpcxwalk" "$DIRNAME_REAL/data/raw")

EXCLUDES=( --exclude="$DIRNAME_REAL/data/raw/chunk_*" )

tar -cf "$TARPATH" "${TAR_ARGS[@]}" \
    "${EXCLUDES[@]}" \
    "${INCLUDE[@]}" \
  || { echo "FAIL: tar returned an error"; rm -f "$TARPATH"; exit 1; }

# --full: append the bulk data files as data/bulk/ (ppp_paths.py's fallback location).
if [ $FULL -eq 1 ]; then
  echo "Appending bulk data from $BULK_SH as data/bulk/ ..."
  BULKLIST=$(mktemp)
  (cd "$BULK_SH" && ls -A) >"$BULKLIST"
  tar -rf "$TARPATH" -C "$BULK_SH" --transform "s|^|$NAME/data/bulk/|" -T "$BULKLIST" \
    || { echo "FAIL: could not append the bulk files"; rm -f "$TARPATH" "$BULKLIST"; exit 1; }
  rm -f "$BULKLIST"
fi

# Empty directory stubs so the tree extracts complete.
STUB=$(mktemp -d)
mkdir -p "$STUB/$NAME/data/int" "$STUB/$NAME/data/fin" "$STUB/$NAME/data/conf" "$STUB/$NAME/logs"
STUBDIRS=( "$NAME/data/int" "$NAME/data/fin" "$NAME/data/conf" "$NAME/logs" )
if [ $FULL -eq 0 ]; then
  mkdir -p "$STUB/$NAME/data/bulk"
  STUBDIRS+=( "$NAME/data/bulk" )
fi
tar -rf "$TARPATH" -C "$STUB" "${STUBDIRS[@]}"
rm -rf "$STUB"

# Safety net: verify no confidential path slipped into the archive.
if tar -tf "$TARPATH" | grep -q "data/conf/."; then
  echo "FATAL: archive contains data/conf contents — deleting it. Report this bug."
  rm -f "$TARPATH"
  exit 1
fi

echo
echo "=== DONE ==="
ls -lh "$TARPATH"
echo "Verify listing:  tar -tf '$TARPATH' | head"
echo "Extracts to:     $NAME/"
echo "REMINDER: data/conf (confidential WoS + author validation) is not included;"
echo "recipients needing calculateGovOverlap002 must obtain it privately from the authors."
