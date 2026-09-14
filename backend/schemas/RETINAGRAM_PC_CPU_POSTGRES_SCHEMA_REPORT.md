# RetinaGram PC-CPU PostgreSQL Schema Report

Source inspected: `Parthik880/Diabetic-Retinopathy-`, branch `pc-cpu`

Verified against:
- `backend/db/models.py`
- `backend/db/migrations/versions/0001_local_storage.py`

## Summary

The current `pc-cpu` schema defines **7 application tables**:

1. `patients`
2. `screening_sessions`
3. `eye_results`
4. `reports`
5. `sync_state`
6. `app_settings`
7. `legacy_imports`

An Alembic-managed PostgreSQL database will also normally contain the migration bookkeeping table `alembic_version`.

---

## 1. `patients`

Purpose: stores the core patient record and patient contact/clinical metadata.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `legacy_id` | VARCHAR(200) | Unique, nullable |
| `patient_code` | VARCHAR(100) | Required, unique, indexed |
| `name` | VARCHAR(200) | Required |
| `age` | INTEGER | Required, check `0 <= age <= 130` |
| `gender` | VARCHAR(20) | Required |
| `phone` | VARCHAR(20) | Nullable |
| `email` | VARCHAR(254) | Nullable |
| `clinical_metadata` | JSONB | Required |
| `created_at` | TIMESTAMPTZ | Required |
| `updated_at` | TIMESTAMPTZ | Required |

Indexes:
- `ix_patients_patient_code` — unique index on `patient_code`

Relationships:
- One patient → many `screening_sessions`

---

## 2. `screening_sessions`

Purpose: represents one screening/session associated with a patient.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `legacy_id` | VARCHAR(200) | Unique, nullable |
| `patient_id` | UUID | FK → `patients.id`, required, `ON DELETE CASCADE` |
| `started_at` | TIMESTAMPTZ | Required |
| `completed_at` | TIMESTAMPTZ | Nullable |
| `status` | VARCHAR(30) | Required |
| `notes` | TEXT | Required |
| `created_at` | TIMESTAMPTZ | Required |
| `updated_at` | TIMESTAMPTZ | Required |

Indexes:
- `ix_screening_sessions_patient_id`

Relationships:
- Many sessions → one patient
- One session → many eye results
- One session → many reports

Deleting a patient cascades to that patient's sessions.

---

## 3. `eye_results`

Purpose: stores per-eye analysis results for OS/OD, including model outputs and references to generated files.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `session_id` | UUID | FK → `screening_sessions.id`, required, `ON DELETE CASCADE` |
| `eye` | VARCHAR(2) | Required; only `OS` or `OD` |
| `run_id` | VARCHAR(200) | Nullable, indexed |
| `scan_datetime` | TIMESTAMPTZ | Nullable, indexed |
| `status` | VARCHAR(30) | Required |
| `image_quality` | VARCHAR(30) | Nullable |
| `dr_grade` | INTEGER | Nullable |
| `grade_label` | VARCHAR(200) | Nullable |
| `confidence` | FLOAT | Nullable |
| `result_json` | JSONB | Nullable |
| `original_image_path` | TEXT | Nullable |
| `restored_image_path` | TEXT | Nullable |
| `lesion_overlay_path` | TEXT | Nullable |
| `gradcam_path` | TEXT | Nullable |
| `cloud_object_keys` | JSONB | Required |
| `created_at` | TIMESTAMPTZ | Required |
| `updated_at` | TIMESTAMPTZ | Required |

Constraints:
- `one_result_per_eye`: unique (`session_id`, `eye`)
- `valid_eye`: eye must be `OS` or `OD`

Indexes:
- `ix_eye_results_session_id`
- `ix_eye_results_run_id`
- `ix_eye_results_scan_datetime`

Relationships:
- Many eye results → one screening session
- One eye result → zero or more reports

---

## 4. `reports`

