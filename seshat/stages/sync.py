#!/usr/bin/env python3
"""
SESHAT Server Sync Utility
Convenient script for syncing processed data to remote servers (CIR, etc.)
"""

import os
import sys
import argparse
import yaml
import json
import subprocess
import shlex
from pathlib import Path
from os.path import dirname, abspath, exists, isdir
from datetime import datetime
from typing import Dict, List, Optional, Union
from copy import deepcopy
from mne_bids import print_dir_tree
from seshat.utils import log, askdirectory

# Use an XDG-compliant per-user path instead of a hard-coded system path.
sync_config = os.path.join(
    os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')),
    'seshat', 'sync_config.yml'
)
general_log_file = os.path.join(
    os.environ.get('XDG_STATE_HOME', os.path.expanduser('~/.local/state')),
    'seshat', 'sync_to_server.log'
)

# Allowlist of rsync flags that may be specified per-server in a config file.
# Free-form option strings from config are never passed to subprocess directly.
_RSYNC_OPTION_ALLOWLIST = {
    '--checksum', '--compress', '--no-compress', '--bwlimit',
    '--timeout', '--contimeout', '--no-motd', '--partial',
    '--progress', '--no-progress',
}
# Allowlist of ssh flags that may be specified per-server in a config file.
_SSH_OPTION_ALLOWLIST = {
    '-p', '-i', '-o', '-l', '-F', '-c',
}

