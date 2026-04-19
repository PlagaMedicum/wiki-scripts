from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from threading import Event, Thread
from time import perf_counter

from biblio.observability import format_elapsed, get_logger

HEARTBEAT_INTERVAL_SECONDS = 2.0
TRANSPORT_WAIT_REPORT_THRESHOLD_SECONDS = 1.0
TRANSPORT_RETRY_DELAYS = (1.0, 2.0, 4.0)
RETRYABLE_ERROR_NAMES = frozenset(
    {
        "ChunkedEncodingError",
        "ConnectTimeout",
        "ConnectionError",
        "ConnectionResetError",
        "FatalServerError",
        "MaxlagTimeoutError",
        "ProtocolError",
        "ReadTimeout",
        "Server504Error",
        "Timeout",
    }
)

_transport_wait_reporter: Callable[[str], None] | None = None


def set_transport_wait_reporter(reporter: Callable[[str], None] | None) -> None:
    global _transport_wait_reporter
    _transport_wait_reporter = reporter


def report_transport_wait(message: str, *, delay: float) -> None:
    logger = get_logger()
    logger.info("transport wait seconds=%.3f message=%s", delay, message)
    if delay < TRANSPORT_WAIT_REPORT_THRESHOLD_SECONDS:
        return
    if _transport_wait_reporter is not None:
        _transport_wait_reporter(message)


def is_retryable_transport_error(exc: Exception) -> bool:
    return any(name in RETRYABLE_ERROR_NAMES for name in _exception_names(exc))


def transport_retry_delay(attempt: int) -> float:
    index = max(0, min(attempt - 1, len(TRANSPORT_RETRY_DELAYS) - 1))
    return TRANSPORT_RETRY_DELAYS[index]


@contextmanager
def monitor_operation(
    ui,
    *,
    start_message: str,
    pending_message: str,
    heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    on_heartbeat: Callable[[float], None] | None = None,
):
    logger = get_logger()
    started = perf_counter()
    stop = Event()

    ui.info(start_message)
    logger.info("operation started message=%s", start_message)

    def heartbeat() -> None:
        while not stop.wait(heartbeat_interval):
            elapsed = perf_counter() - started
            if on_heartbeat is not None:
                on_heartbeat(elapsed)
            message = f"{pending_message} after {format_elapsed(elapsed)}"
            ui.warn(message)
            logger.warning("operation pending seconds=%.3f message=%s", elapsed, message)

    thread = Thread(target=heartbeat, name="biblio-operation-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=0.1)


def _exception_names(exc: Exception) -> set[str]:
    return {cls.__name__ for cls in type(exc).mro()}
