#!/usr/bin/env python3
"""
NatMEG Pipeline Application
Main executable entry point for the NatMEG processing pipeline
"""

import sys
import os
import argparse
from pathlib import Path

# Add the current directory to the Python path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Main entry point for the natmeg command"""
    parser = argparse.ArgumentParser(
        description="NatMEG MEG/EEG Processing Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Launch GUI configuration
  natmeg gui
  
  # Run complete pipeline
  natmeg run --config config.yml
  
  # Run specific component
  natmeg maxfilter --config config.yml
  natmeg bidsify --config config.yml
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # GUI command
    gui_parser = subparsers.add_parser('gui', help='Launch configuration GUI')
    gui_parser.add_argument('--config', help='Configuration file to load')
    
    # Run complete pipeline
    run_parser = subparsers.add_parser('run', help='Run complete pipeline')
    run_parser.add_argument('--config', required=True, help='Configuration file')
    
    # Individual components
    copy_parser = subparsers.add_parser('copy', help='Data synchronization only')
    copy_parser.add_argument('--config', required=True, help='Configuration file')
    
    hpi_parser = subparsers.add_parser('hpi', help='HPI coregistration only')
    hpi_parser.add_argument('--config', required=True, help='Configuration file')
    
    maxfilter_parser = subparsers.add_parser('maxfilter', help='MaxFilter processing only')
    maxfilter_parser.add_argument('--config', required=True, help='Configuration file')
    
    bidsify_parser = subparsers.add_parser('bidsify', help='BIDS conversion only')
    bidsify_parser.add_argument('--config', required=True, help='Configuration file')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'gui':
            from run_config import config_UI
            config = config_UI(args.config)
            if config:
                print("Configuration saved successfully!")
        
        elif args.command == 'run':
            # Run complete pipeline
            from utils import log
            import yaml
            
            with open(args.config, 'r') as f:
                config = yaml.safe_load(f)
            
            log("Starting complete NatMEG pipeline", 'info')
            
            # Execute pipeline steps based on config
            if config['RUN'].get('Copy to Cerberos', False):
                log("Running data synchronization...", 'info')
                import copy_to_cerberos
                copy_to_cerberos.main(args.config)
                
            if config['RUN'].get('Add HPI coregistration', False):
                log("Running HPI coregistration...", 'info')
                import add_hpi
                add_hpi.main(args.config)

            if config['RUN'].get('Run Maxfilter', False):
                log("Running MaxFilter processing...", 'info')
                import maxfilter
                maxfilter.main(args.config)

            if config['RUN'].get('Bidsify', False):
                log("Running BIDS conversion...", 'info')
                import bidsify
                bidsify.main(args.config)
            
            log("Pipeline completed successfully!", 'info')
        
        elif args.command == 'copy':
            import copy_to_cerberos
            copy_to_cerberos.main(args.config)
        
        elif args.command == 'hpi':
            import add_hpi
            add_hpi.main(args.config)
        
        elif args.command == 'maxfilter':
            import maxfilter
            maxfilter.main(args.config)
        
        elif args.command == 'bidsify':
            import bidsify
            bidsify.main(args.config)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()