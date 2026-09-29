# Replicating the Patent-Paper Pairs (PPP) Dataset

This package regenerates the PPP dataset — patent-paper pairs (1976-2023) linking USPTO
patents to the scientific papers they emerged from — **entirely from the data shipped in
this directory**. One script runs the whole pipeline end to end.

The canonical output is 42,967 pairs: 16,738 high-confidence (97.4% precision per
independent hand-validation, n=115) and 26,229 mid-confidence (84.0%, n=50).

## TL;DR

```bash
# 1. Python 3.11 environment
py -3.11 -m venv .venv313                       # Windows; on Linux: python3.11 -m venv .venv313
.venv313/Scripts/python -m pip install -r requirements.txt
# GPU torch (PyPI's Windows wheel is CPU-only):
.venv313/Scripts/python -m pip install --force-reinstall torch==2.9.1 \
    --index-url https://download.pytorch.org/whl/cu126

# 2. Local LLM for institution matching
#    Install Ollama (https://ollama.com), then:
ollama pull llama3.1:8b

# 3. Say where the ~79 GB of bulk data should live (any disk outside this folder;
#    skip this to use ./data/bulk/, which is where a --full archive extracts them):
echo D:/ppp_data > bulk_dir.txt          # or: export PPP_BULK_DIR=/mnt/d/ppp_data

# 4. Run everything (~2 days wall-clock; see timings below).
#    If you received the slim archive, the script automatically downloads the
#    missing Zenodo-hosted bulk files (~79 GB) into that directory first.
bash run_pipeline.sh
```

Final outputs land in `data/fin/`; the published dataset is `finalpppsadjusted.csv`
(columns: `magid`, `patent_id`, `confidence_level` ∈ {high, mid}).

## Computational requirements

Measured on the reference machine (July 2026 canonical run): 32 logical cores,
512 GB RAM, NVIDIA RTX 4090 (24 GB), Windows 11 + Git Bash.

| Resource | Minimum | Notes |
|---|---|---|
| RAM | **320 GB** (512 GB comfortable) | peak ~300 GB in calculateCitationOverlap001 (whole-file load of the 10 GB-compressed citation table) |
| GPU | CUDA GPU, ~8 GB VRAM (24 GB used in practice) | sentence-transformer encoding + Ollama; larger VRAM = larger encode batches |
| CPU | 16+ cores strongly recommended | self-plagiarism stage runs a 24-worker pool for ~25 h |
| Disk | ~300 GB free | ~79 GB bulk data (separate directory), ~8 GB other inputs, ~50 GB intermediates |
| Wall-clock | **~48-52 hours** total | breakdown below |

Per-stage wall-clock on the reference machine:

| Stage | Time | Dominant resource |
|---|---|---|
| buildBigPossiblePairs003 | ~45 min | RAM/disk |
| addAuthorsInventors001 | ~4-5 h | CPU (single core) |
| calculateContributorOverlap001 | ~1.5 h | CPU |
| encodePapersPatents002 | **~14 h** | GPU (3.47 M papers + 1.01 M patents encoded) |
| calculateContentSimilarity001 | ~5 min | GPU |
| calculateCitationOverlap001 | ~40 min | **RAM (~300 GB peak)** |
| calculateFieldOverlap001 | ~15 min | RAM |
| calculateGovOverlap002 | ~20 min | RAM |
| calculateInstitutionOverlap005 | ~2 h | GPU (Ollama llama3.1:8b, temperature 0) |
| calculateSelfPlagiarism004 | **~25 h** | CPU (24-core diff_match_patch over 12.4 M text pairs) |
| trainRandomForest009 | ~35 min | CPU (single core; incl. patent-family rebuild) |
| applyLLMadjustment002 | ~10 min | trivial |

## Directory structure

`run_pipeline.sh` creates any missing directories; only the **data inputs** must be
supplied (they ship with the replication archive).

