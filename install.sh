#!/bin/bash
# SESHAT Pipeline installer
#
# Installs the 'seshat' command (with the deprecated 'natmeg' alias) as an
# isolated, globally-available CLI tool for the current user, using
# `uv tool` (preferred) or `pipx` as a fallback. Each install gets its own
# private virtual environment, so it never conflicts with other Python
# projects or the system Python.
#
# Primary target: Rocky Linux / RHEL / Fedora (dnf-based). Also works on
# Debian/Ubuntu (apt-based) and macOS (Homebrew).

set -e

EDITABLE=false
FORCE_PIPX=false
FORCE_UV=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --editable|-e)
            EDITABLE=true
            shift
            ;;
        --uv)
            FORCE_UV=true
            shift
            ;;
        --pipx)
            FORCE_PIPX=true
            shift
            ;;
        --help|-h)
            cat <<'HLP'
SESHAT Pipeline Installer

Installs the 'seshat' command (with the deprecated 'natmeg' alias) as an
isolated, globally-available CLI tool for the current user, using
uv tool (preferred) or pipx as a fallback.

Usage: bash install.sh [options]

Options:
  --editable, -e   Install in editable mode from this checkout (for development;
                    code changes take effect immediately without reinstalling)
  --uv             Force use of 'uv tool install'
  --pipx           Force use of 'pipx install'
  --help, -h       Show this help message

No option is required for a normal install: the script picks 'uv' if
available (installing it automatically otherwise), falling back to 'pipx'.
HLP
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS=$(uname -s)
echo "Detected platform: $OS"

# Detect a dnf-based distro (Rocky/RHEL/Fedora/AlmaLinux/CentOS) for
# distro-specific package hints (python3-tkinter, pipx, etc.).
IS_DNF=false
if command -v dnf &> /dev/null; then
    IS_DNF=true
fi

# --- opm_utility_scripts git submodule ---
# Not published to PyPI; not a dependency in pyproject.toml. It must be
# fetched and installed alongside seshat for 'seshat run --opm-preprocess'
# (seshat/stages/opm_preprocess.py) to work.
OPM_UTILS_DIR="$SOURCE_DIR/opm_utility_scripts"
if [ -f "$SOURCE_DIR/.gitmodules" ] && command -v git &> /dev/null; then
    if [ ! -f "$OPM_UTILS_DIR/pyproject.toml" ]; then
        echo "Fetching opm_utility_scripts submodule..."
        git -C "$SOURCE_DIR" submodule update --init --recursive
    fi
fi
INSTALL_OPM_UTILS=false
if [ -f "$OPM_UTILS_DIR/pyproject.toml" ]; then
    INSTALL_OPM_UTILS=true
else
    echo "⚠ opm_utility_scripts submodule not found at $OPM_UTILS_DIR."
    echo "  The OPM preprocessing stage ('opm_preprocess') will not work until you run:"
    echo "    git submodule update --init --recursive"
    echo "  and then re-run this script."
fi

