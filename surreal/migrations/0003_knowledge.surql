-- 0003 long-term memory: entities, aliases, relationships, facts, resolution and provenance.

DEFINE TABLE entity SCHEMAFULL;
DEFINE FIELD name ON entity TYPE string ASSERT string::len(string::trim($value)) > 0;
DEFINE FIELD name_key ON entity TYPE string VALUE fn::normalize_name($this.name);
DEFINE FIELD base_type ON entity TYPE string
    ASSERT $value INSIDE ['person', 'organization', 'location', 'event', 'object', 'concept'];
DEFINE FIELD subtype ON entity TYPE option<string>;
DEFINE FIELD description ON entity TYPE option<string>;
DEFINE FIELD aliases ON entity TYPE array<string> DEFAULT [];
DEFINE FIELD spaces ON entity TYPE array<string> DEFAULT [];
DEFINE FIELD embedding ON entity TYPE option<array<float>>;
DEFINE FIELD embedding_model ON entity TYPE option<string>;
DEFINE FIELD confidence ON entity TYPE float DEFAULT 1.0 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD salience ON entity TYPE float DEFAULT 0.5 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD mention_count ON entity TYPE int DEFAULT 0;
DEFINE FIELD first_seen_at ON entity TYPE option<datetime>;
DEFINE FIELD last_seen_at ON entity TYPE option<datetime>;
DEFINE FIELD archived ON entity TYPE bool DEFAULT false;
DEFINE FIELD merged_into ON entity TYPE option<record<entity>>;
DEFINE FIELD metrics ON entity TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD metrics_at ON entity TYPE option<datetime>;
DEFINE FIELD projection ON entity TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD created_at ON entity TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD updated_at ON entity TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON entity TYPE object FLEXIBLE DEFAULT {};
-- Not UNIQUE: merged entities keep their name_key as an alias record; the application resolves
-- inside a transaction (see knowledge use cases).
DEFINE INDEX entity_key ON entity FIELDS base_type, name_key;
DEFINE INDEX entity_type ON entity FIELDS base_type;
DEFINE INDEX entity_archived ON entity FIELDS archived;
DEFINE INDEX entity_name_ft ON entity FIELDS name FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX entity_description_ft ON entity FIELDS description FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX entity_emb ON entity FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;

DEFINE TABLE alias SCHEMAFULL;
DEFINE FIELD entity ON alias TYPE record<entity>;
DEFINE FIELD alias ON alias TYPE string;
DEFINE FIELD alias_key ON alias TYPE string VALUE fn::normalize_name($this.alias);
DEFINE FIELD source ON alias TYPE string DEFAULT 'extraction'
    ASSERT $value INSIDE ['extraction', 'merge', 'manual', 'import'];
DEFINE FIELD created_at ON alias TYPE datetime DEFAULT time::now() READONLY;
DEFINE INDEX alias_key ON alias FIELDS alias_key;
DEFINE INDEX alias_unique ON alias FIELDS entity, alias_key UNIQUE;

-- Vocabulary of relationship kinds. Seeded kinds are prompted to the extractor; new kinds arrive
-- as proposed and are reviewed in the dashboard. `functional` kinds hold at most one current value
-- per subject, so a new fact supersedes the previous one.
DEFINE TABLE relation_kind SCHEMAFULL;
DEFINE FIELD kind ON relation_kind TYPE string ASSERT $value = /^[A-Z][A-Z0-9_]*$/;
DEFINE FIELD description ON relation_kind TYPE option<string>;
DEFINE FIELD seeded ON relation_kind TYPE bool DEFAULT false;
DEFINE FIELD proposed ON relation_kind TYPE bool DEFAULT false;
DEFINE FIELD functional ON relation_kind TYPE bool DEFAULT false;
DEFINE FIELD inverse ON relation_kind TYPE option<string>;
DEFINE FIELD usage_count ON relation_kind TYPE int DEFAULT 0;
DEFINE FIELD created_at ON relation_kind TYPE datetime DEFAULT time::now() READONLY;

DEFINE TABLE related_to SCHEMAFULL TYPE RELATION IN entity OUT entity ENFORCED;
DEFINE FIELD kind ON related_to TYPE string ASSERT $value = /^[A-Z][A-Z0-9_]*$/;
DEFINE FIELD proposed ON related_to TYPE bool DEFAULT false;
DEFINE FIELD weight ON related_to TYPE float DEFAULT 1.0;
DEFINE FIELD confidence ON related_to TYPE float DEFAULT 1.0 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD spaces ON related_to TYPE array<string> DEFAULT [];
DEFINE FIELD mention_count ON related_to TYPE int DEFAULT 1;
DEFINE FIELD fact ON related_to TYPE option<record<fact>>;
DEFINE FIELD first_seen_at ON related_to TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD last_seen_at ON related_to TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON related_to TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX related_kind ON related_to FIELDS kind;
DEFINE INDEX related_unique ON related_to FIELDS in, out, kind UNIQUE;