```
mattrewriteofemma/
├── run_pipeline.sh              # master script — runs the 12 notebooks in order
├── ppp_paths.py                 # where each data directory lives (imported by every notebook)
├── bulk_dir.sh / bulk_dir.txt   # the bulk directory's location, for the shell scripts / persistently
├── requirements.txt             # Python 3.11 environment (see torch note inside)
├── *.ipynb                      # pipeline notebooks (executed headlessly by the script)
├── compute_plagiarism_metrics001.py
├── woscpcxwalk/                 # Stata tooling that originally built the WoS↔CPC crosswalks
│                                #   (their outputs ship in data/raw; Stata NOT needed to replicate)
├── data/
│   ├── raw/        [INPUT]     # ~7 MB. Master copies that CANNOT be re-downloaded (see Data)
│   ├── conf/       [INPUT]     # confidential: 3 WoS files (~5 GB) + author-validation
│   │                           #   responses (authorhandcheck/, PPP_*Responded*.csv) —
│   │                           #   DO NOT REDISTRIBUTE (respondents promised confidentiality)
│   ├── int/        [generated] # intermediates; safe to delete; recreated by the pipeline
│   └── fin/        [generated] # final outputs
└── logs/           [generated] # one log per notebook per run

<bulk directory>   [INPUT]      # ~79 GB, OUTSIDE this folder (D:/ppp_data by default here):
                                #   every file downloadFiles002 fetches from Zenodo — MAG/OpenAlex,
                                #   PatentsView g_*.tsv.zip, PQR. Kept out so a synced folder never
                                #   carries them and the replication archive stays small.
                                #   Set it in bulk_dir.txt or $PPP_BULK_DIR; the fallback is
                                #   ./data/bulk/, where a --full archive extracts them.
```

## Data

The distribution archive (`ppp_replication_<date>.tar`, under 1 GB) ships only the
files that cannot be re-downloaded (hand-coded files, LLM assessments, prompt,
crosswalks) — that is all of `data/raw`, now ~7 MB.
`run_pipeline.sh` detects missing Zenodo-hosted files at startup and downloads them
automatically (~79 GB — the MAG bulk files, USPTO/PatentsView files, and PQR files,
via `downloadFiles002.ipynb`) into the **bulk directory** before running the pipeline.
An optional `--full` archive variant (~82 GB) bundles those too, as `data/bulk/`, for
fully-offline replication.

The bulk directory deliberately lives outside the package: it is regenerable from
public Zenodo records, so there is no reason for a synced folder or an archive to
carry 79 GB of it. Point it anywhere with a line in `bulk_dir.txt` (persistent) or
`PPP_BULK_DIR` (one run); with neither set it falls back to `./data/bulk/`.

**The archive never contains `data/conf/`** — the confidential Web of Science extracts
and the author-validation responses (collected under a promise of confidentiality).
Their roles differ:
- The three WoS `.dta` files are **required** (calculateGovOverlap002 builds a model
  feature from them); replicators must obtain them privately from the authors under
  their own WoS license. The pipeline fails fast with a clear message if they are absent.
- The author-validation responses (`authorhandcheck/`) are **optional**: without them
  the pipeline still produces the identical dataset and only skips the final accuracy
  crosstab.

Two provenance classes:

1. **Re-downloadable** (the bulk directory): the MAG-derived bulk files, the
   PatentsView `g_*.tsv.zip` files and the PQR files come from public Zenodo records
   (4845629, 14170964, 11461587, 3936556, 11374125, 15783125);
   `downloadFiles002.ipynb` fetches them if ever needed.
2. **Disk-only masters** (everything else): the PatentsView `g_*.tsv.zip` bulk files
   (PatentsView has migrated its download site), all hand-coded validation files, the
   LLM prompts, the Grok-4 assessment CSVs (`*DONOTDELETE*.csv` — regenerating them
   requires paid, non-deterministic API calls), the WoS↔CPC crosswalk `.dta` files, and
   `data/conf` (confidential WoS extracts, licensed — excluded from public copies of the
   archive; only `calculateGovOverlap002` reads them).

`data/int` and `data/fin` are fully regenerable — delete them freely and re-run.

(Per-file provenance — which Zenodo record holds which file, the complete do-not-delete
list — is in `REPLICATION_README.md`.)

## Software environment

