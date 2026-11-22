# Module 03: Reproduction Science — STEP 2: DECIDE

## Decision Record
- **Chosen Option**: **Option B (`synthetic_repro`)**
- **Decision Storage Key**: `decisions.module_03.repro_approach = synthetic_repro`

---

## Technical Reasoning & Tradeoff Defense

### 1. Root-Cause Signal & Causal Variable Isolation
The problem statement describes an intermittent 500 error that clusters specifically on **popular short links** and occurs a few times per hour under normal operations.
- This failure pattern strongly indicates a **concurrency race condition, cache stampede, or database contention** on simultaneous operations targeting the exact same resource.
- Synthetic reproduction directly isolates and manipulates the suspected causal variable—**concurrent request volume on a single key**—by allowing an engineer to send 10, 20, or 50 simultaneous asynchronous requests in a matter of milliseconds.
- In contrast, production replay captures serialized requests across thousands of disparate links and routes, burying the rare concurrent collision in megabytes of irrelevant traffic.

### 2. Privacy, Compliance, and Data Minimization
Capturing and replaying actual production traffic requires storing raw HTTP payloads, headers, query parameters, authorization tokens, cookies, and client IP addresses.
- Replaying this data on local developer workstations presents serious security and regulatory risks (e.g., GDPR, CCPA, SOC 2 compliance violations and secret leakage).
- Synthetic reproduction uses purely mock data, synthetic short codes, and test API credentials, maintaining zero compliance risk.

### 3. Tight Feedback Loop & Rapid Iteration
- Writing a targeted, 20-line asynchronous synthetic script (using `asyncio`/`aiohttp` or `httpx`) takes minutes. If the initial concurrency hypothesis fails to trigger the issue, parameters (concurrency level, timing delay, cache warm/cold state) can be modified in seconds.
- Production replay infrastructure (such as GoReplay or TCPReplay) requires packet capture permissions, storage provisioning, network routing, and traffic filtering harnesses, creating significant operational friction.

### 4. Deterministic Shareability & Permanent CI Regression Testing
- A lightweight synthetic reproduction script (`reproduce_race.py`) is completely self-contained and portable across developer environments.
- Once the underlying bug is fixed, the synthetic script transitions immediately into an automated regression test in CI/CD pipelines, guaranteeing that the race condition never regresses.