DEFINE TABLE fact SCHEMAFULL;
DEFINE FIELD statement ON fact TYPE string ASSERT string::len(string::trim($value)) > 0;
DEFINE FIELD space ON fact TYPE string;
DEFINE FIELD subject ON fact TYPE record<entity>;
DEFINE FIELD object ON fact TYPE option<record<entity>>;
DEFINE FIELD object_literal ON fact TYPE option<string>;
DEFINE FIELD kind ON fact TYPE string ASSERT $value = /^[A-Z][A-Z0-9_]*$/;
DEFINE FIELD category ON fact TYPE option<string>;
DEFINE FIELD confidence ON fact TYPE float DEFAULT 1.0 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD salience ON fact TYPE float DEFAULT 0.5 ASSERT $value >= 0.0 AND $value <= 1.0;
DEFINE FIELD embedding ON fact TYPE option<array<float>>;
DEFINE FIELD embedding_model ON fact TYPE option<string>;
DEFINE FIELD valid_from ON fact TYPE option<datetime>;
DEFINE FIELD valid_to ON fact TYPE option<datetime>;
DEFINE FIELD recorded_at ON fact TYPE datetime DEFAULT time::now();
DEFINE FIELD invalidated_at ON fact TYPE option<datetime>;
DEFINE FIELD superseded_by ON fact TYPE option<record<fact>>;
DEFINE FIELD supersedes ON fact TYPE option<record<fact>>;
DEFINE FIELD status ON fact TYPE string DEFAULT 'active'
    ASSERT $value INSIDE ['active', 'invalidated', 'archived'];
DEFINE FIELD source_kind ON fact TYPE string DEFAULT 'extraction'
    ASSERT $value INSIDE ['extraction', 'manual', 'import', 'agent'];
DEFINE FIELD flags ON fact TYPE array<string> DEFAULT [];
DEFINE FIELD access_count ON fact TYPE int DEFAULT 0;
DEFINE FIELD last_accessed_at ON fact TYPE option<datetime>;
DEFINE FIELD projection ON fact TYPE object FLEXIBLE DEFAULT {};
DEFINE FIELD created_at ON fact TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD updated_at ON fact TYPE datetime VALUE time::now();
DEFINE FIELD metadata ON fact TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX fact_subject ON fact FIELDS subject;
DEFINE INDEX fact_object ON fact FIELDS object;
DEFINE INDEX fact_space ON fact FIELDS space;
DEFINE INDEX fact_status ON fact FIELDS status;
DEFINE INDEX fact_kind ON fact FIELDS kind;
DEFINE INDEX fact_recorded ON fact FIELDS recorded_at;
DEFINE INDEX fact_statement_ft ON fact FIELDS statement FULLTEXT ANALYZER english BM25 HIGHLIGHTS;
DEFINE INDEX fact_emb ON fact FIELDS embedding HNSW DIMENSION 1024 DIST COSINE;

DEFINE TABLE merge_candidate SCHEMAFULL;
DEFINE FIELD left ON merge_candidate TYPE record<entity>;
DEFINE FIELD right ON merge_candidate TYPE record<entity>;
DEFINE FIELD score ON merge_candidate TYPE float;
DEFINE FIELD reason ON merge_candidate TYPE string;
DEFINE FIELD status ON merge_candidate TYPE string DEFAULT 'pending'
    ASSERT $value INSIDE ['pending', 'approved', 'rejected', 'auto'];
DEFINE FIELD decided_at ON merge_candidate TYPE option<datetime>;
DEFINE FIELD decided_by ON merge_candidate TYPE option<string>;
DEFINE FIELD created_at ON merge_candidate TYPE datetime DEFAULT time::now() READONLY;
DEFINE FIELD metadata ON merge_candidate TYPE object FLEXIBLE DEFAULT {};
DEFINE INDEX merge_candidate_pair ON merge_candidate FIELDS left, right UNIQUE;
DEFINE INDEX merge_candidate_status ON merge_candidate FIELDS status;

-- in = the entity that was merged away (loser), out = the surviving entity.
DEFINE TABLE same_as SCHEMAFULL TYPE RELATION IN entity OUT entity ENFORCED;
DEFINE FIELD reason ON same_as TYPE string;
DEFINE FIELD score ON same_as TYPE option<float>;
DEFINE FIELD merged_by ON same_as TYPE string DEFAULT 'system';
DEFINE FIELD merged_at ON same_as TYPE datetime DEFAULT time::now() READONLY;

-- Provenance: which message mentioned which entity, and which message a fact or entity came from.
DEFINE TABLE mentions SCHEMAFULL TYPE RELATION IN message OUT entity ENFORCED;
DEFINE FIELD spans ON mentions TYPE array<object> FLEXIBLE DEFAULT [];
DEFINE FIELD confidence ON mentions TYPE float DEFAULT 1.0;
DEFINE FIELD created_at ON mentions TYPE datetime DEFAULT time::now() READONLY;
DEFINE INDEX mentions_unique ON mentions FIELDS in, out UNIQUE;

