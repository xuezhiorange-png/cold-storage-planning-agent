"""Behavioral contract tests for B01, B02, B03.

These tests exercise REAL behaviour that the current implementation does NOT
provide.  Every test in this file MUST FAIL on the current codebase:

* B01 – StructuredLoggingMiddleware does not call metrics.record_http_request().
* B02 – record_outbox_delivery_attempt / record_outbox_delivery_failure /
        record_configuration_validation_failure / record_redaction_bypass_detected
        accept arbitrary label values without bounds checking.
* B03 – _JSONFormatter copies extra fields via log_record[key] = value
        without recursive redaction of nested secrets.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry
from starlette.responses import PlainTextResponse

from cold_storage.bootstrap.configuration_redactor import EmitPoint, SecretType
from cold_storage.bootstrap.logging import _JSONFormatter
from cold_storage.bootstrap.metrics.registry import ObservableMetrics
from cold_storage.bootstrap.middleware.structured_logging import (
    StructuredLoggingMiddleware,
)
from cold_storage.bootstrap.observability.failure_classes import (
    ALERTABLE_FAILURE_CLASSES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_metrics() -> ObservableMetrics:
    """Return an ObservableMetrics with its own isolated CollectorRegistry."""
    return ObservableMetrics(registry=CollectorRegistry())


def _make_app() -> FastAPI:
    """Return a minimal FastAPI app with /health/live and /boom routes."""
    app = FastAPI()

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def health_ready() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("intentional crash")

    return app


def _exposition(metrics: ObservableMetrics) -> str:
    """Return the Prometheus text exposition for the given metrics."""
    return metrics.collect()


def _counter_value(
    metrics: ObservableMetrics,
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> float:
    """Read a counter's value from the exposition output.

    Handles the prometheus_client ``_total`` suffix convention:
    a counter named ``foo`` appears as ``foo_total`` in exposition,
    while ``foo_total`` appears as ``foo_total`` (no double suffix).
    """
    exposition = _exposition(metrics)

    # Try the raw name first, then name + "_total" (prometheus convention)
    candidates = [metric_name]
    if not metric_name.endswith("_total"):
        candidates.append(metric_name + "_total")

    for name in candidates:
        if labels:
            # Build label matchers: key="val" pairs, sorted for consistency
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            pattern = rf"^{re.escape(name)}\{{{re.escape(label_str)}\}}\s+(\d+\.?\d*)"
        else:
            pattern = rf"^{re.escape(name)}\s+(\d+\.?\d*)"

        for line in exposition.splitlines():
            m = re.match(pattern, line)
            if m:
                return float(m.group(1))

    return 0.0


def _histogram_count(
    metrics: ObservableMetrics,
    metric_name: str,
    labels: dict[str, str] | None = None,
) -> float:
    """Read a histogram's _count from the exposition output."""
    exposition = _exposition(metrics)

    candidates = [metric_name]
    if not metric_name.endswith("_total"):
        candidates.append(metric_name + "_total")

    for name in candidates:
        count_metric = name + "_count"
        if labels:
            label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            pattern = rf"^{re.escape(count_metric)}\{{{re.escape(label_str)}\}}\s+(\d+\.?\d*)"
        else:
            pattern = rf"^{re.escape(count_metric)}\s+(\d+\.?\d*)"

        for line in exposition.splitlines():
            m = re.match(pattern, line)
            if m:
                return float(m.group(1))

    return 0.0


# ===========================================================================
# TEST GROUP 1 – HTTP Counter Increment (B01)
# ===========================================================================


