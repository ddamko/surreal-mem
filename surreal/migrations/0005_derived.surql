-- 0005 derived memory written by the reflection job: conversation summaries and observations.

DEFINE TABLE summary SCHEMAFULL;
DEFINE FIELD conversation ON summary TYPE record<conversation>;
DEFINE FIELD space ON summary TYPE string;
DEFINE FIELD content ON summary TYPE string;
DEFINE FIELD covers_from ON summary TYPE int;
DEFINE FIELD covers_to ON summary TYPE int;
DEFINE FIELD model ON summary TYPE option<string>;
DEFINE FIELD embedding ON summary TYPE option<array<float>>;
DEFINE FIELD embedding_model ON summary TYPE option<string>;
DEFINE FIELD created_at ON summary TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD metadata ON summary TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX summary_conversation ON summary FIELDS conversation;
DEFINE INDEX summary_space ON summary FIELDS space;
DEFINE INDEX summary_content_ft ON summary FIELDS content FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX summary_emb ON summary FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;

DEFINE TABLE observation SCHEMAFULL;
DEFINE FIELD space ON observation TYPE string;
DEFINE FIELD kind ON observation TYPE string DEFAULT 'insight'
    ASSERT $value INSIDE ['insight', 'pattern', 'contradiction', 'reflection'];
DEFINE FIELD content ON observation TYPE string;
DEFINE FIELD about ON observation TYPE array<record<entity>> DEFAULT [];
DEFINE FIELD facts ON observation TYPE array<record<fact>> DEFAULT [];
DEFINE FIELD confidence ON observation TYPE float DEFAULT 1.0 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD status ON observation TYPE string DEFAULT 'active'
    ASSERT $value INSIDE ['active', 'resolved', 'archived'];
DEFINE FIELD model ON observation TYPE option<string>;
DEFINE FIELD embedding ON observation TYPE option<array<float>>;
DEFINE FIELD embedding_model ON observation TYPE option<string>;
DEFINE FIELD created_at ON observation TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD updated_at ON observation TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON observation TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX observation_space ON observation FIELDS space;
DEFINE INDEX observation_kind ON observation FIELDS kind;
DEFINE INDEX observation_status ON observation FIELDS status;
DEFINE INDEX observation_content_ft ON observation FIELDS content FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX observation_emb ON observation FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;
