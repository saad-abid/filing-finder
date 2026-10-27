"""Web server for the chat page.

Run from the project folder:
    .venv\\Scripts\\python.exe -m uvicorn src.api.app:app --reload
Then open http://localhost:8000 for the chat page (after `npm run build` in
web/), or http://localhost:8000/docs to try the API directly. While editing the
page, also run `npm run dev` in web/ and open http://localhost:5173.

Endpoints:
    GET  /api/health              is the database and Ollama ready?
    GET  /api/examples            example questions for the page
    POST /api/questions           {"question": "..."} -> {"id": "..."}
    GET  /api/questions/{id}      status (queued / running / done / error) + answer
If web/dist exists (after `npm run build`), the page itself is served at /.
"""
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.api.jobs import JobQueue

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = ROOT / "web/dist"
CASES = ROOT / "eval/answer_cases.json"


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def real_answer(question):
    from src.answer.answer import answer, to_dict
    return to_dict(answer(question))


def real_health():
    from src.answer.llm import settings
    from src.db import connect
    status = {"database": False, "passages": 0, "ollama": False,
              "model": settings()[1], "model_installed": False}
    try:
        with connect() as conn:
            status["passages"] = conn.execute("SELECT count(*) FROM chunks").fetchone()[0]
        status["database"] = True
    except (Exception, SystemExit):
        pass
    url, model = settings()
    try:
        tags = requests.get(f"{url}/api/tags", timeout=3).json().get("models", [])
        status["ollama"] = True
        status["model_installed"] = any(m.get("name") == model for m in tags)
    except Exception:
        pass
    status["ready"] = status["database"] and status["passages"] > 0 and status["model_installed"]
    return status


def warm_up():
    """Load the search model now, so the first question doesn't wait a minute for it."""
    try:
        from src.indexing.embedder import get_model
        get_model()
    except Exception:
        pass


def create_app(answer_fn=real_answer, health_fn=real_health, warm=True):
    """answer_fn/health_fn can be swapped for fakes in tests."""
    jobs = JobQueue(answer_fn)

    @asynccontextmanager
    async def lifespan(app):
        if warm:
            threading.Thread(target=warm_up, daemon=True).start()
        yield

    app = FastAPI(title="FilingFinder", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return health_fn()

    @app.get("/api/examples")
    def examples():
        cases = json.loads(CASES.read_text(encoding="utf-8"))
        return [c["question"] for c in cases if c["expect"].startswith("answered")]

    @app.post("/api/questions", status_code=202)
    def ask(q: Question):
        text = q.question.strip()
        if len(text) < 3:
            raise HTTPException(422, "Please type a question.")
        return {"id": jobs.submit(text)}

    @app.get("/api/questions/{job_id}")
    def result(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown question id (the server may have restarted).")
        return job

    if WEB_DIST.exists():   # the built React page, so one server runs everything
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    return app


app = create_app()
