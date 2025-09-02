#!/bin/bash
# Cross-platform NatMEG Pipeline installer

#set -e

echo "Installing NatMEG Pipeline..."

# Detect operating system
OS=$(uname -s)
ARCH=$(uname -m)

echo "Detected platform: $OS ($ARCH)"

# Function to find conda installation
find_conda_path() {
    # Check if conda is already in PATH
    if command -v conda &> /dev/null; then
        local conda_exe=$(which conda)
        local conda_base=$(dirname $(dirname "$conda_exe"))
        echo "$conda_base"
        return 0
    fi
    
    # Common conda installation paths by platform
    local conda_paths=()
    case "$OS" in
        "Darwin")  # macOS
            conda_paths=(
                "/opt/homebrew/Caskroom/miniconda/base"
                "/usr/local/Caskroom/miniconda/base"
                "/usr/local/Caskroom/miniforge3/base"
                "$HOME/miniconda3"
                "$HOME/miniforge3"
                "$HOME/anaconda3"
                "$HOME/conda"
                "/opt/miniconda3"
                "/opt/miniforge3"
                "/opt/anaconda3"
            )
            ;;
        "Linux")
            conda_paths=(
                "$HOME/miniconda3"
                "$HOME/miniforge3"
                "$HOME/anaconda3"
                "/opt/miniconda3"
                "/opt/miniforge3"
                "/opt/anaconda3"
                "/usr/local/miniconda3"
                "/usr/local/miniforge3"
                "/usr/local/anaconda3"
            )
            ;;
        *)
            echo "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    # Check common installation paths
    for path in "${conda_paths[@]}"; do
        if [ -d "$path" ] && [ -f "$path/etc/profile.d/conda.sh" ]; then
            echo "$path"
            return 0
        fi
    done
    
    return 1
}

# Find conda installation
echo "Looking for conda installation..."
if CONDA_BASE=$(find_conda_path); then
    echo "Found conda at: $CONDA_BASE"
else
    echo "Error: Could not find conda installation"
    echo ""
    echo "Please install conda first:"
    case "$OS" in
        "Darwin")
            echo "  brew install miniconda"
            echo "  or download from: https://docs.conda.io/en/latest/miniconda.html"
            ;;
        "Linux")
            echo "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
            echo "  bash Miniconda3-latest-Linux-x86_64.sh"
            ;;
    esac
    exit 1
fi


# Copy relevant files to local
if [ -f "$HOME/.local/bin/NatMEG-utils" ]; then
    echo "NatMEG utils already exists at $HOME/.local/bin/NatMEG-utils"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi
RELEVANT_FILES=("install.sh" "natmeg_pipeline.py" "utils.py" "copy_to_cerberos.py" "maxfilter.py" "add_hpi.py" "bidsify.py" "sync_to_cir.py" "render_report.py" "report_template.html" "README.md" "run_config.py") 
SOURCE_DIR=$(pwd)
TARGET_DIR="$HOME/.local/bin/NatMEG-utils"

# Create local bin directory
mkdir -p "$HOME/.local/bin"
mkdir -p "$TARGET_DIR"

for file in "${RELEVANT_FILES[@]}"; do
    if [ -f "$SOURCE_DIR/$file" ]; then
        cp "$SOURCE_DIR/$file" "$TARGET_DIR"
        echo "Copied $file to $TARGET_DIR"
    else
        echo "Warning: $file does not exist in $SOURCE_DIR"
    fi
done

# Determine shell config file
SHELL_CONFIG=""
if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
    SHELL_CONFIG="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
    SHELL_CONFIG="$HOME/.bashrc"
else
    SHELL_CONFIG="$HOME/.profile"
fi

echo "Using shell config: $SHELL_CONFIG"

# Create the natmeg executable
echo "Creating natmeg executable..."
if [ -f "$HOME/.local/bin/NatMEG-utils/natmeg" ]; then
    echo "natmeg executable already exists at $HOME/.local/bin/NatMEG-utils/natmeg"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