class ServerSync:
    """Handle syncing data to remote servers with rsync"""

    def __init__(self, config: Union[str, Dict] = sync_config):
        """Initialize with configuration"""
        if isinstance(config, str):
            with open(config, 'r') as f:
                if config.endswith('.json'):
                    self.config = json.load(f)
                elif config.endswith('.yml') or config.endswith('.yaml'):
                    self.config = yaml.safe_load(f)
                else:
                    raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
        else:
            self.config = config
            
        self.timestamp = datetime.now().strftime('%Y%m%d')
        self.log_file = f'sync_to_server.log'
        
    def validate_server_config(self, server_name: str) -> Dict:
        """Validate server configuration"""
        servers = self.config.get('servers', {})
        if server_name not in servers:
            available = list(servers.keys())
            raise ValueError(f"Server '{server_name}' not found. Available: {available}")
        
        server_config = servers[server_name]
        required_fields = ['host', 'user', 'remote_path']
        
        for field in required_fields:
            if field not in server_config:
                raise ValueError(f"Missing required field '{field}' in server config for '{server_name}'")
        
        return server_config
    
    def get_local_path(self, path: str = None) -> str:
        """Get local path for syncing"""
        if not path:
            path = askdirectory(title="Select Local Path",
                                initialdir='neuro/data/local')
            if not path:
                raise ValueError("No local path selected")
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Local path does not exist: {path}")
        
        return os.path.abspath(path)
    
    def build_rsync_command(self, local_path: str, server_config: Dict, 
                          exclude_patterns: List[str] = None,
                          include_patterns: List[str] = None,
                          dry_run: bool = False) -> List[str]:
        """Build rsync command with options"""
        
        cmd = ['rsync']

        local_path = local_path.rstrip('/')
        remote_root = server_config['remote_path'].rstrip('/')
        
        remote_dest = f"{server_config['user']}@{server_config['host']}:{remote_root}"

        cmd.extend(self.config.get('default_rsync_options', []))
        
        global_excludes = self.config.get('sync_defaults', {}).get('global_excludes', [])

        global_includes = self.config.get('sync_defaults', {}).get('global_includes', [])
        
        log_commands = self.config.get('log_commands', {})
        
        # Validate per-server rsync options against the allowlist to prevent
        # arbitrary flag injection from a potentially attacker-controlled config.
        raw_custom_opts = server_config.get('rsync_options', [])
        custom_opts = []
        for opt in raw_custom_opts:
            flag = opt.split('=')[0] if '=' in opt else opt
            if flag in _RSYNC_OPTION_ALLOWLIST:
                custom_opts.append(opt)
            else:
                log(f"Ignoring disallowed rsync option from config: {opt!r}", 'warning')

        # Validate per-server ssh options against the allowlist.
        raw_ssh_opts = server_config.get('ssh_options', [])
        ssh_opts = []
        i = 0
        while i < len(raw_ssh_opts):
            flag = raw_ssh_opts[i]
            if flag in _SSH_OPTION_ALLOWLIST:
                ssh_opts.append(flag)
                # These flags take a value argument; consume it too.
                if flag in {'-p', '-i', '-o', '-l', '-F', '-c'} and i + 1 < len(raw_ssh_opts):
                    i += 1
                    ssh_opts.append(raw_ssh_opts[i])
            else:
                log(f"Ignoring disallowed ssh option from config: {flag!r}", 'warning')
            i += 1
        
        if global_excludes:
            for pattern in global_excludes:
                cmd.extend(['--exclude', pattern])
        
        if exclude_patterns:
            for pattern in exclude_patterns:
                cmd.extend(['--exclude', pattern])
        
        if global_includes:
            for pattern in global_includes:
                cmd.extend(['--include', pattern])
        
        if include_patterns:
            for pattern in include_patterns:
                cmd.extend(['--include', pattern])

        if '--itemize-changes' not in cmd:
            cmd.append('--itemize-changes')

        if dry_run:
            cmd.append('--dry-run')
            
        if custom_opts:
            cmd.extend(custom_opts)
            
        if ssh_opts:
            ssh_cmd = ['ssh'] + ssh_opts
            cmd.extend(['-e', ' '.join(shlex.quote(arg) for arg in ssh_cmd)])

        if '--stats' not in cmd:
            cmd.append('--stats')
        cmd.extend([local_path, remote_dest])

        if log_commands and log_commands.get('file'):
            # Confine the log file path to a subdirectory of local_path to prevent
            # an attacker-controlled config from writing to arbitrary system paths.
            raw_log = log_commands['file']
            resolved = os.path.realpath(os.path.join(local_path, raw_log))
            local_real = os.path.realpath(local_path)
            if resolved.startswith(local_real + os.sep) or resolved == local_real:
                cmd.extend(['--log-file', resolved])
            else:
                log(f"Ignoring --log-file path outside project directory: {raw_log!r}", 'warning')

        return cmd
    
    def sync_directory(self, local_path: str, server_name: str,
                      exclude_patterns: List[str] = None,
                      include_patterns: List[str] = None,
                      dry_run: bool = False,
                      delete: bool = False) -> bool:
        """Sync a directory to remote server and optionally delete local files after successful transfer"""
        
        log_path = f'{local_path}/log' or './log'
        if not os.path.exists(log_path):
            os.makedirs(log_path, exist_ok=True)
        
        if not os.path.exists(local_path):
            log(f"Local path does not exist: {local_path}", 'error', 
                logfile=self.log_file, logpath=log_path)
            return False
            
        try:
            server_config = self.validate_server_config(server_name)
            cmd = self.build_rsync_command(
                local_path, server_config, exclude_patterns,
                include_patterns, dry_run)
            cmd_str = ' '.join(shlex.quote(arg) for arg in cmd)
            log(f"Executing: {cmd_str}", 'info', logfile=self.log_file, logpath=log_path)

            if dry_run:
                log("DRY RUN MODE - No files will be transferred", 'info',
                    logfile=self.log_file, logpath=log_path)
                if delete:
                    log("DRY RUN MODE - Local files would be deleted after successful sync", 'info',
                        logfile=self.log_file, logpath=log_path)
                print_dir_tree(local_path, max_depth=2)

            # Snapshot files before transfer so deletion is based on a directory
            # diff rather than parsing rsync stdout (which is vulnerable to injection).
            snapshot_before = self._snapshot_files(local_path) if (delete and not dry_run) else set()

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.stdout:
                log(f"Rsync output:\n{result.stdout}", 'info',
                    logfile=self.log_file, logpath=log_path)

            if result.stderr:
                log(f"Rsync errors:\n{result.stderr}", 'warning',
                    logfile=self.log_file, logpath=log_path)

            if result.returncode == 0:
                log(f"Successfully synced {local_path} to {server_name}", 'info',
                    logfile=self.log_file, logpath=log_path)

                if delete and not dry_run:
                    self._delete_local_files_after_sync(local_path, snapshot_before, log_path)

                return True
            else:
                log(f"Rsync failed with return code {result.returncode}", 'error',
                    logfile=self.log_file, logpath=log_path)
                return False
                
        except Exception as e:
            log(f"Error syncing to {server_name}: {e}", 'error',
                logfile=self.log_file, logpath=log_path)
            return False
    
    def _snapshot_files(self, base_path: str) -> set:
        """Return the set of all regular file paths under base_path."""
        result = set()
        for root, _dirs, files in os.walk(base_path):
            for fname in files:
                result.add(os.path.join(root, fname))
        return result

    def _delete_local_files_after_sync(self, local_path: str, snapshot_before: set, log_path: str):
        """Delete local files that existed before the sync (i.e. were transferred).

        Uses a pre/post directory snapshot instead of parsing rsync stdout,
        which would be vulnerable to output-injection from a malicious remote.
        Files are only deleted if they still exist and are strictly under local_path.
        """
        try:
            local_real = os.path.realpath(local_path)
            snapshot_after = self._snapshot_files(local_path)
            # Files present both before and after the transfer are candidates for deletion.
            candidates = snapshot_before & snapshot_after

            deleted_count = 0
            for file_path in candidates:
                # Safety check: only delete files strictly within local_path.
                resolved = os.path.realpath(file_path)
                if not (resolved.startswith(local_real + os.sep) or resolved == local_real):
                    log(f"Skipping deletion of file outside project directory: {file_path}", 'warning',
                        logfile=self.log_file, logpath=log_path)
                    continue
                try:
                    os.remove(file_path)
                    deleted_count += 1
                    log(f"Deleted local file after successful sync: {file_path}", 'info',
                        logfile=self.log_file, logpath=log_path)
                except Exception as e:
                    log(f"Failed to delete local file {file_path}: {e}", 'warning',
                        logfile=self.log_file, logpath=log_path)

            if deleted_count > 0:
                log(f"Deleted {deleted_count} local files after successful sync", 'info',
                    logfile=self.log_file, logpath=log_path)
                self._cleanup_empty_directories(local_path, log_path)

        except Exception as e:
            log(f"Error during local file cleanup: {e}", 'warning',
                logfile=self.log_file, logpath=log_path)
    
    def _cleanup_empty_directories(self, base_path: str, log_path: str):
        """Remove empty directories after file deletion"""
        try:
            for root, dirs, files in os.walk(base_path, topdown=False):
                if root == log_path or log_path in root:
                    continue
                    
                if not files and not dirs:
                    try:
                        os.rmdir(root)
                        log(f"Removed empty directory: {root}", 'info',
                            logfile=self.log_file, logpath=log_path)
                    except Exception as e:
                        log(f"Failed to remove empty directory {root}: {e}", 'warning',
                            logfile=self.log_file, logpath=log_path)
        except Exception as e:
            log(f"Error during directory cleanup: {e}", 'warning',
                logfile=self.log_file, logpath=log_path)
    
    def check_server_connection(self, server_name: str) -> bool:
        """Test connection to server"""
        try:
            server_config = self.validate_server_config(server_name)
            
            ssh_cmd = ['ssh']
            ssh_opts = server_config.get('ssh_options', [])
            if ssh_opts:
                ssh_cmd.extend(ssh_opts)
            
            ssh_cmd.extend([
                f"{server_config['user']}@{server_config['host']}",
                'echo "Connection test successful"'
            ])
            
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"Successfully connected to {server_name}")
                return True
            else:
                print(f"Failed to connect to {server_name}: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error testing connection to {server_name}: {e}")
            return False

