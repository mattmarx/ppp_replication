#!/usr/bin/env bash
# run_pipeline.sh — execute the full PPP pipeline headlessly, notebook by notebook, in order.
#
# Works from Git Bash or WSL. Each notebook is executed in place (its cell outputs
# are saved back into the .ipynb, so the run is auditable) and logged to logs/.
# Stops at the first failure; resume with:  bash run_pipeline.sh --from <notebook.ipynb>
#
# Usage:
#   bash run_pipeline.sh                 # full run
#   bash run_pipeline.sh --from trainRandomForest010.ipynb   # resume from a stage
#   PPP_BULK_DIR=/d/ppp_data bash run_pipeline.sh            # bulk data elsewhere
#
# The ~79 GB of downloadable inputs are NOT kept in this directory; see the
# "bulk storage" section below and bulk_dir.txt.
#
# Expected total runtime is DAYS (embedding + local-LLM stages). Run it somewhere
# it can survive a logout (e.g. a persistent terminal), and disable system sleep.

set -u
cd "$(dirname "$0")"

NOTEBOOKS=(
  buildBigPossiblePairs003.ipynb
  addAuthorsInventors001.ipynb
  calculateContributorOverlap001.ipynb
  encodePapersPatents002.ipynb
  calculateContentSimilarity001.ipynb
  calculateCitationOverlap001.ipynb
  calculateFieldOverlap001.ipynb
  calculateGovOverlap002.ipynb
  calculateInstitutionOverlap005.ipynb
  calculateSelfPlagiarism004.ipynb
  trainRandomForest010.ipynb   # random forest + Grok-4 adjustment (applyLLMadjustment002 folded in)
)

FROM=""
if [ "${1:-}" = "--from" ] && [ -n "${2:-}" ]; then
  FROM="$2"
fi

# ------------------------------------------------------------------ preflight
echo "=== PPP pipeline runner ==="

PY=""
for cand in ./.venv313/Scripts/python.exe ./wslvenv/bin/python python3 python; do
  if { command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; } \
     && "$cand" -c "import nbconvert, pandas" >/dev/null 2>&1; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "FAIL: no Python with nbconvert+pandas found."
  echo "Run: .venv313/Scripts/python -m pip install -r requirements.txt"
  exit 1
fi
echo "Python: $PY"

if ! "$PY" -c "import torch; import sys; sys.exit(0 if torch.cuda.is_available() else 1)" 2>/dev/null; then
  echo "FAIL: torch.cuda.is_available() is False — the encoding notebooks require a CUDA GPU."
  echo "PyPI ships CPU-only torch on Windows; reinstall from the CUDA wheel index:"
  echo "  .venv313/Scripts/python -m pip install --force-reinstall torch==2.9.1 --index-url https://download.pytorch.org/whl/cu126"
  exit 1
fi
echo "GPU: CUDA available"

# Check Ollama from the notebook runtime's Python (WSL curl cannot reach a
# Windows-side Ollama at localhost, but the Windows python.exe can).
if ! "$PY" -c "import urllib.request,sys; sys.exit(0 if b'llama3.1:8b' in urllib.request.urlopen('http://localhost:11434/api/tags', timeout=5).read() else 1)" 2>/dev/null; then
  echo "FAIL: Ollama is not running with llama3.1:8b (needed by calculateInstitutionOverlap005)."
  echo "Start Ollama and run: ollama pull llama3.1:8b"
  exit 1
fi
echo "Ollama: llama3.1:8b available"

