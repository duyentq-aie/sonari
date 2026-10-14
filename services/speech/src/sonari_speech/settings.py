"""Process configuration, read from SPEECH_* environment variables.

The capacity numbers come from spikes/gop/onnx/BENCH.md (int8). They were measured on a
laptop, not on the VPS: re-measure there and override with SPEECH_MAX_IN_FLIGHT.
"""

import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MODEL_FILE = "wav2vec2_int8.onnx"

# Cores -> the largest burst of simultaneous 3 s requests whose p95 stayed under 2 s
# (BENCH.md, "Capacity", int8, one intra-op thread per request).
INT8_CAPACITY = {1: 2, 2: 5, 4: 7}


def capacity_for(cores: int) -> int:
    """Measured capacity for `cores`: that of the largest measured core count not above it."""
    if cores < 1:
        raise ValueError("cores must be at least 1")
    return INT8_CAPACITY[max(measured for measured in INT8_CAPACITY if measured <= cores)]


CGROUP_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")


def usable_cores(cpu_max: Path = CGROUP_CPU_MAX) -> int:
    """Cores this process may use: the CPUs it can run on, capped by a container CPU quota.

    `docker run --cpus=2` leaves the affinity at every host CPU and sets a cgroup quota
    instead, so the quota (cgroup v2 `cpu.max`: "<quota> <period>" or "max <period>") is
    read too, rounded down.
    """
    cores = len(os.sched_getaffinity(0))
    try:
        quota, period = cpu_max.read_text().split()
        if quota != "max":
            cores = min(cores, max(1, int(quota) // int(period)))
    except (OSError, ValueError):
        pass
    return cores


def default_model_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "~/sonari-data")).expanduser() / "onnx"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPEECH_", extra="ignore")

    service_name: str = "speech"
    log_level: str = "INFO"

    # Where the int8 model is. `python -m sonari_speech.runtime.weights` fills it.
    model_dir: Path = Field(default_factory=default_model_dir)
    # One intra-op thread per request, as BENCH.md measured the capacity.
    intra_op_threads: int = Field(default=1, ge=1)
    # Cores this process may use; inference runs up to this many requests at once (`slots`).
    cores: int = Field(default_factory=usable_cores, ge=1)
    # Running plus waiting requests; one more is refused with 503. None: BENCH.md's table for
    # `cores`. Set it (SPEECH_MAX_IN_FLIGHT) to a capacity measured on the real machine.
    max_in_flight: int | None = Field(default=None, ge=1)
    retry_after_s: int = Field(default=2, ge=1)

    # Audio limits (P20): clips over `max_clip_s` and speech under `min_speech_s` are rejected.
    max_clip_s: float = 15.0
    min_speech_s: float = 0.3
    max_upload_bytes: int = 5_000_000
    ffmpeg_path: str = "ffmpeg"
    decode_timeout_s: float = 10.0

    # Dev only: keep every scored recording here (scoring/dump.py). Never set in an image.
    debug_dump_dir: Path | None = None

    @property
    def model_path(self) -> Path:
        return self.model_dir / MODEL_FILE

    @property
    def slots(self) -> int:
        """Requests inferring at once: one per core, but never more than may be in flight, since
        a running request is in flight too and a slot past the limit could never be used. On 12
        cores that is 7, BENCH.md's capacity: each admitted request gets its own core and none
        waits (12 at once measured p95 2.08 s, over the 2 s target; 7 measured 1.26 s)."""
        return min(self.cores, self.in_flight_limit)

    @property
    def in_flight_limit(self) -> int:
        """SPEECH_MAX_IN_FLIGHT as given, else the measured capacity for the cores: never more
        than was measured, however many cores there are."""
        return self.max_in_flight if self.max_in_flight is not None else capacity_for(self.cores)
