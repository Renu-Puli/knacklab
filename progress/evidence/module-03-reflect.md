# Module 03: REFLECT Submission

## Question 1: What core problem does this module solve in Core API & CRUD?
This module solves the problem of creating and managing shortened URLs through a Core API. It provides CRUD operations to create, list, and retrieve links. It also validates URLs to prevent unsafe inputs and provides a public redirect endpoint to send users to the original website. Click tracking is performed in the background without interrupting the redirect process.

## Question 2: Which decision in this module has the biggest impact, and why?
The most important decision was choosing Option A: using a separate `/r/{code}` route for redirects. This keeps public redirect functionality separate from API endpoints such as `/health`, `/links`, and `/docs`. It prevents route conflicts, improves maintainability, and makes it easier to expand the application in the future.

## Question 3: What evidence proves the implementation works end-to-end?
The implementation was verified using automated tests and database integration checks. The tests confirmed that:
- A new short link can be created successfully.
- Links can be listed and retrieved.
- Tenant isolation prevents one organization from accessing another organization's links.
- Valid short codes return HTTP 307 redirects with the correct destination.
- Unknown short codes return HTTP 404.
- Expired links return HTTP 410.
- Invalid and malicious URLs are rejected.
- Click events are recorded without interrupting redirects, even when analytics fails.

The regression tests passed, and the results were saved in `progress/evidence/module-03-build.txt`, `progress/evidence/module-03-break.txt`, and `progress/evidence/module-03-fix.txt`.

