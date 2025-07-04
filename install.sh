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
    # Common conda installation paths by platform
    local conda_paths=()
    
    case "$OS" in
        "Darwin")  # macOS
            conda_paths=(
                "/opt/homebrew/Caskroom/miniconda/base"
                "/usr/local/Caskroom/miniconda/base"
                "$HOME/miniconda3"
                "$HOME/anaconda3"
                "$HOME/conda"
                "/opt/miniconda3"
                "/opt/anaconda3"
            )
            ;;
        "Linux")
            conda_paths=(
                "$HOME/miniconda3"
                "$HOME/anaconda3"
                "/opt/miniconda3"
                "/opt/anaconda3"
                "/usr/local/miniconda3"
                "/usr/local/anaconda3"
            )
            ;;
        *)
            echo "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    # Check if conda is already in PATH
    if command -v conda &> /dev/null; then
        local conda_exe=$(which conda)
        local conda_base=$(dirname $(dirname "$conda_exe"))
        echo "$conda_base"
        return 0
    fi
    
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

# Create local bin directory
mkdir -p "$HOME/.local/bin"

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
if [ -f "$HOME/.local/bin/natmeg" ]; then
    echo "natmeg executable already exists at $HOME/.local/bin/natmeg"
    read -p "Do you want to overwrite it? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled."
        exit 0
    fi
fi

cat > "$HOME/.local/bin/natmeg" << EOF
#!/bin/bash
# NatMEG Pipeline Executable - Auto-generated

# Don't exit on errors to prevent terminal crashes
set +e

# Function to find and initialize conda
find_and_init_conda() {
    # Check if conda is already available
    if command -v conda &> /dev/null; then
        return 0
    fi
    
    # Try sourcing shell config files to initialize conda
    for config in "\$HOME/.zshrc" "\$HOME/.bashrc" "\$HOME/.profile"; do
        if [ -f "\$config" ]; then
            source "\$config" 2>/dev/null
            if command -v conda &> /dev/null; then
                return 0
            fi
        fi
    done
    
    # List of possible conda paths
    local conda_paths=(
        "$CONDA_BASE"
        "/opt/homebrew/Caskroom/miniconda/base"
        "/usr/local/Caskroom/miniconda/base"
        "\$HOME/miniconda3"
        "\$HOME/anaconda3"
        "\$HOME/conda"
        "/opt/miniconda3"
        "/opt/anaconda3"
        "/usr/local/miniconda3"
        "/usr/local/anaconda3"
    )
    
    # Try to find conda.sh in common locations
    for path in "\${conda_paths[@]}"; do
        if [ -f "\$path/etc/profile.d/conda.sh" ]; then
            source "\$path/etc/profile.d/conda.sh" 2>/dev/null
            if command -v conda &> /dev/null; then
                return 0
            fi
        fi
    done
    
    echo "Error: Could not find conda installation"
    echo "Searched in:"
    printf '  %s\\n' "\${conda_paths[@]}"
    echo ""
    echo "Please ensure conda is installed and try:"
    echo "  source ~/.zshrc  # or ~/.bashrc"
    echo "  conda --version"
    return 1
}

# Initialize conda
if ! find_and_init_conda; then
    exit 1
fi

# Check if environment exists
ENV_NAME="natmeg_utils"
if ! conda env list 2>/dev/null | grep -q "\$ENV_NAME"; then
    echo "Error: Conda environment '\$ENV_NAME' not found"
    echo ""
    echo "Available environments:"
    conda env list 2>/dev/null || echo "  (none - conda may not be working)"
    echo ""
    echo "To create the environment:"
    echo "  conda create -n \$ENV_NAME python=3.9 -y"
    echo "  conda activate \$ENV_NAME"
    echo "  cd $HOME/Sites/NatMEG-utils"
    echo "  pip install -e ."
    exit 1
fi

# Check if we're already in the right environment
if [ "\$CONDA_DEFAULT_ENV" = "\$ENV_NAME" ]; then
    echo "Already in environment \$ENV_NAME"
else
    # Activate environment
    echo "Activating environment \$ENV_NAME..."
    conda activate "\$ENV_NAME" 2>/dev/null
    if [ \$? -ne 0 ]; then
        echo "Error: Failed to activate conda environment '\$ENV_NAME'"
        echo "Try running: conda activate \$ENV_NAME"
        exit 1
    fi
fi

# Run natmeg pipeline
SCRIPT_PATH="$HOME/Sites/NatMEG-utils/natmeg_pipeline.py"
if [ -f "\$SCRIPT_PATH" ]; then
    python "\$SCRIPT_PATH" "\$@"
else
    echo "Error: Could not find natmeg_pipeline.py at \$SCRIPT_PATH"
    echo "Please ensure the NatMEG-utils repository is at the correct location"
    exit 1
fi
EOF

# Make it executable
chmod +x "$HOME/.local/bin/natmeg"

# Add to PATH if not already there
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo "Adding $HOME/.local/bin to PATH in $SHELL_CONFIG"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_CONFIG"
    echo "Please run: source $SHELL_CONFIG"
else
    echo "$HOME/.local/bin is already in PATH"
fi

# Initialize conda for environment check
echo "Checking conda environment..."
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
fi

# Check if conda environment exists
if command -v conda &> /dev/null && conda env list 2>/dev/null | grep -q "natmeg_utils"; then
    echo "✓ Conda environment 'natmeg_utils' found"
else
    echo "⚠ Warning: Conda environment 'natmeg_utils' not found"
    echo ""
    echo "To create the environment:"
    echo "  conda create -n natmeg_utils python=3.9 -y"
    echo "  conda activate natmeg_utils"
    echo "  cd $HOME/Sites/NatMEG-utils"
    echo "  pip install -e ."
fi

echo ""
echo "Installation complete!"
echo ""
echo "Testing the installation..."

# Test if the executable works
if command -v natmeg &> /dev/null || [ -f "$HOME/.local/bin/natmeg" ]; then
    echo "✓ natmeg executable created successfully"
    
    # Test basic execution (initialize conda first for testing)
    if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
        source "$CONDA_BASE/etc/profile.d/conda.sh" 2>/dev/null
    fi
    
    if "$HOME/.local/bin/natmeg" --help &> /dev/null; then
        echo "✓ natmeg executable runs correctly"
    else
        echo "⚠ natmeg executable created but may need conda environment"
    fi
else
    echo "✗ Failed to create natmeg executable"
fi

echo ""
echo "Usage:"
echo "  natmeg gui                    # Launch GUI"
echo "  natmeg run --config config.yml  # Run pipeline"
echo ""
echo "If this is your first time:"
echo "  1. source $SHELL_CONFIG"
echo "  2. Create conda environment if needed:"
echo "     conda create -n natmeg_utils python=3.9 -y"
echo "     conda activate natmeg_utils"
echo "     cd $HOME/Sites/NatMEG-utils"
echo "     pip install -e ."
echo "  3. Test with: natmeg --help"
echo ""
echo "Troubleshooting:"
echo "  - Check if conda is working: conda --version"
echo "  - Check PATH includes ~/.local/bin: echo \$PATH"
echo "  - View executable: cat ~/.local/bin/natmeg"