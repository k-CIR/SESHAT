# Contributing

Improvements and contributions are welcome.

## Development Guidelines

- Do not modify scripts locally for personal workflows without contributing changes upstream.
- Follow standard GitHub practices: create a branch or fork before making changes.
- Submit pull requests for all modifications.
- Ensure installation works on Rocky Linux/RHEL (primary target), Debian/Ubuntu, and macOS.
- Test compatibility with both `uv` and `pipx` installers (`bash install.sh --uv` / `--pipx`).

## Testing Installation

```bash
bash install.sh --editable

seshat --help
seshat gui
```
