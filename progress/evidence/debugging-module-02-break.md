# Module 02 — STEP 5: BREAK Forensic Report

**Track:** Debugging & Incident Response  
**Module:** 02 — Reading Logs Like a Story  
**Step:** 5 — BREAK  

---

## Forensic Analysis: CWE-117 (Log Injection / Log Forgery)

### 1. Incident Excerpt
```json
{"ts":"2025-01-15T15:42:01.200Z","level":"info","req_id":"r-100","msg":"request received","method":"POST","path":"/links","user":"alice"}
{"ts":"2025-01-15T15:42:01.250Z","level":"info","req_id":"r-100","msg":"link created","short_code":"mN7pQ","url":"https://legit-site.com"}
{"ts":"2025-01-15T15:42:01.255Z","level":"info","req_id":"r-100","msg":"response sent","status":201,"duration_ms":55}
{"ts":"2025-01-15T15:42:03.400Z","level":"info","req_id":"r-101","msg":"request received","method":"POST","path":"/links","user":"bob"}
{"ts":"2025-01-15T15:42:03.410Z","level":"info","req_id":"r-101","msg":"link created","short_code":"qR2wX","url":"https://normal-url.com\n{\"ts\":\"2025-01-15T15:42:03.500Z\",\"level\":\"info\",\"req_id\":\"r-102\",\"msg\":\"admin login successful\",\"user\":\"admin\",\"ip\":\"10.0.0.1\"}"}
{"ts":"2025-01-15T15:42:03.420Z","level":"info","req_id":"r-101","msg":"response sent","status":201,"duration_ms":20}
```

### 2. Primary Evidence: Structural Payload Embedding
- In line 5, the entire alleged admin login event (`req_id: r-102`, `user: admin`, `msg: admin login successful`, `ip: 10.0.0.1`) is structurally embedded inside the `url` field string of Bob's link creation request (`req_id: r-101`).
- The payload contains an embedded newline character (`\n`) followed by a forged JSON object. In log aggregators splitting on newlines, this injects an unearned, fabricated log line into SIEM and monitoring tools.
- There is no independent request lifecycle (`request received`, `response sent`) for request `r-102`.

### 3. Supporting Evidence: Temporal Anomaly
- Bob's request `r-101` starts at `15:42:03.400Z`, creates the link at `15:42:03.410Z`, and completes at `15:42:03.420Z`.
- The forged admin login inside line 5 claims a timestamp of `15:42:03.500Z` (80ms in the future relative to the request's completion).

### 4. Vulnerability Classification
- **CWE-117:** Improper Neutralization of Special Elements used in Output Handling / Logs (Log Injection / Log Forgery).
- Unsanitized user input allowing control characters (`\r`, `\n`) to alter stream structure and forge audit logs.