class TestB01HttpCounterIncrement:
    """StructuredLoggingMiddleware MUST record HTTP metrics after each request."""

    @pytest.mark.anyio
    async def test_http_requests_total_incremented(self) -> None:
        """After a successful GET /health/live the http_requests_total counter
        for method=GET path=/health/live status=200 must increment by 1."""
        metrics = _fresh_metrics()
        metrics.register_route_template("/health/live")

        app = _make_app()
        middleware = StructuredLoggingMiddleware(app, metrics=metrics)  # type: ignore[call-arg]

        before = _counter_value(
            metrics,
            "http_requests_total",
            labels={"method": "GET", "path": "/health/live", "status": "200"},
        )

        transport = httpx.ASGITransport(app=middleware)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/health/live")
        assert resp.status_code == 200

        after = _counter_value(
            metrics,
            "http_requests_total",
            labels={"method": "GET", "path": "/health/live", "status": "200"},
        )
        assert after == before + 1, (
            f"http_requests_total did not increment: before={before}, after={after}"
        )

    @pytest.mark.anyio
    async def test_histogram_count_incremented(self) -> None:
        """After a successful request the http_request_duration_seconds
        histogram count for the route must increment by 1."""
        metrics = _fresh_metrics()
        metrics.register_route_template("/health/live")

        app = _make_app()
        middleware = StructuredLoggingMiddleware(app, metrics=metrics)  # type: ignore[call-arg]

        transport = httpx.ASGITransport(app=middleware)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            await client.get("/health/live")

        count = _histogram_count(
            metrics,
            "http_request_duration_seconds",
            labels={"method": "GET", "path": "/health/live", "status": "200"},
        )
        assert count >= 1, f"http_request_duration_seconds count is {count}, expected >= 1"

    @pytest.mark.anyio
    async def test_404_raw_path_not_in_exposition(self) -> None:
        """A 404 hit on an unregistered path must NOT introduce a raw URL
        path into the Prometheus exposition output."""
        metrics = _fresh_metrics()
        metrics.register_route_template("/health/live")

        app = _make_app()
        middleware = StructuredLoggingMiddleware(app, metrics=metrics)  # type: ignore[call-arg]

        transport = httpx.ASGITransport(app=middleware)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/nonexistent/deeply/nested/path")
        assert resp.status_code == 404

        exposition = _exposition(metrics)
        assert "/nonexistent/deeply/nested/path" not in exposition, (
            "Raw 404 path leaked into Prometheus exposition"
        )

    @pytest.mark.anyio
    async def test_metrics_endpoint_not_self_recorded(self) -> None:
        """Requests to the /metrics endpoint itself must NOT appear in
        http_requests_total (self-scrape must not pollute counters)."""
        metrics = _fresh_metrics()
        metrics.register_route_template("/health/live")
        metrics.register_route_template("/metrics")

        app = _make_app()

        @app.get("/metrics")
        async def metrics_endpoint() -> PlainTextResponse:
            return PlainTextResponse(metrics.collect(), media_type="text/plain")

        middleware = StructuredLoggingMiddleware(app, metrics=metrics)  # type: ignore[call-arg]

        transport = httpx.ASGITransport(app=middleware)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 200

        # The /metrics request itself must NOT be counted
        exposition = _exposition(metrics)
        metrics_lines = [
            line
            for line in exposition.splitlines()
            if "http_requests_total" in line and 'path="/metrics"' in line
        ]
        assert len(metrics_lines) == 0, (
            f"/metrics self-request leaked into http_requests_total: {metrics_lines}"
        )

    @pytest.mark.anyio
    async def test_exception_route_records_500(self) -> None:
        """An exception in the app must record status=500 in http_requests_total."""
        metrics = _fresh_metrics()
        metrics.register_route_template("/boom")

        app = _make_app()
        middleware = StructuredLoggingMiddleware(app, metrics=metrics)  # type: ignore[call-arg]

        transport = httpx.ASGITransport(app=middleware)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            with contextlib.suppress(Exception):
                await client.get("/boom")
        # The middleware re-raises; httpx may raise or return 500.
        # Either way the counter must record 500.

        after = _counter_value(
            metrics,
            "http_requests_total",
            labels={"method": "GET", "path": "/boom", "status": "500"},
        )
        assert after >= 1, f"Expected http_requests_total status=500 >= 1, got {after}"


# ===========================================================================
# TEST GROUP 2 – Label Bounds (B02)
# ===========================================================================


