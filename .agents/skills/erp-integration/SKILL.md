---
name: erp-integration
description: Trace and validate SAARI cross-module contracts when a change affects more than one ERP app.
---

# ERP integration
Begin at the concrete URL or service entry point and map producers, consumers, models, signals, permissions, notifications and reports. Check existing touchpoints such as compras/services/integracao_planejamento.py, planejamento/services/cronograma_suprimentos/painel.py and financeiro/services/integracoes.py only if relevant. Record identifiers, statuses, units, timestamps and ownership from code; do not infer a full business workflow from directory names. Define input/output and failure behavior before edits. Preserve transaction boundaries, idempotency on retries/imports and authorization across app boundaries. Validate a focused end-to-end scenario in an isolated environment plus regression cases in each affected module. Coordinate file ownership to avoid concurrent edits.
