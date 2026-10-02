-- 0001 baseline: shared analyzers and functions that later migrations build on.
-- Applied once; never edit an applied migration, add a new one instead.

DEFINE ANALYZER IF NOT EXISTS english
    TOKENIZERS class, camel
    FILTERS lowercase, ascii, snowball(english);

-- Canonical form used for entity matching and unique keys.
DEFINE FUNCTION IF NOT EXISTS fn::normalize_name($name: string) -> string {
    RETURN string::trim(string::lowercase($name));
};
