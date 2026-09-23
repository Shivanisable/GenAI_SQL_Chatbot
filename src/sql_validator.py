"""Conservative validation for LLM-generated read-only SQL."""
import re
class SQLValidationError(ValueError): pass
def normalize_sql(sql: str) -> str:
    value = sql.strip()
    value = re.sub(r"^```(?:sql)?\s*", "", value, flags=re.I)
    return re.sub(r"\s*```$", "", value).strip()
def validate_sql(sql: str) -> str:
    candidate = normalize_sql(sql)
    if not candidate: raise SQLValidationError("The model returned an empty SQL query.")
    if any(marker in candidate for marker in ("--", "/*", "*/")): raise SQLValidationError("SQL comments are not allowed.")
    body = candidate[:-1].strip() if candidate.endswith(";") else candidate
    if ";" in body: raise SQLValidationError("Multiple SQL statements are not allowed.")
    if not re.match(r"^(SELECT|WITH)\b", body, re.I): raise SQLValidationError("Only SELECT or WITH ... SELECT queries are allowed.")
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|REPLACE)\b", re.I)
    if forbidden.search(body): raise SQLValidationError("The query contains a forbidden database operation.")
    return candidate
