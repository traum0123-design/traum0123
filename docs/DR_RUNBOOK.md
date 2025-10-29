# Disaster Recovery Runbook

This runbook outlines backup and restore procedures and operational checks.

## Backups

SQLite (dev/stage):
- Set `DATABASE_URL=sqlite:///./payroll_portal/app.db`
- Create backup:
```
python scripts/backup_db.py
```
- Result is stored in `backups/app_YYYYmmddTHHMMSSZ.db`

PostgreSQL (production):
- Use `pg_dump` to export the database:
```
export DATABASE_URL=postgresql://user:pass@host:5432/db
pg_dump --no-owner --format=custom "$DATABASE_URL" > backups/backup_$(date -u +%Y%m%dT%H%M%SZ).dump
```
- Restore:
```
pg_restore --clean --no-owner -d "$DATABASE_URL" backups/backup_....dump
```

Point-in-Time Recovery (PITR):
- Enable WAL archiving on Postgres (`archive_mode=on`, `archive_command`).
- Continuous archiving to object storage (e.g., S3) with retention (e.g., 7–30 days).
- PITR steps:
  1. Stop app, restore base backup to a new instance.
  2. Configure `recovery.signal` (PG ≥12) and `recovery_target_time` (or LSN).
  3. Start postgres, verify recovery to the target timestamp.
  4. Point app to the recovered instance after sanity checks.

## Migrations

- Enforce Alembic on startup (`PAYROLL_ENFORCE_ALEMBIC=1`) and in CI.
- To apply pending migrations:
```
alembic upgrade head
```
- Preflight check: run `python scripts/verify_migrations.py` in CI and at startup (`PAYROLL_ENFORCE_ALEMBIC=1`).
- To rollback one revision (staging only):
```
alembic downgrade -1
```

## DR Drill

1. Take a fresh backup (see above).
2. Restore into a staging DB.
3. Run migrations to head (if needed): `alembic upgrade head`.
4. Smoke test:
   - `/api/healthz` returns ok
   - `/api/meta` returns version/build
   - Portal login and export work
5. Validate data samples (companies, payrolls, withholding).
6. Rollback rehearsal:
   - Apply a new dummy migration, then `alembic downgrade -1`, verify app health.
7. Blue/Green:
   - Bring up a green environment (new DB + app), point traffic via load balancer after health checks.

## Notes

- Application writes are idempotent when clients provide `Idempotency-Key`, reducing duplicate records after retries.
- Audit logs (optional) and request IDs help correlate issues during incident response.
- Enforce read-only rootfs and seccomp in container runtime, keep /tmp writable.
- Export links can be HMAC-signed/expiring when `EXPORT_HMAC_SECRET` is set.
