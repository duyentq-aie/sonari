import json
from pathlib import Path

import pytest

from sonari_speech.errors import MessageKey
from sonari_speech.settings import INT8_CAPACITY, Settings, capacity_for, usable_cores

VI_JSON = Path(__file__).resolve().parents[3] / "apps" / "web" / "messages" / "vi.json"


def test_capacity_table_is_the_int8_column_of_bench_md() -> None:
    # spikes/gop/onnx/BENCH.md, int8, 3 s clip, p95 <= 2 s: 1 core 2, 2 cores 5, 4 cores 7.
    assert INT8_CAPACITY == {1: 2, 2: 5, 4: 7}


@pytest.mark.parametrize(("cores", "expected"), [(1, 2), (2, 5), (3, 5), (4, 7), (8, 7), (64, 7)])
def test_capacity_for_uses_the_largest_measured_core_count_not_above(
    cores: int, expected: int
) -> None:
    assert capacity_for(cores) == expected


def test_capacity_for_rejects_zero_cores() -> None:
    with pytest.raises(ValueError):
        capacity_for(0)


def test_defaults_follow_the_bench_numbers_for_the_usable_cores() -> None:
    settings = Settings(cores=2)
    assert settings.intra_op_threads == 1
    assert settings.slots == 2
    assert settings.in_flight_limit == 5


def gate(**settings: int) -> tuple[int, int]:
    found = Settings(**settings)  # type: ignore[arg-type]
    return found.slots, found.in_flight_limit


# cores -> (slots, in-flight limit). The limit is BENCH.md's capacity, never the core count: 12
# cores once gave in_flight_limit=12, and 12 at once measured p95 2.08 s, over the 2 s target.
@pytest.mark.parametrize(
    ("cores", "expected"), [(1, (1, 2)), (2, (2, 5)), (4, (4, 7)), (12, (7, 7))]
)
def test_the_limit_never_exceeds_the_measured_capacity_nor_slots_the_limit(
    cores: int, expected: tuple[int, int]
) -> None:
    assert gate(cores=cores) == expected
    assert expected[1] <= capacity_for(cores)


def test_max_in_flight_is_an_explicit_override_and_slots_follow_it() -> None:
    assert gate(cores=2, max_in_flight=9) == (2, 9)
    assert gate(cores=12, max_in_flight=12) == (12, 12)  # a capacity measured on the real machine
    assert gate(cores=4, max_in_flight=1) == (1, 1)  # as given: no slot that could never run


def test_max_in_flight_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEECH_MAX_IN_FLIGHT", "10")
    assert gate(cores=12) == (10, 10)


def test_settings_read_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPEECH_CORES", "3")
    monkeypatch.setenv("SPEECH_MODEL_DIR", str(tmp_path))
    settings = Settings()
    assert settings.slots == 3
    assert settings.model_path == tmp_path / "wav2vec2_int8.onnx"


def test_the_model_dir_defaults_to_data_dir_onnx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEECH_MODEL_DIR", raising=False)
    monkeypatch.setenv("DATA_DIR", "/somewhere")
    assert Settings().model_dir == Path("/somewhere/onnx")


def test_every_message_key_has_vietnamese_copy_in_vi_json() -> None:
    messages = json.loads(VI_JSON.read_text("utf-8"))
    for key in MessageKey:
        node = messages
        for part in key.value.split("."):
            assert part in node, f"{key.value} is missing from vi.json"
            node = node[part]
        assert isinstance(node, str) and node.strip(), f"{key.value} is empty in vi.json"


def test_no_message_key_is_a_prefix_of_another() -> None:
    values = [key.value for key in MessageKey]
    for a in values:
        assert not any(b != a and b.startswith(a + ".") for b in values), a


@pytest.mark.parametrize(
    ("cpu_max", "expected"),
    [
        ("max 100000\n", 12),  # no quota: every core this process may run on
        ("200000 100000\n", 2),  # docker --cpus=2
        ("150000 100000\n", 1),  # 1.5 CPUs: round down, never promise more than the quota
        ("50000 100000\n", 1),  # a fraction of a CPU is still one worker
        ("4000000 100000\n", 12),  # a quota above the affinity does not add cores
        ("garbage\n", 12),
    ],
)
def test_usable_cores_respects_the_cgroup_cpu_quota(
    cpu_max: str, expected: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.sched_getaffinity", lambda _: set(range(12)))
    path = tmp_path / "cpu.max"
    path.write_text(cpu_max)
    assert usable_cores(path) == expected


def test_usable_cores_without_a_cgroup_file_is_the_affinity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.sched_getaffinity", lambda _: {0, 1, 2})
    assert usable_cores(tmp_path / "missing") == 3
