"""The README exit-code table matches nwp-core's exit codes."""

from __future__ import annotations

from pathlib import Path

from nwp_core.errors import (
    AccessDenied,
    ConfigError,
    LocationUnusableError,
    RunFailedError,
    RunNotReadyError,
    exit_code_for_class,
)

_README = Path(__file__).resolve().parents[2] / "README.md"
_HEADING = "## Códigos de saída"
_HEADER = ["Código", "Significado", "Quando o cod-nowcast-ons retorna"]
_MEANINGS = {
    0: "Sucesso",
    1: "Erro interno",
    2: "Erro de configuração ou erro fatal da execução",
    3: "Itens com falha",
    4: "Entrada não pronta",
}


def _table() -> list[list[str]]:
    lines = _README.read_text(encoding="utf-8").splitlines()
    after = lines[lines.index(_HEADING) + 1 :]
    end = next(
        (i for i, line in enumerate(after) if line.startswith("## ")),
        len(after),
    )
    return [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in after[:end]
        if line.startswith("|")
    ]


def test_readme_table_lists_the_exit_codes() -> None:
    header, separator, *rows = _table()
    assert header == _HEADER
    assert all(set(cell) <= set("-:") for cell in separator)
    assert [row[0] for row in rows] == ["0", "1", "2", "3", "4"]
    assert {int(row[0]): row[1] for row in rows} == _MEANINGS
    assert all(len(row) == 3 and row[2] for row in rows)


def test_exit_code_classes_match_the_table() -> None:
    classes = (
        ValueError,
        ConfigError,
        LocationUnusableError,
        AccessDenied,
        RunFailedError,
        RunNotReadyError,
    )
    assert {cls.__name__: exit_code_for_class(cls) for cls in classes} == {
        "ValueError": 1,
        "ConfigError": 2,
        "LocationUnusableError": 2,
        "AccessDenied": 2,
        "RunFailedError": 3,
        "RunNotReadyError": 4,
    }
