# OPM Preprocessing: Structured Comparison

**Legacy:** `098e376` (flat-script repo layout, `add_hpi.py`)
**Current:** `9cc4bda` (`seshat` package, `seshat/stages/opm_preprocess.py` + `opm_utility_scripts` submodule)

## 0. Scope note

At `Legacy` there is no file literally named `opm_preprocess.py`. The
functional predecessor of today's OPM preprocessing stage is **`add_hpi.py`**
(root of the repo), invoked via `natmeg_pipeline.py hpi --config …` or as
step `RUN: Add HPI coregistration` in the pipeline config. This document
compares that script against the current `seshat/stages/opm_preprocess.py`
plus the logic it now delegates to the `opm_utility_scripts` git submodule
(`opm_utility_scripts/hpi/_core.py`, `channels.py`, `io.py`, `analog/*`,
`viz.py`).

Everything else that touched OPM data in the old repo (`maxfilter.py`,
`natmeg_pipeline.py`) only *excluded* OPM files from SQUID MaxFilter
processing (`exclude_patterns = [..., 'opm', ...]`); it performed no OPM
signal processing of its own, so it is not part of this comparison.

## 1. Module layout

| | `Legacy` | `Current` |
|---|---|---|
| Entry point | `add_hpi.py` (root, monolithic, 1124 lines) | `seshat/stages/opm_preprocess.py` (509 lines, thin orchestrator) |
| Core algorithm | Implemented inline in `add_hpi.py` | Delegated to external submodule `opm_utility_scripts` (git submodule, ~3900 lines across `hpi/_core.py`, `channels.py`, `io.py`, `analog/`, `viz.py`) |
| Invocation | `python add_hpi.py -c config.yml` or `natmeg_pipeline.py hpi --config …` | `python -m seshat.stages.opm_preprocess -c config.yml` or `seshat opm-preprocess --config …` |
| Pipeline toggle | `RUN: Add HPI coregistration: true` | `RUN: opm_preprocess: true` (config key renamed) |
| CLI verbosity | none (bare `print()` everywhere) | `-v/--verbose` flag, `configure_verbosity()` / `verbose_print()` gate |
| `main()` signature | `main(config=None)` | `main(config=None, log_file_path=None)` — accepts a pipeline-supplied log path so the stage no longer reconfigures logging when run inside `seshat run` |

## 2. Pipeline overview

Both versions follow the same high-level shape: **discover subjects/sessions
→ locate Polhemus + HPI files for the session → fit HPI coil positions once
per session → apply the resulting transform to every OPM data file in that
session, in parallel.** The step-by-step differences below are grouped in
pipeline order.

```
 1. Load config                     (get_parameters)
 2. Enumerate subjects/sessions      (main loop)
 3. Discover hedscan data files      (find_hpi_fit)
 4. Discover Polhemus digitisation   (find_hpi_fit)
 5. Discover & select HPI recording  (find_hpi_fit)
 6. Bad/zero channel removal         (HPI recording)
 7. Per-coil amplitude estimation    (peak detection + windowing)
 8. Coil localisation (dipole fit)   (device coordinates)
 9. Device→head transform            (point matching + rigid fit)
10. Quality gating                  (GOF thresholds, session abort)
11. Per-file transform application   (process_single_file / apply_transform)
12. Resampling                      (per file)
13. Analog channel renaming         (optional, new)
14. Save output                     (naming convention)
15. QC visualisation                (plot)
16. Parallel dispatch & logging     (ProcessPoolExecutor)
```

## 3. Step-by-step differences

### Step 1 — Configuration loading (`get_parameters`)

Both parse `Project`/`OPM` sections from YAML/JSON identically for the
shared keys (`tasks`, `polhemus`, `hpi_names`, `frequency`,
`downsample_to_hz`, `overwrite`, `plot`, `logfile`). New keys added on the
current side:

| Key | Legacy | Current |
|---|---|---|
| `rename_analog_channels` | — | new; gates the analog-channel rename step |
| `noise_reffile` | — | new (added in the tip commit `Current`); path to a reference recording for noisy-channel detection |

