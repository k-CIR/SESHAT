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
            tree.setdefault('__files__', []).append({
                'name': entry.name,
                'relpath': os.path.join(rel_path, entry.name)
            })
    return tree

def dict_to_html_report(data, title="Dict Report", output_file="report.html"):
    # Set up the environment and load templates from the current directory
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('report_template.html')

    html = template.render(title=title, data=data)

    # Save to file
    with open(output_file, 'w') as f:
        f.write(html)

def args_parser():
    parser = argparse.ArgumentParser(description=
                                     '''Generate a report from a nested directory structure.
                                     ''',
                                     add_help=True,
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
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    project = config['project'].get("name", "")
    project_root = dirname(config['project']['squidMEG'] or config['project'])

    dir_tree = nested_dir_tree(project_root)

    dict_to_html_report(dir_tree, title=project, output_file=join(project_root,'report.html'))

if __name__ == "__main__":
    main()