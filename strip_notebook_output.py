"""Git clean filter: strip outputs and execution counts from a notebook read on stdin.

Enabled per clone with:
  git config filter.stripoutput.clean "python strip_notebook_output.py"
  git config filter.stripoutput.smudge cat
Working-copy notebooks keep their outputs; only the committed version is stripped.
"""
import json
import sys

nb = json.loads(sys.stdin.buffer.read().decode("utf-8"))
for cell in nb.get("cells", []):
    if cell.get("cell_type") == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
        cell.get("metadata", {}).pop("execution", None)
sys.stdout.buffer.write((json.dumps(nb, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
