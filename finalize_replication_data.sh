#!/usr/bin/env bash
# finalize_replication_data.sh
#
# Run this from the mattrewriteofemma directory AFTER Dropbox has finished
# downloading ("Make available offline") the data files. Idempotent: re-run
# until it reports PASS.
#
# What it does:
#   1. Verifies every required data file is actually hydrated on disk
#      (size-on-disk >= 90% of logical size, via GetCompressedFileSizeW —
#      does not itself trigger any Dropbox downloads). Only files inside this
#      (synced) folder can be placeholders; the bulk data directory lives outside
#      it, so those files are merely checked for existence.
#   2. Moves data/fin -> ../PPP_final_outputs and recreates an empty data/fin,
#      so data/int and data/fin can be deleted and the pipeline re-run cleanly.
#   3. Smoke-reads one key input per pipeline stage with pandas.
#
# Usage: bash finalize_replication_data.sh

set -u
cd "$(dirname "$0")"
. ./bulk_dir.sh
# Works from WSL (wslpath) or Git Bash (cygpath).
if command -v wslpath >/dev/null 2>&1; then
  ROOT_WIN=$(wslpath -w "$PWD")
elif command -v cygpath >/dev/null 2>&1; then
  ROOT_WIN=$(cygpath -w "$PWD")
else
  echo "ERROR: neither wslpath (WSL) nor cygpath (Git Bash) found; cannot determine the Windows path."
  exit 1
fi
FAIL=0

echo "=== PPP replication data finalizer ==="
echo "Directory: $PWD"
echo

# ---------------------------------------------------------------- 1. hydration
echo "--- Step 1: checking Dropbox hydration of required files ---"

# Required files outside data/raw (data/raw and data/fin are checked in full).
REQUIRED_EXTRA=(
  "data/conf/wosdoi.dta"
  "data/conf/wosgrantnums.dta"
  "data/conf/wosusgrants.dta"
)

for f in "${REQUIRED_EXTRA[@]}"; do
  if [ ! -e "$f" ]; then
    echo "MISSING ENTIRELY: $f"
    FAIL=1
  fi
done

# The bulk downloads live outside this folder, so they cannot be Dropbox
# placeholders — existence is all that matters. run_pipeline.sh re-fetches any
# that are absent.
echo "Bulk data directory: $BULK"
for f in pqrs_authorid_workid.tsv inventorid_patentid.tsv pqrs_dataset.tsv \
         _pcs_oa.csv paperdates.zip g_patent.tsv.zip PaperAbstracts.nt.bz2; do
  [ -e "$BULK_SH/$f" ] || echo "  absent (will be re-downloaded): $f"
done

