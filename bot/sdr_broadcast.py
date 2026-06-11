"""SDR broadcast — transmits HIGH/CRITICAL incident reports as FM audio via HackRF.

Pipeline:
    compose_broadcast_script()          → English radio-style spoken text
    _text_to_wav()                      → QVAC supertonic TTS via Node subprocess
    _fm_modulate()                      → numpy FM IQ (cross-platform, no extra deps)
    hackrf_transfer                     → radio transmission

⚠  POC / demo only. Transmitting on any frequency requires regulatory
   authorisation. In Taiwan: NCC regulations apply. Use at minimal power
   in a controlled environment for testing only.

Dependencies (available via package manager — no macOS-specific tools needed):
    hackrf        (brew install hackrf  /  apt install hackrf)
    node          (for QVAC TTS; already required by the rest of the project)
    numpy         (already in bot/requirements.txt via retriever.py)
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile  # used by broadcast_ir for WAV temp file only
import wave
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger("copilot.sdr")

# ── default transmission parameters ──────────────────────────────────────────
DEFAULT_FREQUENCY_HZ = 469_660_000   # 469.660 MHz
DEFAULT_SAMPLE_RATE   = 2_000_000    # 2 MHz — HackRF TX minimum
DEFAULT_FM_DEVIATION  = 5_000        # ±5 kHz narrowband FM (standard voice)
DEFAULT_TX_GAIN       = 20           # VGA gain 0-47 dB; keep low for POC
DEFAULT_TX_AMP        = 0            # TX amplifier: 0=off (very short range)

_TTS_ONCE_JS = Path(__file__).parent.parent / "tools" / "tts_once.mjs"
_NODE        = shutil.which("node")


def check_dependencies() -> list[str]:
    """Return names of any missing required binaries."""
    missing = []
    if not _NODE:
        missing.append("node")
    if not shutil.which("hackrf_transfer"):
        missing.append("hackrf_transfer")
    if not _TTS_ONCE_JS.exists():
        missing.append(f"tools/tts_once.mjs (expected at {_TTS_ONCE_JS})")
    return missing


# ── script composition ────────────────────────────────────────────────────────

def compose_broadcast_script(risk_data: dict[str, Any], node_info: dict[str, Any]) -> str:
    """Build a concise English radio-style emergency broadcast script from IR data.

    Always English so the TTS (supertonic, EN model) renders clearly.
    Kept short (under 200 chars) — the supertonic model has an input length limit.
    """
    risk    = risk_data.get("risk", "UNKNOWN")
    summary = risk_data.get("summary", "") or ""

    node_id = node_info.get("long_name") or node_info.get("from_id") or "unknown node"
    lat     = node_info.get("lat")
    lon     = node_info.get("lon")
    dist_m  = node_info.get("dist_from_base_m")
    bearing = node_info.get("bearing_compass")

    parts: list[str] = [f"EMERGENCY. Risk {risk}. Node {node_id}."]

    if lat is not None and lon is not None:
        lat_str = f"{lat:.3f}".replace("-", "minus ").replace(".", " point ")
        lon_str = f"{lon:.3f}".replace("-", "minus ").replace(".", " point ")
        parts.append(f"GPS {lat_str} North, {lon_str} East.")
    elif dist_m is not None and bearing:
        parts.append(f"{dist_m} meters, bearing {bearing}.")

    # Truncate summary to keep total script short
    if summary:
        short = summary[:80].rstrip()
        parts.append(short + ("…" if len(summary) > 80 else "."))

    parts.append("Request immediate rescue. Over.")

    return " ".join(parts)


# ── TTS (QVAC via Node) ───────────────────────────────────────────────────────

def _text_to_wav(text: str, wav_path: Path, timeout: int = 180) -> None:
    """Convert text to WAV using QVAC supertonic TTS (tools/tts_once.mjs)."""
    if not _NODE:
        raise RuntimeError("node not found in PATH")
    if not _TTS_ONCE_JS.exists():
        raise FileNotFoundError(f"tts_once.mjs not found at {_TTS_ONCE_JS}")

    result = subprocess.run(
        [_NODE, str(_TTS_ONCE_JS), str(wav_path)],
        input=text,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"tts_once.mjs exited {result.returncode}: {result.stderr[-400:]}"
        )
    log.debug("tts_once stderr: %s", result.stderr[-200:])


# ── FM modulation (pure numpy) ────────────────────────────────────────────────

def _read_wav_mono(wav_path: Path) -> tuple[int, np.ndarray]:
    """Read WAV file → normalised mono float32 array."""
    with wave.open(str(wav_path), "rb") as wf:
        n_ch   = wf.getnchannels()
        sw     = wf.getsampwidth()
        rate   = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    dtype = np.int16 if sw == 2 else np.int32
    scale = 32768.0  if sw == 2 else 2_147_483_648.0
    samples = np.frombuffer(frames, dtype=dtype).astype(np.float32) / scale
    if n_ch > 1:
        samples = samples.reshape(-1, n_ch).mean(axis=1)
    return rate, samples


def _fm_modulate(
    audio: np.ndarray,
    audio_rate: int,
    output_rate: int,
    deviation: int,
) -> bytes:
    """FM-modulate audio and return HackRF-ready interleaved int8 IQ bytes.

    HackRF expects: I0 Q0 I1 Q1 … as signed 8-bit (-128..127).
    """
    # Resample audio to SDR output rate via linear interpolation
    n_out  = int(len(audio) * output_rate / audio_rate)
    t_in   = np.arange(len(audio), dtype=np.float64)
    t_out  = np.linspace(0.0, len(audio) - 1, n_out)
    audio_up = np.interp(t_out, t_in, audio.astype(np.float64))

    # Normalise to ±0.8 (headroom)
    peak = np.max(np.abs(audio_up))
    if peak > 0:
        audio_up = audio_up / peak * 0.8

    # FM modulate: instantaneous phase = 2π × (deviation/Fs) × Σ x[n]
    phase = 2.0 * np.pi * (deviation / output_rate) * np.cumsum(audio_up)
    iq    = np.exp(1j * phase).astype(np.complex64)

    # Interleave I/Q → int8
    interleaved = np.empty(len(iq) * 2, dtype=np.float32)
    interleaved[0::2] = iq.real
    interleaved[1::2] = iq.imag
    return np.clip(interleaved * 127, -128, 127).astype(np.int8).tobytes()


# ── HackRF transmission ───────────────────────────────────────────────────────

def fm_transmit(
    wav_path: Path,
    frequency_hz: int = DEFAULT_FREQUENCY_HZ,
    sample_rate: int  = DEFAULT_SAMPLE_RATE,
    deviation: int    = DEFAULT_FM_DEVIATION,
    tx_gain: int      = DEFAULT_TX_GAIN,
    tx_amp: int       = DEFAULT_TX_AMP,
) -> None:
    """Modulate wav_path as FM and transmit via hackrf_transfer.

    IQ bytes are piped directly to hackrf_transfer stdin (same pattern as
    morse_tx.py) — no temp file, works cross-platform.
    Requires sudo; configure sudoers NOPASSWD for hackrf_transfer for
    unattended operation (see bot/README or .env.example notes).
    """
    audio_rate, audio = _read_wav_mono(wav_path)
    duration_s = len(audio) / audio_rate
    log.info(
        "sdr: FM modulating %.1f s audio (%d Hz → %d Hz, dev=%d Hz)",
        duration_s, audio_rate, sample_rate, deviation,
    )

    iq_bytes = _fm_modulate(audio, audio_rate, sample_rate, deviation)

    cmd = [
        "sudo", "hackrf_transfer",
        "-t", "/dev/stdin",
        "-f", str(frequency_hz),
        "-s", str(sample_rate),
        "-x", str(tx_gain),
        "-a", str(tx_amp),
    ]
    log.info(
        "sdr: TX start → %.3f MHz  |  %.1f s audio  |  gain %d dB  |  amp %s",
        frequency_hz / 1e6, duration_s, tx_gain, "on" if tx_amp else "off",
    )
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, stderr = proc.communicate(input=iq_bytes)
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)

    # Extract "Total time" from hackrf_transfer stderr for a clean summary line
    total_line = next(
        (l for l in stderr.decode(errors="replace").splitlines() if "Total time" in l),
        None,
    )
    log.info("sdr: TX done  → %.3f MHz  |  %s", frequency_hz / 1e6,
             total_line.strip() if total_line else "complete")


# ── public entry point ────────────────────────────────────────────────────────

def broadcast_ir(
    risk_data: dict[str, Any],
    node_info: dict[str, Any],
    frequency_hz: int = DEFAULT_FREQUENCY_HZ,
    tx_gain: int      = DEFAULT_TX_GAIN,
    tx_amp: int       = DEFAULT_TX_AMP,
) -> None:
    """Full pipeline: IR data → TTS WAV → FM IQ → HackRF transmission.

    Designed to be called from a daemon thread — catches and logs all errors
    so a broadcast failure never affects the basestation's primary receive loop.
    """
    missing = check_dependencies()
    if missing:
        log.warning("sdr: broadcast skipped — missing: %s", ", ".join(missing))
        return

    script = compose_broadcast_script(risk_data, node_info)
    log.info("sdr: broadcast script (%d chars): %s…", len(script), script[:80])

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        wav_path = Path(tf.name)

    try:
        log.info("sdr: generating TTS audio via QVAC…")
        _text_to_wav(script, wav_path)
        size_kb = wav_path.stat().st_size / 1024
        log.info("sdr: WAV ready (%.1f KB) → starting FM transmission", size_kb)
        fm_transmit(wav_path, frequency_hz=frequency_hz, tx_gain=tx_gain, tx_amp=tx_amp)
    except subprocess.CalledProcessError as e:
        log.error("sdr: subprocess failed — %s", e)
    except Exception:
        log.exception("sdr: broadcast failed (non-fatal)")
    finally:
        wav_path.unlink(missing_ok=True)
