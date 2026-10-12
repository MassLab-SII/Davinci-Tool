# Development

Run from the repository root.

```bash
pip install -r requirements.txt
pip install -e '.[dev]'

# EES
python -m unittest discover -s tests/ees -v
python -m compileall -q src/ees

# EGTS
PYTHONPATH=src/egts python -m pytest tests/egts -q
python -m compileall -q src/egts scripts/egts
for f in scripts/egts/*.sh; do bash -n "$f"; done
```

Generated outputs belong under `output/`, `workspaces/`, `artifacts/`, or `outputs/`, which are
ignored by Git. Never commit API keys, private endpoints, or generated user data.
