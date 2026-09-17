# Certivote — Secure Online Voting System for Evelyn Hone College

**Status:** Pre-build / architecture review
**Type:** Self-initiated final-year project, to be pitched to the college after completion
**Author:** Cletus Bwalya

---

## 1. Problem

Evelyn Hone College runs sectional and campus-wide student leadership elections annually, around October–November, before final exams. Like most Zambian institutions, these are run on paper. There is no documented case of a Zambian institution running online student elections — this would be a first, if it works.

Online voting has real precedent worth learning from, both good and bad:

- **Helios** (used since 2008 across 10,000+ elections — Princeton, IACR, UCL Belgium, etc.): open-source, cryptographically verifiable, the gold standard for trust-minimized voting.
- **Washington D.C.'s 2010 internet voting pilot**: fully compromised within 36 hours by a University of Michigan team, via a shell-injection vulnerability in a file upload handler, plus a default password left unchanged on network hardware. The intrusion went undetected for two days.
- **University of Zululand, South Africa (2020)**: online SRC election suspended after students reported others had accessed their one-time email-based voting PINs and voted on their behalf. The credential (email password) wasn't independent of general account compromise.

Certivote is designed specifically against both documented failure modes, not against a generic threat model.

## 2. Objectives

- Build a working, secure online voting system for a real institutional use case
- Make double-voting, vote tampering, and impersonation genuinely hard — not just procedurally discouraged
- Prove the concept at Evelyn Hone first; use it as the foundation for a pitch to the college, and potentially other Zambian institutions later (UNZA, ZICAS) if it succeeds
- Serve as a flagship final-year project and portfolio piece

## 3. Scope for v1

- **Single-tenant**: built for one institution (Evelyn Hone) only. No multi-tenant abstraction in v1 — deferred until a second real institution actually wants it, to avoid adding tenant-isolation complexity (a common real-world SaaS vulnerability class) before it's needed.
- **Self-built, no institutional dependency required to complete it.** The in-person voter-registration step (below) is built and tested by the developer acting as registrar; live deployment at scale would require the SRC/registrar's office to staff that step during a real election.
- **No personal spend required.** SMS/OTP integration is built and fully tested against a provider's free sandbox mode; a live phone-based demo (if desired) uses free trial credit, not personal funds. Operational SMS cost for a real election is scoped as the adopting institution's cost, not the developer's.

## 4. Security Architecture

### Voter verification
- One-time, in-person registration: voter's phone number is verified against their student ID and bound to their student record. This closes the Zululand gap — the credential isn't obtainable through a compromised email/portal account, because it isn't an email/portal account.
- On voting day: student enters their student ID → system sends an OTP to the bound phone number.
- OTP is single-use, expires in ~5 minutes, invalidated immediately on use or on a new OTP request.
- Voting session dies immediately after ballot submission — no persistent session, no "remember me."
- Immediate out-of-band SMS confirmation on vote cast ("Your vote was recorded at [time]. If this wasn't you, contact [x] now.") — gives the real voter a live tripwire instead of finding out after results are announced, which is what happened at Zululand.

### Anonymity
- Voter identity ("has voted") and ballot content are written to separate tables/stores at the moment of casting, with no retained link between them — so even an admin with full database access cannot reconstruct who voted for whom.

### Tamper-evidence
- Ballots are hash-chained as cast (each entry's hash includes the previous entry's hash). Any retroactive edit breaks the chain visibly.
- Full audit log of all admin actions and vote-cast events.
- Real-time anomaly alerting: repeated OTP requests for one voter, unusual vote velocity, etc., flagged live rather than discovered in a post-election audit.

### Application hardening (directly addressing the D.C. failure)
- No shell/filesystem/SQL operations touch unsanitized user input; parameterized queries throughout.
- No file upload feature (not needed for this use case — removes that entire attack surface).
- No default credentials anywhere; all secrets generated and stored via environment variables / secrets manager.
- Automated verification before launch: OWASP ZAP (dynamic scanning), Semgrep (static analysis), GitHub Dependabot (dependency vulnerabilities) — run instead of/alongside a hired pentester, since one may not be reachable in time.
- Built against the OWASP ASVS checklist as the security spec, not ad hoc judgment calls.

## 5. Tech Stack (proposed)

- Frontend/backend: consistent with prior projects — React frontend, Flask or Next.js backend depending on final call
- Database: Neon (Postgres)
- Hosting: Vercel / Render
- SMS: Africa's Talking (sandbox for dev/testing; free trial credit for any live demo)

## 6. Timeline Pressure

Current date: mid-September. Target: elections around October–November, alongside the developer's own final exams. This is tight — v1 scope above is deliberately minimal (single-tenant, no speculative multi-institution infrastructure) to fit the window.

## 7. Open Questions for Review

- Any failure mode in the voter-verification flow not covered above?
- Is the hash-chain approach sufficient for tamper-evidence at this scale, or is something like periodic public checkpoint publishing worth the added complexity for v1?
- Any concerns with the single-tenant scope decision, given the longer-term multi-institution ambition?
- Realistic assessment of the timeline given exam overlap — what should be cut first if time runs short?
