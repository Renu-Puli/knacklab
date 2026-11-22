# Module 01 - PRETEST: Starting Check & Setup Check

## Part A: Quick Setup Check
- **OS & Shell**: Windows 11, PowerShell / cmd
- **Python**: Python 3.13.3 (v3.10+ requirement met)
- **Docker**: Docker version 29.9.2 (containers available)
- **Git**: git version 2.50.0.windows.1 (version control ready)
- **HTTP Client**: curl.exe 8.22.0 (terminal API test tool ready)
- **Errors / Missing Tools**: None. All core runtime and debugging tools are installed and verified.

## Part B: Student Starting Responses & Evaluation
1. **Self-Rating**: `ok` — uses logs and stack traces, but multi-service / complex issues take time.
2. **First 3 checks for slow app**: Resource utilization (CPU/RAM), application logs (errors/slow requests), database & network latency.
3. **`ECONNREFUSED 127.0.0.1:5432`**: PostgreSQL database service is either down or not listening on port 5432.
4. **Symptom vs Root Cause**: Symptom is the observable malfunction; root cause is the underlying defect or state that triggered it.
5. **Local works, production fails**: Divergent configuration between environments, and differences in dependencies, data, permissions, or infrastructure.
6. **Error message vs Reproduction**: Student prioritized reproduction to confirm the failure mode and validate subsequent fixes.
7. **2 AM outage first action**: Check recent deployments (mitigate/identify recent changes before diving into code).
8. **"Worked yesterday" follow-up**: "What changed since it last worked—code, configuration, dependencies, infrastructure, or data?"
