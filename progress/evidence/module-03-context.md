# Module 03: CONTEXT Micro-Exercise

## Question 1: Worst thing an attacker can make redirect do
An attacker could create a malicious short link that redirects users to a phishing website. For example, users may click our short URL and get redirected to a fake banking website where their credentials could be stolen. This can lead to phishing attacks and credential theft.

## Question 2: URL Schemes allowed and blocked
We will explicitly allow `http://` and `https://` schemes because they are standard web protocols. We will block `javascript:`, `data:`, and `file:` schemes because they can introduce client-side security risks such as stored Cross-Site Scripting (XSS) and local file exposure.