class TestB02LabelBounds:
    """Unregistered / high-cardinality label values MUST be rejected and
    HIGH_CARDINALITY_LABEL_REJECTED incremented."""

    # --- record_outbox_delivery_attempt -----------------------------------

    def test_outbox_delivery_attempt_rejects_high_attempt_number(self) -> None:
        """attempt_number=999999 must be rejected as high cardinality."""
        metrics = _fresh_metrics()
        metrics.register_queue("audit_events")

        before = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "outbox_delivery_attempts_total"},
        )

        metrics.record_outbox_delivery_attempt(queue="audit_events", attempt_number=999999)

        after = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "outbox_delivery_attempts_total"},
        )
        assert after > before, (
            "HIGH_CARDINALITY_LABEL_REJECTED was not incremented for attempt_number=999999"
        )

        # The raw attempt value must NOT appear in exposition
        exposition = _exposition(metrics)
        assert "999999" not in exposition, (
            "Raw attempt_number=999999 leaked into Prometheus exposition"
        )

    def test_outbox_delivery_attempt_valid_value_passes(self) -> None:
        """A valid small attempt_number must be accepted."""
        metrics = _fresh_metrics()
        metrics.register_queue("audit_events")

        metrics.record_outbox_delivery_attempt(queue="audit_events", attempt_number=1)

        after = _counter_value(
            metrics,
            "outbox_delivery_attempts_total",
            labels={"queue": "audit_events", "attempt": "1"},
        )
        assert after == 1, f"Valid attempt_number=1 was not recorded, got {after}"

    # --- record_outbox_delivery_failure -----------------------------------

    def test_outbox_delivery_failure_rejects_unregistered_class(self) -> None:
        """failure_class="user-controlled-class" must be rejected."""
        metrics = _fresh_metrics()
        metrics.register_queue("audit_events")

        before = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "outbox_delivery_failures_total"},
        )

        metrics.record_outbox_delivery_failure(
            queue="audit_events", failure_class="user-controlled-class"
        )

        after = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "outbox_delivery_failures_total"},
        )
        assert after > before, (
            "HIGH_CARDINALITY_LABEL_REJECTED was not incremented for "
            "failure_class='user-controlled-class'"
        )

        exposition = _exposition(metrics)
        assert "user-controlled-class" not in exposition, (
            "Raw failure_class='user-controlled-class' leaked into exposition"
        )

    def test_outbox_delivery_failure_valid_class_passes(self) -> None:
        """A valid alertable failure class must be accepted."""
        metrics = _fresh_metrics()
        metrics.register_queue("audit_events")

        valid_class = next(iter(ALERTABLE_FAILURE_CLASSES))
        metrics.record_outbox_delivery_failure(queue="audit_events", failure_class=valid_class)

        after = _counter_value(
            metrics,
            "outbox_delivery_failures_total",
            labels={"queue": "audit_events", "class": valid_class},
        )
        assert after == 1, f"Valid failure_class={valid_class!r} was not recorded, got {after}"

    # --- record_configuration_validation_failure --------------------------

    def test_config_validation_failure_rejects_arbitrary_class(self) -> None:
        """failure_class="arbitrary-config-error" must be rejected."""
        metrics = _fresh_metrics()

        before = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "configuration_validation_failures_total"},
        )

        metrics.record_configuration_validation_failure(failure_class="arbitrary-config-error")

        after = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "configuration_validation_failures_total"},
        )
        assert after > before, (
            "HIGH_CARDINALITY_LABEL_REJECTED was not incremented for "
            "failure_class='arbitrary-config-error'"
        )

        exposition = _exposition(metrics)
        assert "arbitrary-config-error" not in exposition, (
            "Raw failure_class='arbitrary-config-error' leaked into exposition"
        )

    def test_config_validation_failure_valid_class_passes(self) -> None:
        """A valid alertable failure class must be accepted."""
        metrics = _fresh_metrics()

        valid_class = "DATABASE_UNREACHABLE"
        metrics.record_configuration_validation_failure(failure_class=valid_class)

        after = _counter_value(
            metrics,
            "configuration_validation_failures_total",
            labels={"class": valid_class},
        )
        assert after == 1, f"Valid failure_class={valid_class!r} was not recorded, got {after}"

    # --- record_redaction_bypass_detected ---------------------------------

    def test_redaction_bypass_rejects_arbitrary_secret_type(self) -> None:
        """secret_type="raw-secret-value" must be rejected."""
        metrics = _fresh_metrics()

        before = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "REDACTION_BYPASS_DETECTED"},
        )

        metrics.record_redaction_bypass_detected(secret_type="raw-secret-value", emit_point="LOG")

        after = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "REDACTION_BYPASS_DETECTED"},
        )
        assert after > before, (
            "HIGH_CARDINALITY_LABEL_REJECTED was not incremented for secret_type='raw-secret-value'"
        )

        exposition = _exposition(metrics)
        assert "raw-secret-value" not in exposition, (
            "Raw secret_type='raw-secret-value' leaked into exposition"
        )

    def test_redaction_bypass_rejects_arbitrary_emit_point(self) -> None:
        """emit_point="dynamic-destination" must be rejected."""
        metrics = _fresh_metrics()

        before = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "REDACTION_BYPASS_DETECTED"},
        )

        metrics.record_redaction_bypass_detected(
            secret_type="TOKEN", emit_point="dynamic-destination"
        )

        after = _counter_value(
            metrics,
            "HIGH_CARDINALITY_LABEL_REJECTED",
            labels={"metric_name": "REDACTION_BYPASS_DETECTED"},
        )
        assert after > before, (
            "HIGH_CARDINALITY_LABEL_REJECTED was not incremented for "
            "emit_point='dynamic-destination'"
        )

        exposition = _exposition(metrics)
        assert "dynamic-destination" not in exposition, (
            "Raw emit_point='dynamic-destination' leaked into exposition"
        )

    def test_redaction_bypass_valid_values_pass(self) -> None:
        """Valid SecretType + EmitPoint enum values must be accepted."""
        metrics = _fresh_metrics()

        metrics.record_redaction_bypass_detected(
            secret_type=SecretType.TOKEN,
            emit_point=EmitPoint.LOG,
        )

        after = _counter_value(
            metrics,
            "REDACTION_BYPASS_DETECTED",
            labels={"secret_type": SecretType.TOKEN, "emit_point": EmitPoint.LOG},
        )
        assert after == 1, f"Valid redaction bypass was not recorded, got {after}"


