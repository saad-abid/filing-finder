"""Talk to the local AI model through Ollama.

This is the only file that knows about Ollama. To use a different model,
change OLLAMA_MODEL in .env; to use a different provider, replace chat_json().
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3.5:4b"
CONTEXT_TOKENS = 8192   # Ollama's default is smaller and would silently cut our prompt


@dataclass
class LLMReply:
    content: dict          # the model's JSON answer
    model: str
    prompt_tokens: int     # how much the model read
    output_tokens: int     # how much it wrote
    seconds: float


def settings():
    load_dotenv(ROOT / ".env")
    return (os.environ.get("OLLAMA_URL", DEFAULT_URL).rstrip("/"),
            os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL))


def chat_json(system, user, schema, timeout=1800):
    """Send a prompt and get back JSON that matches `schema`."""
    url, model = settings()
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "format": schema,      # Ollama forces the reply into this JSON shape
        "stream": False,
        "think": False,        # skip hidden "thinking" text; too slow on CPU
        # num_gpu=0 runs on the CPU. On this PC Ollama crashes trying the old
        # Nvidia chip ("unsupported toolchain"); set OLLAMA_NUM_GPU on a machine
        # with a supported GPU to speed things up.
        "options": {"temperature": 0, "num_ctx": CONTEXT_TOKENS,
                    "num_gpu": int(os.environ.get("OLLAMA_NUM_GPU", "0"))},
    }
    try:
        resp = requests.post(f"{url}/api/chat", json=payload, timeout=timeout)
    except requests.ConnectionError:
        raise SystemExit(f"Can't reach Ollama at {url}. Is the Ollama app running?")
    if resp.status_code == 404:
        raise SystemExit(f"Model '{model}' isn't downloaded. Run: ollama pull {model}")
    resp.raise_for_status()
    data = resp.json()
    return LLMReply(
        content=json.loads(data["message"]["content"]),
        model=model,
        prompt_tokens=data.get("prompt_eval_count", 0),
        output_tokens=data.get("eval_count", 0),
        seconds=data.get("total_duration", 0) / 1e9,
    )
