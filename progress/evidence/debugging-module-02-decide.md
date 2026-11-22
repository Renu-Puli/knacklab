# Module 02 — STEP 2: DECIDE Evidence

**Track:** Debugging & Incident Response  
**Module:** 02 — Reading Logs Like a Story  
**Step:** 2 — DECIDE  
**Decision Key:** `decisions.module_02.log_strategy`  
**Choice:** `B` (`minimal_default`)  

---

## Decision Reasoning

Production systems should maintain a high signal-to-noise ratio while controlling log ingestion, indexing, storage, and performance overhead. Logging everything at `DEBUG` level by default can generate enormous volumes of data and make important incidents harder to identify among routine events.

However, minimal logging must not create observability gaps. We complement `WARN`-and-above production logging with:
1. Structured JSON formatting across all services.
2. Distributed tracing and correlation IDs (`request_id`).
3. Metric alerts and anomaly thresholds.
4. Targeted dynamic `DEBUG` logging capabilities that can be enabled on-demand for specific tenants, users, or endpoints during incident investigations.

This strategy establishes a cost-efficient, low-noise production baseline while preserving rapid forensic capabilities. The recognized trade-off is that historical telemetry prior to flipping dynamic flags may be limited; therefore, critical business transactions, security events, and degradation markers must always be instrumented at appropriate levels (`INFO`, `WARN`, `ERROR`).
