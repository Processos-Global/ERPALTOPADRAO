---
name: saari-design-system
description: Extend SAARI Django templates and CSS consistently across light/dark themes and existing module UI.
---

# SAARI design system
Inspect the actual template inheritance from templates/layouts/base.html and relevant module template, includes in templates/components/, static/css/base.css, static/css/ui.css and page styles. Identify effective tokens, typography, spacing, navigation and theme switches from the cascade rather than assuming one file is authoritative. Reuse current components and Bootstrap APIs only after checking their loaded version. Keep semantic HTML, keyboard focus, contrast, responsive behavior and clear empty/error states. Preserve escaping, form errors and CSRF. Validate representative pages in both themes and narrow/wide viewports; verify no unrelated module changed visually. Do not introduce a new UI framework or invent product behavior.
