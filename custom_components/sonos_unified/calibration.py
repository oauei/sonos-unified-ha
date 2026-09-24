"""Acoustic calibration module for Sonos Unified."""

from __future__ import annotations

import io
import math
import struct
import wave
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHIRP_DURATION = 0.08  # 80ms chirp
START_FREQ = 800.0  # 800 Hz
END_FREQ = 4000.0  # 4 kHz


def generate_chirp_pcm(
    sample_rate: int = SAMPLE_RATE,
    duration: float = CHIRP_DURATION,
    f0: float = START_FREQ,
    f1: float = END_FREQ,
) -> list[float]:
    """Generate a frequency sweep (chirp) with Hanning window."""
    num_samples = int(sample_rate * duration)
    samples: list[float] = []
    k = (f1 - f0) / duration

    for i in range(num_samples):
        t = i / sample_rate
        # Hanning window envelope to avoid click artifacts at start/end
        window = 0.5 * (1.0 - math.cos(2.0 * math.pi * i / (num_samples - 1)))
        # Instantaneous frequency: f(t) = f0 + k*t, phase = 2*pi*(f0*t + 0.5*k*t^2)
        phase = 2.0 * math.pi * (f0 * t + 0.5 * k * t * t)
        sample = window * math.sin(phase)
        samples.append(sample)

    return samples


def generate_calibration_wav(
    sample_rate: int = SAMPLE_RATE,
    pre_silence: float = 0.5,
    post_silence: float = 0.5,
) -> bytes:
    """Generate a single acoustic reference chirp WAV file."""
    chirp = generate_chirp_pcm(sample_rate=sample_rate)
    pre_samples = int(sample_rate * pre_silence)
    post_samples = int(sample_rate * post_silence)

    total_samples = [0.0] * pre_samples + chirp + [0.0] * post_samples

    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        # Pack to 16-bit signed integers
        raw_bytes = bytearray()
        for sample in total_samples:
            int_val = int(max(-1.0, min(1.0, sample)) * 32767)
            raw_bytes.extend(struct.pack("<h", int_val))
        wav_file.writeframes(raw_bytes)

    return output.getvalue()


def generate_metronome_wav(
    sample_rate: int = SAMPLE_RATE,
    bpm: int = 120,
    measures: int = 8,
) -> bytes:
    """Generate a rhythmic click track (metronome) for ear verification."""
    click_duration = 0.015  # 15ms click
    click_samples = int(sample_rate * click_duration)
    interval_samples = int(sample_rate * (60.0 / bpm))

    # Click waveform (1 kHz pulse)
    click: list[float] = []
    for i in range(click_samples):
        t = i / sample_rate
        env = math.exp(-i / (sample_rate * 0.004))
        click.append(env * math.sin(2.0 * math.pi * 1200.0 * t))

    total_clicks = measures * 4
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        raw_bytes = bytearray()

        for _ in range(total_clicks):
            for sample in click:
                int_val = int(max(-1.0, min(1.0, sample)) * 32767)
                raw_bytes.extend(struct.pack("<h", int_val))
            # Pad silence until next beat
            silence_count = max(0, interval_samples - click_samples)
            raw_bytes.extend(b"\x00\x00" * silence_count)

        wav_file.writeframes(raw_bytes)

    return output.getvalue()


def compute_cross_correlation_offset(
    signal: list[float],
    reference_chirp: list[float],
    sample_rate: int = SAMPLE_RATE,
    expected_gap_ms: float = 2000.0,
) -> float | None:
    """Compute arrival time difference between two detected chirp peaks.

    Returns the latency offset in milliseconds:
    offset_ms = measured_gap_ms - expected_gap_ms.
    Positive value indicates secondary speaker lags primary speaker.
    """
    ref_len = len(reference_chirp)
    sig_len = len(signal)
    if sig_len < ref_len * 2:
        return None

    # Calculate cross-correlation for peak detection
    correlations: list[float] = []
    step = 2  # downsample search step for speed
    for i in range(0, sig_len - ref_len, step):
        corr = sum(signal[i + j] * reference_chirp[j] for j in range(0, ref_len, 4))
        correlations.append(corr)

    # Find the two largest distinct peaks separated by roughly expected_gap_ms
    min_separation_samples = int((expected_gap_ms * 0.7 * sample_rate) / (1000 * step))

    max_idx1 = 0
    max_val1 = -1e9
    for idx, val in enumerate(correlations):
        if val > max_val1:
            max_val1 = val
            max_idx1 = idx

    max_idx2 = -1
    max_val2 = -1e9
    for idx, val in enumerate(correlations):
        if abs(idx - max_idx1) >= min_separation_samples and val > max_val2:
            max_val2 = val
            max_idx2 = idx

    if max_idx2 == -1:
        _LOGGER.warning("Could not detect two distinct peaks in calibration recording")
        return None

    # Sort peaks chronologically
    first_idx, second_idx = sorted([max_idx1, max_idx2])
    measured_gap_samples = (second_idx - first_idx) * step
    measured_gap_ms = (measured_gap_samples / sample_rate) * 1000.0

    offset_ms = measured_gap_ms - expected_gap_ms
    _LOGGER.info(
        "Detected acoustic peaks at %d and %d. Measured gap: %.2f ms, Offset: %.2f ms",
        first_idx * step,
        second_idx * step,
        measured_gap_ms,
        offset_ms,
    )
    return round(offset_ms, 1)
