"""Outside calls: which errors count as the network's, and trying again with a growing wait."""

import pytest

from app import outside


def test_retry_tries_again_then_gives_the_last_error() -> None:
    waits: list[float] = []
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("slow")
        return "ok"

    assert outside.retry(flaky, sleep=waits.append) == "ok"
    assert waits == [1.0, 2.0]  # 1 s, then double

    def down() -> str:
        raise ConnectionError("refused")

    waits.clear()
    with pytest.raises(ConnectionError, match="refused"):
        outside.retry(down, attempts=2, sleep=waits.append)
    assert waits == [1.0]


def test_a_bug_is_not_retried() -> None:
    calls = {"n": 0}

    def broken() -> None:
        calls["n"] += 1
        raise KeyError("a bug, not the network")

    with pytest.raises(KeyError):
        outside.retry(broken, sleep=lambda _: None)
    assert calls["n"] == 1


def test_storage_errors_include_the_network_and_a_missing_file() -> None:
    errors = outside.storage_errors()
    assert issubclass(FileNotFoundError, errors) and KeyError in errors
    assert not issubclass(ZeroDivisionError, errors)
