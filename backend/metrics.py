"""Prometheus collectors and timing for the interpretation pipeline."""

import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

LLM_LATENCY = Histogram(
    "llm_request_duration_seconds",
    "Time spent waiting on a successful upstream LLM response.",
    buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 25, 40),
)

LLM_OUTCOMES = ("success", "timeout", "http_error", "invalid_response")
LLM_REQUESTS = Counter(
    "llm_requests",
    "Upstream LLM calls, by outcome.",
    ["outcome"],
)
# Export every outcome at 0 so dashboards and alerts see the series before the first failure.
for outcome in LLM_OUTCOMES:
    LLM_REQUESTS.labels(outcome=outcome)


STAGES = ("input_check", "local_match", "upstream_request", "response_parse", "latex_repair")
STAGE_DURATION = Histogram(
    "interpret_stage_duration_seconds",
    "Elapsed wall time for each interpretation stage, including failed attempts.",
    ["stage", "outcome"],
    buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 25, 40, 60),
)
STAGE_RUNS = Counter(
    "interpret_stage_runs_total",
    "Completed interpretation stage attempts, by outcome.",
    ["stage", "outcome"],
)
for stage in STAGES:
    for outcome in ("success", "error"):
        STAGE_DURATION.labels(stage=stage, outcome=outcome)
        STAGE_RUNS.labels(stage=stage, outcome=outcome)


@contextmanager
def time_stage(stage: str):
    """Time a stage across awaits, recording exceptions before propagating them."""
    if stage not in STAGES:
        raise ValueError(f"Unknown processing stage: {stage}")
    started = time.perf_counter()
    outcome = "error"
    try:
        yield
        outcome = "success"
    finally:
        STAGE_DURATION.labels(stage=stage, outcome=outcome).observe(time.perf_counter() - started)
        STAGE_RUNS.labels(stage=stage, outcome=outcome).inc()


def stage_snapshot():
    """Read cumulative seconds from the same histograms exported to Prometheus."""
    values = {stage: {"stage": stage, "total_seconds": 0.0, "attempts": 0, "errors": 0} for stage in STAGES}
    for family in STAGE_DURATION.collect():
        for sample in family.samples:
            row = values[sample.labels["stage"]]
            if sample.name.endswith("_sum"):
                row["total_seconds"] += sample.value
            elif sample.name.endswith("_count"):
                row["attempts"] += int(sample.value)
                if sample.labels["outcome"] == "error":
                    row["errors"] += int(sample.value)
    return [{**row, "average_seconds": row["total_seconds"] / row["attempts"] if row["attempts"] else None}
            for row in values.values()]
