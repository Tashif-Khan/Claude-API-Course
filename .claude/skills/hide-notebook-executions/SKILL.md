---
name: hide-notebook-executions
description: Hide all execution traces in a Jupyter notebook — clear cell outputs, reset execution counters, and collapse code cell inputs. Use when the user asks to hide/clear code cell executions, outputs, or execution counts in a .ipynb file.
---

# Hide notebook executions

Remove all visible signs of execution from a Jupyter notebook (`.ipynb`), leaving the markdown and code content intact.

## Arguments

The argument is the notebook to clean. If none is given, use the notebook currently open in the IDE; if that's not a `.ipynb` file either, ask which notebook to clean.

## Steps

1. Before clearing, inspect the notebook's code cell outputs. If any outputs look valuable (plots, computed results the user may want to keep — as opposed to error tracebacks or noise), confirm with the user before deleting them.

2. Run this Python against the notebook (adjust the path):

```python
import json

p = r"<notebook path>"
nb = json.load(open(p, encoding="utf-8"))
for c in nb["cells"]:
    if c["cell_type"] == "code":
        c["outputs"] = []
        c["execution_count"] = None
        c.setdefault("metadata", {}).setdefault("jupyter", {})["source_hidden"] = True
json.dump(nb, open(p, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
```

This does three things per code cell:
- clears `outputs`
- resets `execution_count` to `None` (blank `[ ]` badge)
- sets `metadata.jupyter.source_hidden: true` so the code input renders collapsed in VS Code / JupyterLab

3. If the user only wants outputs/counters hidden but the code visible, skip the `source_hidden` line.

4. Remind the user to reopen or revert the file in their editor to pick up the on-disk change.
