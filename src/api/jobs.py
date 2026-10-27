"""A one-at-a-time queue for questions.

Answers take minutes on a CPU and the model can only run once at a time, so
questions wait in line and are answered by a single background worker. The
web page gets a ticket id straight away and checks back for the result.

Everything is kept in memory only: restarting the server forgets all
questions (there is no saved history, by design).
"""
import queue
import threading
import time
import uuid
from collections import OrderedDict

MAX_KEPT = 100   # forget the oldest finished questions after this many


class JobQueue:
    def __init__(self, work):
        """work(question) -> dict; runs in the background worker thread."""
        self._work = work
        self._jobs = OrderedDict()
        self._waiting = queue.Queue()
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, question):
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "question": question, "status": "queued",
                                  "created": time.time(), "started": None, "finished": None,
                                  "answer": None, "error": None}
            self._forget_old()
        self._waiting.put(job_id)
        return job_id

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            ahead = sum(1 for j in self._jobs.values()
                        if j["status"] in ("queued", "running") and j["created"] < job["created"])
            now = job["finished"] or time.time()
            return {**job, "position": ahead if job["status"] == "queued" else 0,
                    "seconds": round(now - (job["started"] or job["created"]))}

    def _run(self):
        while True:
            job_id = self._waiting.get()
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                job["status"], job["started"] = "running", time.time()
            try:
                result, error, status = self._work(job["question"]), None, "done"
            except (Exception, SystemExit) as e:   # our code uses SystemExit for "Ollama is down" etc.
                result, error, status = None, str(e) or type(e).__name__, "error"
            with self._lock:
                job.update(status=status, answer=result, error=error, finished=time.time())

    def _forget_old(self):
        finished = [k for k, j in self._jobs.items() if j["status"] in ("done", "error")]
        for k in finished[:max(0, len(self._jobs) - MAX_KEPT)]:
            del self._jobs[k]
