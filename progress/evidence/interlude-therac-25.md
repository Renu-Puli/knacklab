# Interlude: Therac-25 — Reflection & Investigation Analysis

Delivered between **Module 01 (Hypothesis-First Debugging)** and **Module 02 (Reading Logs Like a Story)**.

---

## Question 1: Falsifiable Hypotheses & Disconfirming Tests

**Prompt:**
> *The AECL engineers had a hypothesis — "the software works correctly" — but they never designed a test that could disprove it. They ran diagnostics that could only confirm their belief. A hypothesis you cannot disprove is not a hypothesis. It is a belief. When you are debugging, how do you make sure your hypotheses are genuinely testable? What does a good disconfirming test look like?*

**Approved Reflection:**
A genuine hypothesis must make an explicit, falsifiable prediction: *"If hypothesis X is true, condition Y MUST hold, and condition Z CANNOT happen."* A good disconfirming test specifically targets the failure boundaries, timing anomalies, and edge conditions where the hypothesis is expected to break, rather than running standard happy-path diagnostics.

In our Module 01 investigation:
- For Bug #1 (Database connection failure), we formed two competing hypotheses. The configuration mismatch hypothesis was disproven because inspecting `.env` against the PostgreSQL container configuration proved all parameters, ports, and credentials matched. The container state hypothesis was confirmed when `docker ps -a` showed `upsk-sdf-postgres` exited.
- For Bug #2 (Pagination duplicates), instead of settling for static pagination queries that passed repeatedly, we designed a concurrent-insertion simulation to intentionally challenge the offset pagination model under mutation. When duplicate IDs appeared across pages, the empirical evidence disproved any assumption that static sorting alone was mutation-safe. Testing assumptions through deliberate disconfirming experiments separates scientific debugging from confirmation bias.

---

## Question 2: Silent Safety Nets Masking Upstream Defects

**Prompt:**
> *The race condition existed in the Therac-20 for years, but hardware interlocks masked it completely. The bug was real, present, and firing — and nobody knew, because another layer caught the failure. What "safety nets" exist in your own systems — caches, retries, fallback defaults, load balancers, circuit breakers — that might be silently catching bugs you have never seen? If you removed one of those safety nets tomorrow, what would break?*

**Approved Reflection:**
Modern distributed applications rely heavily on defensive safety nets such as caching layers, task retries, load balancers, and error-fallback defaults. In our URL shortener platform:
- **Redis Cache**: A cache-aside layer serves 302 redirects in sub-millisecond time. However, if the primary database is experiencing connection pool exhaustion, slow sequential scans, or query lock timeouts, the cache can mask this failure for high-traffic hot keys. If Redis were removed tomorrow, the raw traffic would hit PostgreSQL directly, causing instant connection starvation and query timeouts.
- **Celery / Async Task Retries**: Automatic background retry policies catch transient network errors, deadlocks, and third-party webhook timeouts. Without proper dead-letter monitoring or retry-exhaustion alerts, retries can silently absorb permanent schema or serialization bugs until workers grind to a halt under a retry storm.
- **Default Fallback Logic**: Returning fallback defaults (e.g., empty arrays or null records in `except` blocks) keeps client-facing HTTP status codes green (200 OK) while silently swallowing database corruptions or permissions failures. Removing these fallbacks would expose the true fault lines across the service.

---

## Question 3: Telemetry vs. Ground-Truth User Reports

**Prompt:**
> *The patients told their doctors something was wrong. They described burning, shock, pain. The operators checked the machine's logs, saw green, and concluded the patients must be mistaken. When have you trusted a dashboard, a metric, or a log file over a human being who told you "something is wrong"? What would it take for you to trust the human over the telemetry?*

**Approved Reflection:**
Telemetry, aggregated metric dashboards, and standard log files only measure what someone explicitly thought to instrument. If a defect manifests in a domain that lacks instrumentation—such as an unlogged timing window, subtle data race, or a 200 OK HTTP response returning an incorrect payload—the monitoring dashboards will show green despite severe customer impairment.

When a human user reports a severe anomaly that contradicts green dashboards:
1. Treat the contradiction not as user error, but as an **observability gap**. The telemetry itself is likely blind to the user's specific execution path, client device, network environment, or sequence timing.
2. Step out from behind the dashboard and reproduce the exact workflow step-by-step, including user keystrokes, timings, input sequences, and environmental nuances (just as Fritz Hager did at the Therac-25 console).
3. Verify ground-truth system state directly—such as querying raw database tables, inspecting network packets, or checking client-side execution logs—rather than relying exclusively on aggregated service-level indicators (SLIs). Human reports are qualitative telemetry and must be given first-class evidential weight.
