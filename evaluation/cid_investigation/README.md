# CID Investigation

This folder contains the focused investigation track for `main.cid`.

## Purpose

The goal is to verify that the agent can reliably understand and query the CID
catalog before changing production behavior. The investigation separates:

- deterministic database evidence;
- CID-specific probe questions;
- agent execution traces;
- scoring and failure taxonomy;
- general fixes only after grouped root-cause evidence.

## Task 1 Baseline

Run the deterministic CID inventory:

```bash
./.venv/bin/python evaluation/cid_investigation/build_cid_baseline.py
```

The script writes `evaluation/cid_investigation/results/cid_baseline_<timestamp>.json`
with:

- CID row counts and distinct keys;
- hierarchy counts for `DS_CAPITULO`, `DS_GRUPO`, and `DS_CATEGORIA`;
- chapter distribution;
- lexical samples for common disease terms;
- join quality for `internacoes.DIAG_PRINC = c.CID`.

Results are evidence for later tasks. They are not production fixes by
themselves.