- **Python 3.11** (3.12+ also works; 3.11 is what the canonical run used).
  `requirements.txt` pins all versions. Two gotchas handled in it:
  - On Windows, PyPI's `torch` wheel is CPU-only — reinstall from the cu126 index
    (command in TL;DR). Verify: `python -c "import torch; print(torch.cuda.is_available())"`.
  - `peft` must stay at the pinned 0.15.2 (0.18+ breaks the pinned transformers).
- **Ollama** with `llama3.1:8b` pulled and the server running (used only by
  calculateInstitutionOverlap005, at temperature 0).
- **Hugging Face**: `all-MiniLM-L6-v2` downloads automatically on first use (~90 MB).
- No database, no Stata, no paid API keys are required for replication.

## Running

```bash
bash run_pipeline.sh                                  # full run
bash run_pipeline.sh --from <notebook.ipynb>          # resume after a failure
TEMP_FILES=/c/ppp_temp bash run_pipeline.sh           # store intermediates outside a synced folder
PPP_BULK_DIR=/e/ppp_data bash run_pipeline.sh         # bulk data on another disk, this run only
```

The script preflights the environment (Python packages, CUDA, Ollama, input data),
creates missing directories, then executes each notebook headlessly in order, saving
executed outputs back into the notebooks and logging to `logs/`. It stops at the first
failure and prints the resume command. Notebook cell output is buffered until each
notebook finishes — during long stages, activity is best judged by CPU/GPU load, not logs.

Practical advice for the multi-day run: disable system sleep and OS updates; if the
package lives in a Dropbox/OneDrive-synced folder, the script marks `data/int` as
sync-ignored automatically (or use `TEMP_FILES` to relocate it entirely), and the bulk
data is already outside the package by design — keep `bulk_dir.txt` pointed at a
non-synced disk.

## Outputs

| File (in `data/fin/`) | Contents |
|---|---|
| `finalpppsadjusted.csv` | **The dataset.** `magid` (MAG paper id), `patent_id` (USPTO), `confidence_level` (high/mid) |
| `finalpppsadjusted_prescored.csv` | same universe before labeling, including the score-2 band ("low", ~65% precision) excluded from the published file |
| `finalppps.csv` | raw random-forest scores before the LLM adjustment step |

## Determinism

All stochastic steps are seeded (`random_state=42`: the random-forest classifier, the
negative-training-sample draw, shuffles, train/test split). Re-running from
`trainRandomForest009` onward on the same intermediates is **bit-for-bit reproducible**
(verified by MD5 across consecutive runs). A full end-to-end re-run is *near*-identical
rather than exact, for three documented reasons: (1) `diff_match_patch` uses a 1-second
wall-clock budget per comparison, so plagiarism metrics depend marginally on machine
load; (2) Ollama at temperature 0 is greedy but not formally guaranteed deterministic;
(3) GPU floating-point epsilon on threshold-boundary pairs. In practice these move band
membership by well under a percent and precision not at all.

## Validation

Hand-validation against 230+ independently coded pairs (raters graded pairs A/B =
genuine, C/D = not). The validation responses were collected from paper authors under a
promise of confidentiality and live in `data/conf/authorhandcheck/`; without them the
pipeline still produces the identical dataset but skips the accuracy crosstab.

| Band | N | Precision (A/B) |
|---|---|---|
| high | 16,738 | 97.4% (n=115) |
| mid | 26,229 | 84.0% (n=50) |
| low (excluded from published file) | 16,731 | ~65-75% (n=12-18 across runs) |

Archived vintages with provenance notes: `../PPP_final_outputs/README.md`.

## Known quirks

1. `trainRandomForest009.ipynb` writes diagnostic figures to
   `../../../Apps/Overleaf/ppprev1/figures/`; the script pre-creates this path. To keep
   figures local, edit `graphoutputdir` in that notebook.
2. The standalone tools (`classify_ppp_claude_batch.py`, `merge_ppp_data.py`,
   `PPPs_with_scientist_inventorsGPU.ipynb`) are not part of the replication pipeline —
   see `BATCH_CLASSIFY_README.md` for their use (they require LLM API keys).
3. `ARCHIVE/` contains superseded experiments and a side branch; nothing in the pipeline
   depends on it.
