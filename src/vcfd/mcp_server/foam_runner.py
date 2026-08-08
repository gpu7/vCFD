"""OpenFOAM command execution: mock, Docker, or native."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from vcfd.config import OpenFOAMMode, Settings


@dataclass
class RunResult:
    returncode: int
    stdout: str
    command: list[str]
    mode: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class FoamRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(
        self,
        case_dir: Path,
        args: list[str],
        *,
        timeout: int | None = 600,
    ) -> RunResult:
        mode = self.settings.openfoam_mode
        if mode == OpenFOAMMode.MOCK:
            return self._run_mock(case_dir, args)
        if mode == OpenFOAMMode.DOCKER:
            return self._run_docker(case_dir, args, timeout=timeout)
        if mode == OpenFOAMMode.NATIVE:
            return self._run_native(case_dir, args, timeout=timeout)
        raise ValueError(f"Unknown OpenFOAM mode: {mode}")

    def build_command(self, case_dir: Path, args: list[str]) -> list[str]:
        """Build argv for async job launch (non-mock)."""
        mode = self.settings.openfoam_mode
        if mode == OpenFOAMMode.MOCK:
            return ["python3", "-c", self._mock_script(case_dir, args)]
        if mode == OpenFOAMMode.DOCKER:
            return self._docker_argv(case_dir, args)
        if mode == OpenFOAMMode.NATIVE:
            return self._native_argv(case_dir, args)
        raise ValueError(f"Unknown OpenFOAM mode: {mode}")

    def _run_mock(self, case_dir: Path, args: list[str]) -> RunResult:
        cmd = args[0] if args else "unknown"
        # Simulate common OpenFOAM utilities for offline tests.
        if cmd == "blockMesh":
            poly = case_dir / "constant" / "polyMesh"
            poly.mkdir(parents=True, exist_ok=True)
            (poly / "points").write_text("// mock points\n", encoding="utf-8")
            (poly / "owner").write_text("// mock owner\n", encoding="utf-8")
            (poly / "neighbour").write_text("// mock neighbour\n", encoding="utf-8")
            (poly / "faces").write_text("// mock faces\n", encoding="utf-8")
            (poly / "boundary").write_text("// mock boundary\n", encoding="utf-8")
            out = (
                "/* mock blockMesh */\n"
                "Mesh OK.\n"
                "nCells: 400\n"
                "Max non-orthogonality = 0\n"
            )
            return RunResult(0, out, ["mock", *args], "mock")
        if cmd == "checkMesh":
            out = (
                "/* mock checkMesh */\n"
                "Mesh stats\n"
                "    cells: 400\n"
                "    faces: 1600\n"
                "    points: 500\n"
                "Max non-orthogonality = 0 OK.\n"
                "Mesh OK.\n"
            )
            return RunResult(0, out, ["mock", *args], "mock")
        if cmd in {"simpleFoam", "foamRun", "pimpleFoam"}:
            # Write a fake time directory with minimal U/p so post tools can run.
            tdir = case_dir / "1000"
            tdir.mkdir(parents=True, exist_ok=True)
            (tdir / "U").write_text(
                _mock_u_field(),
                encoding="utf-8",
            )
            (tdir / "p").write_text(
                _mock_p_field(),
                encoding="utf-8",
            )
            out = (
                "/* mock solver */\n"
                "Time = 1000\n"
                "smoothSolver:  Solving for Ux, Initial residual = 1e-06, Final residual = 1e-08\n"
                "DICPCG:  Solving for p, Initial residual = 1e-06, Final residual = 1e-08\n"
                "ExecutionTime = 0.1 s\n"
                "End\n"
            )
            return RunResult(0, out, ["mock", *args], "mock")
        if cmd == "foamToVTK":
            vtk = case_dir / "VTK"
            vtk.mkdir(parents=True, exist_ok=True)
            (vtk / "case.vtk").write_text("# vtk DataFile mock\n", encoding="utf-8")
            return RunResult(0, "/* mock foamToVTK */\n", ["mock", *args], "mock")
        return RunResult(0, f"/* mock ran: {' '.join(args)} */\n", ["mock", *args], "mock")

    def _mock_script(self, case_dir: Path, args: list[str]) -> str:
        # For async mock jobs we re-invoke FoamRunner synchronously via a tiny script.
        return (
            "from pathlib import Path\n"
            "from vcfd.config import Settings, OpenFOAMMode\n"
            "from vcfd.mcp_server.foam_runner import FoamRunner\n"
            f"s = Settings(openfoam_mode=OpenFOAMMode.MOCK, cases_root=Path({str(case_dir.parent)!r}))\n"
            f"r = FoamRunner(s).run(Path({str(case_dir)!r}), {args!r})\n"
            "print(r.stdout)\n"
            "raise SystemExit(r.returncode)\n"
        )

    def _docker_argv(self, case_dir: Path, args: list[str]) -> list[str]:
        if not shutil.which("docker"):
            raise RuntimeError("docker not found on PATH; install Docker or use mock/native mode.")
        case_dir = case_dir.resolve()
        image = self.settings.openfoam_docker_image
        # Mount the case parent so each case is /work/<case_name> inside the container.
        mount = str(case_dir.parent)
        inner = f"/work/{case_dir.name}"
        foam_cmd = " ".join(shlex_quote(a) for a in args)
        # Must cd after sourcing bash.rc — OpenFOAM entry env may start in /root.
        shell = (
            "set -e; "
            "if [ -f /openfoam/bash.rc ]; then . /openfoam/bash.rc; "
            "elif [ -f /usr/lib/openfoam/openfoam2506/etc/bashrc ]; then "
            ". /usr/lib/openfoam/openfoam2506/etc/bashrc; fi; "
            f"cd {shlex_quote(inner)}; "
            f"{foam_cmd}"
        )
        return [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{mount}:/work",
            image,
            "bash",
            "-lc",
            shell,
        ]

    def _native_argv(self, case_dir: Path, args: list[str]) -> list[str]:
        bashrc = self.settings.openfoam_bashrc or ""
        foam_cmd = " ".join(shlex_quote(a) for a in args)
        if bashrc:
            shell = f"source {shlex_quote(bashrc)} && cd {shlex_quote(str(case_dir))} && {foam_cmd}"
        else:
            shell = f"cd {shlex_quote(str(case_dir))} && {foam_cmd}"
        return ["bash", "-lc", shell]

    def _run_docker(self, case_dir: Path, args: list[str], timeout: int | None) -> RunResult:
        cmd = self._docker_argv(case_dir, args)
        return self._exec(cmd, timeout=timeout, mode="docker")

    def _run_native(self, case_dir: Path, args: list[str], timeout: int | None) -> RunResult:
        cmd = self._native_argv(case_dir, args)
        return self._exec(cmd, timeout=timeout, mode="native")

    def _exec(self, cmd: list[str], *, timeout: int | None, mode: str) -> RunResult:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or "") + (exc.stderr or "")
            return RunResult(124, str(out), cmd, mode)
        out = (proc.stdout or "") + (proc.stderr or "")
        return RunResult(proc.returncode, out, cmd, mode)


def shlex_quote(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _mock_u_field() -> str:
    return """/*--------------------------------*- C++ -*----------------------------------*\\
| mock U field for tests                                                     |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volVectorField;
    object      U;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (1 0 0);

boundaryField
{
    inlet
    {
        type            fixedValue;
        value           uniform (1 0 0);
    }
    outlet
    {
        type            zeroGradient;
    }
    walls
    {
        type            noSlip;
    }
    frontAndBack
    {
        type            empty;
    }
}

// ************************************************************************* //
"""


def _mock_p_field() -> str:
    return """/*--------------------------------*- C++ -*----------------------------------*\\
| mock p field for tests                                                     |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       volScalarField;
    object      p;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{
    inlet
    {
        type            zeroGradient;
    }
    outlet
    {
        type            fixedValue;
        value           uniform 0;
    }
    walls
    {
        type            zeroGradient;
    }
    frontAndBack
    {
        type            empty;
    }
}

// ************************************************************************* //
"""