# ===========================================================================
# TEST GROUP 3 – Recursive Extra Redaction (B03)
# ===========================================================================


class TestB03RecursiveExtraRedaction:
    """Extra fields attached to log records via extra={...} MUST be
    recursively redacted before appearing in the JSON output."""

    @staticmethod
    def _capture_log(
        message: str,
        extra: dict[str, Any] | None = None,
        level: int = logging.INFO,
    ) -> str:
        """Log a message through _JSONFormatter and return the JSON output."""
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(_JSONFormatter())

        logger_name = f"test.redaction.{id(extra)}"
        test_logger = logging.getLogger(logger_name)
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(handler)
        try:
            test_logger.log(level, message, extra=extra or {})
        finally:
            test_logger.removeHandler(handler)
        return stream.getvalue()

    def test_nested_dict_authorization_redacted(self) -> None:
        """Nested dict with authorization key must be redacted."""
        output = self._capture_log(
            "event",
            extra={
                "payload": {
                    "authorization": "Bearer VERY_SECRET_TOKEN",
                    "items": [{"password": "secret-password"}],
                },
            },
        )
        assert "VERY_SECRET_TOKEN" not in output, (
            "Nested secret 'VERY_SECRET_TOKEN' was not redacted in log output"
        )
        assert "secret-password" not in output, (
            "Nested secret 'secret-password' was not redacted in log output"
        )

    def test_nested_dict_token_redacted(self) -> None:
        """Nested dict with token key must be redacted."""
        output = self._capture_log(
            "event",
            extra={
                "config": {
                    "token": "sk-live-abcdef1234567890",
                },
            },
        )
        assert "sk-live-abcdef1234567890" not in output, (
            "Nested token value was not redacted in log output"
        )

    def test_deeply_nested_password_redacted(self) -> None:
        """Passwords in deeply nested structures must be redacted."""
        output = self._capture_log(
            "event",
            extra={
                "level1": {
                    "level2": {
                        "level3": {
                            "password": "deeply-nested-secret-value",
                        },
                    },
                },
            },
        )
        assert "deeply-nested-secret-value" not in output, (
            "Deeply nested password was not redacted in log output"
        )

    def test_object_str_with_secret_redacted(self) -> None:
        """An object whose __str__ returns 'token=OBJECT_SECRET'
        must have the secret redacted in log output."""

        class SneakyObject:
            def __str__(self) -> str:
                return "token=OBJECT_SECRET"

        output = self._capture_log(
            "event",
            extra={"sneaky": SneakyObject()},
        )
        assert "OBJECT_SECRET" not in output, (
            "Secret from object.__str__() was not redacted in log output"
        )

    def test_object_str_raises_shows_redaction_failed(self) -> None:
        """An object whose __str__ raises must produce <REDACTION_FAILED>
        in the log output (fail-closed)."""

        class BrokenObject:
            def __str__(self) -> str:
                raise ValueError("cannot stringify")

        output = self._capture_log(
            "event",
            extra={"broken": BrokenObject()},
        )
        # The formatter should either show <REDACTION_FAILED> or handle
        # the error gracefully — the raw exception must not leak secrets.
        # For fail-closed: we expect <REDACTION_FAILED> or similar marker.
        assert "<REDACTION_FAILED>" in output or "REDACTION_FAILED" in output, (
            "Object.__str__() raised but <REDACTION_FAILED> not found in output; "
            f"output was: {output!r}"
        )

    def test_list_of_dicts_with_secrets_redacted(self) -> None:
        """A list containing dicts with secrets must be recursively redacted."""
        output = self._capture_log(
            "event",
            extra={
                "users": [
                    {"name": "alice", "password": "alice-secret"},
                    {"name": "bob", "api_key": "bob-api-key-12345"},
                ],
            },
        )
        assert "alice-secret" not in output, "Secret in list-of-dicts was not redacted"
        assert "bob-api-key-12345" not in output, "API key in list-of-dicts was not redacted"
