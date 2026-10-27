import threading
import time

from fastapi.testclient import TestClient

from src.api.app import create_app


def fake_answer(question):
    return {"question": question, "status": "answered",
            "sentences": [{"text": "Apple relies on outsourcing partners.", "citations": [1]}],
            "sources": [{"number": 1, "citation": "Apple 10-K FY2024, Risk Factors, p. 8"}]}


def fake_health():
    return {"database": True, "passages": 3847, "ollama": True,
            "model": "qwen3.5:4b", "model_installed": True, "ready": True}


def client(answer_fn=fake_answer):
    return TestClient(create_app(answer_fn, fake_health, warm=False))


def wait_for(c, job_id, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = c.get(f"/api/questions/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_ask_returns_a_ticket_then_the_answer():
    c = client()
    r = c.post("/api/questions", json={"question": "Does Apple rely on suppliers?"})
    assert r.status_code == 202
    job = wait_for(c, r.json()["id"])
    assert job["status"] == "done"
    assert job["answer"]["sentences"][0]["citations"] == [1]
    assert job["question"] == "Does Apple rely on suppliers?"


def test_empty_or_too_long_questions_are_rejected():
    c = client()
    assert c.post("/api/questions", json={"question": "  "}).status_code == 422
    assert c.post("/api/questions", json={"question": "x" * 501}).status_code == 422
    assert c.post("/api/questions", json={}).status_code == 422


def test_unknown_ticket_is_404():
    assert client().get("/api/questions/nope").status_code == 404


def test_questions_wait_in_line_one_at_a_time():
    release = threading.Event()
    def slow_answer(question):
        release.wait(5)
        return fake_answer(question)
    c = client(slow_answer)
    first = c.post("/api/questions", json={"question": "first question"}).json()["id"]
    second = c.post("/api/questions", json={"question": "second question"}).json()["id"]
    time.sleep(0.1)
    assert c.get(f"/api/questions/{first}").json()["status"] == "running"
    waiting = c.get(f"/api/questions/{second}").json()
    assert waiting["status"] == "queued" and waiting["position"] == 1
    release.set()
    assert wait_for(c, second)["status"] == "done"


def test_errors_are_reported_not_crashing_the_server():
    def broken(question):
        raise SystemExit("Can't reach Ollama at http://127.0.0.1:11434. Is the Ollama app running?")
    c = client(broken)
    job = wait_for(c, c.post("/api/questions", json={"question": "anything here"}).json()["id"])
    assert job["status"] == "error" and "Ollama" in job["error"]
    # the worker keeps going after an error
    assert c.get("/api/health").json()["ready"] is True


def test_examples_come_from_the_test_set():
    examples = client().get("/api/examples").json()
    assert len(examples) == 10 and examples[0].startswith("How did Apple")
