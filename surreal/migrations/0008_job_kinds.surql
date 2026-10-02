-- 0008 more job kinds for the scheduler (reflect_sweep) and salience recomputation.
DEFINE FIELD OVERWRITE kind ON job TYPE string
    ASSERT $value INSIDE ['extract', 'embed', 'reflect', 'reflect_sweep', 'metrics', 'project', 'import', 'resolve', 'salience'];
DEFINE FIELD IF NOT EXISTS reflected_to ON conversation TYPE int DEFAULT 0;
DEFINE FIELD IF NOT EXISTS reflected_at ON conversation TYPE option<datetime>;
