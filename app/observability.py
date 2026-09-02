"""Structured logs, optional Prometheus metrics, optional OpenTelemetry spans."""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from contextlib import contextmanager
from threading import Lock

from . import config, request_context


_configured = False
_lock = Lock()
_http_requests: dict[tuple[str, str], int] = defaultdict(int)
_job_claims = 0


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = request_context.current()
        record.request_id = context.request_id or "-"
        record.path = context.path or "-"
        record.method = context.method or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "method": getattr(record, "method", "-"),
            "path": getattr(record, "path", "-"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def reset_for_tests() -> None:
    """Drop handlers and counters so a test can reconfigure logging in isolation."""
    global _configured, _job_claims
    _configured = False
    _job_claims = 0
    _http_requests.clear()
    logging.getLogger().handlers.clear()


def configure() -> None:
    """Idempotent. JSON logs in production; plain text stays readable in development."""
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    if config.JSON_LOGS:
        handler.setFormatter(JsonFormatter())
        _configure_structlog()
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(request_id)s %(message)s"))
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(logging.INFO)
    else:
        root.addHandler(handler)
    logging.getLogger("bidproof").setLevel(logging.INFO)
    _configured = True


def _configure_structlog() -> None:
    try:
        import structlog
    except ImportError:
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
    )


def bind_log_context() -> None:
    context = request_context.current()
    try:
        import structlog

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=context.request_id or "-",
            method=context.method or "-",
            path=context.path or "-",
        )
    except ImportError:
        return


def record_http(method: str, status_code: int) -> None:
    with _lock:
        _http_requests[(method.upper(), str(status_code))] += 1


def record_job_claim() -> None:
    global _job_claims
    with _lock:
        _job_claims += 1


def prometheus_text() -> str:
    from .repositories import jobs

    lines = [
        "# HELP bidproof_http_requests_total HTTP requests by method and status",
        "# TYPE bidproof_http_requests_total counter",
    ]
    with _lock:
        for (method, code), count in sorted(_http_requests.items()):
            lines.append(f'bidproof_http_requests_total{{method="{method}",code="{code}"}} {count}')
        claims = _job_claims
    lines.extend(
        [
            "# HELP bidproof_job_claims_total Jobs claimed by this process",
            "# TYPE bidproof_job_claims_total counter",
            f"bidproof_job_claims_total {claims}",
            "# HELP bidproof_jobs Jobs currently stored, by status",
            "# TYPE bidproof_jobs gauge",
        ]
    )
    for status, count in sorted(jobs.status_counts().items()):
        lines.append(f'bidproof_jobs{{status="{status}"}} {count}')
    return "\n".join(lines) + "\n"


@contextmanager
def trace_span(name: str):
    """No-op unless BIDPROOF_OTEL=1 and OpenTelemetry is installed."""
    if not config.OTEL_ENABLED:
        yield
        return
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("bidproof")
        with tracer.start_as_current_span(name):
            yield
    except ImportError:
        yield
