-- 0007 retrieval support: lexical lookup of aliases for entity linking, access tracking indexes.

DEFINE INDEX alias_ft ON alias FIELDS alias FULLTEXT ANALYZER english BM25;
DEFINE INDEX fact_last_accessed ON fact FIELDS last_accessed_at;
DEFINE INDEX fact_salience ON fact FIELDS salience;
