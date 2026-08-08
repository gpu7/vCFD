"""Field sampling from OpenFOAM ASCII U fields."""

from pathlib import Path

from vcfd.mcp_server.field_sample import parse_vector_internal_field, sample_pipe_results


def test_parse_uniform_vector(tmp_path: Path):
    p = tmp_path / "U"
    p.write_text(
        "dimensions [0 1 -1 0 0 0 0];\ninternalField   uniform (1.5 0 0);\n",
        encoding="utf-8",
    )
    vecs = parse_vector_internal_field(p)
    assert vecs == [(1.5, 0.0, 0.0)]


def test_parse_nonuniform_vector(tmp_path: Path):
    p = tmp_path / "U"
    p.write_text(
        "internalField   nonuniform List<vector>\n"
        "2\n"
        "(\n"
        "(1 0 0)\n"
        "(2 0 0)\n"
        ")\n"
        ";\n",
        encoding="utf-8",
    )
    vecs = parse_vector_internal_field(p)
    assert len(vecs) == 2
    assert vecs[0][0] == 1.0
    assert vecs[1][0] == 2.0


def test_sample_structured(tmp_path: Path):
    case = tmp_path / "c"
    tdir = case / "10"
    tdir.mkdir(parents=True)
    # 2 axial x 2 radial = 4 cells, i fastest
    n_axial, n_radial = 2, 2
    lines = ["internalField   nonuniform List<vector>", "4", "("]
    # j=0: lower (near center), j=1: near wall — higher then lower U
    for j in range(n_radial):
        for i in range(n_axial):
            u = 0.2 if j == 0 else 0.05
            lines.append(f"({u} 0 0)")
    lines.append(")")
    lines.append(";")
    (tdir / "U").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sample = sample_pipe_results(case, n_axial=n_axial, n_radial=n_radial, radius=0.05)
    assert sample["u_max"] == 0.2
    assert len(sample["radii"]) == 2
