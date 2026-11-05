"""Pin the generated test shapefile to the committed shapefile parts."""

from __future__ import annotations

from pathlib import Path

import shapefile

COMMITTED_SHP = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "data"
    / "shapes"
    / "test_shapes.shp"
)


def test_generated_shapefile_matches_the_committed_parts(
    generated_shapefile: Path,
) -> None:
    """The generated shapefile equals the committed one, .dbf bytes aside.

    ticket-028 deletes this test together with the committed parts under
    ``tests/fixtures/data/shapes/``.
    """
    with (
        shapefile.Reader(str(generated_shapefile)) as generated,
        shapefile.Reader(str(COMMITTED_SHP)) as committed,
    ):
        assert generated.shapeType == committed.shapeType
        assert [s.parts for s in generated.shapes()] == [
            s.parts for s in committed.shapes()
        ]
        assert [s.points for s in generated.shapes()] == [
            s.points for s in committed.shapes()
        ]
        assert generated.bbox == committed.bbox
        assert generated.fields == committed.fields
        assert [list(r) for r in generated.records()] == [
            list(r) for r in committed.records()
        ]
    assert generated_shapefile.with_suffix(".prj").read_text(
        encoding="ascii"
    ) == COMMITTED_SHP.with_suffix(".prj").read_text(encoding="ascii")