# --- Find a system Python (>=3.9) to back the tool install, preferring one
#     that already has tkinter so 'seshat gui' works out of the box. ---
find_system_python() {
    local best_with_tk=""
    local best_without_tk=""
    for candidate in python3.13 python3.12 python3.11 python3.10 python3.9 python3 python; do
        if command -v "$candidate" &> /dev/null; then
            local version major minor
            version=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
            major=${version%%.*}
            minor=${version##*.}
            if [ "$major" -eq 3 ] 2>/dev/null && [ "$minor" -ge 9 ] 2>/dev/null; then
                if "$candidate" -c "import tkinter" 2>/dev/null; then
                    [ -z "$best_with_tk" ] && best_with_tk="$candidate"
                else
                    [ -z "$best_without_tk" ] && best_without_tk="$candidate"
                fi
            fi
        fi
    done
    if [ -n "$best_with_tk" ]; then
        echo "$best_with_tk"
    else
        echo "$best_without_tk"
    fi
}

SYSTEM_PYTHON=$(find_system_python || true)

if [ -z "$SYSTEM_PYTHON" ]; then
    echo "❌ Error: no suitable Python 3.9+ interpreter found." >&2
    if [ "$IS_DNF" = true ]; then
        echo "   Install one with: sudo dnf install python3.12" >&2
    else
        echo "   Please install Python 3.9 or higher." >&2
    fi
    exit 1
fi

echo "✓ Using Python: $SYSTEM_PYTHON ($($SYSTEM_PYTHON --version 2>&1))"

if $SYSTEM_PYTHON -c "import tkinter" 2>/dev/null; then
    echo "✓ tkinter available - GUI ('seshat gui') will work"
else
    echo "⚠ tkinter not found for $SYSTEM_PYTHON."
    echo "  'seshat gui' will not work until tkinter is installed for this interpreter."
    if [ "$IS_DNF" = true ]; then
        echo "  Install it with: sudo dnf install python3-tkinter"
    elif [ "$OS" = "Darwin" ]; then
        echo "  Install it with: brew install python-tk"
    else
        echo "  Install it with: sudo apt install python3-tk"
    fi
    echo "  The command-line interface (seshat run, seshat copy, etc.) works regardless."
fi

# --- Choose installer: uv tool (preferred, fast, self-contained) or pipx ---
INSTALLER=""
if [ "$FORCE_PIPX" = true ]; then
    INSTALLER="pipx"
elif [ "$FORCE_UV" = true ]; then
    INSTALLER="uv"
elif command -v uv &> /dev/null; then
    INSTALLER="uv"
elif command -v pipx &> /dev/null; then
    INSTALLER="pipx"
fi

if [ -z "$INSTALLER" ]; then
    echo "Neither 'uv' nor 'pipx' found. Installing 'uv' (recommended, self-contained, no root needed)..."
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget &> /dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if command -v uv &> /dev/null; then
        INSTALLER="uv"
    else
        echo "❌ Error: could not install uv automatically." >&2
        echo "   Install one of the following manually and re-run this script:" >&2
        echo "   - uv:   https://docs.astral.sh/uv/getting-started/installation/" >&2
        echo "   - pipx: https://pipx.pypa.io/stable/installation/" >&2
        exit 1
    fi
fi

echo "Using installer: $INSTALLER"

# --- Install / reinstall SESHAT as an isolated global tool ---
echo "Installing SESHAT..."

if [ "$INSTALLER" = "uv" ]; then
    UV_ARGS=(tool install --force --reinstall --python "$SYSTEM_PYTHON")
    [ "$EDITABLE" = true ] && UV_ARGS+=(--editable)
    [ "$INSTALL_OPM_UTILS" = true ] && UV_ARGS+=(--with-editable "$OPM_UTILS_DIR")
    UV_ARGS+=("$SOURCE_DIR")
    uv "${UV_ARGS[@]}"
    uv tool update-shell || true
else
    if ! command -v pipx &> /dev/null; then
        echo "Installing pipx..."
        if [ "$IS_DNF" = true ] && command -v dnf &> /dev/null && sudo -n true 2>/dev/null; then
            sudo dnf install -y pipx || "$SYSTEM_PYTHON" -m pip install --user pipx
        else
            "$SYSTEM_PYTHON" -m pip install --user pipx
        fi
        "$SYSTEM_PYTHON" -m pipx ensurepath || true
        export PATH="$HOME/.local/bin:$PATH"
    fi
    PIPX_ARGS=(install --force --python "$SYSTEM_PYTHON")
    [ "$EDITABLE" = true ] && PIPX_ARGS+=(--editable)
    PIPX_ARGS+=("$SOURCE_DIR")
    pipx "${PIPX_ARGS[@]}"
    if [ "$INSTALL_OPM_UTILS" = true ]; then
        pipx inject seshat "$OPM_UTILS_DIR" --editable --force
    fi
    pipx ensurepath || true
fi

echo "✓ SESHAT installed"

# --- Optional: Linux desktop launcher for GUI usage ---
if [ "$OS" = "Linux" ] && command -v seshat &> /dev/null; then
    DESKTOP_DIR="$HOME/.local/share/applications"
    DESKTOP_FILE="$DESKTOP_DIR/seshat.desktop"
    SESHAT_BIN="$(command -v seshat)"
    ICON_PATH="$SOURCE_DIR/assets/seshat_col_white.svg"
    mkdir -p "$DESKTOP_DIR"

    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=SESHAT
Comment=SESHAT Pipeline Config Editor
Exec=$SESHAT_BIN gui
Icon=$ICON_PATH
Terminal=false
Categories=Science;Education;
StartupNotify=true
EOF
    chmod +x "$DESKTOP_FILE"
    echo "✓ Linux desktop app created at $DESKTOP_FILE"
fi

echo ""
if command -v seshat &> /dev/null; then
    echo "✅ Installation complete!"
    echo ""
    echo "Usage:"
    echo "  seshat gui                        # Launch GUI"
    echo "  seshat run --config config.yml    # Run pipeline"
    echo "  seshat report --config config.yml # Generate HTML report only"
    echo ""
    echo "('natmeg' is also available as a deprecated alias for 'seshat')"
    echo ""
    echo "To update later:      bash install.sh"
    echo "To uninstall:         $([ "$INSTALLER" = "uv" ] && echo "uv tool uninstall seshat" || echo "pipx uninstall seshat")"
else
    echo "⚠ Installed, but 'seshat' is not yet on PATH in this shell."
    echo "  Open a new terminal, or run:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi
