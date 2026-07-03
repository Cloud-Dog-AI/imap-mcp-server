---
template-id: T-NQS
template-version: 1.0
applies-to: docs/NORMALISED_QUERY.md
registry: service
required: conditional
when-applicable: ""
template-last-updated: 2026-06-12
template-owner: public-standards

project: imap-mcp-server
doc-last-updated: 2026-06-18
doc-git-commit: 7683f39
doc-git-branch: main
doc-source-shas: []
doc-age-policy: 90d
doc-conformance-stamp: 2026-06-18T00:00:00Z
---

# Normalised Query & Similarity Key

This project maintains a **Search Ledger** so an MCP client can ask:
- "What’s new since I last ran this (similar) search?"
- "Move duplicates since my last similar search to folder X"

To do this deterministically, we define **normalisation** and a **similarity key**.

## 1) Canonical Search Request

A "search request" is a JSON object containing:

- `profile_id` (string)
- `mode` (`cache` | `imap` | `hybrid` | `vector`)
- `query` (string) — user query expression
- `filters` (object)
  - `folders_include` (list of strings)
  - `folders_exclude` (list of strings)
  - `flags_include` / `flags_exclude` (list of strings)
  - `date_from_utc` / `date_to_utc` (RFC3339 timestamps)
  - `size_min` / `size_max` (bytes)
  - `limit` (int) *(volatile; excluded from similarity unless pinned)*
  - `sort` (e.g. `date_desc`) *(volatile; excluded unless pinned)*

## 2) Normalisation Rules

### 2.1 Query string normalisation (`query_norm`)
1. Unicode normalise to NFKC.
2. Trim leading/trailing whitespace.
3. Lowercase.
4. Collapse internal whitespace runs to a single space.
5. Remove redundant surrounding quotes (optional; keep inner quotes).
6. Keep the original unmodified query for display/audit (`query_raw`).

### 2.2 Filter canonicalisation (`filters_norm`)
- For list fields (`folders_include`, `folders_exclude`, `flags_*`):
  - strip whitespace
  - drop empty values
  - de-duplicate
  - sort lexicographically
- For date fields:
  - parse and re-emit as RFC3339 with `Z` (UTC) and seconds precision.
- For numeric fields:
  - ensure ints
- **Volatile fields** excluded by default from similarity:
  - `limit`, `sort`, `page`, `cursor`, `dry_run`, `record_search`
- Volatile fields may be included if explicitly pinned by the client:
  - `similarity_pins: ["limit", "sort"]`

### 2.3 Canonical JSON serialisation
Construct canonical object:
```json
{
  "profile_id": "...",
  "mode": "cache",
  "query_norm": "...",
  "filters_norm": { "...": "..." },
  "pinned": ["limit"]
}
```
Serialise using:
- UTF-8
- JSON with sorted keys
- no whitespace (`separators=(',',':')`)

## 3) Similarity Key

`similarity_key = sha256(canonical_json).hexdigest()`

This key is used to find the "last similar search" for delta queries.

## 4) Delta Baseline (High Water Mark)

The Search Ledger records a high-water-mark for delta computation:
- Preferred: `per_folder_modseq_max` (if QRESYNC / CONDSTORE supported)
- Else: `per_folder_uid_max`
- Fallback: `max_received_at_utc`

## 5) Reference Python Implementation

> Use this as a reference. Other languages must match behaviour.

```python
import json, re, hashlib, unicodedata
from datetime import datetime, timezone

VOLATILE_FIELDS = {"limit","sort","page","cursor","dry_run","record_search"}

def _rfc3339_z(ts: str) -> str:
    dt = datetime.fromisoformat(ts.replace("Z","+00:00"))
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00","Z")

def normalise_query(q: str) -> str:
    q = unicodedata.normalize("NFKC", q or "")
    q = q.strip().lower()
    q = re.sub(r"\s+", " ", q)
    return q

def canonicalise_filters(filters: dict, pins=None) -> tuple[dict, list[str]]:
    pins = set(pins or [])
    out = {}
    for k, v in (filters or {}).items():
        if k in VOLATILE_FIELDS and k not in pins:
            continue
        if v is None:
            continue
        if isinstance(v, list):
            vals = sorted({str(x).strip() for x in v if str(x).strip()})
            if vals:
                out[k] = vals
        elif k in {"date_from_utc","date_to_utc"}:
            out[k] = _rfc3339_z(str(v))
        elif isinstance(v, (int, float)) and k.startswith("size_"):
            out[k] = int(v)
        else:
            out[k] = v
    return out, sorted(pins)

def similarity_key(profile_id: str, mode: str, query: str, filters: dict, similarity_pins=None) -> tuple[str, dict]:
    qn = normalise_query(query)
    fn, pins = canonicalise_filters(filters, similarity_pins)
    canonical = {
        "profile_id": profile_id,
        "mode": mode,
        "query_norm": qn,
        "filters_norm": fn,
        "pinned": pins,
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",",":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest(), canonical
```
