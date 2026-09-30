# Zenodo Upload Plan

Goal: make every non-confidential replication input downloadable, so the distribution
archive shrinks to essentially code + (privately shared) confidential files, and
`run_pipeline.sh`'s download step can fetch everything else.

## Already hosted — no action

| Zenodo record | Files |
|---|---|
| 3936556, 4845629, 6629738, 11461587, 14170964 | All MAG-derived bulk files (~75 GB) |
| 11374125 (public) | PQR files: `pqrs_dataset.tsv`, `inventorid_patentid.tsv` |
| 23048170 (public) | `pqrs_authorid_workid.tsv` (not in 11374125, which has only the full `authorid_workid.tsv`) |
| 15783125 | **All USPTO/PatentsView files — VERIFIED 2026-07-11**: contains the complete PatentsView final release; all 10 `g_*.tsv.zip` the pipeline uses match the local copies byte-for-byte. No USPTO upload needed. |

## To upload — ONE small record (~6 MB total)

(Two files were retired rather than uploaded. `self_plagiarism_PPPs.tsv` went on
2026-07-11 — Emma's original training set, gated behind an `original_training` flag
since removed from trainRandomForest009; it lives in `ARCHIVE/unused_data_raw/`.
`patent_families.tsv` (430 MB) went on 2026-09-04: no code reads it, and
trainRandomForest009 rebuilds the families it held from `g_us_rel_doc.tsv.zip`
(Zenodo 15783125), so it is regenerable and needs no home.)

### 1. Project-generated inputs — ~3 MB

```
ppp_grok4_refined_3DONOTDELETE.csv
ppp_grok4_refined_4_allDONOTDELETE.csv
ppp_grok4_refined_4_allDONOTDELETE_MISSING.csv
ppp_prompt.txt
```

(The `woscpc*.dta` crosswalks are small, regenerable via `woscpcxwalk/`, and ship in
the replication tar — no upload needed. `_README.pdf` is already on record 15783125.)

### 2. Internal hand-coded files — <1 MB (coded by project RAs, cleared for upload)

```
Check Pairs_Josh.csv / .xlsx
mag_patent_ppp_Henry.csv
cornell_phd_audit_of_pairs.csv
```

## Never upload

- `data/conf/wos*.dta` — Web of Science licensed extracts. Share only privately under
  the recipient's WoS license.
- `data/conf/authorhandcheck/` and `data/conf/PPP_Round2 - Responded.csv`,
  `PPP_Working Sheet - Responded*.csv` — the "golden" validation responses from paper
  authors, **collected under a promise of confidentiality**. Disclosing them would
  breach that promise. They are required only to reproduce the accuracy-validation
  statistics (applyLLMadjustment002's crosstab), not the dataset itself; a replicator
  without them gets the identical finalpppsadjusted.csv (moved from data/raw to
  data/conf on 2026-07-11).

## Suggested packaging

One new Zenodo record, e.g. **"Patent-Paper Pairs (PPP): replication inputs"**,
containing both groups ≈ **6 MB**, with the record description pointing to this
repository and REPLICATION.md.

## Storage layout (changed 2026-09-04)

Everything downloadable now lives in a **bulk directory outside this package**
(`bulk_dir.txt` / `$PPP_BULK_DIR`, `D:/ppp_data` here; fallback `./data/bulk/`), so
`data/raw` holds only the ~7 MB of files that must be uploaded or shipped, and the slim
archive no longer excludes anything. `downloadFiles002.ipynb` writes into that directory,
and the g_* fetch from 15783125 is already part of the standard flow.

## After uploading — code changes (ask Claude to do these, providing the record ID)

1. `downloadFiles002.ipynb`: add a cell fetching the new record's files into `databulk`
   (group 2's Grok-4 CSVs and group 3's hand-coded files are read from `dataraw`, so
   either point them at `dataraw` or move those reads to `databulk` — pick one).
2. `run_pipeline.sh`: move the now-downloadable entries out of `DISK_ONLY` and into
   `ZENODO_FILES`.
3. `REPLICATION.md` / `REPLICATION_README.md`: update the Data section and archive sizes.
