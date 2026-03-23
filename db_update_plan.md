You're on the right track thinking about *versioning the **changes*** rather than trying to stuff multi‑GB `.fif` files into a database.

For MEG-sized binaries (\~2 GB per file), the most robust, low‑friction pattern I’ve seen work in labs is a **hybrid**:

*   **Git** → version your code & pipeline configuration.
*   **DVC (Data Version Control)** → version and move the *large files* (keeps your project directory structure intact while storing the blobs in a remote cache like SSH/S3/Azure/GCS).
*   **A small, versioned database** (e.g., **Dolt**) → commit‑time snapshots of **metadata, lineage, manifests**, and run logs, with SQL diff/merge across branches.

This gives you:

*   Efficient handling of 2 GB `.fif` files (dedup, resumable pushes/pulls).
*   Human-auditable **SQL** diffs of “what changed?” (new files, replacements, preprocessing parameters).
*   The ability to keep **all data in current project-based directories** (no replatforming).

Below is a practical, minimal implementation you can stand up in a day.

***

## Architecture at a glance

    project/
      ├─ data/
      │   ├─ projectA/
      │   │   ├─ raw/
      │   │   │   └─ subj01_run01_raw.fif
      │   │   └─ preproc/
      │   │       └─ subj01_run01_filt-40Hz.fif
      ├─ pipeline/
      │   └─ scripts/...
      ├─ db/                 <-- a Dolt repo: SQL tables, branches, tags
      ├─ .git/               <-- Git for code/config
      ├─ .dvc/               <-- DVC for large files
      └─ dvc.yaml            <-- pipeline steps (optional but recommended)

*   `Git` manages `pipeline/`, `dvc.yaml`, and the `db/` Dolt repository contents.
*   `DVC` manages the **binary files** under `data/` but keeps the folders and file names visible locally (it tracks them via `.dvc` files and a content-addressed cache, with remote storage).
*   `Dolt` stores **tracking tables** (paths, content hashes, sizes, provenance, run IDs, parameters, machine), which you **branch/merge and diff** like Git—**but with SQL**.

***

## What each tool does for you

*   **DVC**: “Git for data”, but the big blobs live in a remote. Your project directories stay the same; DVC just replaces the heavy-lift of copying with content-addressed storage, deduplication, and versioning.
*   **Dolt**: A SQL database you can `commit`, `branch`, `merge`, and `diff`. Perfect for **metadata** about your files and pipeline runs. (You *can* store small derivatives or previews, but don’t store the 2 GB FIFs here.)

***

## Minimal setup (one-time)

> Assumes you have Git, DVC, and Dolt installed on your machines.

1.  **Initialize Git & DVC**

```bash
git init
dvc init
```

2.  **Set a DVC remote** (pick one: SSH/S3/Azure/GCS; here’s SSH)

```bash
dvc remote add -d storage ssh://user@server:/data/dvc-cache
# Optional: tune performance for big files
dvc config cache.protected true
dvc config core.checksum_jobs 4
```

3.  **Initialize Dolt in `db/`**

```bash
mkdir -p db && cd db
dolt init
# Optional: create a remote for Dolt if you want to push the DB itself
# dolt remote add origin file:///srv/dolt-meg-meta   # or S3, etc.
cd ..
```

***

## Data tracking with DVC (keeps project layout intact)

Add your data dirs; DVC will create `.dvc` files that Git tracks, while data blobs go to the DVC cache/remote:

```bash
# Example: track all FIFs under project directories
dvc add data/projectA/raw/*.fif
dvc add data/projectA/preproc/*.fif

# Commit those "pointers" with Git
git add data/.gitignore data/projectA/**/*.dvc
git commit -m "Track MEG FIFs with DVC"

# Push the actual blobs to the remote cache
dvc push
```

When new files appear (or files are regenerated), re-run `dvc add` on them and `dvc push`.

***

## A simple, useful Dolt schema (SQL)

Create SQL tables to track your file inventory and pipeline runs. Inside `db/`:

```bash
cd db

dolt sql -q "
CREATE TABLE files (
  file_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  project       VARCHAR(128) NOT NULL,
  rel_path      TEXT NOT NULL,             -- e.g., 'projectA/preproc/subj01_run01_filt-40Hz.fif'
  size_bytes    BIGINT NOT NULL,
  sha256        CHAR(64) NOT NULL,         -- content hash
  mtime_epoch   BIGINT NOT NULL,           -- modified time for sanity checks
  dvc_tracked   BOOLEAN NOT NULL,
  added_at_utc  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"

dolt sql -q "
CREATE TABLE runs (
  run_id        VARCHAR(64) PRIMARY KEY,   -- e.g., ISO timestamp or UUID
  host          VARCHAR(128) NOT NULL,     -- machine name
  user_name     VARCHAR(128) NOT NULL,
  pipeline_rev  VARCHAR(128) NOT NULL,     -- git commit/tag of pipeline
  params_json   JSON NOT NULL,             -- preprocessing parameters
  started_utc   TIMESTAMP NOT NULL,
  finished_utc  TIMESTAMP NULL
);
"

dolt sql -q "
CREATE TABLE file_lineage (
  parent_sha256 CHAR(64) NOT NULL,
  child_sha256  CHAR(64) NOT NULL,
  run_id        VARCHAR(64) NOT NULL,
  step_name     VARCHAR(128) NOT NULL,     -- e.g., 'filter_40Hz'
  notes         TEXT NULL,
  PRIMARY KEY (parent_sha256, child_sha256, run_id),
  FOREIGN KEY (run_id) REFERENCES runs(run_id)
);
"

# Commit the initial schema snapshot
dolt add .
dolt commit -m "Initialize metadata schema (files, runs, file_lineage)"
cd ..
```