def get_parameters(config: Union[str, Dict]) -> Dict:
    """
    Extract and merge BIDS configuration parameters from file or dictionary.
    """
    if isinstance(config, str):
        if config.endswith('.json'):
            with open(config, 'r') as f:
                config_dict = json.load(f)
        elif config.endswith('.yml') or config.endswith('.yaml'):
            with open(config, 'r') as f:
                config_dict = yaml.safe_load(f)
        else:
            raise ValueError("Unsupported configuration file format. Use .json or .yml/.yaml")
    elif isinstance(config, dict):
        config_dict = deepcopy(config)

    sync_dict = deepcopy(config_dict['Project'])
    return sync_dict


def create_example_config():
    """Create example server configuration"""
    example_config = {
        'servers': {
            'cir': {
                'host': 'cir-server.example.com',
                'user': 'your_username',
                'remote_path': '/data/natmeg/project_name',
                'ssh_options': ['-p', '22', '-i', '~/.ssh/id_rsa'],
                'rsync_options': ['--checksum']
            },
        },
        'default_rsync_options': [
            '--archive',
            '--verbose',
            '--compress',
            '--partial',
            '--progress',
            '--human-readable'
        ],
        'sync_defaults': {
            'global_excludes': [
                '*.tmp', 
                '*.log', 
                '.DS_Store', 
                '__pycache__/', 
                '.git/', 
                '*.bak'
            ],
            'global_includes': [
                '*.bids', 
                '*.json', 
                '*.tsv', 
                '*.txt'
            ]
        }
    }
    
    return example_config


