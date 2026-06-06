"""Operations / control dashboard (DASH-1).

Server-rendered FastAPI + HTMX/Jinja dashboard mounted on cloud/app.py.
Monitor pipeline state + safely re-drive idempotent stages, with HTTP Basic
auth and an audit trail. See docs/superpowers/specs/2026-06-06-pipeline-dashboard-dash1-design.md.

NOTE: do not import submodules (router/auth/…) here — Tasks' tests import
submodules directly, and a top-level re-export would force the whole package
to import at once. App wiring uses `from cloud.dashboard import router`.
"""
from __future__ import annotations
