-- 0006 operations: the background job queue (ADR-0011).

DEFINE TABLE job SCHEMAFULL;
DEFINE FIELD kind ON job TYPE string
    ASSERT $value INSIDE ['extract', 'embed', 'reflect', 'metrics', 'project', 'import', 'resolve'];
DEFINE FIELD status ON job TYPE string DEFAULT 'queued'
    ASSERT $value INSIDE ['queued', 'running', 'done', 'failed', 'dead'];
DEFINE FIELD priority ON job TYPE int DEFAULT 5;
DEFINE FIELD payload ON job TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD result ON job TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD error ON job TYPE option<string>;
DEFINE FIELD attempts ON job TYPE int DEFAULT 0;
DEFINE FIELD max_attempts ON job TYPE int DEFAULT 3;
DEFINE FIELD claimed_by ON job TYPE option<string>;
DEFINE FIELD lease_until ON job TYPE option<datetime>;
DEFINE FIELD scheduled_at ON job TYPE datetime DEFAULT time::now();
DEFINE FIELD started_at ON job TYPE option<datetime>;
DEFINE FIELD finished_at ON job TYPE option<datetime>;
DEFINE FIELD duration_ms ON job TYPE option<int>;
DEFINE FIELD correlation_id ON job TYPE option<string>;
DEFINE FIELD dedupe_key ON job TYPE option<string>;
DEFINE FIELD created_at ON job TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD updated_at ON job TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON job TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX job_status_scheduled ON job FIELDS status, scheduled_at;
DEFINE INDEX job_kind ON job FIELDS kind;
DEFINE INDEX job_dedupe ON job FIELDS dedupe_key;
DEFINE INDEX job_created ON job FIELDS created_at;