`default_config.yml` / `RUN` section: `Add HPI coregistration` renamed to
`opm_preprocess`; `Run Maxfilter` and `Run BIDS conversion` toggles are
commented out of the current `seshat run` orchestration (`maxfilter`/
`bidsify` are only reachable as standalone CLI subcommands now — `bidsify`
is a stub — this is a pipeline-integration change, not an OPM-processing
change, but affects what runs around the OPM step).

### Step 2/3 — Subject/session + hedscan file discovery

Identical subject (`sub-*`) / session (6-digit dir) enumeration in both.

File-exclusion patterns differ:

- **Legacy**: `exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif', 'hpi']`
  — the literal substring `'hpi'` is blanket-excluded from candidate
  hedscan files.
- **Current**: `exclude_patterns = [r'-\d+\.fif', '_trans', 'avg.fif']`
  — the blanket `'hpi'` substring filter is dropped; only the
  *configured* `hpinames` patterns (e.g. `HPIpre`, `HPIpost`, …) are
  excluded from the hedscan-file list. This avoids accidentally excluding
  legitimate task recordings that happen to contain the substring `hpi`.

`proc_patterns` (shared `seshat/utils.py`, formerly root `utils.py`) gained
`'proc-hpi'` as an exclusion pattern in the current version, so files
already produced by a previous OPM-preprocessing run are no longer
re-discovered as unprocessed inputs.

### Step 4 — Polhemus digitisation discovery

- **Legacy**: only searches the legacy layout —
  `{opmMEGdir}/{subject}/{session}/triux/*{task-or-polhemus-pattern}*.fif`,
  filtered by `exclude_patterns`/`noise_patterns`. Assumes TRIUX/Elekta
  FIF recordings are the sole polhemus source.
- **Current**: adds a preferred **"Stage 1"** lookup of a new
  `{opmMEGdir}/{subject}/{session}/polhemus/` directory containing `.json`
  or `.fif` files whose name contains both the subject and session ID;
  candidates are sorted by an embedded 14-digit timestamp and only the
  **most recent** file is used. The legacy `triux/` search ("Stage 2") is
  kept **unchanged** as a fallback when no `polhemus/` files exist. This
  adds support for a newer standalone Polhemus-digitiser JSON format
  (`pylhemus-dig/1`) alongside the old TRIUX-embedded digitisation.

### Step 5 — Loading the Polhemus fiducials/HPI positions

- **Legacy**: manually reads `mne.io.read_info(polfile)['dig']` and
  assumes a **fixed point order** — `dig[0]` = LPA, `dig[1]` = nasion,
  `dig[2]` = RPA, and any `kind==2` points are HPI. This is fragile: it
  breaks if the digitisation order ever differs from that convention.
- **Current**: `opm_utility_scripts.io.load_polhemus()` identifies points
  by their **FIFF `kind`/`ident` codes** regardless of storage order
  (`kind==1` cardinal fiducials keyed by `ident` 1/2/3 → LPA/nasion/RPA,
  `kind==2` → HPI, `kind==3` → EEG, `kind==4` → extra headshape points),
  explicitly validates that all three fiducials are present (raises a
  clear `ValueError` otherwise), and transparently supports three input
  types: a `.json` (`pylhemus-dig/1`), a `.fif`, or a pre-loaded
  `mne.channels.DigMontage`.

Coordinate-frame handling also changed: `Legacy` unconditionally treats
the loaded points as isotrak/RAS and applies
`get_ras_to_neuromag_trans(nasion, lpa, rpa)`. `Current` disambiguates by
source: JSON (`pol_source == 'json'`) still gets the isotrak→head
conversion; a `.fif`/`DigMontage` source is treated as **already in head
coordinates** and passed straight through unconverted — avoiding a
double-transform for the newer FIF/DigMontage-based digitisation path that
`Legacy` could not encounter (it only ever supported the FIF/triux route,
converted unconditionally).

### Step 5 (cont.) — HPI recording discovery & candidate selection

