"""Persistent sequential project queue for Khiem YouTube."""
import json
import os
import tempfile
import time
import uuid
from pathlib import Path

class ProjectQueue:
    def __init__(self, path):
        self.path = Path(path)
        self.jobs = []
        self.load()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".queue_", suffix=".json", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "jobs": self.jobs}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.jobs = data.get("jobs", [])
                for job in self.jobs:
                    if job.get("status") == "running":
                        job["status"] = "interrupted"
                        job["error"] = "Phần mềm đóng khi dự án đang chạy. Bấm Chạy lại."
                self.save()
            except (OSError, ValueError, TypeError):
                self.jobs = []

    def add(self, config, mode):
        job = dict(id=uuid.uuid4().hex[:12], name=config.get("name", "Dự án"),
                   config=dict(config), mode=mode, status="pending",
                   error="", started=None, finished=None, elapsed=0)
        self.jobs.append(job)
        self.save()
        return job

    def next_pending(self):
        return next((j for j in self.jobs if j["status"] == "pending"), None)

    def update(self, job, status, error=""):
        job["status"] = status
        job["error"] = str(error)
        now = time.time()
        if status == "running":
            job["started"] = now
            job["finished"] = None
        elif status in ("success", "failed"):
            job["finished"] = now
            job["elapsed"] = max(0, now - (job.get("started") or now))
        self.save()

    def retry(self, job):
        if job["status"] not in ("failed", "interrupted"):
            return False
        job.update(status="pending", error="", started=None, finished=None, elapsed=0)
        self.save()
        return True
