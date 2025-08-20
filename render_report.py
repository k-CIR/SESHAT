import argparse
import pandas as pd
from glob import glob
import os
from os.path import join, isdir, dirname, basename
from mne_bids import print_dir_tree
import re
from json2html import json2html
from jinja2 import Environment, FileSystemLoader
from typing import Union
import yaml
from utils import askForConfig

def nested_dir_tree(root_path, rel_path=""):
    tree = {}
    for entry in os.scandir(os.path.join(root_path, rel_path)):
        if entry.is_dir():
            tree[entry.name] = nested_dir_tree(root_path, os.path.join(rel_path, entry.name))
        else:
            stat_info = entry.stat()
            tree.setdefault('__files__', []).append({
                'name': entry.name,
                'relpath': os.path.join(rel_path, entry.name),
                'mtime': stat_info.st_mtime,
                'size': stat_info.st_size,
            })
    return tree

# Old HTML report removed; only table report is supported

def create_hierarchical_list(tree, current_path="", level=0):
    """Convert nested directory tree to hierarchical list maintaining folder structure.
    Classic tree order: folders first (at current level), then files.
    Files in a directory are shown at the same indentation level as their sibling folders.
    """
    items = []

    # 1) Add directories at this level (classic tree lists folders first)
    directories = [(key, value) for key, value in tree.items() if key != '__files__' and isinstance(value, dict)]
    for dir_name, dir_content in sorted(directories, key=lambda kv: kv[0].lower()):
        dir_path = os.path.join(current_path, dir_name) if current_path else dir_name
        dir_mtime = get_directory_mtime(dir_content)
        dir_size = get_directory_size(dir_content)
        items.append({
            'name': dir_name,
            'type': 'folder',
            'path': dir_path,
            'folder_path': current_path,
            'level': level,
            'mtime': dir_mtime,
            'size': dir_size,
        })
        # Recursively add this folder's contents
        items.extend(create_hierarchical_list(dir_content, dir_path, level + 1))

    # 2) Add files in the current directory
    if '__files__' in tree:
        for file_info in sorted(tree['__files__'], key=lambda x: x['name'].lower()):
            items.append({
                'name': file_info['name'],
                'type': 'file',
                'relpath': file_info['relpath'],
                'folder_path': current_path,
                'level': level,
                'mtime': file_info['mtime'],
                'size': file_info.get('size', 0),
            })

    return items

def get_directory_mtime(dir_tree):
    """Get the latest modification time from a directory tree."""
    max_mtime = 0
    
    for key, value in dir_tree.items():
        if key == '__files__':
            for file_info in value:
                if file_info['mtime']:
                    max_mtime = max(max_mtime, file_info['mtime'])
        elif isinstance(value, dict):
            sub_mtime = get_directory_mtime(value)
            if sub_mtime is not None:
                max_mtime = max(max_mtime, sub_mtime)
    
    return max_mtime if max_mtime > 0 else None

def get_directory_size(dir_tree):
    """Get the total size (bytes) of all files in a directory tree."""
    total = 0
    for key, value in dir_tree.items():
        if key == '__files__':
            for file_info in value:
                total += int(file_info.get('size', 0) or 0)
        elif isinstance(value, dict):
            total += get_directory_size(value)
    return total

def dict_to_table_report(data, title="File Report", output_file="table_report.html"):
    """Generate HTML report using sortable table template."""
    from datetime import datetime
    
    # Set up the environment and load templates
    env = Environment(loader=FileSystemLoader('.'))
    
    # Add custom filter for datetime formatting
    def datetime_format(timestamp, fmt='%Y-%m-%d %H:%M:%S'):
        if timestamp:
            return datetime.fromtimestamp(timestamp).strftime(fmt)
        return ''
    
    env.filters['strftime'] = datetime_format
    def human_bytes(num, suffix='B'):
        try:
            num = float(num)
        except Exception:
            return ''
        for unit in ['','K','M','G','T','P','E','Z']:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Y{suffix}"
    env.filters['filesize'] = human_bytes
    template = env.get_template('report_template.html')
    
    # Create hierarchical list maintaining folder structure
    hierarchical_list = create_hierarchical_list(data)
    
    # Calculate summary statistics
    file_count = sum(1 for item in hierarchical_list if item['type'] == 'file')
    dir_count = sum(1 for item in hierarchical_list if item['type'] == 'folder')
    
    # Get last update time from all files
    file_times = [item['mtime'] for item in hierarchical_list if item['type'] == 'file' and item['mtime']]
    last_update = datetime.fromtimestamp(max(file_times)).strftime('%Y-%m-%d %H:%M:%S') if file_times else 'N/A'
    
    html = template.render(
        title=title,
        hierarchical_list=hierarchical_list,
        file_count=file_count,
        dir_count=dir_count,
        last_update=last_update
    )
    
    # Save to file
    with open(output_file, 'w') as f:
        f.write(html)
    
    print(f"Table report generated: {output_file}")

def count_directories(tree):
    """Count total directories in the tree."""
    count = 0
    for key, value in tree.items():
        if key != '__files__' and isinstance(value, dict):
            count += 1 + count_directories(value)
    return count

def args_parser():
    parser = argparse.ArgumentParser(description='Generate a report from a nested directory structure.', add_help=True,
                                     usage='render_report [-h] [-c CONFIG]')
    parser.add_argument('-c', '--config', type=str, help='Path to the configuration file', default=None)
    args = parser.parse_args()
    return args

def main(config: str=None):
    if config is None:
        args = args_parser()
        config_file = args.config
        if not config_file or not os.path.exists(config_file):
            config_file = askForConfig()
    else:
        config_file = config
        
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    project = config['project'].get("name", "")
    project_root = dirname(config['project']['squidMEG'] or config['project'])

    dir_tree = nested_dir_tree(project_root)

    dict_to_table_report(dir_tree, title=project, output_file=join(project_root, 'report.html'))
    print(f"Table report generated at: {join(project_root, 'report.html')}")

if __name__ == "__main__":
    main()