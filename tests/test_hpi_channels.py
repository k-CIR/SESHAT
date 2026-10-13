"""Regression tests for invalid sensor geometry; no recording data needed."""

import mne
import numpy as np
import pytest

from opm_utility_scripts.channels import find_zero_location_channels, get_hpi_output_channels


def test_zero_location_checks_components_and_nonfinite_values():
    info = mne.create_info(['zero', 'cancel', 'nan', 'inf', 'near'], 1000, 'mag')
    positions = [(0, 0, 0), (.05, -.05, 0), (np.nan, 0, 0),
                 (np.inf, 0, 0), (.0009, .0009, .0009)]
    for channel, position in zip(info['chs'], positions):
        channel['loc'][:3] = position
    assert list(find_zero_location_channels(info)) == ['zero', 'nan', 'inf', 'near']


def test_unused_tolerance_warns_without_changing_selection():
    info = mne.create_info(['valid'], 1000, 'mag')
    info['chs'][0]['loc'][:3] = (.01, 0, 0)
    with pytest.warns(DeprecationWarning, match='has no effect'):
        assert len(find_zero_location_channels(info, tolerance=.02)) == 0


def test_hpi_names_that_overlap_have_exact_indices():
    info = mne.create_info(['hpiout1', 'hpiout11'], 1000, 'misc')
    data = np.tile(np.sin(np.arange(2000) * .2), (2, 1))
    raw = mne.io.RawArray(data, info, verbose=False)
    names, indices = get_hpi_output_channels(raw)
    assert names == ['hpiout1', 'hpiout11']
    np.testing.assert_array_equal(indices, [0, 1])