> Why SHA256?
>
> *   Stable content identifier: if a file is identical on two machines or regenerated, the hash proves sameness even if the path differs. Perfect for dedup & lineage.

***

## Lightweight indexer: scan project dirs → update Dolt

Below is a **simple Python script** you can run after each pipeline stage. It:

*   Walks your `data/` directories.
*   Computes SHA256 (streaming).
*   Writes or updates a CSV manifest of file records.
*   Imports the CSV into Dolt, then **commits** with a helpful message.

> Save as `pipeline/scripts/index_files.py`

```python
#!/usr/bin/env python3
import csv
import hashlib
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # adjust if needed
DATA_ROOT = PROJECT_ROOT / "data"
DB_DIR = PROJECT_ROOT / "db"
MANIFEST_CSV = DB_DIR / "files_manifest.csv"

def sha256_file(p: Path, buf_size=1024*1024):
    h = hashlib.sha256()
    with p.open("rb") as f:
        while True:
            chunk = f.read(buf_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def rows():
    for root, _, files in os.walk(DATA_ROOT):
        for name in files:
            if not name.lower().endswith(".fif"):
                continue
            fp = Path(root) / name
            stat = fp.stat()
            yield {
                "project": Path(root).parts[-2] if "project" in root.lower() else "unknown",
                "rel_path": str(fp.relative_to(DATA_ROOT)),
                "size_bytes": stat.st_size,
                "sha256": sha256_file(fp),
                "mtime_epoch": int(stat.st_mtime),
                "dvc_tracked": True  # if you only put FIFs under DVC; otherwise detect from .dvc files
            }

def main():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "project","rel_path","size_bytes","sha256","mtime_epoch","dvc_tracked"
        ])
        w.writeheader()
        for r in rows():
            w.writerow(r)

    # Import into Dolt (requires dolt CLI on PATH)
    # Upsert semantics: use a staging table and MERGE or rely on REPLACE if you set a unique key.
    # For simplicity, load into a temp table then merge.
    os.chdir(DB_DIR)
    os.system('dolt sql -q "CREATE TABLE IF NOT EXISTS files_tmp LIKE files"')
    os.system(f'dolt table import -u files_tmp "{MANIFEST_CSV.name}"')  # -u: create/update
    os.system('dolt sql -q "REPLACE INTO files SELECT * FROM files_tmp"')
    os.system('dolt sql -q "DROP TABLE files_tmp"')

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    os.system(f'dolt commit -Am "Index update from script at {ts}"')

if __name__ == "__main__":
    sys.exit(main())
```

**Run it:**

```bash
python3 pipeline/scripts/index_files.py
```

> Tip: If you prefer not to shell out from Python, you can use `dolt sql -q` directly from your Bash scripts, or use a MySQL client library to connect to the Dolt SQL server (`dolt sql-server`) and run upserts.

***

## Recording preprocessing runs & lineage

When a preprocessing step runs (e.g., filtering), log a **run** and link **parent→child** hashes.

Example Bash snippet you can call inside your pipeline step:

```bash
RUN_ID=$(date -u +"run_%Y%m%dT%H%M%SZ")
HOST=$(hostname)
USER_NAME=$(whoami)
PIPELINE_REV=$(git -C . rev-parse --short HEAD)
PARAMS_JSON='{"filter":"lowpass=40","software":"mne","version":"x.y.z"}'

cd db
# Insert the run
dolt sql -q "
INSERT INTO runs (run_id, host, user_name, pipeline_rev, params_json, started_utc)
VALUES ('$RUN_ID', '$HOST', '$USER_NAME', '$PIPELINE_REV', JSON_VALID('$PARAMS_JSON') ? CAST('$PARAMS_JSON' AS JSON) : JSON_ARRAY(), UTC_TIMESTAMP());
"
cd ..

# ... run your preprocessing to create the child FIF ...

# After producing child FIF(s), refresh the file index
python3 pipeline/scripts/index_files.py

# Record lineage (example: known parent/child paths)
PARENT_SHA=$(python3 - <<'PY'
from pathlib import Path
import hashlib, sys
p=Path("data/projectA/raw/subj01_run01_raw.fif")
h=hashlib.sha256()
with p.open("rb") as f:
    for chunk in iter(lambda: f.read(1024*1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
)

CHILD_SHA=$(python3 - <<'PY'
from pathlib import Path
import hashlib, sys
p=Path("data/projectA/preproc/subj01_run01_filt-40Hz.fif")
h=hashlib.sha256()
with p.open("rb") as f:
    for chunk in iter(lambda: f.read(1024*1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
)

cd db
dolt sql -q "
INSERT IGNORE INTO file_lineage (parent_sha256, child_sha256, run_id, step_name, notes)
VALUES ('$PARENT_SHA', '$CHILD_SHA', '$RUN_ID', 'filter_40Hz', 'Butterworth lowpass 40Hz');
"
dolt commit -Am "Record lineage for $RUN_ID"
cd ..
```