cat > "$HOME/.local/bin/NatMEG-utils/natmeg" << EOF
#!/bin/bash
# NatMEG Pipeline Executable - Auto-generated

# SAFETY CHECKS - Prevent terminal crashes at all costs
set +e  # Don't exit on errors
set +u  # Don't exit on undefined variables
set +o pipefail  # Don't exit on pipe failures

# Disable bash strict mode completely to prevent crashes
unset BASH_ENV
unset ENV

# Multiple layers of error handling
trap 'echo "Warning: Error in natmeg script, but terminal will remain open." >&2; exit 1' ERR
trap 'echo "Warning: Script interrupted, but terminal will remain open." >&2; exit 130' INT
trap 'echo "Warning: Script terminated, but terminal will remain open." >&2; exit 143' TERM

# Safety function to test conda without crashing
safe_conda_test() {
    local cmd="\$1"
    shift
    if command -v conda >/dev/null 2>&1; then
        # Use timeout to prevent hanging
        if command -v timeout >/dev/null 2>&1; then
            timeout 10 conda "\$cmd" "\$@" 2>/dev/null || return 1
        else
            conda "\$cmd" "\$@" 2>/dev/null || return 1
        fi
    else
        return 1
    fi
}

# Function to find and initialize conda with safety checks
find_and_init_conda() {
    # Check if conda is already available
    if command -v conda >/dev/null 2>&1; then
        if safe_conda_test --version >/dev/null; then
            return 0
        fi
    fi
    
    # Try sourcing the detected conda installation first
    if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ] && [ -r "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        if source "$CONDA_BASE/etc/profile.d/conda.sh" >/dev/null 2>&1; then
            if command -v conda >/dev/null 2>&1 && safe_conda_test --version >/dev/null; then
                return 0
            fi
        fi
    fi
    
    # Fallback: try sourcing shell config files
    for config in "\$HOME/.zshrc" "\$HOME/.bashrc" "\$HOME/.profile"; do
        if [ -f "\$config" ] && [ -r "\$config" ]; then
            if source "\$config" >/dev/null 2>&1; then
                if command -v conda >/dev/null 2>&1 && safe_conda_test --version >/dev/null; then
                    return 0
                fi
            fi
        fi
    done
    
    echo "Error: Could not initialize conda"
    echo "Detected conda base: $CONDA_BASE"
    echo "Please ensure conda is properly installed and accessible."
    return 1
}

# Initialize conda with safety checks
if ! find_and_init_conda; then
    echo "Failed to initialize conda. Exiting safely."
    exit 1
fi

# Verify conda is working before proceeding (silent check)
if ! safe_conda_test --version >/dev/null; then
    echo "Error: Conda found but not working properly"
    echo "Try running manually: conda --version"
    exit 1
fi

# Check if environment exists with safety checks
ENV_NAME="natmeg_utils"

# Safe environment check (silent)
env_exists=false
if env_list=\$(safe_conda_test env list 2>/dev/null); then
    if echo "\$env_list" | grep -q "\$ENV_NAME"; then
        env_exists=true
    fi
fi

if [ "\$env_exists" = false ]; then
    echo "Error: Conda environment '\$ENV_NAME' not found"
    echo ""
    echo "Available environments:"
    safe_conda_test env list 2>/dev/null || echo "  (could not list environments)"
    echo ""
    echo "To create the environment:"
    echo "  conda create -n \$ENV_NAME python=3.9 -y"
    echo "  conda activate \$ENV_NAME"
    echo "  cd \$(dirname "\$0")"
    echo "  pip install -e ."
    exit 1
fi

# Safe environment execution with multiple fallbacks
# Check if we're already in the right environment
current_env="\${CONDA_DEFAULT_ENV:-none}"
if [ "\$current_env" = "\$ENV_NAME" ]; then
    execution_method="direct"
else
    execution_method="conda_run"
fi

# Run natmeg pipeline with safety checks
SCRIPT_PATH="\$HOME/.local/bin/NatMEG-utils/natmeg_pipeline.py"
if [ ! -f "\$SCRIPT_PATH" ]; then
    echo "Error: Could not find natmeg_pipeline.py at \$SCRIPT_PATH"
    echo "Please ensure the NatMEG-utils repository is at the correct location"
    exit 1
