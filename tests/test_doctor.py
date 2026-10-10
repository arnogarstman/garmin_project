from garminreader.doctor import Result, Skip, Status, run


def _ok() -> str:
    return "fine"


def _skip() -> str:
    raise Skip("not configured")


def _fail() -> str:
    raise RuntimeError("boom")


def test_run_classifies_each_check() -> None:
    assert run({"a": _ok, "b": _skip, "c": _fail}) == [
        Result("a", Status.OK, "fine"),
        Result("b", Status.SKIPPED, "not configured"),
        Result("c", Status.FAILED, "RuntimeError: boom"),
    ]
