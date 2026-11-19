---
name: django-testing
description: Design and run focused Django tests for SAARI changes with verified isolated database settings.
---

# Django testing
Read config/settings.py, the relevant tests and any test-only settings before running commands. Confirm the selected Python environment and that the configured test database is isolated and disposable; default MySQL settings are not evidence of safety. Derive cases from actual code and user criteria: success, boundaries, missing data, permissions, object ownership and cross-module regressions. Use independent expected values for financial assertions. For file behavior use temporary storage and check access control. Run focused tests first, broaden only for a concrete risk. Record exact command, number of tests, failures, skipped cases and database configuration without revealing secrets. For documentation/configuration-only work, validate syntax and structure without starting Django or connecting to a database.
