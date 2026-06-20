# Technical Debt

| ID | Reason | Impact | Temporary Approach | Permanent Resolution | Module | Priority | Target Version | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TD-001 | V1 starts with demo coefficients | Calculations require professional review | Mark all demo coefficients unverified and requires_review | Replace with reviewed coefficient governance workflow | coefficients | High | V1.1 | Open |
| TD-002 | OCR intentionally omitted | Scanned PDFs cannot be searched | Mark scanned PDFs requires_ocr=true | Add approved OCR pipeline after privacy review | knowledge | Medium | V2 | Open |
| TD-003 | Some non-project modules still use in-memory baseline services | Scheme, knowledge, and report metadata are not fully durable yet | Keep deterministic behavior and explicit module boundaries | Add SQLAlchemy-backed repositories for schemes, knowledge documents, reports, and agent runs | schemes/knowledge/reports/planning_agent | High | V1.2 | Open |
| TD-004 | npm audit reports transitive dependency vulnerabilities after initial install | Security review required before production use | Do not run forced breaking upgrades during baseline implementation | Upgrade or replace affected packages with compatibility testing | frontend | High | V1.1 | Open |
