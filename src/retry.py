import time
from typing import Callable, TypeVar

T = TypeVar("T")


RETRYABLE_MARKERS = (
    "lost connection",
    "gone away",
    "connection reset",
    "could not connect",
    "can't connect",
    "cannot connect",
    "timeout",
    "timed out",
    "server closed the connection",
    "connection refused",
    "actively refused",
    "10061",
    "temporarily unavailable",
    "too many connections",
)


def is_retryable(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in RETRYABLE_MARKERS)


def retry_call(
    func: Callable[[], T],
    retries: int = 3,
    backoff_seconds: float = 0.5,
    logger=None,
    what: str = "operation",
) -> T:
    attempts = max(1, retries)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001 - 需要按文本判断网络类错误
            last_exc = exc
            if attempt >= attempts or not is_retryable(exc):
                raise
            delay = backoff_seconds * (2 ** (attempt - 1))
            if logger:
                logger.warning(
                    "%s 失败，第 %s/%s 次，%.1fs 后重试: %s",
                    what,
                    attempt,
                    attempts,
                    delay,
                    exc,
                )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
