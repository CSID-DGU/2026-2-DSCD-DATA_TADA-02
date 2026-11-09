import json
import logging
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
logger = logging.getLogger("data_tada")


def event(event_name: str, **fields):
    # No prompts, outputs, authorization headers or credentials in routine logs.
    logger.info(json.dumps({"event": event_name, "request_id": request_id_var.get(), **fields}, ensure_ascii=False))


@contextmanager
def span(name: str, **fields):
    start = time.perf_counter()
    status = "ok"
    try:
        yield
    except BaseException:
        status = "error"
        raise
    finally:
        event("span", name=name, elapsed_ms=round((time.perf_counter() - start) * 1000, 3), status=status, **fields)


class Metrics:
    """Bounded-label, per-process counters. External monitoring aggregates replicas."""

    BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120)

    def __init__(self):
        self.lock = Lock()
        self.started_at = time.time()
        self.counts = Counter()
        self.seconds = Counter()
        self.buckets = defaultdict(Counter)

    def record(self, method, route, status, duration):
        key = (method, route, str(status))
        with self.lock:
            self.counts[key] += 1
            self.seconds[key] += duration
            for boundary in self.BUCKETS:
                if duration <= boundary:
                    self.buckets[key][boundary] += 1

    def render(self):
        lines = ["# TYPE process_start_time_seconds gauge", f"process_start_time_seconds {self.started_at}",
                 "# TYPE process_uptime_seconds gauge", f"process_uptime_seconds {time.time() - self.started_at}",
                 "# TYPE process_cpu_seconds_total counter", f"process_cpu_seconds_total {time.process_time()}",
                 "# TYPE http_requests_total counter", "# TYPE http_request_duration_seconds histogram"]
        with self.lock:
            for (method, route, status), count in sorted(self.counts.items()):
                labels = f'method="{method}",route="{route}",status="{status}"'
                key = method, route, status
                lines.append(f"http_requests_total{{{labels}}} {count}")
                for boundary in self.BUCKETS:
                    lines.append(f'http_request_duration_seconds_bucket{{{labels},le="{boundary}"}} {self.buckets[key][boundary]}')
                lines.extend([
                    f'http_request_duration_seconds_bucket{{{labels},le="+Inf"}} {count}',
                    f"http_request_duration_seconds_count{{{labels}}} {count}",
                    f"http_request_duration_seconds_sum{{{labels}}} {self.seconds[key]}",
                ])
        return "\n".join(lines) + "\n"
