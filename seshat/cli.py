#!/usr/bin/env python3
"""
SESHAT Pipeline — main CLI entry point.
Replaces natmeg_pipeline.py.
"""
import sys
import os
import argparse
import warnings
import yaml

from seshat.utils import log, configure_logging


def main():
    """Main entry point for the seshat command."""
    parser = argparse.ArgumentParser(
        description="SESHAT MEG/EEG Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create default configuration file
  seshat create-config                    # Creates default_config.yml
  seshat create-config -o my_config.yml  # Creates my_config.yml

  # Launch GUI for interactive configuration
  seshat gui
  seshat gui --config existing_config.yml

  # Run complete processing pipeline
  seshat run --config config.yml

  # Run individual pipeline components
  seshat copy --config config.yml
  seshat opm-preprocess --config config.yml
  seshat maxfilter --config config.yml
  seshat bidsify --config config.yml

  # Server synchronization
  seshat sync --config project.yml [--dry-run]
  seshat sync --directory /data/project [--dry-run]
  seshat sync --create-config
  seshat sync --test --server cir --server-config servers.yml
        """,
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # gui
    gui_parser = subparsers.add_parser('gui', help='Launch configuration GUI')
    gui_parser.add_argument('--config', help='Configuration file to load')
    gui_parser.add_argument('--create-config', help='Create default configuration file and exit')

    # run
    run_parser = subparsers.add_parser('run', help='Run complete pipeline')
    run_parser.add_argument('--config', required=True, help='Configuration file')
    run_parser.add_argument('--dry-run', action='store_true', help='Preview without executing')
    run_parser.add_argument('--delete', action='store_true', help='Delete files on server not in source')
    run_parser.add_argument('--exclude', action='append', help='Exclude pattern')
    run_parser.add_argument('--include', action='append', help='Include pattern')
    run_parser.add_argument('--no-report', action='store_true', help='Skip final HTML report generation')

    # individual stages
    copy_parser = subparsers.add_parser('copy', help='Data copy only')
    copy_parser.add_argument('--config', required=True, help='Configuration file')

    opm_parser = subparsers.add_parser('opm-preprocess', help='OPM preprocessing only')
    opm_parser.add_argument('--config', required=True, help='Configuration file')

    maxfilter_parser = subparsers.add_parser('maxfilter', help='MaxFilter processing only')
    maxfilter_parser.add_argument('--config', required=True, help='Configuration file')
    maxfilter_parser.add_argument('--dry-run', action='store_true', help='Show commands without executing')

    bidsify_parser = subparsers.add_parser('bidsify', help='BIDS conversion only')
    bidsify_parser.add_argument('--config', required=True, help='Configuration file')

    report_parser = subparsers.add_parser('report', help='Generate project HTML report only')
    report_parser.add_argument('--config', required=True, help='Project configuration file')
    report_parser.add_argument('--no-report', action='store_true', help='(Ignored for compatibility)')

    create_config_parser = subparsers.add_parser('create-config', help='Create default configuration file')
    create_config_parser.add_argument('--output', '-o', default='default_config.yml',
                                      help='Output filename (default: default_config.yml)')

    sync_parser = subparsers.add_parser('sync', help='Sync data to remote server')
    sync_parser.add_argument('--config', help='Project configuration file')
    sync_parser.add_argument('--directory', nargs='*', metavar=('PATH', 'SERVER'),
                             help='Sync custom directory to specified server')
    sync_parser.add_argument('--dry-run', action='store_true', help='Preview without transferring')
    sync_parser.add_argument('--create-config', action='store_true', help='Create example server configuration file')
    sync_parser.add_argument('--server-config', help='Server configuration file')
    sync_parser.add_argument('--server', help='Server name (default: cir)', default='cir')
    sync_parser.add_argument('--test', action='store_true', help='Test connection to server and exit')
    sync_parser.add_argument('--exclude', action='append', metavar='PATTERN', help='Exclude files matching pattern')
    sync_parser.add_argument('--include', action='append', metavar='PATTERN', help='Include files matching pattern')
    sync_parser.add_argument('--delete', action='store_true',
                             help='Delete local files after successful sync (use with caution!)', default=False)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == 'gui':
            from seshat.config import config_UI
            config_UI(args.config)

        elif args.command == 'run':
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)

            from seshat.config import rename_legacy_keys
            config = rename_legacy_keys(config)

            # Phase 2.4: use new key names
            logfile = config['Project'].get('logfile', 'pipeline_log.log')
            project_root = os.path.join(config['Project'].get('Root', '.'), config['Project'].get('Name', ''))
            logpath = os.path.join(project_root, 'logs')
            os.makedirs(logpath, exist_ok=True)
            configure_logging(log_dir=logpath, log_file=logfile)

            dry_run = getattr(args, 'dry_run', False)

            log("Pipeline", '----------------------------------------------------', 'info')
            log("Pipeline", f'Using config file: {args.config}', 'info', f'{logpath}/{logfile}')

            if dry_run:
                log("Pipeline", "DRY RUN MODE - No actual processing will be performed", 'info',
                    f'{logpath}/{logfile}')

            log("Pipeline", "Starting", 'info', f'{logpath}/{logfile}')

            pipeline_success = []

            if config['RUN'].get('copy_raw', False):
                from seshat.stages import copy as copy_stage
                copy_success = copy_stage.main(args.config)
                pipeline_success.append(copy_success)

            if config['RUN'].get('opm_preprocess', False):
                from seshat.stages import opm_preprocess as opm_stage
                opm_preprocess_success = opm_stage.main(args.config)
                pipeline_success.append(opm_preprocess_success)

            # if config['RUN'].get('Run Maxfilter', False):
            #     from seshat.stages import maxfilter as mf_stage
            #     maxfilter_success = mf_stage.main(args.config, dry_run=dry_run)
            #     pipeline_success.append(maxfilter_success)

            # if config['RUN'].get('Run BIDS conversion', False):
            #     from seshat.stages import bidsify as bids_stage
            #     bids_success = bids_stage.main(args.config)
            #     pipeline_success.append(bids_success)

            if config['RUN'].get('sync', False):
                from seshat.stages import sync as sync_stage
                bids_path = config['Project'].get('BIDS', '.')
                sync_path = os.path.dirname(bids_path) if bids_path else '.'

                syncer = sync_stage.ServerSync()
                success = syncer.sync_directory(
                    sync_path, 'cir',
                    exclude_patterns=getattr(args, 'exclude', None),
                    include_patterns=getattr(args, 'include', None),
                    dry_run=dry_run,
                    delete=getattr(args, 'delete', False),
                )
                pipeline_success.append(success)

            if not getattr(args, 'no_report', False):
                try:
                    from seshat.stages import report as report_stage
                    report_stage.main(args.config)
                    log("Pipeline", "Report generated (report.html)", 'info', f'{logpath}/{logfile}')
                except Exception as e:
                    log("Pipeline", f"Report generation failed: {e}", 'warning', f'{logpath}/{logfile}')

            if all(pipeline_success):
                log("Pipeline", "Completed successfully!", 'info', f'{logpath}/{logfile}')
            else:
                log("Pipeline", f"Completed with errors, see {logpath}/{logfile}", 'error',
                    f'{logpath}/{logfile}')

        elif args.command == 'copy':
            from seshat.stages import copy as copy_stage
            copy_stage.main(args.config)

        elif args.command == 'opm-preprocess':
            from seshat.stages import opm_preprocess as opm_stage
            opm_stage.main(args.config)

        elif args.command == 'maxfilter':
            from seshat.stages import maxfilter as mf_stage
            dry_run = getattr(args, 'dry_run', False)
            mf_stage.main(args.config, dry_run=dry_run)

        elif args.command == 'bidsify':
            # bidsify stage is not yet implemented; stub kept for CLI compatibility
            log("Pipeline", "bidsify stage is not yet implemented", 'warning')

        elif args.command == 'report':
            try:
                from seshat.stages import report as report_stage
                report_stage.main(args.config)
                log("Report", "Report generated (report.html)", 'info')
            except Exception as e:
                log("Report", f"Report generation failed: {e}", 'error')
                sys.exit(1)

        elif args.command == 'create-config':
            from seshat.config import create_config_file
            success = create_config_file(args.output)
            if success:
                print(f"Created default configuration file: {args.output}")
                print("Edit this file to customize your pipeline settings.")
            else:
                print(f"Failed to create configuration file: {args.output}")
                sys.exit(1)

        elif args.command == 'sync':
            from seshat.stages import sync as sync_stage

            if args.create_config:
                example = sync_stage.create_example_config()
                cfg_file = 'server_sync_config.yml'
                with open(cfg_file, 'w') as f:
                    yaml.dump(example, f, default_flow_style=False, indent=2, sort_keys=False)
                print(f"Created example configuration file: {cfg_file}")
                print("Edit this file with your server details before using the sync tool.")
                return

            if args.server_config:
                syncer = sync_stage.ServerSync(args.server_config)
            else:
                try:
                    syncer = sync_stage.ServerSync()
                except FileNotFoundError:
                    print("No default server config found. Use --create-config or --server-config.")
                    return

            if args.test:
                syncer.check_server_connection(args.server)
                return

            if args.directory:
                local_path = args.directory[0]
                server = args.server
                if len(args.directory) > 1 and not args.server:
                    server = args.directory[1]
                success = syncer.sync_directory(
                    local_path, server,
                    exclude_patterns=args.exclude,
                    include_patterns=args.include,
                    dry_run=args.dry_run,
                    delete=args.delete,
                )
                if success:
                    log("Sync", "Completed successfully!", 'info')
                else:
                    log("Sync", "Failed. Check log files for details.", 'error')

            elif args.config:
                try:
                    with open(args.config, 'r') as f:
                        proj_cfg = yaml.safe_load(f)

                    from seshat.config import rename_legacy_keys
                    proj_cfg = rename_legacy_keys(proj_cfg)

                    project_name = proj_cfg.get('Project', {}).get('Name', None)
                    root_name = proj_cfg.get('Project', {}).get('Root', None)

                    if not project_name or not root_name:
                        print("Project name and root directory must be specified.")
                        return

                    local_path = os.path.join(root_name, project_name)
                    if os.path.exists(local_path):
                        print(f"Inferred local directory from project config: {local_path}")
                    else:
                        print('Could not infer directory from project config; specify --directory')
                        return
                except Exception as e:
                    print(f'Error reading project config {args.config}: {e}')
                    return

                success = syncer.sync_directory(
                    local_path, args.server,
                    exclude_patterns=args.exclude,
                    include_patterns=args.include,
                    dry_run=args.dry_run,
                    delete=args.delete,
                )
                if success:
                    log("Sync", "Completed successfully!", 'info')
                else:
                    log("Sync", "Failed. Check log files for details.", 'error')

            else:
                sync_stage.main()

    except Exception as e:
        log("Pipeline", f"Error: {e}", 'error')
        sys.exit(1)


def natmeg_compat():
    """Deprecated entry point. Use 'seshat' instead."""
    warnings.warn(
        "The 'natmeg' command is deprecated. Use 'seshat' instead.",
        DeprecationWarning,
        stacklevel=1,
    )
    print("[WARNING] 'natmeg' is deprecated. Please update your scripts to use 'seshat'.")
    main()


if __name__ == "__main__":
    main()
