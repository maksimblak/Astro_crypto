from __future__ import annotations

import atexit
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - platform-specific fallback
    fcntl = None


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATUS_PATH = DATA_DIR / "auto_update_status.json"
LOG_PATH = DATA_DIR / "auto_update.log"
LOCK_PATH = DATA_DIR / "auto_update.lock"
DEFAULT_INTERVAL_SECONDS = 12 * 60 * 60
DEFAULT_STARTUP_DELAY_SECONDS = 30
PIPELINE_STEPS = [
    ("market_data", [str(BASE_DIR / "research" / "main.py")]),
    ("astro_scoring", [str(BASE_DIR / "research" / "astro_scoring.py")]),
    ("pivot_profiles", [str(BASE_DIR / "research" / "astro_extended_analysis.py")]),
]

_STATUS_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_ACTIVE_CHILD: subprocess.Popen | None = None
_ACTIVE_CHILD_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(int(raw), minimum)
    except ValueError:
        return default


def _python_executable() -> str:
    project_python = BASE_DIR / ".venv" / "bin" / "python"
    if project_python.exists():
        return str(project_python)
    return sys.executable


def _pipeline_commands() -> list[tuple[str, list[str]]]:
    python_bin = _python_executable()
    return [(name, [python_bin, *args]) for name, args in PIPELINE_STEPS]


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_update_status() -> dict:
    default_status = {
        "enabled": auto_update_enabled(),
        "running": False,
        "interval_seconds": auto_update_interval_seconds(),
        "startup_delay_seconds": auto_update_startup_delay_seconds(),
        "last_started_at": None,
        "last_finished_at": None,
        "last_success_at": None,
        "last_error": None,
        "last_stage": None,
        "log_path": str(LOG_PATH),
        "status_path": str(STATUS_PATH),
    }
    if not STATUS_PATH.exists():
        return default_status
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_status
    return {**default_status, **payload}


def _write_status(payload: dict):
    _ensure_data_dir()
    merged = {**load_update_status(), **payload}
    tmp_path = STATUS_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(STATUS_PATH)


def _append_log(title: str, text: str):
    _ensure_data_dir()
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{_now_iso()}] {title}\n")
        if text:
            handle.write(text.rstrip() + "\n")


def _acquire_process_lock():
    if fcntl is None:
        return None

    _ensure_data_dir()
    handle = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None

    handle.seek(0)
    handle.truncate()
    handle.write(
        json.dumps({"pid": os.getpid(), "locked_at": _now_iso()}, ensure_ascii=False)
    )
    handle.flush()
    return handle


def _release_process_lock(handle):
    if handle is None:
        return
    try:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def auto_update_enabled() -> bool:
    return _read_bool_env("ASTROBTC_AUTO_UPDATE", True)


