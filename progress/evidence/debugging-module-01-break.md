# Module 01 — STEP 5: BREAK Hypotheses

## Track: Debugging & Incident Response (`debugging-incident-response`)
## Module: 01
## Step: BREAK

### The Intermittent Production Phenomenon
Under static conditions, offset pagination (`offset = (page - 1) * limit`) with deterministic secondary sorting (`Link.id.desc()`) returns distinct, non-overlapping pages. However, under concurrent link creation, users observe intermittent duplicate records across page boundaries.

---

### Formulated Hypotheses

#### Hypothesis 1 (Primary): Dataset Shifting via Concurrent Insertions (The Offset Drift Problem)
- **Statement**: Offset-based pagination relies on a static dataset state between sequential page requests. Because links are ordered newest-first (`created_at DESC, id DESC`), inserting new records during browsing prepends items to the top of the dataset. This shifts all existing records down by the number of inserted items.
- **Mechanism**:
  - User loads Page 1 (`offset=0, limit=10`). Items at index `0..9` are viewed.
  - A concurrent write inserts 1 new record at the top (index `0`).
  - The item originally at index `9` (bottom of Page 1) is pushed to index `10`.
  - User requests Page 2 (`offset=10, limit=10`).
  - Index `10` is read as the first item of Page 2, causing the user to see that record on both Page 1 and Page 2.
- **Prediction**: If Page 1 is retrieved, an item is inserted, and Page 2 is retrieved with standard offset math, the boundary item from Page 1 will reappear on Page 2.

#### Hypothesis 2: Concurrent Writes Interacting with Sort Order & Timestamp Clusters
- **Statement**: Concurrent bursts of insertions sharing identical or near-identical timestamps shift the relative page boundaries. Even with deterministic sorting tie-breakers, offset pagination over an actively mutating dataset produces boundary drift, manifesting as intermittent duplicate or skipped items.
- **Prediction**: Rapid concurrent writes interleaved with pagination requests will produce intermittent duplicate or missed records depending on write timing relative to page fetch intervals.
