"""ObservableMetrics: bounded-cardinality Prometheus metrics registry.

All label values are pre-registered via register_*() class methods.
Attempts to record with unregistered label values are rejected and
increment HIGH_CARDINALITY_LABEL_REJECTED.  No raw URL paths or
dynamic auto-enrollment are permitted.

16 metric families (bounded cardinality):
    process_uptime_seconds          Gauge
    http_requests_total             Counter
    http_request_duration_seconds   Histogram
    dependency_up                   Gauge
    outbox_backlog_total            Gauge
    outbox_lag_seconds              Gauge
    outbox_delivery_attempts_total  Counter
    outbox_delivery_failures_total  Counter
    outbox_poison_messages_total    Counter
    outbox_retry_exhaustion_total   Counter
    configuration_validation_failures_total  Counter
    REDACTION_BYPASS_DETECTED       Counter
    HIGH_CARDINALITY_LABEL_REJECTED Counter
    audit_chain_integrity_status    Gauge
    audit_log_write_seconds         Histogram
    agent_capability_status         Gauge
"""

from __future__ import annotations

import logging
import time

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounded cardinality caps
# ---------------------------------------------------------------------------
_MAX_ROUTES = 10
_MAX_DEPENDENCIES = 8
_MAX_QUEUES = 8
_MAX_CAPABILITIES = 8

# Allowed HTTP methods and status codes (no raw paths)
_ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_ALLOWED_STATUSES: frozenset[str] = frozenset(
    {
        "200",
        "201",
        "204",
        "301",
        "302",
        "400",
        "401",
        "403",
        "404",
        "409",
        "422",
        "500",
        "503",
    }
)

