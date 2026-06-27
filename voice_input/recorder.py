from __future__ import annotations

import logging
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from voice_input.config import AudioSettings
from voice_input.paths import resolve_runtime_path
from voice_input.utils import ensure_directory


@dataclass(slots=True)
class RecordingResult:
    wav_path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    frame_count: int


class AudioRecorder:
    def __init__(
        self,
        settings: AudioSettings,
        temp_dir: str | Path = "temp",
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.temp_dir = ensure_directory(resolve_runtime_path(temp_dir))
        self.logger = logger or logging.getLogger(__name__)
        self._stream = None
        self._frames = []
        self._started_at = 0.0
        self._np = None

    def start(self) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice and numpy are required for recording. Run .\\run.ps1 first.") from exc

        self._np = np
        self._frames = []
        self._started_at = time.perf_counter()

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            if status:
                self.logger.warning("Audio callback status=%s", status)
            self._frames.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.settings.sample_rate,
            channels=self.settings.channels,
            device=self.settings.device,
            dtype="float32",
            callback=callback,
        )
        self._stream.start()

    def stop(self) -> RecordingResult:
        if self._stream is None or self._np is None:
            raise RuntimeError("Recording was not started.")

        stream = self._stream
        self._stream = None
        stream.stop()
        stream.close()

        duration = max(0.0, time.perf_counter() - self._started_at)
        if self._frames:
            audio = self._np.concatenate(self._frames, axis=0)
        else:
            audio = self._np.zeros((0, self.settings.channels), dtype="float32")

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        wav_path = self.temp_dir / f"recording_{timestamp}_{int(time.time() * 1000) % 1000:03d}.wav"
        self._write_wav(wav_path, audio)

        return RecordingResult(
            wav_path=wav_path,
            duration_seconds=duration,
            sample_rate=self.settings.sample_rate,
            channels=self.settings.channels,
            frame_count=int(audio.shape[0]) if hasattr(audio, "shape") else 0,
        )

    def _write_wav(self, wav_path: Path, audio) -> None:  # noqa: ANN001
        np = self._np
        if np is None:
            raise RuntimeError("NumPy is not initialized.")

        audio = np.asarray(audio, dtype="float32")
        if audio.ndim == 1:
            audio = audio.reshape(-1, 1)
        audio = np.clip(audio, -1.0, 1.0)
        pcm = (audio * 32767.0).astype(np.int16)

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(self.settings.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.settings.sample_rate)
            wav_file.writeframes(pcm.reshape(-1).tobytes())

    def log_input_device_info(self) -> None:
        try:
            import sounddevice as sd

            default_input = sd.query_devices(kind="input")
            self.logger.info("Microphone detected name=%s", default_input.get("name", "unknown"))
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Could not query microphone: %s", exc)

    @staticmethod
    def list_input_devices() -> str:
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice is required to list microphones. Run .\\run.ps1 first.") from exc
        return str(sd.query_devices())
