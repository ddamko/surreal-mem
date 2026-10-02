-- 0004 reasoning memory: traces, steps, tools and tool calls, linked to messages and entities.

DEFINE TABLE trace SCHEMAFULL;
DEFINE FIELD conversation ON trace TYPE option<record<conversation>>;
DEFINE FIELD space ON trace TYPE string;
DEFINE FIELD agent_id ON trace TYPE string;
DEFINE FIELD task ON trace TYPE string;
DEFINE FIELD status ON trace TYPE string DEFAULT 'running'
    ASSERT $value INSIDE ['running', 'completed', 'failed', 'abandoned'];
DEFINE FIELD outcome ON trace TYPE option<string>;
DEFINE FIELD success ON trace TYPE option<bool>;
DEFINE FIELD step_count ON trace TYPE int DEFAULT 0;
DEFINE FIELD embedding ON trace TYPE option<array<float>>;
DEFINE FIELD embedding_model ON trace TYPE option<string>;
DEFINE FIELD started_at ON trace TYPE datetime DEFAULT time::now();
DEFINE FIELD completed_at ON trace TYPE option<datetime>;
DEFINE FIELD updated_at ON trace TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON trace TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX trace_space ON trace FIELDS space;
DEFINE INDEX trace_conversation ON trace FIELDS conversation;
DEFINE INDEX trace_status ON trace FIELDS status;
DEFINE INDEX trace_task_ft ON trace FIELDS task FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX trace_emb ON trace FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;

DEFINE TABLE step SCHEMAFULL;
DEFINE FIELD trace ON step TYPE record<trace>;
DEFINE FIELD seq ON step TYPE int ASSERT $value >= 1;
DEFINE FIELD thought ON step TYPE option<string>;
DEFINE FIELD action ON step TYPE option<string>;
DEFINE FIELD observation ON step TYPE option<string>;
DEFINE FIELD started_at ON step TYPE datetime DEFAULT time::now();
DEFINE FIELD duration_ms ON step TYPE option<int>;
DEFINE FIELD metadata ON step TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX step_trace_seq ON step FIELDS trace, seq UNIQUE;

DEFINE TABLE tool SCHEMAFULL;
DEFINE FIELD name ON tool TYPE string;
DEFINE FIELD description ON tool TYPE option<string>;
DEFINE FIELD call_count ON tool TYPE int DEFAULT 0;
DEFINE FIELD created_at ON tool TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD metadata ON tool TYPE object FLEXIBLE DEFAULT {};

DEFINE TABLE tool_call SCHEMAFULL;
DEFINE FIELD step ON tool_call TYPE record<step>;
DEFINE FIELD tool ON tool_call TYPE record<tool>;
DEFINE FIELD arguments ON tool_call TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD result ON tool_call TYPE option<string>;
DEFINE FIELD success ON tool_call TYPE option<bool>;
DEFINE FIELD duration_ms ON tool_call TYPE option<int>;
DEFINE FIELD created_at ON tool_call TYPE datetime DEFAULT time::now();
DEFINE FIELD metadata ON tool_call TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX tool_call_step ON tool_call FIELDS step;
DEFINE INDEX tool_call_tool ON tool_call FIELDS tool;

-- Cross-layer edges.
DEFINE TABLE initiated_by SCHEMAFULL TYPE RELATION IN trace OUT message ENFORCED;
DEFINE FIELD created_at ON initiated_by TYPE datetime DEFAULT time::now() READONLY;
DEFINE INDEX initiated_by_unique ON initiated_by FIELDS in, out UNIQUE;

DEFINE TABLE touched SCHEMAFULL TYPE RELATION IN step OUT entity ENFORCED;
DEFINE FIELD how ON touched TYPE string DEFAULT 'mention' ASSERT $value INSIDE ['read', 'write', 'mention'];
DEFINE FIELD created_at ON touched TYPE datetime DEFAULT time::now() READONLY;
DEFINE INDEX touched_unique ON touched FIELDS in, out, how UNIQUE;
