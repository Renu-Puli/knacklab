# Scenario Confirmation: linkops (URL Shortener Platform)

- **Skill**: Debugging & Incident Response (`debugging-incident-response`)
- **Product Scenario**: `linkops`
- **Application Focus**:
  - `POST /links` creates short links
  - `GET /:shortCode` redirects and tracks analytics
  - `GET /api/admin/links` and `DELETE /api/admin/links/:id` administrative endpoints
  - Background Celery worker processing analytics jobs
- **Hard Constraints**:
  - Redirect hot path availability and latency
  - Admin validation & authorization
  - Concurrency accuracy in analytics
  - Cache invalidation on mutation
  - Worker retry behavior under failure