fi

if [ ! -r "\$SCRIPT_PATH" ]; then
    echo "Error: Cannot read natmeg_pipeline.py at \$SCRIPT_PATH"
    echo "Please check file permissions"
    exit 1
fi

# Execute with appropriate method and safety checks
case "\$execution_method" in
    "direct")
        python "\$SCRIPT_PATH" "\$@"
        ;;
    "conda_run")
        # Test conda run first
        if safe_conda_test run -n "\$ENV_NAME" python --version >/dev/null; then
            conda run -n "\$ENV_NAME" python "\$SCRIPT_PATH" "\$@"
        else
            echo "Error: Cannot execute in environment \$ENV_NAME"
            echo "Try manually: conda activate \$ENV_NAME && python \$SCRIPT_PATH"
            exit 1
        fi
        ;;
    *)
        echo "Error: Unknown execution method"
        exit 1
        ;;
esac
EOF

# Make it executable
chmod +x "$HOME/.local/bin/NatMEG-utils/natmeg"

# Add to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin/NatMEG-utils"; then
    echo "Adding $HOME/.local/bin/NatMEG-utils to PATH in $SHELL_CONFIG"
    echo 'export PATH="$HOME/.local/bin/NatMEG-utils:$PATH"' >> "$SHELL_CONFIG"
    echo "Please run: source $SHELL_CONFIG"
else
    echo "$HOME/.local/bin/NatMEG-utils is already in PATH"
fi

# Check conda environment (reuse existing conda initialization)
echo "Checking conda environment..."
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh" 2>/dev/null
fi

if command -v conda &> /dev/null && conda env list 2>/dev/null | grep -q "natmeg_utils"; then
    echo "✓ Conda environment 'natmeg_utils' found"
    ENV_EXISTS=true
else
    echo "⚠ Warning: Conda environment 'natmeg_utils' not found"
    ENV_EXISTS=false
fi

echo ""
echo "Installation complete!"
echo ""
echo "Testing the installation..."

# Test if the executable works
if command -v natmeg &> /dev/null || [ -f "$HOME/.local/bin/NatMEG-utils/natmeg" ]; then
    echo "✓ natmeg executable created successfully"
    
    # Test basic execution only if environment exists
    if [ "$ENV_EXISTS" = true ] && "$HOME/.local/bin/NatMEG-utils/natmeg" --help &> /dev/null; then
        echo "✓ natmeg executable runs correctly"
        INSTALL_SUCCESS=true
    else
        echo "⚠ natmeg executable created but needs conda environment setup"
        INSTALL_SUCCESS=false
    fi
else
    echo "✗ Failed to create natmeg executable"
    INSTALL_SUCCESS=false
fi

echo ""
echo "Usage:"
echo "  natmeg gui                      # Launch GUI"
echo "  natmeg run --config config.yml   # Run pipeline"
echo "  natmeg report --config config.yml # Generate HTML report only"
echo ""

# Conditional instructions based on installation status
if [ "$ENV_EXISTS" = false ]; then
    echo "NEXT STEPS - Create conda environment:"
    echo "  1. source $SHELL_CONFIG"
    echo "  2. conda create -n natmeg_utils python=3.9 -y"
    echo "  3. conda activate natmeg_utils"
    echo "  4. cd \$(dirname "\$0")"
    echo "  5. pip install -e ."
    echo "  6. Test with: natmeg --help"
elif [ "$INSTALL_SUCCESS" = true ]; then
    echo "✅ Installation complete and ready to use!"
    echo "Test with: natmeg --help"
else
    echo "TROUBLESHOOTING:"
    echo "  - Ensure conda is working: conda --version"
    echo "  - Check PATH: echo \$PATH"
    echo "  - View executable: cat ~/.local/bin/NatMEG-utils/natmeg"
    echo "  - Re-run installer if needed"
fi