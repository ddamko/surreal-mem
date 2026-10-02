-- 0002 spaces, agents, conversations and messages (short-term memory layer).

-- A space partitions memories (personal, work, project:<name>). Entities are global; everything
-- else carries a `space` string that must match an id in this table.
DEFINE TABLE space SCHEMAFULL;
DEFINE FIELD name ON space TYPE string ASSERT $value = /^[a-z0-9][a-z0-9._:-]*$/;
DEFINE FIELD description ON space TYPE option<string>;
DEFINE FIELD created_at ON space TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD metadata ON space TYPE object FLEXIBLE DEFAULT {};

DEFINE TABLE agent SCHEMAFULL;
DEFINE FIELD name ON agent TYPE string ASSERT $value = /^[a-z0-9][a-z0-9._:-]*$/;
DEFINE FIELD kind ON agent TYPE option<string>;
DEFINE FIELD created_at ON agent TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD last_seen_at ON agent TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON agent TYPE object FLEXIBLE DEFAULT {};

DEFINE TABLE conversation SCHEMAFULL;
DEFINE FIELD space ON conversation TYPE string ASSERT $value = /^[a-z0-9][a-z0-9._:-]*$/;
DEFINE FIELD agent_id ON conversation TYPE string;
DEFINE FIELD user_id ON conversation TYPE string DEFAULT 'default';
DEFINE FIELD title ON conversation TYPE option<string>;
DEFINE FIELD status ON conversation TYPE string DEFAULT 'open'
    ASSERT $value INSIDE ['open', 'idle', 'closed'];
DEFINE FIELD external_id ON conversation TYPE option<string>;
DEFINE FIELD message_count ON conversation TYPE int DEFAULT 0;
DEFINE FIELD last_message_at ON conversation TYPE option<datetime>;
DEFINE FIELD started_at ON conversation TYPE datetime DEFAULT time::now();
DEFINE FIELD updated_at ON conversation TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON conversation TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX conversation_space ON conversation FIELDS space;
DEFINE INDEX conversation_agent ON conversation FIELDS agent_id;
DEFINE INDEX conversation_external ON conversation FIELDS agent_id, external_id;
DEFINE INDEX conversation_started ON conversation FIELDS started_at;

DEFINE TABLE message SCHEMAFULL;
DEFINE FIELD conversation ON message TYPE record<conversation>;
DEFINE FIELD space ON message TYPE string;
DEFINE FIELD seq ON message TYPE int ASSERT $value >= 1;
DEFINE FIELD role ON message TYPE string ASSERT $value INSIDE ['user', 'assistant', 'system', 'tool'];
DEFINE FIELD content ON message TYPE string;
DEFINE FIELD name ON message TYPE option<string>;
DEFINE FIELD tokens ON message TYPE option<int>;
DEFINE FIELD embedding ON message TYPE option<array<float>>;
DEFINE FIELD embedding_model ON message TYPE option<string>;
DEFINE FIELD extraction_status ON message TYPE string DEFAULT 'pending'
    ASSERT $value INSIDE ['pending', 'queued', 'running', 'done', 'failed', 'skipped'];
DEFINE FIELD created_at ON message TYPE datetime DEFAULT time::now();
DEFINE FIELD metadata ON message TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX message_conversation_seq ON message FIELDS conversation, seq UNIQUE;
DEFINE INDEX message_space ON message FIELDS space;
DEFINE INDEX message_created ON message FIELDS created_at;
DEFINE INDEX message_content_ft ON message FIELDS content FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX message_emb ON message FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;
