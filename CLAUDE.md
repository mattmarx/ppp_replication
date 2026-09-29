# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a rewrite of Emma's Patent-Paper-Pair (PPP) identification system that generates a dataset of approximately 500,000 patent-paper pairs from 1976-2023. The project identifies connections between patents and scientific papers through various similarity metrics and machine learning approaches.

## Architecture

The codebase is primarily implemented in Jupyter notebooks with Python, following a sequential data processing pipeline:

### Core Data Processing Pipeline

**Phase 1: Data Preparation**
- `buildBigPossiblePairs*.ipynb` - Creates potential patent-paper pairs for analysis

**Phase 2: Feature Calculation (run after Phase 1)**
- `addAuthorsInventors*.ipynb` & `calculateContributorOverlap*.ipynb` - Analyzes author/inventor overlap
- `encodePapersPatents*.ipynb` & `calculateContentSimilarity*.ipynb` - Computes semantic similarity using embeddings
- `calculateCitationOverlap*.ipynb` - Measures citation network overlap
- `calculateFieldOverlap*.ipynb` - Analyzes research field similarities
- `calculateGovOverlap*.ipynb` - Identifies government funding connections
- `calculateInstitutionOverlap*.ipynb` - Measures institutional affiliations
- `calculateSelfPlagiarism*.ipynb` - Detects text reuse patterns (depends on encodePapersPatents)

**Phase 3: Model Training**
- `trainRandomForest*.ipynb` - Trains classification models to identify genuine PPPs

### Key Data Directories

Every notebook resolves these through `ppp_paths.py` (`databulk`, `dataraw`, `dataconf`,
`dataint`, `datafin`) rather than hard-coding them.

- *bulk directory* (outside this repo; `bulk_dir.txt` or `$PPP_BULK_DIR`, default `./data/bulk/`) -
  the ~79 GB of public bulk files `downloadFiles002` fetches from Zenodo (OpenAlex/MAG,
  PatentsView `g_*.tsv.zip`, PQR). Kept out of the repo so a synced folder never carries them
- `data/raw/` - small inputs that cannot be re-downloaded: hand-coded CSVs, WoS↔CPC
  crosswalks, Grok-4 LLM assessments, prompt
- `data/conf/` - confidential inputs (WoS extracts, author-validation responses); never redistribute
- `data/int/` - Intermediate processed files (.parquet, .tsv formats)
- `data/fin/` - Final PPP dataset outputs
- `paperencodings/` - Embedded paper representations
- `patencodings/` - Embedded patent representations

## Dependencies

The project uses a comprehensive Python stack defined in `emmagithub/PatentPaperPairs-main/PatentPaperPairs-main/requirements.txt`:

**Core Libraries:**
- `pandas`, `numpy` - Data manipulation
- `torch`, `tensorflow` - Deep learning frameworks
- `scikit-learn` - Machine learning
- `sentence-transformers` - Text embeddings
- `spacy` - NLP processing
- `jupyter` - Notebook environment

**Database:**
- `psycopg2-binary` - PostgreSQL connectivity (requires local PostgreSQL with OpenAlex/PatentsView data)

## Development Environment

**Jupyter Notebooks:**
- Primary development environment
- Run notebooks in the execution sequence specified in README.md
- Each notebook handles a specific phase of the pipeline

**Text Processing:**
- Uses pre-trained language models for encoding papers and patents
- Requires substantial computational resources (GPU recommended)
- `compute_plagiarism_metrics001.py` provides utilities for plagiarism detection

**Data Requirements:**
- Local PostgreSQL database with OpenAlex and PatentsView data
- Pre-encoded paper and patent embeddings
- Substantial disk space for intermediate files

## File Naming Conventions

- Notebooks use numerical suffixes (001, 002, etc.) for versioning
- Data files use descriptive names with clear prefixes:
  - `possiblepairs_*` - Potential patent-paper pairs with calculated features
  - `embedded*` - Vector representations of text
  - Final outputs in `data/fin/finalppps.csv`

## Important Notes

- The pipeline must be executed sequentially as described in README.md
- Some notebooks have dependencies on earlier pipeline stages
- The project includes validation through multiple approaches (self-plagiarism detection, manual coding)
- Stata integration available via `pppapp003.do` for statistical analysis