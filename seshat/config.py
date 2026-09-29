import yaml
import json

default_path = '/neuro/data/local'

# Human-readable labels for snake_case RUN keys
RUN_LABELS = {
    'copy_raw':       'Copy raw data',
    'opm_preprocess': 'OPM preprocessing',
    'sync':           'Sync to server',
}


def create_default_config():
    """Create default configuration dictionary without GUI dependencies"""
    config = {
        'RUN': {
            'copy_raw':       True,
            'opm_preprocess': True,
            'sync':           True
        },
        'Project': {
            'Name': '',
            'cir_id': '',
            'InstitutionName': 'Karolinska Institutet',
            'InstitutionAddress': 'Nobels vag 9, 171 77, Stockholm, Sweden',
            'InstitutionDepartmentName': 'Department of Clinical Neuroscience (CNS)',
            'Description': 'project for MEG data',
            'Tasks': [''],
            'sinuhe_raw': '/neuro/data/sinuhe/<project_path_on_sinuhe>',
            'kaptah_raw': '/neuro/data/kaptah/<project_path_on_kaptah>',
            'stimulus':   '/neuro/data/stimulus/<project_path_on_stimulus>',
            'Polhemus':   '/neuro/data/polhemus/<project>',
            'Root': default_path,
            'Raw':  f'{default_path}/<project>/raw',
            'BIDS': f'{default_path}/<project>/BIDS',
            'Calibration': f'{default_path}/<project>/triux_files/sss/sss_cal.dat',
            'Crosstalk':   f'{default_path}/<project>/triux_files/ctc/ct_sparse.fif',
            'logfile': 'pipeline_log.log'
        },
        'OPM': {
            'rename_analog_channels': True,
            'polhemus': [''],
            'hpi_names': ['HPIpre', 'HPIpost', 'HPIbefore', 'HPIafter'],
            'frequency': 33,
            'downsample_to_hz': 1000,
            'noise_reffile': '',
            'overwrite': False,
            'plot': False,
        },
        'MaxFilter': {
            'standard_settings': {
                'trans_conditions': [''],
                'trans_option': 'continuous',
                'merge_runs': True,
                'empty_room_files': ['empty_room_before.fif', 'empty_room_after.fif'],
                'sss_files': [''],
                'autobad': True,
                'badlimit': '7',
                'bad_channels': [''],
                'tsss_default': True,
                'correlation': '0.98',
                'movecomp_default': True,
                'subjects_to_skip': ['']
            },
            'advanced_settings': {
                'force': False,
                'downsample': False,
                'downsample_factor': '4',
                'apply_linefreq': False,
                'linefreq_Hz': '50',
                'maxfilter_version': '/neuro/bin/util/maxfilter',
                'MaxFilter_commands': '',
                'debug': False
            }
        }
    }
    return config

def merge_with_defaults(config: dict, defaults: dict) -> dict:
    """Recursively fill in keys missing from `config` using `defaults`.

    Needed when loading an older ("legacy") config file that predates a
    newly added setting (e.g. OPM.noise_reffile): without this, the field
    is absent from the loaded config, never gets a GUI widget, and keeps
    being dropped every time the file is re-saved. Existing values already
    present in `config` are never overwritten.
    """
    merged = dict(config)
    for key, default_val in defaults.items():
        if key not in merged:
            merged[key] = default_val
        elif isinstance(default_val, dict) and isinstance(merged[key], dict):
            merged[key] = merge_with_defaults(merged[key], default_val)
    return merged


def rename_legacy_keys(config: dict) -> dict:
    """Rename legacy keys in the configuration dictionary.
    Preserves insertion order. Also normalises legacy values (e.g. continous→continuous).
    """
    legacy_keys = {
        'RUN': {
            # Resolve oldest key directly to final name to avoid a broken two-step chain
            'Add HPI coregistration': 'opm_preprocess',
            'Copy to Cerberos':       'copy_raw',
            'OPM preprocessing':      'opm_preprocess',
            'Sync to CIR':            'sync',
        },
        'Project': {
            'Sinuhe raw': 'sinuhe_raw',
            'Kaptah raw': 'kaptah_raw',
            'Stimuli':    'stimulus',
            'CIR-ID':     'cir_id',
            'Logfile':    'logfile',
        }
    }

    def replace_key_preserve_order(d: dict, old: str, new: str) -> dict:
        new_dict = {}
        for k, v in d.items():
            if k == old:
                if new not in d:
                    new_dict[new] = v
            else:
                new_dict[k] = v
        return new_dict

    def apply_mapping(cfg_node: dict, mapping_node: dict) -> dict:
        node = dict(cfg_node)
        for map_key, map_val in mapping_node.items():
            if isinstance(map_val, str):
                if map_key in node:
                    node = replace_key_preserve_order(node, map_key, map_val)
            elif isinstance(map_val, dict):
                if map_key in node and isinstance(node[map_key], dict):
                    node[map_key] = apply_mapping(node[map_key], map_val)
                else:
                    for child_key, child_val in list(node.items()):
                        if isinstance(child_val, dict):
                            node[child_key] = apply_mapping(child_val, {map_key: map_val})
        return node

    config = apply_mapping(config, legacy_keys)

    # Normalise legacy value: 'continous' → 'continuous'
    try:
        mf_std = config.get('MaxFilter', {}).get('standard_settings', {})
        if mf_std.get('trans_option') == 'continous':
            mf_std['trans_option'] = 'continuous'
    except Exception:
        pass

    return config


def create_config_file(output_file: str = 'default_config.yml'):
    """Create a default configuration file and save it to disk"""
    try:
        config_data = create_default_config()
        if output_file.endswith('.json'):
            with open(output_file, 'w') as f:
                json.dump(config_data, f, indent=4)
        else:
            if not output_file.endswith(('.yml', '.yaml')):
                output_file += '.yml'
            with open(output_file, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
        return True
    except Exception as e:
        print(f"Error creating config file: {e}")
        return False

