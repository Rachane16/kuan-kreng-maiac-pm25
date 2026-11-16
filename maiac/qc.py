"""Pure MAIAC AOD scaling, quality masking and daily aggregation."""

from __future__ import annotations

import numpy as np
import warnings


def quality_mask(raw_aod: np.ndarray, aot_qa: np.ndarray, *, fill_value: int, valid_range: tuple[int, int]) -> np.ndarray:
    """Keep finite land pixels with clear sky, normal adjacency and best AOD QA."""
    raw = np.asarray(raw_aod)
    qa = np.asarray(aot_qa).astype(np.uint16)
    if raw.shape != qa.shape:
        raise ValueError("AOD and QA shapes differ")
    return (
        (raw != fill_value)
        & (raw >= valid_range[0])
        & (raw <= valid_range[1])
        & (raw >= 0)
        & ((qa & 0b111) == 0b001)
        & (((qa >> 3) & 0b11) == 0)
        & (((qa >> 5) & 0b111) == 0)
        & (((qa >> 8) & 0b1111) == 0)
    )


def daily_aod(raw_aod: np.ndarray, aot_qa: np.ndarray, *, scale_factor: float, add_offset: float,
              fill_value: int, valid_range: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Return median of valid overpasses and valid count along the first axis.

    Arrays have shape (orbit, ...). Missing pixels remain NaN.
    """
    raw = np.asarray(raw_aod)
    if raw.ndim < 2:
        raise ValueError("Expected an orbit axis and at least one spatial axis")
    valid = quality_mask(raw, aot_qa, fill_value=fill_value, valid_range=valid_range)
    values = np.where(valid, (raw.astype(float) - add_offset) * scale_factor, np.nan)
    counts = valid.sum(axis=0).astype(np.uint16)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        result = np.nanmedian(values, axis=0)
    result[counts == 0] = np.nan
    return result, counts
