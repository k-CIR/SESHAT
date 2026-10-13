"""Regression tests for the opt-in legacy numerical engine."""

import mne
import numpy as np
import pytest
import sys

from opm_utility_scripts.hpi import _legacy
from opm_utility_scripts.hpi import coregister


def fixtures(monkeypatch, gofs=None):
    positions = np.array([[.02, 0., .08], [-.02, 0., .08],
                          [0., .03, .08], [0., -.03, .08]])
    info = mne.create_info(['mag', 'hpiout1', 'hpiout2', 'hpiout3', 'hpiout4'],
                           1000., ['mag'] + ['misc'] * 4)
    info['chs'][0]['loc'][:] = (.1, .02, .03, 1., 0., 0., 0., 1., 0., 0., 0., 1.)
    times = np.arange(12000) / 1000.
    data = np.zeros((5, len(times)))
    for i in range(4):
        data[i + 1] = np.sin(2 * np.pi * 33 * times) * ((times > 3) & (times < 7))
    raw = mne.io.RawArray(data, info, verbose=False)
    montage = mne.channels.make_dig_montage(
        nasion=(0., .1, 0.), lpa=(-.07, 0., 0.), rpa=(.07, 0., 0.),
        hpi=positions, coord_frame='head')
    captures = []

    def amplitudes(cropped, **kwargs):
        captures.append((cropped.first_time, cropped.n_times,
                         cropped.info['line_freq'],
                         [c['drive_chan'] for c in cropped.info['hpi_meas'][0]['hpi_coils']]))
        return {'times': np.array([1.]),
                'slopes': np.arange(4, dtype=float).reshape(1, 4, 1)}
    monkeypatch.setattr(_legacy, 'compute_chpi_amplitudes', amplitudes)
    monkeypatch.setattr(_legacy, 'compute_chpi_locs', lambda *a, **k: {
        'times': np.array([1.]), 'rrs': [positions.copy()],
        'gofs': [np.array(gofs if gofs is not None else [.9, .91, .95, .99])]})
    return raw, montage, captures


def test_legacy_crop_duplicate_model_strict_gof_and_common_schema(monkeypatch):
    raw, montage, captures = fixtures(monkeypatch)
    result = _legacy.fit_hpi_legacy(raw, montage, 33.)
    assert result['engine'] == 'legacy'
    assert result['legacy_inclusion'] is True
    np.testing.assert_array_equal(result['include_hpis'], [False, True, True, True])
    assert result['slope'].shape == (4, 1)
    assert result['optim'] == 'none'
    assert len(captures) == 4
    assert all(abs(c[0] - 4.) < .04 and c[1] == 2001 for c in captures)
    assert all(c[2] is None and c[3] == result['hpi_names'] for c in captures)
    assert np.isfinite(result['dev_to_head_trans']['trans']).all()


def test_custom_legacy_gof_threshold_is_inclusive(monkeypatch):
    raw, montage, _ = fixtures(monkeypatch, [.8, .9, .91, .99])
    result = _legacy.fit_hpi_legacy(raw, montage, 33., new_sfreq=500., gof_limit=.89)
    assert result['legacy_inclusion'] is False
    assert result['gof_inclusive'] is True
    np.testing.assert_array_equal(result['include_hpis'], [False, True, True, True])
    assert result['fit_sfreq'] == 500.


def test_explicit_default_threshold_is_inclusive(monkeypatch):
    raw, montage, _ = fixtures(monkeypatch)
    result = _legacy.fit_hpi_legacy(raw, montage, 33., gof_limit=.9,
                                    strict_legacy_gof=False)
    assert result['include_hpis'][0]


def test_check_recommendation_uses_engine_threshold_and_missing_pol_gof():
    from opm_utility_scripts.hpi.check import _recommendation
    result = _recommendation(
        [.9, .95, .97], [1., 2., 3.], [False, True, True],
        np.full(3, np.nan), gof_accept=.9, gof_inclusive=False,
    )
    assert result[0] == 'POOR'  # strict legacy default excludes GOF == .9
    assert result[3] == 'OK'
    assert any('no fixed-position Polhemus GOF' in reason for reason in result[5])


def test_legacy_zero_position_uses_original_coordinate_sum():
    info = mne.create_info(['cancel', 'origin'], 1000., ['mag', 'mag'])
    info['chs'][0]['loc'][:] = (.05, -.05, 0., 1., 0., 0., 0., 1., 0., 0., 0., 1.)
    info['chs'][1]['loc'][:] = (0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1.)
    assert _legacy._legacy_zero_location_channels(info) == ['cancel', 'origin']


@pytest.mark.parametrize('polfile', [{'unverified': True}, 'digitisation.json'])
def test_legacy_rejects_unverified_digitisation(polfile):
    with pytest.raises((TypeError, ValueError), match='head-frame|canonical|FIF|dict'):
        _legacy._load_head_polhemus(polfile)


def test_legacy_outputs_have_distinct_suffix(monkeypatch):
    monkeypatch.setattr(coregister.mne.io, 'read_info', lambda *a, **k: {'sfreq': 1000.})
    assert coregister._output_suffix('task_raw.fif', 1000., 'current') == '_proc-hpi_raw.fif'
    assert coregister._output_suffix('task_raw.fif', 500., 'legacy') == '_proc-hpi-legacy+ds_raw.fif'


def test_both_cli_parsers_accept_legacy_selector(monkeypatch):
    from opm_utility_scripts.hpi import check
    monkeypatch.setattr(sys, 'argv', ['coregister', '--legacy'])
    assert coregister._parse_args().legacy
    monkeypatch.setattr(sys, 'argv', ['check', '--legacy'])
    assert check._parse_args().legacy
