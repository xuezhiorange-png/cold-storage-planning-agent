# ADR-006 Hybrid Knowledge Retrieval

- Status: Accepted
- Context: Knowledge answers must cite source metadata and support exact and semantic retrieval.
- Decision: Use PostgreSQL full-text retrieval plus pgvector-compatible embedding search.
- Alternatives: Vector-only retrieval or model-only answers.
- Consequences: Retrieval can respect document authority and validity metadata.
