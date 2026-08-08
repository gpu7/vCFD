"""Case management and path safety tests."""

from pathlib import Path

import pytest

from vcfd.mcp_server.cases import create_case_from_template, list_cases, list_templates
from vcfd.mcp_server.paths import resolve_case_dir, validate_case_name
from vcfd.mcp_server.pipe_params import set_pipe_parameters


REPO = Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "cases" / "templates"


def test_validate_case_name():
    assert validate_case_name("pipe1") == "pipe1"
    with pytest.raises(ValueError):
        validate_case_name("../etc")
    with pytest.raises(ValueError):
        validate_case_name("has space")


def test_resolve_no_traversal(tmp_path: Path):
    with pytest.raises(ValueError):
        validate_case_name("..")


def test_create_and_list_case(tmp_path: Path):
    cases_root = tmp_path / "workspace"
    cases_root.mkdir()
    create_case_from_template(cases_root, TEMPLATES, "my_pipe", "hagen_poiseuille")
    items = list_cases(cases_root)
    assert len(items) == 1
    assert items[0]["name"] == "my_pipe"
    assert items[0]["template"] == "hagen_poiseuille"
    assert (cases_root / "my_pipe" / "system" / "controlDict").is_file()


def test_set_pipe_parameters(tmp_path: Path):
    cases_root = tmp_path / "workspace"
    cases_root.mkdir()
    case = create_case_from_template(cases_root, TEMPLATES, "p1", "hagen_poiseuille")
    data = set_pipe_parameters(case, radius=0.02, bulk_velocity=0.05, length=0.5)
    assert data["parameters"]["radius"] == 0.02
    assert data["reynolds_number"] > 0
    assert data["geometry"] == "axisymmetric_wedge_pipe"
    bmd = (case / "system" / "blockMeshDict").read_text(encoding="utf-8")
    assert "0.5" in bmd
    assert "wedge" in bmd
    u = (case / "0" / "U").read_text(encoding="utf-8")
    assert "0.05" in u
    assert "wedge" in u


def test_templates_available():
    assert "hagen_poiseuille" in list_templates(TEMPLATES)


def test_path_stays_in_root(tmp_path: Path):
    p = resolve_case_dir(tmp_path, "ok")
    assert p.parent == tmp_path.resolve()
