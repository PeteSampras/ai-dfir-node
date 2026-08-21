"""Minimal submit/poll job queue in front of llama-server.

Same send/receive shape as the homelab's own LLM admission pattern: a caller
POSTs a prompt and gets a job id back immediately (no held connection), a
single background worker pulls the oldest queued job and calls llama-server
patiently (a long timeout, not the caller's problem), and the caller polls
for the result whenever it wants. This removes the whole timeout-mismatch /
orphaned-retry failure class structurally -- there is nothing for a client
timeout to abandon, because the client was never holding a connection open
in the first place.

SQLite-backed (one file, `queue.db`) rather than Redis -- "very basics" for a
first bring-up on a fresh box; swap the storage layer later if real
concurrency needs it. A single worker thread means jobs run one at a time,
which matches a single local model instance anyway (llama-server here is not
multi-slot).
"""
import os
import queue
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

DB_PATH = os.environ.get("QUEUE_DB_PATH", "/data/queue.db")
LLAMA_BASE_URL = os.environ.get("LLAMA_BASE_URL", "http://llama-server:8080/v1")
LLAMA_MODEL = os.environ.get("LLAMA_MODEL", "local-model")
# Long on purpose -- the whole point of this service is that the CALLER never has
# to pick a timeout that matches how long the model actually takes.
LLAMA_TIMEOUT_S = float(os.environ.get("LLAMA_TIMEOUT_S", "900"))

app = FastAPI(title="llm-queue", description="Submit/poll job queue in front of llama-server")
_work_signal = queue.Queue()  # just a wakeup signal, not the job data (that's in sqlite)


@contextmanager
def _db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _init_db():
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                system_prompt TEXT,
                status TEXT NOT NULL,      -- queued | running | done | failed
                result TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)


class SubmitRequest(BaseModel):
    prompt: str
    system: str | None = None


class SubmitResponse(BaseModel):
    job_id: str
    status: str


class JobStatus(BaseModel):
    job_id: str
    status: str
    result: str | None = None
    error: str | None = None
    created_at: float
    updated_at: float


@app.on_event("startup")
def startup():
    _init_db()
    threading.Thread(target=_worker_loop, daemon=True).start()
    # Re-queue anything left in-flight from a crash/restart -- a job stuck at
    # 'running' with nobody actually working it would otherwise poll forever.
    with _db() as conn:
        conn.execute("UPDATE jobs SET status='queued' WHERE status='running'")


@app.post("/submit", response_model=SubmitResponse)
def submit(req: SubmitRequest):
    job_id = str(uuid.uuid4())
    now = time.time()
    with _db() as conn:
        conn.execute(
            "INSERT INTO jobs (id, prompt, system_prompt, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', ?, ?)",
            (job_id, req.prompt, req.system, now, now),
        )
    _work_signal.put(1)  # wake the worker; harmless if it's already awake/busy
    return SubmitResponse(job_id=job_id, status="queued")


@app.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str):
    with _db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="unknown job_id")
    return JobStatus(
        job_id=row["id"], status=row["status"], result=row["result"], error=row["error"],
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


def _worker_loop():
    while True:
        job = _claim_next_job()
        if job is None:
            # Block until a submit() wakes us, rather than a tight poll loop.
            _work_signal.get()
            continue
        _run_job(job)


def _claim_next_job():
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE jobs SET status='running', updated_at=? WHERE id=?",
            (time.time(), row["id"]),
        )
        return dict(row)


def _run_job(job):
    messages = []
    if job["system_prompt"]:
        messages.append({"role": "system", "content": job["system_prompt"]})
    messages.append({"role": "user", "content": job["prompt"]})
    try:
        with httpx.Client(timeout=LLAMA_TIMEOUT_S) as client:
            resp = client.post(
                f"{LLAMA_BASE_URL}/chat/completions",
                json={"model": LLAMA_MODEL, "messages": messages},
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        with _db() as conn:
            conn.execute(
                "UPDATE jobs SET status='done', result=?, updated_at=? WHERE id=?",
                (content, time.time(), job["id"]),
            )
    except Exception as exc:  # noqa: BLE001 -- a bad job must not kill the worker thread
        with _db() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error=?, updated_at=? WHERE id=?",
                (str(exc)[:2000], time.time(), job["id"]),
            )
