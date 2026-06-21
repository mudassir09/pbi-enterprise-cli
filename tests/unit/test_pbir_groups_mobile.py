"""Unit tests for visual container groups and mobile layout (PBIR GA).

Shapes verified against Power BI Desktop output:
  - group: a group-container visual.json with `visualGroup` + bounding box,
    members tagged with top-level `parentGroupName`.
  - mobile: a sibling mobile.json (visualContainerMobileState) with a position.
"""

from __future__ import annotations

import json

import pytest

from pbi_cli.backends.pbir_backend import PbirBackend
from pbi_cli.intelligence.visual_builder import FieldDef, VisualSpec, build_card


@pytest.fixture()
def backend(tmp_path) -> PbirBackend:
    (tmp_path / "T.Report").mkdir()
    return PbirBackend(str(tmp_path))


def _card(b: PbirBackend, page: str, x: int) -> str:
    spec = VisualSpec("card", build_card(FieldDef(entity="F", property="Sales", agg=0)),
                      x=x, y=10, width=100, height=80)
    return b.visual_add(page, spec)["name"]


class TestVisualGroups:
    def test_group_creates_container_and_tags_members(self, backend):
        backend.page_add("P")
        a, c = _card(backend, "P", 0), _card(backend, "P", 120)
        result = backend.visual_group_add("P", [a, c], display_name="KPIs")
        # group container
        _, g = backend._ga_find_visual_json("P", result["name"])
        assert g["visualGroup"]["displayName"] == "KPIs"
        assert g["visualGroup"]["groupMode"] == "ScaleMode"
        # bounding box spans both cards (x 0..220)
        assert g["position"]["x"] == 0 and g["position"]["width"] == 220
        # members tagged
        _, ma = backend._ga_find_visual_json("P", a)
        _, mc = backend._ga_find_visual_json("P", c)
        assert ma["parentGroupName"] == result["name"]
        assert mc["parentGroupName"] == result["name"]

    def test_group_listed_as_group_type(self, backend):
        backend.page_add("P2")
        a, c = _card(backend, "P2", 0), _card(backend, "P2", 120)
        gid = backend.visual_group_add("P2", [a, c])["name"]
        types = {v["name"]: v["visualType"] for v in backend.visual_list("P2")}
        assert types[gid] == "group"

    def test_group_requires_two_members(self, backend):
        backend.page_add("P3")
        a = _card(backend, "P3", 0)
        with pytest.raises(ValueError):
            backend.visual_group_add("P3", [a])

    def test_group_missing_page_raises(self, backend):
        with pytest.raises(ValueError):
            backend.visual_group_add("Nope", ["a", "b"])


class TestMobileLayout:
    def test_mobile_writes_sibling_json(self, backend):
        backend.page_add("M")
        a = _card(backend, "M", 0)
        assert backend.visual_set_mobile("M", a, x=10, y=20, width=140, height=120)
        vj, _ = backend._ga_find_visual_json("M", a)
        mobile = json.loads((vj.parent / "mobile.json").read_text(encoding="utf-8"))
        assert mobile["position"] == {
            "x": 10, "y": 20, "z": 1, "height": 120, "width": 140, "tabOrder": 0
        }
        assert "visualContainerMobileState" in mobile["$schema"]

    def test_mobile_missing_visual_returns_false(self, backend):
        backend.page_add("M2")
        assert backend.visual_set_mobile("M2", "nope", 0, 0, 100, 100) is False


class TestCliSurface:
    @pytest.fixture()
    def project(self, tmp_path):
        from click.testing import CliRunner
        (tmp_path / "C.Report").mkdir()
        b = PbirBackend(str(tmp_path))
        b.page_add("Pg")
        a, c = _card(b, "Pg", 0), _card(b, "Pg", 120)
        return CliRunner(), str(tmp_path), a, c

    def _run(self, runner, *args):
        from pbi_cli.cli import cli
        return runner.invoke(cli, list(args))

    def test_group_via_cli(self, project):
        runner, pbip, a, c = project
        r = self._run(runner, "visual", "group", "--pbip", pbip, "--page", "Pg",
                      "--member", a, "--member", c, "--name", "KPIs")
        assert r.exit_code == 0, r.output
        assert "Grouped" in r.output

    def test_mobile_via_cli(self, project):
        runner, pbip, a, _ = project
        r = self._run(runner, "visual", "mobile", "--pbip", pbip, "--page", "Pg",
                      "--name", a, "--x", "0", "--y", "0", "--width", "320", "--height", "120")
        assert r.exit_code == 0, r.output
        assert "Mobile layout set" in r.output
