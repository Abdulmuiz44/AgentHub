import threading
import time
from queue import Empty, Queue

from sqlmodel import Session

from app.db.session import engine
from core.contracts import RunStatus
from memory import runs as run_repo
from .runtime import RunRuntimeService


class RunWorker:
    def __init__(self) -> None:
        self.runtime = RunRuntimeService()
        self._queue: Queue[int] = Queue()
        self._queued_ids: set[int] = set()
        self._queued_lock = threading.Lock()
        self._active_lock = threading.Lock()
        self._active_runs = 0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._requeue_incomplete_runs()
        self._thread = threading.Thread(target=self._run_loop, name="agenthub-run-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def enqueue(self, run_id: int) -> None:
        with self._queued_lock:
            if run_id in self._queued_ids:
                return
            self._queued_ids.add(run_id)
            self._queue.put(run_id)

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._active_lock:
                active = self._active_runs
            if self._queue.unfinished_tasks == 0 and active == 0:
                return True
            time.sleep(0.05)
        return False

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                run_id = self._queue.get(timeout=0.2)
            except Empty:
                continue
            with self._queued_lock:
                self._queued_ids.discard(run_id)
            with self._active_lock:
                self._active_runs += 1
            try:
                with Session(engine) as db:
                    self.runtime.process_run(db, run_id)
            finally:
                with self._active_lock:
                    self._active_runs -= 1
                self._queue.task_done()

    def _requeue_incomplete_runs(self) -> None:
        with Session(engine) as db:
            runs = run_repo.list_runs_by_status(
                db,
                [RunStatus.QUEUED.value, RunStatus.RUNNING.value],
            )
            for run in runs:
                if run.status == RunStatus.RUNNING.value:
                    run_repo.update_run(db, run, status=RunStatus.QUEUED.value)
                self.enqueue(run.id)
