# ADR-009 Application Lifecycle and Dependency Injection

- Status: Accepted
- Context: The project previously created database engines and services at import time, causing test isolation issues and environment coupling.
- Decision:
  - No import-time resource creation (engines, sessions, services)
  - FastAPI lifespan manages engine creation on startup and disposal on shutdown
  - Dependencies provided via FastAPI `Depends()` with override support for tests
  - Pure stateless calculators (`CalculationService`, `ColdRoomZonePlanner`, `InvestmentEstimator`) are created in the app factory and remain safe as-is
  - Planning orchestration extracted from `bootstrap/app.py` to `modules/planning/application/service.py`
- Alternatives: Keep import-time initialization with monkeypatch overrides in tests.
- Consequences: Tests can inject mock/temporary engines. CI can use different database URLs per test type.
