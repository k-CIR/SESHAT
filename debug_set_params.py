import json


config_file = 'neuro/data/local/OPM-benchmarking/bids_config.json'

with open(config_file, 'r') as f:
    config_dict = json.load(f)

