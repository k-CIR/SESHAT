# Installation

Primary supported platform: **Rocky Linux** (RHEL/Fedora-family). macOS and
Debian/Ubuntu are also supported.

## Quick Installation

```bash
git clone --recurse-submodules git@github.com:k-CIR/SESHAT.git
cd SESHAT
bash install.sh
```

(If you already cloned without `--recurse-submodules`, `install.sh` will
fetch the missing `opm_utility_scripts` submodule for you.)

This installs `seshat` as an isolated global command for your user account,
using [`uv tool install`](https://docs.astral.sh/uv/guides/tools/) if `uv`
is available (installed automatically otherwise), or `pipx` as a fallback.
It does **not** require `sudo`, conda, or a manually managed virtual
environment, and it won't conflict with any other Python project.

After installation, open a new terminal (or `source ~/.bashrc`) and run:

```bash
seshat gui
seshat run --config config.yml
seshat --help
```

### Options

```bash
bash install.sh --editable   # dev install: code changes apply without reinstalling
bash install.sh --uv         # force uv as the installer
bash install.sh --pipx       # force pipx as the installer
```

## Prerequisites

- Python 3.9+ (the installer picks the newest suitable interpreter it finds)
- Git
- Rocky Linux / RHEL / Fedora, Debian/Ubuntu, or macOS

The GUI (`seshat gui`) uses [PySide6](https://doc.qt.io/qtforpython/), which
ships as a prebuilt pip wheel with Qt bundled inside it - unlike the
previous Tkinter-based GUI, no separate OS package is required. `install.sh`
installs it automatically via the `gui` extra. If installing manually
instead of via `install.sh`, add it yourself: `pip install -e ".[gui]"` (see
below). The command-line interface (`seshat run`/`seshat copy`/etc.) works
without it either way.

## Manual / Development Installation

Instead of `install.sh`, you can install into your own environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"                # [gui] pulls in PySide6 for 'seshat gui'
pip install -e opm_utility_scripts/     # required for the opm-preprocess stage
```

Optional notebook extras (`jupyter`, `ipython`, `seaborn`):

```bash
pip install -e ".[notebook]"
```

## Troubleshooting

### `seshat: command not found`

Ensure `~/.local/bin` is on your `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Reinstalling / updating

Re-run the installer; it reinstalls in place:

```bash
bash install.sh
```

### Uninstalling

```bash
uv tool uninstall seshat   # if installed via uv
pipx uninstall seshat      # if installed via pipx
```

### opm-preprocess stage fails to import `opm_utility_scripts`

The submodule wasn't fetched. Run:

```bash
git submodule update --init --recursive
bash install.sh
```