# PowerShell: list every not-fully-hydrated file under the given paths.
PS_SCRIPT='
$root = "__ROOT__"
Add-Type -MemberDefinition "[DllImport(`"kernel32.dll`", SetLastError=true, CharSet=CharSet.Unicode)] public static extern uint GetCompressedFileSizeW(string lpFileName, out uint lpFileSizeHigh);" -Name K -Namespace W
$targets = @("$root\data\raw", "$root\data\fin", "$root\data\conf")
$bad = 0; $ok = 0; $badbytes = [uint64]0
foreach ($t in $targets) {
  if (-not (Test-Path -LiteralPath $t)) { continue }
  Get-ChildItem -LiteralPath $t -Recurse -File | ForEach-Object {
    # conf: only the files the pipeline actually reads matter
    if ($t -like "*conf" -and $_.Name -notin @("wosdoi.dta","wosgrantnums.dta","wosusgrants.dta")) { return }
    $high = [uint32]0
    $low = [W.K]::GetCompressedFileSizeW($_.FullName, [ref]$high)
    $ondisk = ([uint64]$high * 4294967296) + $low
    if ($_.Length -gt 0 -and $ondisk -lt ($_.Length * 0.9)) {
      "NOT-HYDRATED {0,10:N2} GB  {1}" -f ($_.Length/1GB), $_.FullName.Substring($root.Length+1)
      $script:bad++; $script:badbytes += $_.Length
    } else { $script:ok++ }
  }
}
"SUMMARY hydrated=$ok not_hydrated=$bad remaining_gb={0:N1}" -f ($badbytes/1GB)
'
PS_SCRIPT=${PS_SCRIPT//__ROOT__/$ROOT_WIN}
ENC=$(printf '%s' "$PS_SCRIPT" | iconv -f utf-8 -t utf-16le | base64 -w0)
HYDRA_OUT=$(powershell.exe -NoProfile -EncodedCommand "$ENC" 2>/dev/null | tr -d '\r')
echo "$HYDRA_OUT" | grep -v '^SUMMARY' | head -50
SUMMARY=$(echo "$HYDRA_OUT" | grep '^SUMMARY')
echo "$SUMMARY"
if echo "$SUMMARY" | grep -q 'SUMMARY hydrated=0 '; then
  echo "Hydration check: FAILED — scanned 0 files; the data directories were not found."
  FAIL=1
elif echo "$SUMMARY" | grep -q 'not_hydrated=0'; then
  echo "Hydration check: OK"
else
  echo "Hydration check: FAILED — sync the files above in Dropbox, then re-run."
  FAIL=1
fi
echo

# ------------------------------------------------------- 2. move data/fin out
echo "--- Step 2: moving data/fin -> ../PPP_final_outputs ---"
DEST="../PPP_final_outputs"
if [ "$FAIL" -ne 0 ]; then
  echo "Skipped (fix hydration first so final outputs are not moved as placeholders)."
elif [ -d "$DEST" ] && [ -n "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "Already done: $DEST exists and is non-empty. Leaving it untouched."
  mkdir -p data/fin
elif [ ! -d data/fin ] || [ -z "$(ls -A data/fin 2>/dev/null)" ]; then
  echo "data/fin is missing or empty and $DEST is not populated — nothing to move."
  echo "(If final outputs should exist, restore them before re-running.)"
  mkdir -p data/fin
  FAIL=1
else
  mv data/fin "$DEST" && mkdir -p data/fin \
    && echo "Moved. Final outputs now in $(cd "$DEST" && pwd); empty data/fin recreated." \
    || { echo "Move FAILED"; FAIL=1; }
fi
echo

# ------------------------------------------------------------- 3. smoke tests
echo "--- Step 3: pandas smoke-read of key inputs ---"
if [ "$FAIL" -ne 0 ]; then
  echo "Skipped (reading placeholder files would trigger large Dropbox downloads)."
  echo
  echo "=== FAIL: see messages above, then re-run this script. ==="
  exit 1
fi
# Find a Python that has pandas (WSL venv, Windows venvs, then system Pythons).
PY=""
for cand in ./.venv313/Scripts/python.exe ./wslvenv/bin/python ./venv/Scripts/python.exe ./.venv/Scripts/python.exe python3 python; do
  if { command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; } \
     && "$cand" -c "import pandas" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "FAIL: no Python with pandas found (tried wslvenv, venv, .venv, python3, python)."
  echo "Install pandas into one of them ('pip install pandas') or run this script from WSL."
  echo
  echo "=== FAIL: see messages above, then re-run this script. ==="
  exit 1
fi
echo "(using $PY)"
"$PY" - <<'EOF'
import sys
import pandas as pd
from ppp_paths import databulk, dataraw, dataconf
print(f"  (bulk directory: {databulk})")
checks = [
    (databulk + "_pcs_oa.csv",                            dict(nrows=5)),
    (databulk + "paperdates.zip",                         dict(nrows=5, sep="\t", header=None, compression="zip")),
    (databulk + "g_patent.tsv.zip",                       dict(nrows=5, sep="\t", compression="zip")),
    (databulk + "pqrs_dataset.tsv",                       dict(nrows=5, sep="\t")),
    (dataraw + "ppp_grok4_refined_4_allDONOTDELETE.csv",  dict(nrows=5)),
]
stata_checks = [dataconf + "wosdoi.dta", dataraw + "woscpcclass.dta"]
failed = 0
for path, kw in checks:
    try:
        df = pd.read_csv(path, **kw)
        print(f"  OK   {path} ({len(df.columns)} cols)")
    except Exception as e:
        print(f"  FAIL {path}: {e}")
        failed += 1
for path in stata_checks:
    try:
        it = pd.read_stata(path, chunksize=5)
        df = next(iter(it))
        print(f"  OK   {path} ({len(df.columns)} cols)")
    except Exception as e:
        print(f"  FAIL {path}: {e}")
        failed += 1
sys.exit(1 if failed else 0)
EOF
[ $? -ne 0 ] && FAIL=1
echo

# ------------------------------------------------------------------ 4. result
if [ "$FAIL" -eq 0 ]; then
  echo "=== PASS: replication data finalized. ==="
  echo "data/int and data/fin may now be deleted at any time and regenerated by the pipeline."
else
  echo "=== FAIL: see messages above, then re-run this script. ==="
  exit 1
fi
