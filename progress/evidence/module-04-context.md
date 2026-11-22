# Module 04: Authentication & Authorization – CONTEXT

## Question 1: Name one endpoint that must stay public and why.
The `GET /r/{code}` endpoint must remain public because anyone with a short URL should be able to access it and get redirected to the original destination. Requiring authentication would prevent normal visitors from opening shared short links.

## Question 2: Name two endpoints that must be protected and what an attacker could do without protection.
1. `POST /links` – This endpoint must require authentication because it creates new short links. Without protection, attackers could create malicious links for phishing, spam, or abuse and exhaust server resources.
2. `GET /links` – This endpoint must require authentication and tenant-level authorization because it lists an organization's links. Without protection, attackers could access or scrape other organizations' data, exposing private URLs and business information.
