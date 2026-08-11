# Installation

## Quick Installation

```bash
git clone git@github.com:k-CIR/SESHAT.git
cd SESHAT
bash install.sh
```

The installer automatically detects the platform and sets up the required environment.

After installation:

```bash
natmeg gui
natmeg run --config config.yml
natmeg --help
```

## Manual Installation

### Conda

```bash
conda create -n natmeg_utils python>=3.12 pip uv -y
conda activate natmeg_utils
uv pip install -r requirements.txt
```

### Python Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Prerequisites

- Python 3.12+
- Conda or Miniconda (recommended)
- Git
- macOS or Linux

## Troubleshooting

### PyQt Issues on Linux

Use the conda installation:

```bash
bash install.sh
```

### natmeg command not found

Ensure `~/.local/bin` is on the PATH.

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Environment issues

Recreate the environment:

```bash
conda env remove -n natmeg_utils -y
bash install.sh
```
