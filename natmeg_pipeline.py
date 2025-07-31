#!/usr/bin/env python3
"""
NatMEG Pipeline Application
Main executable entry point for the NatMEG processing pipeline
"""

import sys
import os
import argparse
from pathlib import Path
import yaml
from utils import log

# Add the current directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main entry point for the natmeg command"""
    parser = argparse.ArgumentParser(
        description="NatMEG MEG/EEG Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch GUI for interactive configuration
  natmeg gui
  natmeg gui --config existing_config.yml
  
  # Run complete processing pipeline
  natmeg run --config config.yml
  
  # Run individual pipeline components
  natmeg copy --config config.yml         # Data synchronization only
  natmeg hpi --config config.yml          # HPI coregistration only
  natmeg maxfilter --config config.yml    # MaxFilter processing only
  natmeg bidsify --config config.yml      # BIDS conversion only
  
  # Server synchronization workflow
  natmeg sync create-config                               # Create example server config
  natmeg sync test cir --config servers.yml               # Test server connection
  natmeg sync directory /data/project cir --dry-run       # Preview sync operation
  natmeg sync directory /data/project cir --delete        # Sync with deletion
  natmeg sync directory /data/project cir --exclude "*.log" --include "*.fif"
  
  # Advanced sync options
  natmeg sync directory ./processed_data server_name \\
    --exclude "temp/*" --exclude "*.tmp" \\
    --include "derivatives/*" \\
    --dry-run --delete

For more information, visit: https://github.com/natmeg/natmeg-utils
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # GUI command
    gui_parser = subparsers.add_parser('gui', help='Launch configuration GUI')
    gui_parser.add_argument('--config', help='Configuration file to load')
    
    # Run complete pipeline
    run_parser = subparsers.add_parser('run', help='Run complete pipeline')
    run_parser.add_argument('--config', required=True, help='Configuration file')
    run_parser.add_argument('--dry-run', action='store_true', help='Show what would be executed without actually running it')
    run_parser.add_argument('--delete', action='store_true', help='Delete files on server not in source')
    run_parser.add_argument('--exclude', action='append', help='Exclude pattern (can be used multiple times)')
    run_parser.add_argument('--include', action='append', help='Include pattern (can be used multiple times)')
    
    # Individual components
    copy_parser = subparsers.add_parser('copy', help='Data synchronization only')
    copy_parser.add_argument('--config', required=True, help='Configuration file')
    
    hpi_parser = subparsers.add_parser('hpi', help='HPI coregistration only')
    hpi_parser.add_argument('--config', required=True, help='Configuration file')
    
    maxfilter_parser = subparsers.add_parser('maxfilter', help='MaxFilter processing only')
    maxfilter_parser.add_argument('--config', required=True, help='Configuration file')
    maxfilter_parser.add_argument('--dry-run', action='store_true', help='Show MaxFilter commands without executing them')
    
    bidsify_parser = subparsers.add_parser('bidsify', help='BIDS conversion only')
    bidsify_parser.add_argument('--config', required=True, help='Configuration file')
    
    # Server sync commands
    sync_parser = subparsers.add_parser('sync', help='Sync data to remote server')
    sync_subparsers = sync_parser.add_subparsers(dest='sync_command', help='Sync options')
    
    # Create config
    create_config_parser = sync_subparsers.add_parser('create-config', help='Create example server configuration')
    
    # Test connection
    test_parser = sync_subparsers.add_parser('test', help='Test server connection')
    test_parser.add_argument('server', nargs='?', default='cir', help='Server name from server config (default: cir)')
    test_parser.add_argument('--server-config', help='Server configuration file')
    
    # Sync custom directory
    directory_parser = sync_subparsers.add_parser('directory', help='Sync custom directory')
    directory_parser.add_argument('path', help='Local directory path to sync')
    directory_parser.add_argument('server', nargs='?', default='cir', help='Server name from config (default: cir)')
    directory_parser.add_argument('--server-config', help='Server configuration file')
    directory_parser.add_argument('--dry-run', action='store_true', help='Show what would be synced without doing it')
    directory_parser.add_argument('--delete', action='store_true', help='Delete files on server not in source', default=False)
    directory_parser.add_argument('--exclude', action='append', help='Exclude pattern (can be used multiple times)')
    directory_parser.add_argument('--include', action='append', help='Include pattern (can be used multiple times)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'gui':
            from run_config import config_UI
            config = config_UI(args.config)
            if config:
                log("Configuration saved successfully!", 'info')
        
        elif args.command == 'run':
            # Run complete pipeline
            
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            
            logfile = config['project'].get('Logfile', 'pipeline_log.log')
            # Create log directory in the project root (parent of squidMEG/opmMEG/BIDS)
            project_root = os.path.dirname(config['project'].get('squidMEG', '.')) or os.path.dirname(config['project'].get('opmMEG', '.'))
            logpath = os.path.join(project_root, 'log')
            os.makedirs(logpath, exist_ok=True)
            dry_run = getattr(args, 'dry_run', False)
            
            if dry_run:
                log("DRY RUN MODE - No actual processing will be performed", 'info', logfile=logfile, logpath=logpath)

            log("Starting complete NatMEG pipeline", 'info', logfile=logfile, logpath=logpath)
            
            pipeline_success = []
            
            # Execute pipeline steps based on config
            if config['RUN'].get('Copy to Cerberos', False):
                log("Running data synchronization...", 'info', logfile=logfile, logpath=logpath)
                import copy_to_cerberos
                copy_success = copy_to_cerberos.main(args.config)
                pipeline_success.append(copy_success)
                
            if config['RUN'].get('Add HPI coregistration', False):
                log("Running HPI coregistration...", 'info', logfile=logfile, logpath=logpath)
                import add_hpi
                hpi_success = add_hpi.main(args.config)
                pipeline_success.append(hpi_success)

            if config['RUN'].get('Run Maxfilter', False):
                if dry_run:
                    log("DRY RUN: Would run MaxFilter processing...", 'info', logfile=logfile, logpath=logpath)
                else:
                    log("Running MaxFilter processing...", 'info', logfile=logfile, logpath=logpath)
                import maxfilter
                maxfilter_success = maxfilter.main(args.config, dry_run=dry_run)
                pipeline_success.append(maxfilter_success)

            if config['RUN'].get('Run BIDS conversion', False):
                log("Running BIDS conversion...", 'info', logfile=logfile, logpath=logpath)
                import bidsify
                bids_success = bidsify.main(args.config)
                pipeline_success.append(bids_success)
            
            if config['RUN'].get('Sync to CIR', False):
                if dry_run:
                    log("DRY RUN: Would sync to CIR server...", 'info', logfile=logfile, logpath=logpath)
                else:
                    log("Syncing to CIR server...", 'info', logfile=logfile, logpath=logpath)
                
                import sync_to_cir
                # Use BIDS directory as the sync source
                bids_path = config['project'].get('BIDS', '.')
                sync_path = os.path.dirname(bids_path) if bids_path else '.'
                
                syncer = sync_to_cir.ServerSync()
                success = syncer.sync_directory(
                    sync_path, 'cir',  # Default to 'cir' server
                    exclude_patterns=getattr(args, 'exclude', None),
                    include_patterns=getattr(args, 'include', None),
                    dry_run=dry_run,
                    delete=getattr(args, 'delete', False)
                )
                pipeline_success.append(success)
                if success:
                    log("Sync completed successfully!", 'info', logfile=logfile, logpath=logpath)
                else:
                    log("Sync failed. Check log files for details.", 'error', logfile=logfile, logpath=logpath)
            if all(pipeline_success):
                log("Pipeline completed successfully!", 'info', logfile=logfile, logpath=logpath)
        
        elif args.command == 'copy':
            import copy_to_cerberos
            copy_to_cerberos.main(args.config)
        
        elif args.command == 'hpi':
            import add_hpi
            add_hpi.main(args.config)
        
        elif args.command == 'maxfilter':
            import maxfilter
            dry_run = getattr(args, 'dry_run', False)
            maxfilter.main(args.config, dry_run=dry_run)
        
        elif args.command == 'bidsify':
            import bidsify
            bidsify.main(args.config)
        
        elif args.command == 'sync':
            import sync_to_cir
            if args.sync_command == 'create-config':
                # Create example configuration
                example = sync_to_cir.create_example_config()
                config_file = 'server_sync_config.yml'
                with open(config_file, 'w') as f:
                    yaml.dump(example, f, default_flow_style=False, indent=2, sort_keys=False)
                print(f"Created example configuration file: {config_file}")
                print("Edit this file with your server details before using the sync tool.")
                
            elif args.sync_command == 'test':
                # Test server connection
                syncer = sync_to_cir.ServerSync()
                success = syncer.check_server_connection(args.server)
                return
                    
            elif args.sync_command == 'directory':
                # Sync directory to server
                syncer = sync_to_cir.ServerSync()
                success = syncer.sync_directory(
                        args.path, args.server,
                        exclude_patterns=getattr(args, 'exclude', None),
                        include_patterns=getattr(args, 'include', None),
                        dry_run=getattr(args, 'dry_run', False),
                        delete=getattr(args, 'delete', False)
                    )
                if success:
                    log("Sync completed successfully!", 'info')
                else:
                    log("Sync failed. Check log files for details.", 'error')

            else:
                # If no sync subcommand, print help
                from sync_to_cir import main as sync_main
                sync_main()
            
    except Exception as e:
        log(f"Error: {e}", 'error')
        sys.exit(1)

if __name__ == "__main__":
    main()