# Module 03: Reproduction Science — STEP 1: CONTEXT

## Micro-Exercise Responses & Analysis

### Question 1: A user reports "the app is slow sometimes." What three questions do you ask to narrow this down?
1. **Scope and Conditions**:
   - Under what specific conditions does the slowness occur? Which endpoint, route, user persona, organization/tenant, or workflow is impacted?
2. **Variable Differentiation**:
   - What operational variables differ between slow executions and fast executions? (e.g., request payload size, database table volume, cache hit/miss state, concurrent request volume, network conditions, background job activity).
3. **Quantification and Localization**:
   - Can we measure and locate where the latency is spent? Does telemetry (latency distribution, APM spans, database query times) indicate whether the bottleneck resides in application runtime execution, PostgreSQL query execution, Redis caching, or network transit?

### Question 2: What is the difference between "I cannot reproduce it" and "it is not reproducible"?
- **"I cannot reproduce it"**: A truthful, empirical statement about the observer's current experimental setup. It acknowledges that the bug exists or may exist, but the specific trigger variables (timing, concurrency, state, volume) have not yet been isolated in the current environment.
- **"It is not reproducible"**: A sweeping, unsupportable claim about the state of the system or universe. It incorrectly implies the bug cannot occur at all, dismissing the user's observation and shutting down root-cause investigation.
- **Standup Communication Standard**:
  > *"I haven't reproduced the issue yet in our local/staging environment. I am systematically isolating the trigger variables, specifically investigating concurrency, race conditions, cache states, and payload volumes."*

---

## Pedagogical Assessment
- **Hypothesis Framing**: Isolates variables instead of guessing.
- **Production Thinking**: Connects user symptoms ("slow sometimes") to measurable system parameters (endpoints, cache, concurrency).
- **Communication Discipline**: Exercises intellectual honesty in technical reporting.
