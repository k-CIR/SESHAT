# CLI Usage

The `seshat` command provides access to all pipeline functionality.

> **Note:** The `natmeg` command is still available as a deprecated alias. Please update scripts to use `seshat`.

## GUI

```bash
seshat gui
```

## Configuration

```bash
seshat create-config --output my_config.yml
```

## Run Pipeline

```bash
seshat run --config config.yml
seshat run --config config.yml --dry-run
seshat run --config config.yml --no-report
```

## Individual Components

```bash
seshat copy --config config.yml
seshat opm-preprocess --config config.yml
seshat maxfilter --config config.yml
```

## Server Synchronization

```bash
seshat sync --create-config
seshat sync --server-config servers.yml --test
seshat sync --directory /data/project
seshat sync --directory /data/project --delete
```

## Reports

```bash
seshat report --config config.yml
```

## Help

```bash
seshat --help
seshat run --help
```
