"""Async job manager for long-running OpenFOAM processes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class JobRecord:
    job_id: str
    case_name: str
    command: list[str]
    state: JobState = JobState.QUEUED
    pid: int | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    returncode: int | None = None
    log_path: str = ""
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


class JobManager:
    """Filesystem-backed job tracker with background process supervision."""

    def __init__(self, jobs_root: Path, max_concurrent: int = 2) -> None:
        self.jobs_root = jobs_root
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._procs: dict[str, subprocess.Popen[str]] = {}
        self._records: dict[str, JobRecord] = {}
        self._load_existing()

    def _job_dir(self, job_id: str) -> Path:
        return self.jobs_root / job_id

    def _meta_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "job.json"

    def _load_existing(self) -> None:
        if not self.jobs_root.exists():
            return
        for path in self.jobs_root.iterdir():
            meta = path / "job.json"
            if not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
                data["state"] = JobState(data["state"])
                rec = JobRecord(**data)
                self._records[rec.job_id] = rec
            except Exception:
                continue

    def _persist(self, rec: JobRecord) -> None:
        job_dir = self._job_dir(rec.job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path(rec.job_id).write_text(
            json.dumps(rec.to_dict(), indent=2),
            encoding="utf-8",
        )

    def _running_count(self) -> int:
        self._refresh_all()
        return sum(1 for r in self._records.values() if r.state == JobState.RUNNING)

    def _refresh_all(self) -> None:
        for job_id in list(self._procs.keys()):
            self._refresh(job_id)

    def _refresh(self, job_id: str) -> None:
        proc = self._procs.get(job_id)
        rec = self._records.get(job_id)
        if not rec:
            return
        if proc is None:
            return
        code = proc.poll()
        if code is None:
            return
        rec.returncode = code
        rec.finished_at = time.time()
        rec.state = JobState.FINISHED if code == 0 else JobState.FAILED
        if code != 0 and not rec.error:
            rec.error = f"Process exited with code {code}"
        self._procs.pop(job_id, None)
        self._persist(rec)

    def start(
        self,
        case_name: str,
        command: list[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        meta: dict[str, Any] | None = None,
        timeout_sec: int | None = None,
    ) -> JobRecord:
        with self._lock:
            if self._running_count() >= self.max_concurrent:
                raise RuntimeError(
                    f"Too many concurrent jobs (max {self.max_concurrent}). "
                    "Wait for a job to finish or stop one."
                )
            job_id = uuid.uuid4().hex[:12]
            job_dir = self._job_dir(job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            log_path = job_dir / "stdout.log"
            rec = JobRecord(
                job_id=job_id,
                case_name=case_name,
                command=command,
                state=JobState.RUNNING,
                started_at=time.time(),
                log_path=str(log_path),
                meta=meta or {},
            )
            log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115
            try:
                full_env = os.environ.copy()
                if env:
                    full_env.update(env)
                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd) if cwd else None,
                    env=full_env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
            except Exception as exc:
                log_f.close()
                rec.state = JobState.FAILED
                rec.error = str(exc)
                rec.finished_at = time.time()
                self._records[job_id] = rec
                self._persist(rec)
                raise

            rec.pid = proc.pid
            self._procs[job_id] = proc
            self._records[job_id] = rec
            self._persist(rec)

            if timeout_sec:

                def _watch() -> None:
                    try:
                        proc.wait(timeout=timeout_sec)
                    except subprocess.TimeoutExpired:
                        self.stop(job_id, force=True)
                        with self._lock:
                            r = self._records.get(job_id)
                            if r:
                                r.error = f"Timed out after {timeout_sec}s"
                                r.state = JobState.FAILED
                                self._persist(r)
                    finally:
                        try:
                            log_f.close()
                        except Exception:
                            pass
                        self._refresh(job_id)

                threading.Thread(target=_watch, daemon=True).start()
            else:
                def _wait() -> None:
                    proc.wait()
                    try:
                        log_f.close()
                    except Exception:
                        pass
                    self._refresh(job_id)

                threading.Thread(target=_wait, daemon=True).start()

            return rec

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            self._refresh(job_id)
            return self._records.get(job_id)

    def list_jobs(self, case_name: str | None = None) -> list[JobRecord]:
        with self._lock:
            self._refresh_all()
            jobs = list(self._records.values())
        if case_name:
            jobs = [j for j in jobs if j.case_name == case_name]
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    def stop(self, job_id: str, *, force: bool = False) -> JobRecord:
        with self._lock:
            rec = self._records.get(job_id)
            if not rec:
                raise KeyError(f"Unknown job_id: {job_id}")
            proc = self._procs.get(job_id)
            if proc and proc.poll() is None:
                try:
                    if force:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    else:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            rec.state = JobState.STOPPED
            rec.finished_at = time.time()
            self._procs.pop(job_id, None)
            self._persist(rec)
            return rec

    def tail_log(self, job_id: str, lines: int = 40) -> str:
        rec = self.get(job_id)
        if not rec or not rec.log_path:
            return ""
        path = Path(rec.log_path)
        if not path.is_file():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