- **Legacy**: `hpi_files = [f for f in all_files if file_contains(f, hpinames)]`
  (no exclusion of already-processed/derivative files). The script then
  **iterates and uses the first HPI file that loads without raising an
  exception** (`break` after the first success) — i.e. no quality
  comparison between multiple HPI recordings for a session.
- **Current**: `hpi_files` additionally excludes `proc_patterns +
  exclude_patterns`, so old `proc-hpi`/`tsss`/etc. derivatives are never
  re-selected as fit candidates. All candidate HPI files are then fit via
  `select_best_hpi_file()`, which calls `fit_hpi()` on **every** candidate
  and keeps the one with the highest mean GOF among coils exceeding 0.9
  (falling back to raw mean GOF with a warning if none exceed 0.9). A
  session-level **minimum-quality gate** (`MIN_GOF = 0.7`) then aborts
  processing for that subject/session entirely (logged as an error) if
  even the best candidate's mean GOF is too low — a safeguard `Legacy`
  has no equivalent of.

### Step 6 — Bad/zero-location channel removal (HPI recording)

- **Legacy**: `TC_findzerochans()` — flags magnetometers whose summed
  `loc[0:3]` is within `1e-3` of zero.
- **Current**: `find_zero_location_channels()` (in
  `opm_utility_scripts/channels.py`) — same zero-position check, **plus**
  detection of `NaN`/`Inf` positions (which crash MNE's external-basis SVD
  `_setup_ext_proj`), catching a failure mode the old check missed.
  `opm_preprocess.py`'s `process_single_file` also adds a **pre-flight
  abort**: if more than 100 zero-location channels are found the file is
  skipped before the expensive fit runs (logged as an error); 9 is a
  warning threshold. `Legacy` had no such guard — it always proceeded
  regardless of how many channels were dropped.

### Step 7 — HPI output-channel identification

Both use the same heuristic — misc channels whose name contains `'out'`
and whose signal variance exceeds `1e-25` — implemented as
`TC_get_hpiout_names()` in `Legacy` and `get_hpi_output_channels()` in
`Current` (`channels.py`). Logic is functionally identical; only the name
and module location changed.

### Step 7 (cont.) — Per-coil amplitude estimation / peak-window extraction

- **Legacy**: for each active HPI coil, `find_peaks()` locates the coil's
  activation pulses in its output channel; the script crops a **2-second
  window** centred on the pulse train's midpoint
  (`tmin = mid - 1`, `tmax = mid + 1`) before calling
  `compute_chpi_amplitudes(raw, tmin=0, tmax=2, t_window=2, t_step_min=2)`.
  Requires ≥3 active coils or emits an MNE `warn()` (but still continues).
- **Current** (`fit_hpi_amplitudes()`): same peak-detection approach, but
  the cropped window is **6 seconds** (`tmin = mid - 3`, `tmax = mid + 3`),
  giving `compute_chpi_amplitudes` more data per coil. It also
  **always resamples to a fixed internal fitting rate of 1000 Hz**
  (`_HPI_FIT_SFREQ`) before the peak-detection loop, independent of the
  user's `downsample_to_hz` target (which is applied later, only to the
  *data* files, not the HPI recording used for fitting). It further
  normalises a FieldLine-OPM-specific quirk: `line_freq == 0` is coerced to
  `50.0`, because MNE's `compute_chpi_amplitudes` divides by
  `info['line_freq']` and only guards against `None`, not literal `0`
  (would otherwise raise   `ZeroDivisionError`). `Legacy` has none of these
  safeguards.

### Step 8 — Coil localisation (dipole fitting in device coordinates)

This is the most significant algorithmic change.

- **Legacy**: reuses MNE's stock `compute_chpi_locs()` (imported directly
  from `mne.chpi`), which internally builds dipole-position "guesses" from
  MNE's generic, any-MEG-system conductor/guess-grid machinery
  (`_make_guesses` on a default sphere), i.e. a model **not tailored to
  OPM sensor geometry**.
