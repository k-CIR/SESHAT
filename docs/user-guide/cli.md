# CLI Usage

The `natmeg` command provides access to all pipeline functionality.

## GUI

```bash
natmeg gui
```

## Configuration

```bash
natmeg create-config --output my_config.yml
```

## Run Pipeline

```bash
natmeg run --config config.yml
natmeg run --config config.yml --dry-run
natmeg run --config config.yml --no-report
```

## Individual Components

```bash
natmeg copy --config config.yml
natmeg hpi --config config.yml
natmeg maxfilter --config config.yml
```

## Server Synchronization

```bash
natmeg sync --create-config
natmeg sync --server-config servers.yml --test
natmeg sync --directory /data/project
natmeg sync --directory /data/project --delete
```

## Reports

```bash
natmeg report --config config.yml
```

## Help

```bash
natmeg --help
natmeg run --help
```
