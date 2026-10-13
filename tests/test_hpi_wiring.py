"""Exercise candidate dispatch and configured thresholds without recordings."""

from concurrent.futures import Future
import ast
from pathlib import Path
import warnings

import numpy as np
import pytest

from opm_utility_scripts import io
from opm_utility_scripts.hpi import _core, check


class InlineExecutor:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except Exception as error:
            future.set_exception(error)
        return future


@pytest.mark.parametrize('workers', [1, 2])
def test_candidate_selection_worker_signature_and_order(monkeypatch, workers):
    def fake_fit(path, pol, frequency, *, gof_limit, reffile, center_matching):
        return {'hpi_gofs': np.array([.98, .97, .96])}

    monkeypatch.setattr(_core, 'fit_hpi', fake_fit)
    monkeypatch.setattr(io, 'ProcessPoolExecutor', InlineExecutor)
    path, fit = io.select_best_hpi_file(['first', 'second'], {}, 33., n_jobs=workers)
    assert path == 'first'
    assert len(fit['hpi_gofs']) == 3


def test_recommendation_uses_configured_threshold():
    low_threshold = check._recommendation(np.array([.85, .86, .87]), gof_accept=.8)
    high_threshold = check._recommendation(np.array([.85, .86, .87]), gof_accept=.95)
    assert low_threshold != high_threshold


def test_stage_source_compiles():
    root = Path(__file__).resolve().parents[1]
    for relative in ['seshat/stages/opm_preprocess.py',
                     'opm_utility_scripts/hpi/coregister.py']:
        ast.parse((root / relative).read_text())


def test_hpi_only_does_not_leak_rng_or_warning_filters(monkeypatch):
    import mne
    raw = mne.io.RawArray(np.zeros((1, 100)), mne.create_info(['mag'], 1000, 'mag'),
                          verbose=False)
    amp = {'raw_orig': raw, 'coil_amplitudes': {}, 'hpi_indices': np.arange(3)}
    monkeypatch.setattr(check, 'compute_chpi_opm_locs', lambda *args: {
        'rrs': [np.zeros((3, 3))], 'gofs': [np.ones(3)]})
    filters = list(warnings.filters)
    rng = np.random.get_state()
    check._resolve_hpi_only(amp)
    assert warnings.filters == filters
    after = np.random.get_state()
    np.testing.assert_array_equal(after[1], rng[1])
    assert after[2:] == rng[2:]