- **Current**: implements a **local reimplementation**,
  `compute_chpi_opm_locs()` (`opm_utility_scripts/hpi/_core.py`), built on
  a custom `_make_opm_guesses()` helper. This constructs a spherical
  conductor model whose radius is derived from the actual sensor
  positions in the recording, then restricts candidate dipole guess
  points to those **inside the sensor helmet's minimum sensor radius** —
  a guess grid specifically shaped for the sparse, close-to-scalp
  FieldLine OPM array rather than MNE's generic MEG guess grid. The same
  module also adds `_gof_at_fixed_pos()`, a helper that scores a dipole
  fit at a *fixed* (non-optimised) position — used later for the new
  Polhemus-position diagnostic (Step 9) and for the optional rigid-fit
  refinement (Step 9).

### Step 9 — Device→head transform computation & matching

- **Legacy**: matches `hpi_dev` (fitted, device-frame) to `hpi_orig`
  (Polhemus, head-frame) via a raw (uncentred) `cKDTree` nearest-neighbour
  query, then `_fit_matched_points()` + `_quat_to_affine()` to obtain the
  rigid transform. Fixed inclusion threshold: coils with GOF `> 0.9`. This
  computation happens **inside `process_single_file`, once per data
  file** (recomputed redundantly for every hedscan file in the session,
  though with identical inputs so the result doesn't vary).
- **Current** (`fit_hpi()`):
  - **Centroid-centred** nearest-neighbour matching (`hpi_orig_head -
    mean`, `hpi_dev - mean`) before the `cKDTree` query — more robust
    when the whole point cloud is rotated/offset, not just translated.
  - **Automatic GOF threshold selection**: `0.98` when HPI coils use
    distinct drive frequencies (MEGIN/Elekta+SSS convention), `0.90` when
    all coils share one frequency (the sequential single-frequency OPM
    case) — replacing `Legacy`'s single hard-coded `0.9`. Can still be
    overridden explicitly via `gof_limit`.
  - The transform is computed **once, inside `fit_hpi()`**, and the
    resulting `fit` dict (including `dev_to_head_trans`) is threaded
    through `find_hpi_fit()` → `process_single_file()` →
    `apply_transform()` for every file, instead of being recomputed per
    file.
  - Adds a **guard** if the Polhemus digitisation has fewer HPI points
    than active coils (raises `ValueError` with an actionable message) —
    `Legacy` had no equivalent check and would fail less predictably.
  - Adds a **residual-distance warning**: any included coil with a
    post-fit residual `> 10 mm` triggers a `RuntimeWarning` naming the
    offending coil(s). `Legacy` printed the mean distance but never
    flagged individual coils or warned.
  - Optional **rigid-fit refinement** (`optim='rigid'`): perturbs the
    closed-form transform above with a bounded `L-BFGS-B` optimisation
    (±5–10° rotation, ±5 mm translation) to maximise **mean fixed-position
    GOF** (`_gof_at_fixed_pos`, a signal/physics-based cost — how well a
    dipole at that position explains the measured field). This is **not**
    an equivalent implementation of `Legacy`'s method and **not** used by
    the production pipeline:
    - `Legacy`'s fit minimises Euclidean distance between matched point
      pairs (a purely geometric cost); `optim='rigid'` instead maximises
      signal-fit GOF. Different objective, not a drop-in replacement.
    - The default (`optim="none"`) is the closer structural analogue of
      `Legacy` (closed-form fit, no refinement) — but even `"none"`
      differs from `Legacy` in matching (centroid-centred vs raw) and GOF
      threshold (auto 0.98/0.90 vs fixed 0.9), as above.
    - `optim='rigid'` is **dormant in the actual `seshat opm-preprocess`
      pipeline**: `select_best_hpi_file()` (called from
      `opm_preprocess.py`) and `coregister.py` both call `fit_hpi(...)`
      without an `optim` argument, so they always use `"none"`. The only
      place `'rigid'` is reachable is the standalone diagnostic CLI
      `opm_utility_scripts/hpi/check.py --optimization rigid`, whose own
      default is also `"none"`. So this refinement mode has no
      counterpart in `Legacy` and, as of this comparison, is not part of
      the production OPM-preprocessing pipeline either.

### Step 9 (cont.) — New QC diagnostic: Polhemus-position GOF

`Current` adds `pol_gofs`: for each included coil, it evaluates the dipole
forward model at the **digitised Polhemus position** (transformed to
device space) against the coil's measured field, without optimising the
position. A low `pol_gof` combined with a high `hpi_gof` isolates a
Polhemus-digitisation error from an HPI-recording error — a distinction
`Legacy` could not make (it had no per-coil forward-model scoring against
a fixed position at all).

### Step 10/11/12 — Per-file transform application, resampling, saving

Both scripts:
- resample each data file to `downsample_freq` only if it differs from the
  file's current rate;
- drop `info['bads']` and zero-location channels again per file;
- embed `dev_head_t` and rebuild `info['dig']` from the fit results;
- save with the same naming convention: strip `_raw`, append
  `_proc-hpi[+ds]_raw.fif` (suffix includes `+ds` only if resampling
  occurred).

Differences:
- **Current** factors the transform-application logic into two reusable,
  independently callable functions in `opm_utility_scripts/hpi/_core.py`:
  `apply_transform()` (returns the modified in-memory `Raw`) and
  `save_raw()` (writes it using the standard filename convention). In
  `Legacy` this logic is inline and non-reusable inside
  `process_single_file`.
- **Current** adds the pre-flight >100-bad-channel abort described in
  Step 6, executed *before* `apply_transform()` is even called, to skip
  known-bad files cheaply.
- **Current** adds an **optional analog-channel rename** step (new
  capability, not present in `Legacy` at all): when
  `rename_analog_channels: true`, `generate_analog_channel_mapping()`
  (`opm_utility_scripts/analog/mapping.py`) maps hardware names `ai1…ai20`
  to semantic labels (`ECG`, `EOG1/2`, `RESP`, `Acc1/2 X/Y/Z`,
  `EyeL/R X/Y/P`) with correct FIFF channel `kind`/`unit`, applied via
  `rename_channels()` (`opm_utility_scripts/analog/rename.py`) before the
  file is saved.

### Step 13 — QC visualisation

- **Legacy**: hand-rolled `plot_3d()` — Delaunay-triangulates the sensor
  positions into a 3D mesh and overlays HPI coil positions (device-frame
  in blue, head-frame in green) and digitisation points (black); saved as
  `..._3d_plot.png`.
- **Current**: uses `plot_hpi_alignment()` from
  `opm_utility_scripts/viz.py`, saved as `..._alignment.png`. Same intent
  (visual coregistration QC) with a different, shared/reusable plotting
  implementation used consistently across the whole `opm_utility_scripts`
  toolkit (also used by its standalone `hpi/check.py` QC tool, which has
  no `Legacy` counterpart at all).

### Step 14 — Noise-reference-based bad-channel detection (new; latest commit)

This capability does not exist in `Legacy` in any form. It was added
across the `Current` line of history and extended by the tip commit itself
(`Current`, "added optional noise ref file for bad channel estimations"):

- `find_bads()` (`opm_utility_scripts/hpi/_core.py`) computes background
  PSD power in the 70–80 Hz band (Welch, `n_fft=n_per_seg=5000`) per
  channel from a reference recording, then iteratively (5 passes)
  discards channels whose background power exceeds `mean + 3·std` of the
  currently-retained set, flagging the survivors' complement as noisy. It
  also renders a diagnostic figure marking the threshold and the flagged
  channels.
- Reference source is now configurable end-to-end: a new `OPM.noise_reffile`
  config key → `opm_preprocess.get_parameters()` → `find_hpi_fit()` →
  `select_best_hpi_file(..., reffile=noise_reffile)` → `fit_hpi(...,
  reffile=...)`. When set, a fixed 10 s window starting 10 s into the
  reference recording is extracted once
  (`_load_noise_reffile_window()`) and reused, as a **fresh copy**, for
  every HPI-file candidate in `select_best_hpi_file()` (so bad-channel
  detection is consistent across candidates and isn't mutated between
  fits).
- When `noise_reffile` is **not** given (`None`, the default), `fit_hpi()`
  falls back to extracting a 5-second window from the **end of the HPI
  recording itself** for the same detection step, only if the recording
  is long enough; otherwise bad-channel detection is skipped entirely
  with a printed warning. `Legacy` performs none of this — it never
  attempts frequency-domain noisy-channel rejection, relying solely on
  pre-marked `info['bads']` and zero-location detection.

### Step 15 — Parallel dispatch & orchestration

Structurally unchanged: both iterate `sub-*` → 6-digit session dirs, call
the HPI-fit function once per session, then fan the resulting
`hedscan_files` out to `process_single_file` via
`concurrent.futures.ProcessPoolExecutor(max_workers=len(hedscan_files)*2)`,
collecting exceptions per-future. Differences are limited to logging
plumbing:

- **Legacy**: `main()` always derives and reconfigures its own log
  directory/file from `opmMEGdir.replace('raw', 'logs')`, even when
  invoked as a sub-step of `natmeg_pipeline.py run` (each pipeline stage
  re-initialises logging independently).
- **Current**: `main(config, log_file_path=None)` accepts an explicit
  `log_file_path` from the caller. When run inside `seshat run`
  (`seshat/cli.py`), the already-configured pipeline-wide log file is
  reused directly; the stage only derives its own log path when run
  standalone. `find_hpi_fit()`/`process_single_file()` were likewise
  updated to accept and thread through explicit `log_path`/`logfile`
  parameters instead of only reading module-level config.

## 4. Configuration diff summary

`OPM:` section, `default_config.yml`:

```diff
 OPM:
+  rename_analog_channels: true
   polhemus: ['']
   hpi_names: [HPIpre, HPIpost, HPIbefore, HPIafter]
   frequency: 33
   downsample_to_hz: 1000
+  noise_reffile: ''
   overwrite: false
   plot: false
```

`RUN:` section:

```diff
 RUN:
   Copy to Cerberos: true
-  Add HPI coregistration: true
-  Run Maxfilter: true
-  Run BIDS conversion: true
+  OPM preprocessing: true
   Sync to CIR: true
```

(`Run Maxfilter` / `Run BIDS conversion` are no longer wired into
`seshat run`'s main loop — commented out — though `maxfilter`/`bidsify`
remain reachable as standalone CLI subcommands, with `bidsify` currently a
stub. This is a pipeline-integration change adjacent to, not part of, OPM
preprocessing itself.)

## 5. Net effect

| Aspect | Legacy (`add_hpi.py`) | Current (`opm_preprocess.py` + `opm_utility_scripts`) |
|---|---|---|
| Code organisation | 1 monolithic 1124-line script | Thin 509-line orchestrator + reusable, independently-tested submodule (~3900 lines) |
| Polhemus sources | TRIUX/Elekta FIF only | New `polhemus/` JSON or FIF, TRIUX FIF as fallback |
| HPI-file selection | First loadable file | Best of all candidates by fitted GOF, with session-level quality gate |
| Dipole guess model | Generic MNE MEG guess grid | OPM-tailored spherical guess grid constrained to sensor helmet |
| Bad-channel handling | Zero-location only | Zero/NaN/Inf location + optional PSD-based noisy-channel rejection (config-driven reference file) |
| Transform fit | Per-file, raw nearest-neighbour, fixed 0.9 GOF cutoff | Once per session, centroid-centred matching, auto/explicit GOF cutoff, optional rigid refinement |
| QC diagnostics | Mean distance printout | Per-coil residual warnings, Polhemus-position GOF, dedicated alignment plot |
| New features | — | Analog-channel renaming, verbose flag, pipeline log-path passthrough |
| Failure modes guarded | None | >100-bad-channel abort, insufficient-Polhemus-points error, low-mean-GOF session skip |