def auto_update_interval_seconds() -> int:
    return _read_int_env("ASTROBTC_AUTO_UPDATE_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS, minimum=3600)


def auto_update_startup_delay_seconds() -> int:
    return _read_int_env("ASTROBTC_AUTO_UPDATE_STARTUP_DELAY_SECONDS", DEFAULT_STARTUP_DELAY_SECONDS, minimum=0)


def _kill_child_process(proc: subprocess.Popen):
    """Kill a child process and its entire process group."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait(timeout=3)


def _cleanup_active_child():
    """Kill any active child on parent shutdown (atexit / signal)."""
    global _ACTIVE_CHILD
    with _ACTIVE_CHILD_LOCK:
        if _ACTIVE_CHILD is not None:
            _kill_child_process(_ACTIVE_CHILD)
            _ACTIVE_CHILD = None


def _kill_orphan_scripts():
    """Best-effort kill of orphaned pipeline scripts from previous runs."""
    script_paths = {args[-1] for _, args in PIPELINE_STEPS}
    try:
        out = subprocess.run(
            ["pgrep", "-f", "|".join(script_paths)],
            capture_output=True, text=True, timeout=5,
        )
        for line in out.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
    except Exception:
        pass


def _notify_ws_clients(finished_at: str) -> None:
    """Best-effort cache invalidation + WebSocket broadcast after successful pipeline run."""
    import logging
    _log = logging.getLogger("astrobtc.auto_update")

    # Invalidate cached responses so next request gets fresh data
    try:
        from backend.services.cache_service import invalidate_all
        invalidate_all()
    except Exception:
        _log.debug("Cache invalidation failed after pipeline run", exc_info=True)

    # Push event to connected WebSocket clients via thread-safe call
    try:
        import asyncio
        from backend.routers.ws import broadcast

        try:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(broadcast("data_updated", {"updated_at": finished_at}), loop=loop)
        except RuntimeError:
            # No running loop (sync thread) — use run_until_complete
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(broadcast("data_updated", {"updated_at": finished_at}))
            finally:
                loop.close()
    except Exception:
        _log.debug("WebSocket broadcast failed after pipeline run", exc_info=True)


def run_update_pipeline() -> bool:
    global _ACTIVE_CHILD

    if not _RUN_LOCK.acquire(blocking=False):
        return False

    process_lock = _acquire_process_lock()
    if fcntl is not None and process_lock is None:
        _RUN_LOCK.release()
        return False

    try:
        _kill_orphan_scripts()

        with _STATUS_LOCK:
            _write_status(
                {
                    "enabled": auto_update_enabled(),
                    "running": True,
                    "last_started_at": _now_iso(),
                    "last_error": None,
                    "last_stage": "starting",
                }
            )

        for stage_name, command in _pipeline_commands():
            with _STATUS_LOCK:
                _write_status({"last_stage": stage_name})
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                with _ACTIVE_CHILD_LOCK:
                    _ACTIVE_CHILD = proc
                try:
                    stdout, stderr = proc.communicate(timeout=600)
                except subprocess.TimeoutExpired:
                    _kill_child_process(proc)
                    _append_log(f"{stage_name} TIMEOUT", "Killed after 600s")
                    with _STATUS_LOCK:
                        _write_status(
                            {
                                "running": False,
                                "last_finished_at": _now_iso(),
                                "last_error": f"{stage_name} timed out after 600s",
                                "last_stage": stage_name,
                            }
                        )
                    return False
                finally:
                    with _ACTIVE_CHILD_LOCK:
                        _ACTIVE_CHILD = None
            except OSError as exc:
                _append_log(f"{stage_name} LAUNCH FAILED", str(exc))
                with _STATUS_LOCK:
                    _write_status(
                        {
                            "running": False,
                            "last_finished_at": _now_iso(),
                            "last_error": f"{stage_name} failed to launch: {exc}",
                            "last_stage": stage_name,
                        }
                    )
                return False

            output = (stdout or "").strip()
            error_output = (stderr or "").strip()
            combined_output = "\n".join(part for part in [output, error_output] if part)
            _append_log(f"{stage_name} rc={proc.returncode}", combined_output)

            if proc.returncode != 0:
                with _STATUS_LOCK:
                    _write_status(
                        {
                            "running": False,
                            "last_finished_at": _now_iso(),
                            "last_error": f"{stage_name} failed with rc={proc.returncode}",
                            "last_stage": stage_name,
                        }
                    )
                return False

        finished_at = _now_iso()
        with _STATUS_LOCK:
            _write_status(
                {
                    "running": False,
                    "last_finished_at": finished_at,
                    "last_success_at": finished_at,
                    "last_error": None,
                    "last_stage": "complete",
                }
            )
        # Notify connected WebSocket clients that data was refreshed
        _notify_ws_clients(finished_at)
        return True
    finally:
        _release_process_lock(process_lock)
        _RUN_LOCK.release()


def _auto_update_loop():
    delay_seconds = auto_update_startup_delay_seconds()
    if delay_seconds:
        time.sleep(delay_seconds)

    while True:
        try:
            run_update_pipeline()
        except Exception as exc:  # pragma: no cover - defensive background guard
            import traceback
            _append_log("auto_update exception", traceback.format_exc())
            with _STATUS_LOCK:
                _write_status(
                    {
                        "running": False,
                        "last_finished_at": _now_iso(),
                        "last_error": repr(exc),
                    }
                )
        time.sleep(auto_update_interval_seconds())


def start_auto_updater() -> threading.Thread | None:
    global _THREAD

    if not auto_update_enabled():
        with _STATUS_LOCK:
            _write_status({"enabled": False, "running": False})
        return None

    if _THREAD and _THREAD.is_alive():
        return _THREAD

    atexit.register(_cleanup_active_child)

    _THREAD = threading.Thread(
        target=_auto_update_loop,
        name="astrobtc-auto-updater",
        daemon=True,
    )
    _THREAD.start()
    return _THREAD
