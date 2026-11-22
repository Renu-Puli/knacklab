# Module 04: Authentication & Authorization — STEP 2: DECIDE

## 1. Incident Hypothesis & Decision Focus
- **Incident Scenario**: During application deployment, an environment variable naming mismatch causes Pydantic's `BaseSettings` to fail startup validation with a `ValidationError` when expecting `API_KEY_PRIMARY` instead of `API_KEY_A`.
- **Core Dilemma**: Should the system fail fast on configuration mismatches, or should it accommodate multi-alias deployment conventions?

---

## 2. Decision Options Evaluated

### Option A: Pure Deployment Manifest Update
- Enforce `API_KEY_PRIMARY` strictly in code; update external `.env` and deployment manifests.
- *Tradeoff*: Breaks all existing local environments, test scripts, and historical CI pipelines expecting `API_KEY_A`.

### Option B: Multi-Alias Resolution via `AliasChoices` (Approved Decision)
- Update `Settings` to accept both names interchangeably using Pydantic v2's `AliasChoices`:
  ```python
  api_key_a: str = Field(
      default="",
      validation_alias=AliasChoices("API_KEY_PRIMARY", "API_KEY_A", "api_key_a")
  )
  ```
- *Rationale*:
  - Fully backward-compatible with legacy deployment manifests supplying `API_KEY_A` or `api_key_a`.
  - Fully forward-compatible with updated production manifests supplying `API_KEY_PRIMARY`.
  - Zero breaking changes across unit tests and verification harnesses.
  - Maintains strict fail-fast behavior for required infrastructure variables (`DATABASE_URL`).

---

## 3. Decision Record
- **Chosen Option**: **Option B (`AliasChoices` Multi-Alias Resolution)**
- **State Key**: `decisions.module_04.auth_method = "api_key"`, `decisions.module_04.not_owner_status = 404`
- **Rate Limits Configured**:
  - `create_link_per_min = 30`
  - `redirect_per_min = 120`

