---
name: django-migrations-safe
description: Plan and validate SAARI Django schema and data migrations when a demonstrated model change requires them.
---

# Safe Django migrations
Inspect the model definition, existing migration graph, table size assumptions and all readers/writers of affected fields. Explain why a schema change is necessary. Review nullability, defaults, unique constraints, foreign keys, precision and existing rows. Separate schema and data transformations when needed; make backfill bounded and rerunnable where possible. Assess reversibility and rollback limits explicitly. Generate and inspect migrations only in an isolated environment; run migration checks and a rehearsal on a disposable copy or test database with verified connection settings. Never apply to production, drop data, or run maintenance commands without explicit authorization. Report migration files, expected locks/downtime, data preservation checks and test results.