# ---------------------------------------------------------------- temp storage
# All pipeline intermediates are written to data/int (fully regenerable).
# To keep that churn out of Dropbox:
#   default        : data/int stays in place but is marked with Dropbox's
#                    com.dropbox.ignored stream (on disk, never synced)
#   TEMP_FILES=dir : data/int becomes a directory junction to <dir>, so
#                    intermediates live entirely outside the Dropbox tree:
#                      TEMP_FILES=/c/ppp_temp bash run_pipeline.sh
# Only change TEMP_FILES between runs — never while a run is in progress.
TEMP_FILES="${TEMP_FILES:-}"
LINKTYPE=$(powershell.exe -NoProfile -Command "(Get-Item -LiteralPath 'data\int' -ErrorAction SilentlyContinue).LinkType" 2>/dev/null | tr -d '\r')
if [ -n "$TEMP_FILES" ]; then
  mkdir -p "$TEMP_FILES" || { echo "FAIL: cannot create TEMP_FILES=$TEMP_FILES"; exit 1; }
  if command -v cygpath >/dev/null 2>&1; then TF_WIN=$(cygpath -w "$TEMP_FILES"); else TF_WIN=$(wslpath -w "$TEMP_FILES"); fi
  if [ "$LINKTYPE" = "Junction" ]; then
    echo "Temp: data/int is already a junction (intermediates outside Dropbox)"
  else
    if [ -d data/int ] && [ -n "$(ls -A data/int 2>/dev/null)" ]; then
      echo "Temp: moving existing data/int contents to $TEMP_FILES ..."
      mv data/int/* "$TEMP_FILES"/ || { echo "FAIL: could not move data/int contents"; exit 1; }
    fi
    rmdir data/int 2>/dev/null
    powershell.exe -NoProfile -Command "New-Item -ItemType Junction -Path 'data\int' -Target '$TF_WIN' | Out-Null" \
      && echo "Temp: data/int is now a junction -> $TF_WIN (outside Dropbox)" \
      || { echo "FAIL: could not create junction data/int -> $TF_WIN"; exit 1; }
  fi
elif [ "$LINKTYPE" != "Junction" ]; then
  mkdir -p data/int
  powershell.exe -NoProfile -Command "Set-Content -Path 'data\int' -Stream com.dropbox.ignored -Value 1" 2>/dev/null \
    && echo "Temp: data/int marked Dropbox-ignored (on disk, not synced)"
else
  echo "Temp: data/int is a junction (intermediates outside Dropbox)"
fi

# ---------------------------------------------------------------- bulk storage
# The ~79 GB of downloadable inputs (MAG/OpenAlex, PatentsView, PQR) live OUTSIDE
# this directory so a synced tree never carries them and the archive stays small.
# Location, in order of precedence:
#   PPP_BULK_DIR=/some/dir bash run_pipeline.sh   # this run only
#   bulk_dir.txt                                  # persistent, next to this script
#   ./data/bulk/                                  # fallback (the --full archive)
# The notebooks resolve it identically through ppp_paths.py; exporting PPP_BULK_DIR
# below means they cannot disagree with this script.
. ./bulk_dir.sh
export PPP_BULK_DIR="$BULK"
mkdir -p "$BULK_SH" || { echo "FAIL: cannot create bulk directory $BULK_SH"; exit 1; }
echo "Bulk data: $BULK"
case "$(cd "$BULK_SH" && pwd)" in
  "$PWD"/*) echo "NOTE: the bulk directory is inside this package; set bulk_dir.txt to a path"
            echo "      outside any synced folder to keep ~79 GB out of Dropbox/OneDrive." ;;
esac

# Create the full directory skeleton (idempotent).
mkdir -p data/raw data/conf data/int data/fin logs

# ---------------------------------------------------------- input data check
# Class 1: NOT downloadable — must come from the replication archive (USPTO/
# PatentsView bulk files, hand-coded validation, LLM assessments, crosswalks).
DISK_ONLY=(
  data/raw/woscpcclass.dta data/raw/woscpcsubclass.dta
  data/raw/woscpcclassscore.dta data/raw/woscpcsubclassscore.dta
  data/raw/ppp_grok4_refined_3DONOTDELETE.csv
  data/raw/ppp_grok4_refined_4_allDONOTDELETE.csv
  data/raw/ppp_grok4_refined_4_allDONOTDELETE_MISSING.csv
  data/raw/ppp_prompt.txt
)
MISS=0
for f in "${DISK_ONLY[@]}"; do
  [ -e "$f" ] || { echo "MISSING (not re-downloadable): $f"; MISS=1; }
done
if [ "$MISS" -ne 0 ]; then
  echo "FAIL: the files above ship in the replication archive and cannot be fetched."
  echo "Restore them from ppp_replication_<date>.tar. See REPLICATION.md."
  exit 1
fi
for f in data/conf/wosdoi.dta data/conf/wosgrantnums.dta data/conf/wosusgrants.dta; do
  [ -e "$f" ] || { echo "FAIL: $f missing — confidential WoS input required by calculateGovOverlap002"; \
                   echo "(not in public archives; obtain from the authors under a WoS license)"; exit 1; }
done
if [ ! -d data/conf/authorhandcheck ]; then
  echo "WARNING: data/conf/authorhandcheck/ missing (confidential author-validation"
  echo "responses; not publicly distributed). The pipeline will complete and produce"
  echo "the full dataset, but the final accuracy-scoring crosstab will be skipped."
fi

# Class 2: Zenodo-hosted — auto-fetch via downloadFiles002.ipynb if any is absent.
# These all live in the bulk directory ($BULK), never in data/.
ZENODO_FILES=(
  PaperAbstracts.nt.bz2 papercitations.zip papertitle.zip
  paperauthoridaffiliationname.zip paperauthororder.zip authoridname_normalized.zip
  magfield_oecd_wos_crosswalk.zip paperdoi.zip paperdates.zip
  _pcs_oa.csv
  g_application.tsv.zip g_assignee_disambiguated.tsv.zip g_cpc_at_issue.tsv.zip
  g_gov_interest.tsv.zip g_gov_interest_contracts.tsv.zip g_gov_interest_org.tsv.zip
  g_inventor_disambiguated.tsv.zip g_patent.tsv.zip g_patent_abstract.tsv.zip
  g_us_rel_doc.tsv.zip
  pqrs_dataset.tsv pqrs_authorid_workid.tsv inventorid_patentid.tsv
)
NEED_DL=0
for f in "${ZENODO_FILES[@]}"; do
  [ -e "$BULK_SH/$f" ] || { echo "to download: $BULK/$f"; NEED_DL=1; }
done
if [ "$NEED_DL" -eq 1 ]; then
  echo "=== Download step: fetching missing Zenodo-hosted inputs (up to ~79 GB; this can take hours)"
  DLLOG="logs/$(date +%Y%m%d_%H%M%S)_downloadFiles002.log"
  "$PY" -m jupyter nbconvert --to notebook --execute --inplace \
      --ExecutePreprocessor.timeout=-1 --ExecutePreprocessor.kernel_name=python3 \
      downloadFiles002.ipynb >"$DLLOG" 2>&1 \
    || { echo "FAIL: download step failed (see $DLLOG)"; exit 1; }
  for f in "${ZENODO_FILES[@]}"; do
    [ -e "$BULK_SH/$f" ] || { echo "FAIL: still missing after download: $BULK/$f (see $DLLOG)"; MISS=1; }
  done
  [ "$MISS" -ne 0 ] && exit 1
  echo "Download step complete."
fi
mkdir -p "../../../Apps/Overleaf/ppprev1/figures" 2>/dev/null \
  || echo "WARNING: could not create the Overleaf figures dir; trainRandomForest010 may fail at its figure-saving cells."
echo

# ------------------------------------------------------------------ execution
STAMP=$(date +%Y%m%d_%H%M%S)
SKIPPING=1
[ -z "$FROM" ] && SKIPPING=0

for nb in "${NOTEBOOKS[@]}"; do
  if [ "$SKIPPING" -eq 1 ]; then
    if [ "$nb" = "$FROM" ]; then SKIPPING=0; else echo "skip  $nb"; continue; fi
  fi
  LOG="logs/${STAMP}_${nb%.ipynb}.log"
  echo "=== $(date '+%F %T')  START $nb (log: $LOG)"
  "$PY" -m jupyter nbconvert --to notebook --execute --inplace \
      --ExecutePreprocessor.timeout=-1 \
      --ExecutePreprocessor.kernel_name=python3 \
      "$nb" >"$LOG" 2>&1
  RC=$?
  if [ $RC -ne 0 ]; then
    echo "=== $(date '+%F %T')  FAILED $nb (exit $RC)"
    echo "Last lines of $LOG:"
    tail -20 "$LOG"
    echo
    echo "Fix the problem, then resume with:  bash run_pipeline.sh --from $nb"
    exit $RC
  fi
  echo "=== $(date '+%F %T')  DONE  $nb"
done

echo
echo "=== PIPELINE COMPLETE ==="
echo "Outputs in data/fin/:"
ls -la data/fin/
