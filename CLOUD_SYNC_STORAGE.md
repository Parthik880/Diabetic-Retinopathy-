# Cloud Sync and PostgreSQL storage

## Delivery status

The desktop UI follows the supplied Cloud Sync mockup and retains the existing green/white theme. PostgreSQL repositories, Alembic migrations, legacy JSON import, live storage counts, contact actions and confirmed local cleanup are implemented. No ML model code or checkpoints were changed.

**Production connection is not configured.** The existing shared PostgreSQL Windows service was not modified. Its data directory is `C:\Program Files\PostgreSQL\16\data`, which the app now rejects because it is not RetinaGram-owned. The test cluster is not a production patient database.

## Exact local paths verified on this PC

| Purpose | Resolved path / status |
| --- | --- |
| PostgreSQL binaries | `C:\Program Files\PostgreSQL\16\bin` (`postgres.exe`, `pg_ctl.exe`, `psql.exe`) |
| PostgreSQL data used for isolated integration testing | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\postgres-qa` |
| Preferred production PostgreSQL data | `C:\ProgramData\RetinaGram\postgres-data` — not provisioned/configured |
| Supported per-user production alternative | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\postgres-data` — not provisioned/configured |
| Normal application runtime artifacts | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\runtime` (inference files under `runs`) |
| Normal Electron/backend logs | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\runtime\logs` |
| PostgreSQL QA server log | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\runtime\logs\postgres-qa.log` |
| Test runtime and screenshots | `C:\Users\ADMIN\Music\Diabetic-Retinopathy-\work\communication-qa-1789290123517` |
| Test backend log | `C:\Users\ADMIN\Music\Diabetic-Retinopathy-\work\communication-qa-1789290123517\backend.log` |
| Existing production legacy history (not altered during testing) | `C:\Users\ADMIN\AppData\Roaming\RetinaGram CPU\retinagram-history.json` |

The QA cluster was initially created under the project before the later storage-location requirement. It was stopped and **moved, not reinitialized**, into the app-owned location above. The normal app does not start, initialize, move or delete a PostgreSQL cluster. It connects to an existing local PostgreSQL service.

The QA server was stopped at handoff; its cluster/test data remain recoverable. A stop/start verification retained all 12 synthetic patient rows and the Alembic revision. Its trust-auth loopback configuration is for isolated testing only, not production. No production credentials were created.

`SHOW data_directory` is checked at startup and before Alembic upgrades. Only the exact app-owned cluster locations in `backend/db/session.py` are accepted, with a loopback database host. The PostgreSQL role must be permitted to inspect `data_directory` (for a restricted role, an administrator can grant the appropriate settings-read privilege). No credentials are returned to React or Electron IPC.

## Connection and migration setup

1. Have an administrator configure a dedicated local PostgreSQL database in one of the approved production cluster locations. Do not reinitialize the shared server or use an export folder.
2. Install the project's Python environment and updated `requirements-runtime.txt` using the existing setup procedure.
3. Copy `backend/.env.example` to `backend/.env` and enter `LOCAL_DATABASE_URL` locally. `DATABASE_URL` is a fallback alias. Alternatively, packaged installations can read `%APPDATA%\RetinaGram CPU\backend.env`. Process environment takes precedence.
4. Run `scripts\migrate-database.ps1`, or `.venv\Scripts\python.exe -m alembic upgrade head`, from the project.
5. Start the desktop app with `npm start`. PostgreSQL must already be running. No remote/cloud connection is required for screening.

If configuration, PostgreSQL, schema revision or storage-path validation fails, the app reports **Local patient database unavailable**. There is no fallback to another JSON store. Existing JSON is retained for recovery/migration. Full model-backed startup also still requires the project's original Python/model prerequisites.

## Schema and relationships

- `patients`: UUID, unique indexed patient code, demographics, optional phone/email, timestamps; existing clinical demographics are retained in a small JSONB field.
- `screening_sessions`: UUID, indexed patient FK, start/completion/status/notes/timestamps. Patient delete cascades to sessions.
- `eye_results`: UUID, indexed session FK and scan timestamp, unique `(session_id, eye)`, OS/OD constraint, run ID, quality/grade/confidence, original result JSONB, local artifact paths and separate cloud keys.
- `reports`: UUID, indexed session/eye FKs, report path/type, generation timestamp, SHA-256 and separate cloud key. Cascades with the associated session/eye.
- `sync_state`: UUID, unique entity type/UUID, indexed status constrained to LOCAL_ONLY/PENDING/SYNCED/FAILED/CONFLICT, last sync/remote ID/timestamp.
- `app_settings`: persisted sync preferences.
- `legacy_imports`: source path/hash/import timestamp for idempotent JSON migration.

`0001_local_storage` is the initial Alembic revision. Production does not call `create_all()`. The schema and models pass `alembic check`. Files remain on disk, not as image/PDF binaries in PostgreSQL.

## Legacy JSON migration

After PostgreSQL is reachable and Alembic is current, startup imports the configured legacy history and its adjacent `*-patients.json` registry if present. Each source gets a `.pre-postgres.bak` backup before conversion; originals are never deleted. The existing production JSON was not imported into the test database.

Valid UUID session IDs remain unchanged. Non-UUID legacy patient/session identifiers map deterministically to UUIDs; legacy IDs are retained separately. Run IDs, result JSON, report references and available timestamps are preserved. Missing contacts are accepted. Patient metadata is stored once and reused across sessions. Inline legacy captures are written as files, not image binaries in JSONB.

An advisory lock prevents concurrent migration. Imported rows and completion markers commit together. Failure rolls everything back. Restart skips completed sources. Markers remain after history deletion so retained legacy JSON cannot resurrect deleted records. Invalid legacy input stops migration for review instead of silently dropping records.

## APIs and Send Report

The existing `/api/history`, patient registration and report APIs remain available. The repository reconstructs the flat history response from relational records. Fresh empty sessions stay out of the scan-history list.

Analysis jobs persist eye results server-side when a session is supplied. OS and OD use the same session. PDF export checks the session/eye/run relationship and loads patient identity from PostgreSQL; exported PDFs receive report metadata rows. Saving both eyes also records each PDF.

Send Report retrieves patient details from `/api/patients/{id}` on opening and refreshes before Email/SMS/Call. Missing contacts disable the relevant action. Email first uses the existing PDF export/folder picker, then opens an encoded `mailto:` request and displays the exact PDF path for manual attachment. SMS copies a short message. Call requests `tel:` with a copy-number fallback. Main-process clipboard completion is awaited. Nothing claims delivery.

Electron exposes narrow structured communication, copy-text and open-data-folder actions. Sender/window/origin checks remain enforced. No arbitrary URL/path opener is exposed. `contextIsolation: true`, `nodeIntegration: false` and `sandbox: true` are retained.

## Cloud architecture and counts

No real provider or upload implementation is configured. `CLOUD_DATABASE_URL` is backend-only and optional; a URL alone does not imply connectivity. Connect Cloud reports that the provider is not configured. Sync now and automatic sync are disabled in that state. Patient/report preferences persist; retinal images default unchecked.

The provider boundary separates structured entity synchronization (cloud PostgreSQL) and file synchronization (object storage). UUID-based object keys use `patients/<patient_uuid>/sessions/<session_uuid>/OS|OD/<artifact>`. Cloud object keys are separate from local filesystem paths. A real provider must supply authentication, metadata/file transfer, conflict handling and idempotency. It must never publish local absolute paths or embedded path-bearing result JSON without transforming references. The current app does not perform fake uploads.

When `RETINA_CLOUD_SYNC_ENABLED=true`, entity writes mark relevant rows PENDING; otherwise LOCAL_ONLY. Provider acknowledgments alone can mark SYNCED. Failures mark FAILED; edits occurring during upload retain a pending revision. Remote deletion is never invoked by local cleanup. Automatic scheduling and a real provider are not enabled in this delivery.

Patients, sessions and reports are SQL COUNTs. Pending and unsynchronized counts query sync_state. Last sync uses its maximum recorded timestamp. Managed files are inspected in controlled runtime `runs`, `reports`, `exports`, `tmp` and `temp` folders without following escapes/junctions. Storage shown is their file sizes plus `pg_database_size(current_database())`. That database-size value includes database overhead, not just patient payloads. Arbitrary user-exported folders are neither counted nor scanned.

## Clear local history / independent file cleanup

Nothing is selected by default. The acknowledgement is mandatory; history also requires exact `DELETE`. Unsynchronized records produce the warning: “Some selected records have not been synchronized and may be permanently lost.”

**History deletion affects only rows in:** `patients`, cascading `screening_sessions`, `eye_results`, `reports`, and relevant patient/session/eye-result/report `sync_state` rows. All required SQL executes in one SQLAlchemy transaction. Any database failure rolls it back. `app_settings`, `legacy_imports`, `alembic_version`, tables, indexes, schema, database and PostgreSQL server remain intact.

**History-only deletion does not remove images or PDFs.** Temporary files, generated artifacts, managed PDFs and retinal images are independently selected categories. User-exported PDFs in arbitrary folders are never removed. Model weights, application assets, PostgreSQL files and unrelated application files are outside the inventory.

Selected managed files are staged into a controlled `.cleanup/<operation-id>` recovery directory before database mutation. SQL failure restores staged files. After commit, only those staged files are unlinked. A journal is retained for manual recovery after an OS/process crash; this is not a distributed transaction between PostgreSQL and the filesystem. Locked/unremovable files are reported as retained. Synced metadata/cloud keys remain when removing only local file caches.

The UI blocks cleanup during active analysis, refreshes counts and clears stale in-memory patient/scan state afterward. New registration works immediately after history deletion. The old reset script now uses this same service with explicit CLI categories and confirmation; it no longer recursively removes the app-data root.

**Normal Clear local history never deletes `postgres-data` (or `postgres-qa`), runs initdb, drops a database/schema, or recreates PostgreSQL.**

## Verification

- Frontend TypeScript check and production build: passed.
- Existing analysis workflow (6 cases) and history-grouping/session tests: passed.
- Contact normalization/optional validation, new-session retention and history metadata tests: passed.
- Structured Electron communication security tests (4): passed; forbidden URLs/header injection rejected, launch failure handled.
- Real PostgreSQL integration tests (7): passed. Includes persisted contacts, bilateral rows, report hash/counts, missing cloud/settings, migration/restart idempotency, failed migration rollback, temporary-only cleanup, history-only cleanup preserving files/tables/new registration, and actual PostgreSQL failure rolling back deletes/restoring files.
- Alembic upgrade/current/check: revision `0001_local_storage`; no model/schema drift.
- Actual QA PostgreSQL stop/start: the same 12 synthetic patient rows and Alembic revision survived, then the QA server was stopped. Production Windows service was left unchanged.
- Electron UI integration (20 checks): passed against real PostgreSQL/API and real PDF export. Registration, reload, contacts, SMS clipboard, email/call request/failure, old records, Cloud Sync counts/status, cleanup defaults and focus return verified; no renderer console errors.
- UI screenshot inspected at desktop resolution; design detector returned no findings.
- Actual ML inference was **not** verified: this Music copy lacks its project Python environment and grading/restoration checkpoints. UI inference output was explicitly synthetic. No model files were changed or substituted.
- Actual installed mail/calling applications were **not launched** by automated QA: OS handlers were mocked. Delivery remains the responsibility of the user's installed apps.
- No production patient history was deleted, migrated or overwritten during tests. Test records/files only were created/deleted in isolated storage.

## Files created

- `alembic.ini`, `backend/db/migrations/env.py`, `backend/db/migrations/versions/0001_local_storage.py`: production migrations.
- `backend/db/__init__.py`, `models.py`, `session.py`, `repository.py`: relational schema, safe configuration/path validation, compatibility repository and JSON migration.
- `backend/schemas/storage.py`: input validation separate from ORM models.
- `backend/services/sync_service.py`, `storage_service.py`: honest provider boundary, counts, independent transactional cleanup.
- `backend/.env.example`, `scripts/migrate-database.ps1`: local setup/configuration.
- `frontend/src/components/CloudSyncScreen.tsx`: mockup-based page and cleanup modal.
- `frontend/src/components/SendReportModal.tsx`, `frontend/src/contacts.ts`: communication dialog and contact validation.
- `desktop/communication.cjs`: safe structured external action construction.
- `backend/tests/test_postgres_storage.py`, `frontend/tests/contacts.test.ts`, `desktop/tests/communication.test.cjs`, `desktop/tests/communication-ui.cjs`, `desktop/tests/fixture_server.py`: isolated verification.
- `CLOUD_SYNC_STORAGE.md`: this handoff.

## Files changed

- `backend/app/main.py`: PostgreSQL-backed routes, persistence around analysis/export, safe errors and storage endpoints.
- `backend/app/jobs.py`: active-job guard for cleanup (no inference changes).
- `backend/app/history.py`, `backend/tests/test_history.py`: prior contact-registration work retained as legacy JSON compatibility/test code; not the active production store.
- `frontend/src/App.tsx`, `api.ts`, `types.ts`: load/register contacts from DB, sessions, navigation and cleanup-state reset.
- `frontend/src/components/AddPatientModal.tsx`: optional validated contacts and durable registration/error handling.
- `frontend/src/components/CaptureScreen.tsx`, `TopAppBar.tsx`: keep New Patient/New Session on Capture; add Cloud Sync and remove local-session timestamp.
- `frontend/src/components/ReportScreen.tsx`: Send Report entry point.
- `frontend/src/desktop.d.ts`, `desktop/main.cjs`, `desktop/preload.cjs`: narrow typed desktop bridge.
- `requirements-runtime.txt`, `requirements-lock.txt`, `RetinaGramBackend.spec`: requested SQLAlchemy/psycopg/Alembic dependencies and packaging imports.
- `scripts/reset_local_data.py`: replace recursive app-data destruction with confirmed repository cleanup.

No production cluster provisioning or password was invented. Configure the app-owned production connection before using this build for patient registration.
