"""Data locations for the PPP pipeline.

Every notebook imports its directory roots from here instead of hard-coding them:

    databulk  the ~79 GB of public bulk files fetched by downloadFiles002
              (MAG/OpenAlex, PatentsView, PQR). Kept OUTSIDE this folder so a
              synced tree (Dropbox, OneDrive, Box) never has to carry them.
    dataraw   small inputs that ship with the replication archive and cannot be
              re-downloaded: hand-coded CSVs, WoS/CPC crosswalks, LLM assessments.
    dataconf  confidential inputs (WoS extracts, author-validation responses).
    dataint   regenerable intermediates.
    datafin   final outputs.

databulk is resolved in this order:

    1. the PPP_BULK_DIR environment variable (run_pipeline.sh sets it)
    2. the first non-comment line of bulk_dir.txt next to this file
    3. ./data/bulk/ — the fallback, used by the --full replication archive,
       which extracts the bulk files to exactly that path

The path may be written either way round for the WSL/Windows divide — D:/ppp_data
or /mnt/d/ppp_data — and is translated to whichever side the running interpreter
is on, so the same config works from Git Bash, WSL and Windows Python.
"""

import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_FALLBACK = './data/bulk/'


def _read_config():
    """First non-blank, non-comment line of bulk_dir.txt, or '' if absent."""
    cfg = os.path.join(_HERE, 'bulk_dir.txt')
    if not os.path.exists(cfg):
        return ''
    with open(cfg, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith('#'):
                return line
    return ''


def _translate(d):
    """Rewrite a WSL path as a Windows one (or the reverse) for the running Python."""
    drive = re.match(r'^([A-Za-z]):/(.*)$', d)
    mount = re.match(r'^/mnt/([A-Za-z])/(.*)$', d)
    if os.name == 'nt' and mount:
        return f"{mount.group(1).upper()}:/{mount.group(2)}"
    if os.name != 'nt' and drive:
        return f"/mnt/{drive.group(1).lower()}/{drive.group(2)}"
    return d


def _resolve_bulk():
    d = os.environ.get('PPP_BULK_DIR', '').strip() or _read_config() or _FALLBACK
    # Normalise to a trailing '/' so 'databulk + filename' works everywhere.
    return _translate(d.replace('\\', '/').rstrip('/')) + '/'


databulk = _resolve_bulk()
dataraw = './data/raw/'
dataconf = './data/conf/'
dataint = './data/int/'
datafin = './data/fin/'

if __name__ == '__main__':
    for name in ('databulk', 'dataraw', 'dataconf', 'dataint', 'datafin'):
        path = globals()[name]
        print(f"{name:9s} {path:24s} exists={os.path.isdir(path)}  ({os.path.abspath(path)})")
