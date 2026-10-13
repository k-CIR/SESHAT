"""Synthetic drive recordings with mocked MNE field regression."""

import mne
import numpy as np
import pytest

from opm_utility_scripts.hpi import _core


def recording(active=(True, True, True), start=3., stop=7.):
    times = np.arange(12000) / 1000.
    names = ['mag', 'hpiout1', 'hpiout2', 'hpiout3']
    info = mne.create_info(names, 1000., ['mag', 'misc', 'misc', 'misc'])
    info['chs'][0]['loc'][:3] = (.1, .02, .03)
    data = np.zeros((4, len(times)))
    for index, enabled in enumerate(active, 1):
        if enabled:
            data[index] = np.sin(2 * np.pi * 33 * times) * ((times >= start) & (times <= stop))
        else:
            data[index] = -1. - .01 * np.sin(times)  # nonflat but no positive peaks
    return mne.io.RawArray(data, info, verbose=False)


def mock_amplitudes(monkeypatch, captures):
    def compute(raw, **kwargs):
        captures.append((raw.first_time, raw.n_times,
                         raw.info['hpi_meas'][0]['hpi_coils'][0]['drive_chan']))
        return {'times': np.array([1.]), 'slopes': np.ones((1, 1, 1))}
    monkeypatch.setattr(_core, 'compute_chpi_amplitudes', compute)


def test_surviving_coils_window_metadata_and_caller_preservation(monkeypatch):
    captures = []
    mock_amplitudes(monkeypatch, captures)
    raw = recording((True, False, True))
    original = raw.get_data().copy()
    amp = _core.fit_hpi_amplitudes(raw, 33.)
    assert amp['hpi_names'] == ['hpiout1', 'hpiout3']
    np.testing.assert_array_equal(amp['original_coil_indices'], [0, 2])
    assert amp['slope'].shape == (2, 1)
    assert amp['slope_ch_names'] == ['mag']
    assert [item[2] for item in captures] == amp['hpi_names']
    assert all(abs(item[0] - 4.) < .04 and item[1] == 2001 for item in captures)
    np.testing.assert_array_equal(raw.get_data(), original)
    assert raw.info['hpi_meas'] == []


def test_no_peaks_is_explicit_error():
    with pytest.raises(ValueError, match='No HPI coils'):
        _core.fit_hpi_amplitudes(recording((False, False, False)), 33.)


def test_short_activation_is_rejected():
    with pytest.raises(ValueError, match='shorter than 2 seconds'):
        _core.fit_hpi_amplitudes(recording(start=4., stop=5.), 33.)


def test_noise_tail_containing_activation_is_not_used(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Noise PSD must not use an active HPI tail')
    monkeypatch.setattr(_core, 'find_bads', forbidden)
    assert _core._detect_noise(recording(stop=11.), None, 33.) == ([], None)


def stub_full_fit(monkeypatch):
    raw = recording()
    points = np.array([[.02, 0, .08], [-.02, 0, .08], [0, .03, .08]])
    pol = dict(source='fif', lpa=np.array([-.07, 0, 0]),
               rpa=np.array([.07, 0, 0]), nasion=np.array([0, .1, 0]),
               hpi_orig=points, extra_pts=np.empty((0, 3)), eeg_pts=np.empty((0, 3)))
    amp = dict(hpi_names=['a', 'b', 'c'], hpi_indices=np.arange(3),
               hpi_freqs=np.full(3, 33.), slope=np.ones((3, 1)),
               slope_ch_names=['mag'], raw_orig=raw.copy(), coil_amplitudes={},
               peak_tlast=7.)
    monkeypatch.setattr(_core, '_detect_noise', lambda *a, **kw: ([], None))
    monkeypatch.setattr(_core, 'fit_hpi_amplitudes', lambda *a: amp)
    monkeypatch.setattr(_core, 'compute_chpi_opm_locs', lambda *a: {
        'rrs': [points.copy()], 'gofs': [np.ones(3)]})
    monkeypatch.setattr(_core, 'compute_whitener', lambda *a, **kw: (np.eye(1), None))
    monkeypatch.setattr(_core, '_create_meg_coils', lambda *a: [])
    monkeypatch.setattr(_core, '_concatenate_coils', lambda *a: None)
    monkeypatch.setattr(_core, '_gof_at_fixed_pos', lambda *a: .98)
    return raw, pol


def test_duplicate_assignment_reports_clear_error(monkeypatch):
    raw, pol = stub_full_fit(monkeypatch)
    class DuplicateTree:
        def __init__(self, points):
            pass
        def query(self, points):
            return np.zeros(3), np.array([0, 0, 2])
    monkeypatch.setattr(_core, 'cKDTree', DuplicateTree)
    with pytest.raises(ValueError, match='Duplicate KD-tree assignment'):
        _core.fit_hpi(raw, pol, 33., optim='none')


@pytest.mark.parametrize('success', [True, False])
def test_refinement_residuals_and_failure_fallback(monkeypatch, success):
    from types import SimpleNamespace
    raw, pol = stub_full_fit(monkeypatch)
    def minimize(*args, **kwargs):
        assert kwargs['bounds'][:3] == [(-np.deg2rad(5), np.deg2rad(5))] * 3
        return SimpleNamespace(status=0 if success else 1, success=success,
                               x=np.array([0, 0, 0, .001, 0, 0]), fun=-.98)
    monkeypatch.setattr(_core, 'minimize', minimize)
    if success:
        fit = _core.fit_hpi(raw, pol, 33.)
        assert fit['opt_success']
        np.testing.assert_allclose(fit['dist'], .001, atol=1e-9)
    else:
        with pytest.warns(RuntimeWarning, match='Retaining the initial'):
            fit = _core.fit_hpi(raw, pol, 33.)
        np.testing.assert_allclose(fit['dist'], 0., atol=1e-9)
        assert not fit['opt_success']


def test_full_fit_noise_exclusions_do_not_mutate_caller(monkeypatch):
    raw, pol = stub_full_fit(monkeypatch)
    raw.resample(500., verbose=False)
    original_data = raw.get_data().copy()
    original_names = raw.ch_names.copy()
    amplitude = _core.fit_hpi_amplitudes
    def detect(working, *args, **kwargs):
        assert working.info['sfreq'] == 1000.
        return ['mag'], None
    def compute(working, frequency):
        assert 'mag' not in working.ch_names
        return amplitude(working, frequency)
    monkeypatch.setattr(_core, '_detect_noise', detect)
    monkeypatch.setattr(_core, 'fit_hpi_amplitudes', compute)
    _core.fit_hpi(raw, pol, 33., optim='none')
    assert raw.ch_names == original_names
    assert raw.info['sfreq'] == 500.
    np.testing.assert_array_equal(raw.get_data(), original_data)
