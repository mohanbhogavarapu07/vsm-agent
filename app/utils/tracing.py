"""
VSM AI Agent – Tracing Utility (PRD 3 §13)

Structured observability for every AI decision cycle.
Logs decision metadata in a machine-parseable format.
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

logger = logging.getLogger("vsm.agent.trace")


class DecisionTrace:
    """
    Captures a full decision cycle timeline with structured fields.
    Used for observability, debugging, and accuracy metrics.
    """

    def __init__(self, task_id: int, correlation_id: str) -> None:
        self.task_id = task_id
        self.correlation_id = correlation_id
        self.start_time = time.monotonic()
        self.start_ts = datetime.now(timezone.utc)
        self.node_timings: dict[str, float] = {}
        self.inputs: dict[str, Any] = {}
        self.outputs: dict[str, Any] = {}
        self.errors: list[str] = []

    def record_node(self, node_name: str, duration_ms: float) -> None:
        self.node_timings[node_name] = duration_ms

    def record_input(self, key: str, value: Any) -> None:
        self.inputs[key] = value

    def record_output(self, key: str, value: Any) -> None:
        self.outputs[key] = value

    def record_error(self, error: str) -> None:
        self.errors.append(error)

    def finalize(self) -> dict[str, Any]:
        elapsed_ms = (time.monotonic() - self.start_time) * 1000
        trace = {
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.start_ts.isoformat(),
            "total_duration_ms": round(elapsed_ms, 2),
            "node_timings_ms": self.node_timings,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "errors": self.errors,
        }
        logger.info("DECISION_TRACE: %s", json.dumps(trace, default=str))
        return trace


@contextmanager
def trace_node(trace: DecisionTrace, node_name: str) -> Generator[None, None, None]:
    """Context manager to time individual graph node execution."""
    start = time.monotonic()
    try:
        yield
    finally:
        elapsed_ms = (time.monotonic() - start) * 1000
        trace.record_node(node_name, round(elapsed_ms, 2))