# Histogram buckets: .005 .01 .025 .05 .1 .25 .5 1 2.5 5 10
_HISTOGRAM_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class ObservableMetrics:
    """Centralised, bounded-cardinality Prometheus metrics.

    Usage::

        metrics = ObservableMetrics()
        metrics.register_route_template("/api/projects")
        metrics.register_dependency("postgresql")
        metrics.record_http_request("GET", "/api/projects", "200", 0.034)
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self._registry = registry or CollectorRegistry()

        # --- Registration sets (bounded) -----------------------------------
        self._routes: set[str] = set()
        self._dependencies: set[str] = set()
        self._queues: set[str] = set()
        self._capabilities: set[str] = set()

        # --- 1. process_uptime_seconds  (Gauge) ---------------------------
        self._start_time = time.monotonic()
        self.process_uptime_seconds = Gauge(
            "process_uptime_seconds",
            "Process uptime in seconds.",
            registry=self._registry,
        )

        # --- 2. http_requests_total  (Counter) ----------------------------
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests.",
            ["method", "path", "status"],
            registry=self._registry,
        )

        # --- 3. http_request_duration_seconds  (Histogram) ----------------
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds.",
            ["method", "path", "status"],
            buckets=_HISTOGRAM_BUCKETS,
            registry=self._registry,
        )

        # --- 4. dependency_up  (Gauge) ------------------------------------
        self.dependency_up = Gauge(
            "dependency_up",
            "Dependency health (1=up, 0=down).",
            ["dependency"],
            registry=self._registry,
        )

        # --- 5. outbox_backlog_total  (Gauge) ------------------------------
        self.outbox_backlog_total = Gauge(
            "outbox_backlog_total",
            "Number of events pending in the audit outbox.",
            ["queue"],
            registry=self._registry,
        )

        # --- 6. outbox_lag_seconds  (Gauge) --------------------------------
        self.outbox_lag_seconds = Gauge(
            "outbox_lag_seconds",
            "Age in seconds of the oldest undelivered outbox event.",
            ["queue"],
            registry=self._registry,
        )

        # --- 7. outbox_delivery_attempts_total  (Counter) -----------------
        self.outbox_delivery_attempts_total = Counter(
            "outbox_delivery_attempts_total",
            "Total outbox delivery attempts.",
            ["queue", "attempt"],
            registry=self._registry,
        )

        # --- 8. outbox_delivery_failures_total  (Counter) -----------------
        self.outbox_delivery_failures_total = Counter(
            "outbox_delivery_failures_total",
            "Total outbox delivery failures.",
            ["queue", "class"],
            registry=self._registry,
        )

        # --- 9. outbox_poison_messages_total  (Counter) -------------------
        self.outbox_poison_messages_total = Counter(
            "outbox_poison_messages_total",
            "Events that exceeded retry limits and entered poison state.",
            ["queue"],
            registry=self._registry,
        )

        # --- 10. outbox_retry_exhaustion_total  (Counter) -----------------
        self.outbox_retry_exhaustion_total = Counter(
            "outbox_retry_exhaustion_total",
            "Events whose retries have been exhausted.",
            ["queue"],
            registry=self._registry,
        )

        # --- 11. configuration_validation_failures_total  (Counter) --------
        self.configuration_validation_failures_total = Counter(
            "configuration_validation_failures_total",
            "Configuration validation failures.",
            ["class"],
            registry=self._registry,
        )

        # --- 12. REDACTION_BYPASS_DETECTED  (Counter) ---------------------
        self.REDACTION_BYPASS_DETECTED = Counter(
            "REDACTION_BYPASS_DETECTED",
            "Attempts to bypass configuration redaction.",
            ["secret_type", "emit_point"],
            registry=self._registry,
        )

        # --- 13. HIGH_CARDINALITY_LABEL_REJECTED  (Counter) ---------------
        self.HIGH_CARDINALITY_LABEL_REJECTED = Counter(
            "HIGH_CARDINALITY_LABEL_REJECTED",
            "Attempts to record metrics with unregistered label values.",
            ["metric_name"],
            registry=self._registry,
        )

        # --- 14. audit_chain_integrity_status  (Gauge) --------------------
        self.audit_chain_integrity_status = Gauge(
            "audit_chain_integrity_status",
            "Audit chain integrity (1=valid, 0=broken).",
            registry=self._registry,
        )

        # --- 15. audit_log_write_seconds  (Histogram) ---------------------
        self.audit_log_write_seconds = Histogram(
            "audit_log_write_seconds",
            "Latency of audit log write operations.",
            buckets=_HISTOGRAM_BUCKETS,
            registry=self._registry,
        )

        # --- 16. agent_capability_status  (Gauge) -------------------------
        self.agent_capability_status = Gauge(
            "agent_capability_status",
            "Agent capability availability (1=available, 0=unavailable).",
            ["capability"],
            registry=self._registry,
        )

    # ------------------------------------------------------------------
    # Registry property (for endpoint / text exposition)
    # ------------------------------------------------------------------
    @property
    def registry(self) -> CollectorRegistry:
        """Return the independent CollectorRegistry for exposition."""
        return self._registry

    # ------------------------------------------------------------------
    # Registration helpers — bounded cardinality gates
    # ------------------------------------------------------------------

    def register_route_template(self, template: str) -> None:
        """Register an allowed route template (max ``_MAX_ROUTES``).

        Raises ``ValueError`` when the cap is exceeded.
        """
        key = template.strip()
        if key in self._routes:
            return
        if len(self._routes) >= _MAX_ROUTES:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="http_requests_total",
            ).inc()
            raise ValueError(f"Route cap ({_MAX_ROUTES}) reached. Cannot register route: {key!r}")
        self._routes.add(key)
        logger.debug("Registered route template: %s", key)

    def register_dependency(self, name: str) -> None:
        """Register an allowed dependency name (max ``_MAX_DEPENDENCIES``).

        Raises ``ValueError`` when the cap is exceeded.
        """
        key = name.strip()
        if key in self._dependencies:
            return
        if len(self._dependencies) >= _MAX_DEPENDENCIES:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="dependency_up",
            ).inc()
            raise ValueError(
                f"Dependency cap ({_MAX_DEPENDENCIES}) reached. Cannot register dependency: {key!r}"
            )
        self._dependencies.add(key)
        logger.debug("Registered dependency: %s", key)

    def register_queue(self, name: str) -> None:
        """Register an allowed outbox queue name (max ``_MAX_QUEUES``).

        Raises ``ValueError`` when the cap is exceeded.
        """
        key = name.strip()
        if key in self._queues:
            return
        if len(self._queues) >= _MAX_QUEUES:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_backlog_total",
            ).inc()
            raise ValueError(f"Queue cap ({_MAX_QUEUES}) reached. Cannot register queue: {key!r}")
        self._queues.add(key)
        logger.debug("Registered queue: %s", key)

    def register_capability(self, name: str) -> None:
        """Register an allowed agent capability name (max ``_MAX_CAPABILITIES``).

        Raises ``ValueError`` when the cap is exceeded.
        """
        key = name.strip()
        if key in self._capabilities:
            return
        if len(self._capabilities) >= _MAX_CAPABILITIES:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="agent_capability_status",
            ).inc()
            raise ValueError(
                f"Capability cap ({_MAX_CAPABILITIES}) reached. Cannot register capability: {key!r}"
            )
        self._capabilities.add(key)
        logger.debug("Registered capability: %s", key)

    # ------------------------------------------------------------------
    # Recording helpers — validate then record
    # ------------------------------------------------------------------

    def _refresh_uptime(self) -> None:
        """Update the uptime gauge (monotonic)."""
        self.process_uptime_seconds.set(time.monotonic() - self._start_time)

    # --- HTTP -------------------------------------------------------------

    def record_http_request(
        self,
        method: str,
        path: str,
        status: str,
        duration_seconds: float,
    ) -> None:
        """Record an HTTP request.

        *method* must be one of GET/POST/PUT/PATCH/DELETE.
        *path* must have been registered via register_route_template.
        *status* must be an allowed HTTP status code string.
        """
        method = method.upper()
        if method not in _ALLOWED_METHODS:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="http_requests_total",
            ).inc()
            logger.warning("Rejected HTTP request metric: invalid method %r", method)
            return

        if path not in self._routes:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="http_requests_total",
            ).inc()
            logger.warning(
                "Rejected HTTP request metric: unregistered route %r",
                path,
            )
            return

        if status not in _ALLOWED_STATUSES:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="http_requests_total",
            ).inc()
            logger.warning("Rejected HTTP request metric: invalid status %r", status)
            return

        labels = {
            "method": method,
            "path": path,
            "status": status,
        }
        self.http_requests_total.labels(**labels).inc()
        self.http_request_duration_seconds.labels(**labels).observe(max(0.0, duration_seconds))

    # --- Dependency health ------------------------------------------------

    def record_dependency_health(self, dependency: str, is_up: bool) -> None:
        """Record dependency health.

        *dependency* must have been registered via register_dependency.
        """
        if dependency not in self._dependencies:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="dependency_up",
            ).inc()
            logger.warning(
                "Rejected dependency health metric: unregistered dependency %r",
                dependency,
            )
            return

        self.dependency_up.labels(dependency=dependency).set(1 if is_up else 0)

    # --- Outbox -----------------------------------------------------------

    def record_outbox_backlog(self, queue: str, count: int) -> None:
        """Set the outbox backlog gauge for *queue*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_backlog_total",
            ).inc()
            return
        self.outbox_backlog_total.labels(queue=queue).set(max(0, count))

    def record_outbox_lag(self, queue: str, lag_seconds: float) -> None:
        """Set the outbox lag gauge for *queue*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_lag_seconds",
            ).inc()
            return
        self.outbox_lag_seconds.labels(queue=queue).set(max(0.0, lag_seconds))

    def record_outbox_delivery_attempt(self, queue: str, attempt_number: int) -> None:
        """Increment delivery attempts counter for *queue* and *attempt_number*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_delivery_attempts_total",
            ).inc()
            return
        self.outbox_delivery_attempts_total.labels(queue=queue, attempt=str(attempt_number)).inc()

    def record_outbox_delivery_failure(self, queue: str, failure_class: str) -> None:
        """Increment delivery failures counter for *queue* and *failure_class*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_delivery_failures_total",
            ).inc()
            return
        self.outbox_delivery_failures_total.labels(queue=queue, **{"class": failure_class}).inc()

    def record_outbox_poison_message(self, queue: str) -> None:
        """Increment poison messages counter for *queue*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_poison_messages_total",
            ).inc()
            return
        self.outbox_poison_messages_total.labels(queue=queue).inc()

    def record_outbox_retry_exhaustion(self, queue: str) -> None:
        """Increment retry exhaustion counter for *queue*."""
        if queue not in self._queues:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="outbox_retry_exhaustion_total",
            ).inc()
            return
        self.outbox_retry_exhaustion_total.labels(queue=queue).inc()

    # --- Configuration ----------------------------------------------------

    def record_configuration_validation_failure(self, failure_class: str) -> None:
        """Increment configuration validation failures for *failure_class*."""
        self.configuration_validation_failures_total.labels(**{"class": failure_class}).inc()

    def record_redaction_bypass_detected(self, secret_type: str, emit_point: str) -> None:
        """Increment the redaction-bypass counter."""
        self.REDACTION_BYPASS_DETECTED.labels(secret_type=secret_type, emit_point=emit_point).inc()

    # --- Audit ------------------------------------------------------------

    def record_audit_chain_integrity(self, is_valid: bool) -> None:
        """Set audit chain integrity status (1=valid, 0=broken)."""
        self.audit_chain_integrity_status.set(1 if is_valid else 0)

    def record_audit_log_write(self, duration_seconds: float) -> None:
        """Observe audit log write latency."""
        self.audit_log_write_seconds.observe(max(0.0, duration_seconds))

    # --- Agent capabilities -----------------------------------------------

    def record_capability_status(self, capability: str, is_available: bool) -> None:
        """Set agent capability availability.

        *capability* must have been registered via register_capability.
        """
        if capability not in self._capabilities:
            self.HIGH_CARDINALITY_LABEL_REJECTED.labels(
                metric_name="agent_capability_status",
            ).inc()
            return
        self.agent_capability_status.labels(capability=capability).set(1 if is_available else 0)

    # --- Convenience: refresh uptime before collection --------------------

    def collect(self) -> str:
        """Refresh uptime and return prometheus text exposition format."""
        self._refresh_uptime()
        from prometheus_client import generate_latest

        raw: bytes = generate_latest(self._registry)
        return raw.decode("utf-8")


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_metrics_instance: ObservableMetrics | None = None


def get_metrics() -> ObservableMetrics:
    """Return the global ObservableMetrics singleton."""
    global _metrics_instance  # noqa: PLW0603
    if _metrics_instance is None:
        _metrics_instance = ObservableMetrics()
    return _metrics_instance
