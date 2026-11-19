---
name: django-performance
description: Diagnose and improve Django ORM and request performance in SAARI when a measured bottleneck or query regression is in scope.
---

# Django performance
Trace the route through view, service, manager/model, template and consumers. Establish a reproducible baseline: representative data volume, query count, time, filters and database backend. Inspect queryset evaluation, N+1 access, pagination, aggregation and indexes in the real models. Prefer a focused change that preserves permissions, ordering and semantics. Use select_related/prefetch_related only for demonstrated relations; check memory and join fan-out. For write paths, review transaction cost and lock contention. Validate before/after with the same inputs and isolated test database; document query count/time and any remaining trade-off. Do not run load tests against production or add indexes without migration analysis.