def main(path:str=None):
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="SESHAT Server Sync Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test connection to server
  seshat sync --test --server cir
  
  # Sync custom directory
  seshat sync --directory /path/to/data

  # Generate example config
  seshat sync --create-config
        """
    )

    parser.add_argument('--config', help='Project configuration file (YAML or JSON)')
    parser.add_argument('--server-config', help='Server configuration file (YAML or JSON)')
    parser.add_argument('--create-config', action='store_true', 
                       help='Create example server configuration file')
    parser.add_argument('--test', action='store_true',
                       help='Only test connection to server and exit (use --server to pick server)')
    parser.add_argument('--server', help='Server name (default cir)')
    
    parser.add_argument('--directory', nargs='*', metavar=('PATH', 'SERVER'),
                       help='Sync custom directory to specified server')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be transferred without actually doing it')
    parser.add_argument('--delete', action='store_true',
                       help='Delete local files after successful sync to server (use with caution!)', default=False)
    parser.add_argument('--exclude', action='append', metavar='PATTERN',
                       help='Exclude files matching pattern (can be used multiple times)')
    parser.add_argument('--include', action='append', metavar='PATTERN',
                       help='Include files matching pattern (can be used multiple times)')
    
    args = parser.parse_args()

    server_name = args.server or 'cir'
    
    if args.create_config:
        example = create_example_config()
        server_config_file = 'server_sync_config.yml'
        with open(server_config_file, 'w') as f:
            yaml.dump(example, f, default_flow_style=False, indent=2, sort_keys=False)
        print(f"Created example configuration file: {server_config_file}")
        print("Edit this file with your server details before using the sync tool.")
        return
    
    if args.server_config:
        server_config_file = args.server_config
        if not os.path.exists(server_config_file):
            print(f"Configuration file not found: {server_config_file}")
            print("Use --create-config to generate an example configuration.")
            return
    
        try:
            syncer = ServerSync(server_config_file)
        except Exception as e:
            print(f"Error loading configuration: {e}")
            return
    else:
        syncer = ServerSync()

    if args.test:
        syncer.check_server_connection(server_name)
        return
    
    if args.config:
        try:
            config = get_parameters(args.config)
            print(config)
        except Exception as e:
            print(f"Error loading project configuration: {e}")
            return
        
        project_name = config.get('Name', None)
        root_name = config.get('Root', None)

        if not project_name or not root_name:
            print("Project name and root directory must be specified.")
            return

        directory = dirname(os.path.join(root_name, project_name))

        local_path = directory
        success = syncer.sync_directory(
            local_path, server_name,
            exclude_patterns=args.exclude,
            include_patterns=args.include,
            dry_run=args.dry_run,
            delete=args.delete
        )

    if args.directory:
        local_path = args.directory[0]
        if len(args.directory) > 1 and not args.server:
            server_name = args.directory[1]
        syncer.sync_directory(
            local_path, server_name,
            exclude_patterns=args.exclude,
            include_patterns=args.include,
            dry_run=args.dry_run,
            delete=args.delete
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
