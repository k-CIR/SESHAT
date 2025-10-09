import argparse
import pandas as pd
from glob import glob
import os
from os.path import join, isdir, dirname, basename
from mne_bids import print_dir_tree
import re
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from typing import Union
import yaml
import subprocess
from utils import askForConfig

def nested_dir_tree(root_path, rel_path="", max_entries: int | None = None):
    """Return nested directory tree for local or SSH (user@host:/path) roots.

    Automatically detects remote SSH paths of the form user@host:/absolute/path
    and builds the tree via a remote 'find' command. Falls back gracefully if
    SSH command fails.
    """

    # Remote (SSH) path detection
    if '@' in root_path and ':' in root_path.split('@', 1)[1]:
        user_host, remote_path = root_path.split(':', 1)
        remote_path = remote_path or '/'  # safety
        find_cmd = [
            'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5', user_host,
            f"find '{remote_path}' -mindepth 1 -printf '%y|%P|%T@|%s\\n'"
        ]
        try:
            proc = subprocess.run(find_cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                print(f"[WARN] SSH find failed ({proc.returncode}): {proc.stderr.strip()[:200]}")
                return {}
            lines = proc.stdout.strip().splitlines()
            if max_entries:
                lines = lines[:max_entries]
            tree: dict = {}
            for line in lines:
                try:
                    ftype, rel, mtime, size = line.split('|', 3)
                except ValueError:
                    continue
                if rel == '':
                    continue
                parts = rel.split('/')
                cursor = tree
                for i, part in enumerate(parts):
                    if i == len(parts) - 1 and ftype != 'd':
                        # file
                        cursor.setdefault('__files__', []).append({
                            'name': part,
                            'relpath': rel,
                            'mtime': float(mtime) if mtime else None,
                            'size': int(size) if size.isdigit() else 0,
                        })
                    else:
                        cursor = cursor.setdefault(part, {})
                # Ensure directories have entry even with no files
                if ftype == 'd' and parts:
                    _ = tree
                    for part in parts:
                        _ = _.setdefault(part, {})
            return tree
        except Exception as e:
            print(f"[WARN] Remote listing failed: {e}")
            return {}

    # Local path handling
    tree = {}
    try:
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
    except FileNotFoundError:
        print(f"[WARN] Path not found: {root_path}")
    except PermissionError:
        print(f"[WARN] Permission denied: {root_path}")
    return tree

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

def _flatten_files(tree, base_path=""):
    files = {}
    for key, val in tree.items():
        if key == '__files__':
            for f in val:
                files[os.path.join(base_path, f['relpath'] if 'relpath' in f else f['name'])] = f
        elif isinstance(val, dict):
            sub_base = os.path.join(base_path, key) if base_path else key
            files.update(_flatten_files(val, sub_base))
    return files

def dict_to_table_report(data, title="File Report", output_file="table_report.html", remote_tree=None):
    """Generate a SINGLE hierarchical comparison tree with side-by-side Local / Remote columns."""
    from datetime import datetime

    # Environment setup
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [script_dir, os.getcwd()]
    env = Environment(loader=FileSystemLoader(search_paths))

    # Filters
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

    if remote_tree is None:
        remote_tree = {}

    local_flat = _flatten_files(data)
    remote_flat = _flatten_files(remote_tree)

    # Create simple flat structure without tree complexity
    all_paths = set(local_flat.keys()) | set(remote_flat.keys())
    
    # Get all directory paths
    all_dirs = set()
    for path in all_paths:
        parts = path.split(os.sep)
        for i in range(1, len(parts)):
            dir_path = os.sep.join(parts[:i])
            all_dirs.add(dir_path)
    
    # Use the existing hierarchical list creation from local and remote trees
    local_hierarchy = create_hierarchical_list(data)
    remote_hierarchy = create_hierarchical_list(remote_tree)
    
    # Create dictionaries for quick lookup
    local_items = {item.get('path') or item.get('relpath'): item for item in local_hierarchy}
    remote_items = {item.get('path') or item.get('relpath'): item for item in remote_hierarchy}
    
    # Build a complete hierarchical list that includes remote-only files in proper tree positions
    def build_complete_hierarchy():
        """Build a complete hierarchy that properly integrates remote-only files."""
        # Start with local hierarchy as base
        complete_paths = []
        path_set = set()
        
        # Add all local paths first (maintaining order)
        for item in local_hierarchy:
            path = item.get('path') or item.get('relpath')
            complete_paths.append(path)
            path_set.add(path)
        
        # For remote-only items, insert them in proper hierarchical position
        remote_only_items = []
        for item in remote_hierarchy:
            path = item.get('path') or item.get('relpath')
            if path not in path_set:
                remote_only_items.append(item)
        
        # Sort remote-only items by their path depth and name to maintain hierarchy
        remote_only_items.sort(key=lambda x: (x['level'], (x.get('path') or x.get('relpath')).lower()))
        
        # Insert remote-only items in correct positions
        for remote_item in remote_only_items:
            remote_path = remote_item.get('path') or remote_item.get('relpath')
            remote_parent = remote_item.get('folder_path', '')
            remote_level = remote_item['level']
            
            # Find the correct insertion point to maintain hierarchical order
            inserted = False
            for i, existing_path in enumerate(complete_paths):
                existing_item = local_items.get(existing_path)
                if existing_item:
                    existing_parent = existing_item.get('folder_path', '')
                    existing_level = existing_item['level']
                    
                    # If this remote item should come before the existing item
                    if (remote_parent == existing_parent and 
                        remote_level == existing_level and 
                        remote_item['type'] == 'folder' and existing_item['type'] == 'file'):
                        # Directories before files at same level
                        complete_paths.insert(i, remote_path)
                        inserted = True
                        break
                    elif (remote_parent == existing_parent and 
                          remote_level == existing_level and 
                          remote_item['type'] == existing_item['type'] and
                          remote_item['name'].lower() < existing_item['name'].lower()):
                        # Alphabetical order within same type and level
                        complete_paths.insert(i, remote_path)
                        inserted = True
                        break
                    elif remote_level < existing_level and existing_path.startswith(remote_parent + os.sep):
                        # This remote item is a parent directory that should come before its children
                        complete_paths.insert(i, remote_path)
                        inserted = True
                        break
            
            # If not inserted yet, append at end
            if not inserted:
                complete_paths.append(remote_path)
        
        return complete_paths
    
    all_paths = build_complete_hierarchy()
    
    # Convert to rows for the template, preserving the hierarchical order
    rows = []
    for path in all_paths:
        local_item = local_items.get(path)
        remote_item = remote_items.get(path)
        
        # Determine type from available item
        item_type = (local_item or remote_item)['type']
        name = (local_item or remote_item)['name']
        level = (local_item or remote_item)['level']
        parent = (local_item or remote_item).get('folder_path', '')
        
        if item_type == 'folder':
            # Directory logic
            if local_item and remote_item:
                status = 'ok'
                if local_item.get('size', 0) != remote_item.get('size', 0):
                    status = 'issue'
            elif local_item and not remote_item:
                status = 'missing_remote'
            elif remote_item and not local_item:
                status = 'missing_local'
            else:
                status = 'ok'
            
            rows.append({
                'type': 'dir',
                'relpath': path,
                'name': name,
                'parent': parent,
                'level': level,
                'local_size': local_item.get('size') if local_item else None,
                'remote_size': remote_item.get('size') if remote_item else None,
                'local_mtime': local_item.get('mtime') if local_item else None,
                'remote_mtime': remote_item.get('mtime') if remote_item else None,
                'local_exists': local_item is not None,
                'remote_exists': remote_item is not None,
                'status': status
            })
        else:
            # File logic
            if local_item and remote_item:
                status = 'size_mismatch' if local_item.get('size', 0) != remote_item.get('size', 0) else 'ok'
            elif local_item and not remote_item:
                status = 'missing_remote'
            elif remote_item and not local_item:
                status = 'missing_local'
            else:
                status = 'ok'
            
            rows.append({
                'type': 'file',
                'relpath': path,
                'name': name,
                'parent': parent,
                'level': level,
                'local_size': local_item.get('size') if local_item else None,
                'remote_size': remote_item.get('size') if remote_item else None,
                'local_mtime': local_item.get('mtime') if local_item else None,
                'remote_mtime': remote_item.get('mtime') if remote_item else None,
                'local_exists': local_item is not None,
                'remote_exists': remote_item is not None,
                'status': status
            })

    # Embedded template
    embedded = """<!DOCTYPE html><html><head><meta charset='utf-8'/><title>{{ title }}</title>
<style>
body{font-family:Arial, sans-serif;margin:1rem;}
table{border-collapse:collapse;width:100%;}
th,td{padding:4px 6px;border:1px solid #ccc;font-size:12px;}
tr.dir{background:#f0f4ff;}
tbody tr.dir.status-ok{background:#e8f5e8;}
tbody tr.status-missing_remote{background:#ffe5e5;}
tbody tr.status-size_mismatch{background:#fff4d6;}
tbody tr.status-issue{background:#e6f3ff;}
.indent{display:inline-block;}
thead th{position:sticky;top:0;background:#fff;}
.toolbar{margin:0 0 0.6rem 0;font-size:13px;}
.size{white-space:nowrap;}
.date{white-space:nowrap;font-size:11px;}
.dim{color:#888;}
</style>
<script>
function toggle(path){var base=document.querySelector('tr[data-path="'+path+'"]');var lvl=parseInt(base.dataset.level);var rows=document.querySelectorAll('tr[data-parent]');var show=null;for(var i=0;i<rows.length;i++){var r=rows[i]; if(r.dataset.parent===path){if(show===null){show = r.style.display==='none';} if(show){r.style.display='table-row';} else {hideBranch(r);} }} }
function hideBranch(row){row.style.display='none';var id=row.dataset.path;var rows=document.querySelectorAll('tr[data-parent="'+id+'"]');for(var i=0;i<rows.length;i++){hideBranch(rows[i]);}}
document.addEventListener('DOMContentLoaded', function(){
  document.getElementById('statusFilter').addEventListener('change', function(){
    var v=this.value; 
    var rows=document.querySelectorAll('tbody tr');
    
    // First pass: show/hide based on filter
    var visiblePaths = new Set();
    rows.forEach(function(r){
      var s=r.getAttribute('data-status');
      if(!v || s===v){
        r.style.display='table-row';
        visiblePaths.add(r.getAttribute('data-path'));
      } else {
        r.style.display='none';
      }
    });
    
    // Second pass: ensure parent folders of visible items are also visible
    if(v) {
      visiblePaths.forEach(function(path){
        var parts = path.split('/');
        for(var i = 1; i < parts.length; i++){
          var parentPath = parts.slice(0, i).join('/');
          if(parentPath) {
            var parentRow = document.querySelector('tr[data-path="' + parentPath + '"]');
            if(parentRow && parentRow.classList.contains('dir')){
              parentRow.style.display='table-row';
            }
          }
        }
      });
    }
  });
});
</script>
</head><body>
<h1>{{ title }}</h1>
<div class='toolbar'>Filter: <select id='statusFilter'><option value=''>All</option><option value='ok'>OK</option><option value='size_mismatch'>Size mismatch</option><option value='missing_remote'>Missing remote</option><option value='missing_local'>Missing local</option><option value='issue'>Dir w/ issue</option></select></div>
<table><thead><tr><th>Local Path</th><th>Remote Path</th><th>Local Size</th><th>Remote Size</th><th>Local Modified</th><th>Remote Modified</th><th>Status</th></tr></thead><tbody>
{% for r in rows %}
<tr class='{{ r.type }}{% if r.status %} status-{{ r.status }}{% endif %}' data-path='{{ r.relpath }}' data-parent='{{ r.parent }}' data-status='{{ r.status }}' data-level='{{ r.level }}' {% if r.type=='dir' %}onclick="toggle('{{ r.relpath }}')"{% endif %}>
    <td><span class='indent' style='width: {{ r.level * 14 }}px'></span>{% if r.local_exists %}{% if r.type=='dir' %}📁 {{ r.name }}{% else %}{{ r.name }}{% endif %}{% else %}<span class='dim'>—</span>{% endif %}</td>
    <td>{% if r.remote_exists %}{% if r.type=='dir' %}📁 {{ r.name }}{% else %}{{ r.name }}{% endif %}{% else %}<span class='dim'>—</span>{% endif %}</td>
  <td class='size'>{% if r.local_size is not none %}{{ r.local_size|filesize }}{% endif %}</td>
  <td class='size'>{% if r.remote_size is not none %}{{ r.remote_size|filesize }}{% endif %}</td>
  <td class='date'>{% if r.local_mtime is not none %}{{ r.local_mtime|strftime }}{% endif %}</td>
  <td class='date'>{% if r.remote_mtime is not none %}{{ r.remote_mtime|strftime }}{% endif %}</td>
  <td>{{ r.status }}</td>
</tr>
{% endfor %}
</tbody></table></body></html>"""

    template = env.from_string(embedded)
    html = template.render(title=title, rows=rows)
    with open(output_file, 'w') as f:
        f.write(html)
    print(f"Report generated: {output_file}")

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

    project = config['Project'].get("Name", "")
    root = config['Project'].get("Root", "")
    local_root = join(root, project)
    # Optional remote mirror path (user@host:/abs/path). Adjust if project stored differently remotely.
    remote_root = f'natmeg@compute.kcir.se:/data/vault/natmeg/{project}' if project else None

    dir_tree = nested_dir_tree(local_root)
    if remote_root:
        remote_tree = nested_dir_tree(remote_root)
        if not remote_tree:
            print(f"[INFO] Remote path unreachable or empty: {remote_root}")

    dict_to_table_report(dir_tree, title=project, output_file=join(local_root, 'report.html'), remote_tree=remote_tree if 'remote_tree' in locals() else None)

if __name__ == "__main__":
    main()
