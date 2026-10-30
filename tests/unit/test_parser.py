import pytest

from app import __version__
from app.parser import build_parser


def test_version_flag_prints_version_and_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"{parser.prog} {__version__}\n"