Purpose: stores report metadata and the filesystem/cloud references for generated reports.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `session_id` | UUID | FK → `screening_sessions.id`, required, `ON DELETE CASCADE` |
| `eye_result_id` | UUID | FK → `eye_results.id`, nullable, `ON DELETE CASCADE` |
| `report_path` | TEXT | Nullable |
| `report_type` | VARCHAR(30) | Required |
| `generated_at` | TIMESTAMPTZ | Required |
| `checksum_sha256` | VARCHAR(64) | Nullable |
| `cloud_object_key` | TEXT | Nullable |
| `created_at` | TIMESTAMPTZ | Required |

Constraints:
- `unique_session_report_path`: unique (`session_id`, `report_path`)

Indexes:
- `ix_reports_session_id`
- `ix_reports_eye_result_id`

Relationships:
- Many reports → one screening session
- A report may optionally reference one eye result

---

## 5. `sync_state`

Purpose: tracks whether locally created entities have been synchronized with a future/remote cloud system.

| Column | Type | Constraints / Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `entity_type` | VARCHAR(30) | Required |
| `entity_id` | UUID | Required |
| `sync_status` | VARCHAR(20) | Required, indexed |
| `last_synced_at` | TIMESTAMPTZ | Nullable |
| `remote_id` | VARCHAR(200) | Nullable |
| `updated_at` | TIMESTAMPTZ | Required |

Allowed `sync_status` values:
- `LOCAL_ONLY`
- `PENDING`
- `SYNCED`
- `FAILED`
- `CONFLICT`

Constraints:
- `unique_sync_entity`: unique (`entity_type`, `entity_id`)
- `valid_sync_status`

Index:
- `ix_sync_state_sync_status`

Important note:
`entity_id` is not defined as a database-level foreign key because this table can track multiple entity types.

---

## 6. `app_settings`

Purpose: simple application-level key/value settings stored in PostgreSQL.

| Column | Type | Constraints / Notes |
|---|---|---|
| `key` | VARCHAR(100) | Primary key |
| `value` | JSONB | Required |

This is a general settings table and has no declared foreign keys.

---

## 7. `legacy_imports`

Purpose: records completed imports from the previous JSON/history storage so migration can be idempotent and not re-import the same source repeatedly.

| Column | Type | Constraints / Notes |
|---|---|---|
| `source` | TEXT | Primary key |
| `checksum_sha256` | VARCHAR(64) | Required |
| `imported_at` | TIMESTAMPTZ | Required |

No foreign keys or secondary indexes are declared.

---

## Alembic bookkeeping table

### `alembic_version`

This table is normally created/managed by Alembic itself, not by the RetinaGram ORM model file.

Typical purpose:
- stores the currently applied migration revision
- current application migration is `0001_local_storage`

So a migrated PostgreSQL database will normally have **8 visible tables total**:

- 7 RetinaGram application tables
- 1 Alembic bookkeeping table

---

## Relationship diagram

```text
patients
└── screening_sessions
    ├── eye_results
    │   └── reports (optional eye_result_id)
    └── reports

sync_state
  └── polymorphic entity reference via entity_type + entity_id

app_settings
  └── standalone key/value settings

legacy_imports
  └── standalone migration/import tracking
```

## Delete/cascade behavior

```text
DELETE patient
    ↓ CASCADE
screening_sessions
    ↓ CASCADE
eye_results
    ↓ CASCADE
reports
```

Reports are also directly linked to the screening session, so session deletion cascades to reports as well.

This is useful for `Clear local history`, but application code should still perform deletion through the repository/service layer inside a controlled transaction rather than deleting the PostgreSQL data directory.

---

## Important design observations

- PostgreSQL stores **metadata and structured clinical/history data**.
- Large image/PDF content is referenced through path fields such as `original_image_path`, `restored_image_path`, `lesion_overlay_path`, `gradcam_path`, and `report_path`; it is not stored as PostgreSQL blobs.
- `JSONB` is used for flexible model output (`result_json`), clinical metadata, cloud object-key metadata, and app settings.
- Patient → session → eye-result ownership is protected with cascading foreign keys.
- A session can have at most one `OS` result and one `OD` result because of the (`session_id`, `eye`) unique constraint.
- `sync_state` is already prepared for offline-first cloud synchronization.

## Migration status in the branch

Only one Alembic revision is present in the inspected `pc-cpu` branch:

`0001_local_storage`

It creates all seven application tables listed above.
