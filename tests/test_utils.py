import pytest

from scripts.utils import confirm, debug, is_tty, is_writable, parse_money


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10,50", 10.50),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("1234.56", 1234.56),
        ("R$ 1.234,56", 1234.56),
        ("-42,50", -42.50),
        ("12,345", 12345.0),
        ("", 0.0),
        ("abc", 0.0),
    ],
)
def test_parse_money(raw, expected):
    assert parse_money(raw) == pytest.approx(expected)


def test_is_writable_true_for_existing_dir(tmp_path):
    assert is_writable(tmp_path) is True


def test_is_writable_creates_missing_dirs(tmp_path):
    target = tmp_path / "nested" / "dir"
    assert is_writable(target) is True
    assert target.is_dir()


def test_is_writable_false_on_os_error(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("tempfile.TemporaryFile", boom)
    assert is_writable(tmp_path) is False


def test_is_tty_reflects_stderr(monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)
    assert is_tty() is True

    monkeypatch.setattr("sys.stderr.isatty", lambda: False)
    assert is_tty() is False


def test_confirm_auto_yes_skips_prompt(monkeypatch):
    monkeypatch.setattr("scripts.utils.is_tty", lambda: False)
    assert confirm("Sobrescrever?", auto_yes=True) is True


def test_confirm_non_tty_without_auto_yes_defaults_to_false(monkeypatch):
    monkeypatch.setattr("scripts.utils.is_tty", lambda: False)
    assert confirm("Sobrescrever?", auto_yes=False) is False


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("y", True), ("yes", True), ("s", True), ("sim", True), ("n", False), ("", False)],
)
def test_confirm_tty_reads_input(monkeypatch, answer, expected):
    monkeypatch.setattr("scripts.utils.is_tty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    assert confirm("Sobrescrever?", auto_yes=False) is expected


def test_debug_prints_only_when_enabled(monkeypatch, capsys):
    monkeypatch.delenv("TEXFLOW_DEBUG", raising=False)
    debug("silent")
    assert capsys.readouterr().err == ""

    monkeypatch.setenv("TEXFLOW_DEBUG", "1")
    debug("loud")
    assert "loud" in capsys.readouterr().err