Finally, **mark run finished**:

```bash
cd db
dolt sql -q "UPDATE runs SET finished_utc = UTC_TIMESTAMP() WHERE run_id = '$RUN_ID';"
dolt commit -Am "Finish run $RUN_ID"
cd ..
```

***

## Using **Dolt** like Git (but with SQL superpowers)

*   **Branch for an analysis**:
    ```bash
    cd db
    dolt checkout -b analysis-foo
    # make changes (e.g., add QC flags column, update some rows)
    dolt commit -am "QC flags"
    ```

*   **Diff what changed**:
    ```bash
    dolt diff HEAD~1 files
    dolt diff main analysis-foo -- where="project='projectA'"
    dolt sql -q "SELECT * FROM dolt_diff('files', 'main', 'analysis-foo');"
    ```

*   **Merge back**:
    ```bash
    dolt checkout main
    dolt merge analysis-foo
    dolt commit -m "Merge analysis-foo"
    ```

*   **Tag a release**:
    ```bash
    dolt tag v0.3 "After preprocessing batch-2026-03-23"
    ```

***

## Typical workflows

### 1) New raw data arrives on Machine A

```bash
# place files under data/projectA/raw/
dvc add data/projectA/raw/*.fif
git add data/projectA/raw/*.dvc
git commit -m "Add raw MEG for subj01"
dvc push                   # sends large blobs to remote cache

python3 pipeline/scripts/index_files.py
git -C db add .
git -C db commit -m "Index update: new raw files"
# Optional: push Dolt repo somewhere shared (or just push Git if Dolt is embedded)
```

### 2) Preprocess on Machine B

```bash
git pull
dvc pull                                   # fetches the necessary FIFs
# run your preprocessing -> writes to data/projectA/preproc/
dvc add data/projectA/preproc/*.fif
git add data/projectA/preproc/*.dvc
git commit -m "Preproc subj01 filter 40Hz"
dvc push

python3 pipeline/scripts/index_files.py
# insert run + lineage as shown above
```

### 3) Push to server & publish manifest

*   Your server (or a CI job) `git pull`, `dvc pull`, and can run SQL queries on `db/` to publish a **manifest CSV** or **web view** of current datasets.

***

## Why not store `.fif` inside Dolt?

*   Dolt is excellent for **rows of structured data and their history**. Large binary blobs will bloat the DB, slow diffs/merges, and defeat content‑addressed storage benefits you get from DVC. Keeping `.fif` in DVC gives you deduplication, resumability, and storage-agnostic remotes while preserving your on-disk project structure.

***

## Optional niceties (when you’re ready)

*   **Parameterized runs via `dvc.yaml`**  
    Capture pipeline stages and dependencies so `dvc repro` can rebuild steps as inputs change.
*   **File integrity checks**  
    Add a CI job that verifies that `files.sha256` still matches on disk for critical datasets.
*   **Metadata enrichment**  
    Extract a few headers from `.fif` (using MNE) into the `files` table (subject, run, sampling rate) to enable smarter queries. Keep it small to avoid costly reads.
*   **Access control**  
    Point your DVC remote to secure storage (SSH vault, MinIO/S3 with bucket policies) and host `dolt sql-server` behind your LAN/VPN for multi-user access.
*   **Provenance expansions**  
    Add a `transformations` table to capture exact command lines, container digests, and code revs for full reproducibility.

***

## Quick “getting started” checklist

1.  **Install**: Git, DVC, Dolt on your machines.
2.  **Init**: `git init`, `dvc init`, `mkdir db && (cd db && dolt init)`.
3.  **Remote**: `dvc remote add -d storage ssh://...`.
4.  **Track data**: `dvc add data/**.fif && dvc push`.
5.  **Create schema**: run the Dolt SQL `CREATE TABLE` commands.
6.  **Index**: run `pipeline/scripts/index_files.py` to populate `files` and commit.
7.  **Log runs & lineage** after each pipeline step.
8.  **Query & diff** with Dolt to answer “what changed, when, and why?”.

***

## Want me to tailor this to your current pipeline?

A few quick questions so I can give you a drop‑in config:

*   Which remote storage is easiest for you right now (SSH to your Solna server, S3/MinIO, or something else)?
*   Do you prefer a **single consolidated Dolt repo** for all projects or **one per project**?
*   Which preprocessing steps do you want explicitly traced in lineage (e.g., filtering, ICA, epoching)?
*   Do you want me to add **QC flags** or **subject metadata** columns to the schema?

If you share one of your project directory layouts (just paths, not data), I can produce a ready‑to‑run script set (`dvc.yaml`, indexer, and lineage logger) customized to your structure.
