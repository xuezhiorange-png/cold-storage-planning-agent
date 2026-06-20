# ADR-005 Model Gateway

- Status: Accepted
- Context: V1 must work without a real model API key and tests must not call external APIs.
- Decision: Define `ModelGateway` and `EmbeddingGateway` contracts with fake default adapters.
- Alternatives: Direct SDK calls from Agent services.
- Consequences: Provider swaps are isolated and tests remain deterministic.