DEFINE TABLE extracted_from SCHEMAFULL TYPE RELATION IN fact | entity | related_to OUT message ENFORCED;
DEFINE FIELD extractor ON extracted_from TYPE string DEFAULT 'llm';
DEFINE FIELD model ON extracted_from TYPE option<string>;
DEFINE FIELD confidence ON extracted_from TYPE float DEFAULT 1.0;
DEFINE FIELD created_at ON extracted_from TYPE datetime DEFAULT time::now() READONLY;
DEFINE INDEX extracted_from_unique ON extracted_from FIELDS in, out UNIQUE;

-- Seed vocabulary (ADR-0005). `functional` kinds supersede on write (ADR-0006).
INSERT INTO relation_kind [
    { id: relation_kind:WORKS_AT,        kind: 'WORKS_AT',        seeded: true, functional: false, description: 'Person is employed by or works at an organization' },
    { id: relation_kind:MEMBER_OF,       kind: 'MEMBER_OF',       seeded: true, functional: false, description: 'Person or organization belongs to a group or organization' },
    { id: relation_kind:FOUNDED,         kind: 'FOUNDED',         seeded: true, functional: false, description: 'Person or organization founded an organization' },
    { id: relation_kind:LEADS,           kind: 'LEADS',           seeded: true, functional: false, description: 'Person leads or manages an organization, team or project' },
    { id: relation_kind:REPORTS_TO,      kind: 'REPORTS_TO',      seeded: true, functional: true,  description: 'Person reports to another person' },
    { id: relation_kind:KNOWS,           kind: 'KNOWS',           seeded: true, functional: false, description: 'Person knows another person' },
    { id: relation_kind:FAMILY_OF,       kind: 'FAMILY_OF',       seeded: true, functional: false, description: 'Family relationship between people' },
    { id: relation_kind:LIVES_IN,        kind: 'LIVES_IN',        seeded: true, functional: true,  description: 'Person lives in a location' },
    { id: relation_kind:LOCATED_IN,      kind: 'LOCATED_IN',      seeded: true, functional: true,  description: 'Organization, object or event is located in a location' },
    { id: relation_kind:PARTICIPATED_IN, kind: 'PARTICIPATED_IN', seeded: true, functional: false, description: 'Person or organization took part in an event' },
    { id: relation_kind:ATTENDED,        kind: 'ATTENDED',        seeded: true, functional: false, description: 'Person attended an event' },
    { id: relation_kind:OWNS,            kind: 'OWNS',            seeded: true, functional: false, description: 'Person or organization owns an object' },
    { id: relation_kind:CREATED,         kind: 'CREATED',         seeded: true, functional: false, description: 'Person or organization created an object or concept' },
    { id: relation_kind:USES,            kind: 'USES',            seeded: true, functional: false, description: 'Person, organization or object uses a tool, library or technology' },
    { id: relation_kind:DEPENDS_ON,      kind: 'DEPENDS_ON',      seeded: true, functional: false, description: 'Object or project depends on another object or technology' },
    { id: relation_kind:PART_OF,         kind: 'PART_OF',         seeded: true, functional: false, description: 'Object or concept is a component of a larger one' },
    { id: relation_kind:MAINTAINS,       kind: 'MAINTAINS',       seeded: true, functional: false, description: 'Person or organization maintains an object such as a repository' },
    { id: relation_kind:CONTRIBUTES_TO,  kind: 'CONTRIBUTES_TO',  seeded: true, functional: false, description: 'Person contributes to a project or object' },
    { id: relation_kind:DECIDED,         kind: 'DECIDED',         seeded: true, functional: false, description: 'Person or organization made a decision (an event)' },
    { id: relation_kind:RELATED_TO,      kind: 'RELATED_TO',      seeded: true, functional: false, description: 'Generic association when nothing more specific applies' },
    { id: relation_kind:SIMILAR_TO,      kind: 'SIMILAR_TO',      seeded: true, functional: false, description: 'Two entities are alike or comparable' },
    { id: relation_kind:PREFERS,         kind: 'PREFERS',         seeded: true, functional: false, description: 'Person prefers an object, concept or way of working (preferences)' },
    { id: relation_kind:DISLIKES,        kind: 'DISLIKES',        seeded: true, functional: false, description: 'Person dislikes an object or concept' },
    { id: relation_kind:HAS_ROLE,        kind: 'HAS_ROLE',        seeded: true, functional: true,  description: 'Person holds a role or title' },
    { id: relation_kind:HAS_ATTRIBUTE,   kind: 'HAS_ATTRIBUTE',   seeded: true, functional: false, description: 'Entity has a literal attribute (birthday, port number, version)' },
    { id: relation_kind:SCHEDULED_FOR,   kind: 'SCHEDULED_FOR',   seeded: true, functional: true,  description: 'Event is scheduled for a date or time' },
    { id: relation_kind:MENTIONED_WITH,  kind: 'MENTIONED_WITH',  seeded: true, functional: false, description: 'Co-occurrence without a stated relationship' }
];
