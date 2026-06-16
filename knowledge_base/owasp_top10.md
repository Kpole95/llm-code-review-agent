# OWASP Top 10 — Summary Reference

Condensed reference for the security scanner's RAG context.

## A01: Broken access control
Users can act outside their intended permissions — e.g. changing an ID in a
URL to access another user's data, or reaching admin routes without a role
check. Always verify authorization server-side on every request.

## A02: Cryptographic failures
Sensitive data stored or sent without proper encryption, or using weak
algorithms (MD5/SHA1 for passwords). Hash passwords with bcrypt/argon2,
never store them in plaintext.

## A03: Injection
Untrusted input concatenated into a command interpreter — SQL injection,
command injection, etc. Fix: parameterized queries / prepared statements,
never string concatenation with user input.

## A04: Insecure design
Security flaws baked into the architecture itself — e.g. no rate limiting
on password reset, or business logic that allows negative quantities.

## A05: Security misconfiguration
Default credentials, debug mode in production, verbose error messages
leaking stack traces.

## A06: Vulnerable and outdated components
Using libraries with known CVEs or unmaintained dependencies.

## A07: Identification and authentication failures
Weak password policies, missing MFA, session IDs in URLs, sessions that
don't expire.

## A08: Software and data integrity failures
Deserializing untrusted data with formats that can execute code (e.g.
Python pickle, unsafe YAML loaders).

## A09: Security logging and monitoring failures
Insufficient logging of security events (logins, access failures) — but
never log secrets/passwords themselves.

## A10: Server-side request forgery (SSRF)
Server fetches a user-supplied URL without validation, letting an attacker
make the server hit internal endpoints. Allow-list destination hosts.