# Certivote

Secure online voting system for Evelyn Hone College student elections
(sectional + campus-wide). See `certivote-project-brief.md` for the
original design spec and threat model this is built against.

Live deployment: https://certivote.onrender.com

## What's built

The full core system, end to end:

- **Schema**: `Voter` and `Ballot` are separate tables with no foreign
  key between them (the anonymity guarantee). `Ballot.hash` chains to
  the previous ballot's hash for tamper-evidence.
- **Registrar desk** (`/admin/`): roster import, voter lookup, phone
  registration, re-bind with two-person approval + a 30-minute time-lock
  while an election is open (with an immediate warning SMS to the old
  number), and supervised "kiosk" voting for students with no phone or
  lost access.
- **Election admin**: create elections, add positions/candidates, lock
  positions the moment voting opens.
- **Voter flow** (`/v/`): OTP request/verify (rate-limited, attempt-limited,
  IP-logged), single-use short-lived voting session, transactional ballot
  casting with hash-chaining, immediate SMS confirmation.
- **Results** (`/results/`, no login required): live turnout only while
  voting is open (never a candidate breakdown), a pending message while
  closed-but-uncertified, and the full verified reveal (chain-valid badge,
  winner, public root hash) once certified.
- **Admin accounts**: login lockout after 5 failed attempts (15 min),
  CSRF protection on every browser-facing form.
- **Data retention**: `flask purge-expired-voters` clears voter PII 15
  days after the last election of a cycle closes; never while a cycle is
  active.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL to your Neon connection string,
# generate a real SECRET_KEY

flask db upgrade
python run.py
```

Create your first account:

```bash
flask create-admin tobi somepassword super_admin
```

## Operational readiness

**Downtime, if the system goes down mid-vote:**
- Voting pauses (fails closed -- never silently accepts a broken
  submission) rather than risking a lost or duplicated vote.
- Once restored, the voting window is extended by exactly the outage
  duration, announced publicly, so nobody loses voting time.
- Database recovery: Neon's free tier includes automatic point-in-time
  recovery with a rolling 6-hour history window -- no setup required,
  but act within that window if a restore is ever needed.
- Uptime monitoring: a free UptimeRobot check against
  `https://certivote.onrender.com/results/` alerts the moment the site
  goes down, rather than waiting for a student complaint.

**What the Observer role is for and how to use it:**
The observer account exists so "nobody can rig this" doesn't rest
solely on trusting the developer's word. It should be held by someone
independent of the build -- a lecturer or student rep, not Cletus.
What an observer can do: log in and call `/elections/<id>/audit` (or
the equivalent page once built) to independently re-verify the hash
chain and tally at any point after an election closes. What they
should actually do, in practice: check the audit output once per
election after certification, and spot-check the registrar audit log
(`registrar_audit_log` table) periodically during a live election for
anything unexpected -- an unusual number of re-binds, kiosk votes from
one registrar account, etc. This is a manual check the observer runs
themselves, not an automated alert.

**Cloudflare / edge protection**: not yet in front of the app -- it
requires a custom domain (Cloudflare works via DNS), and this currently
runs on Render's own `onrender.com` domain. Worth adding once/if a
custom domain is purchased for the real pitch. Render's own platform
provides baseline DDoS protection in the meantime.

## Roles

- **Registrar**: registers voters, re-binds phone numbers (immediate
  pre-election; two-person-approved + time-locked during an open
  election), supervises kiosk voting.
- **Super admin**: infrastructure access (deploy, roster import, election
  configuration). Intentionally has no query path linking voter identity
  to ballot content in the application code -- real database-level role
  separation enforcing this is a documented future hardening step, not
  yet implemented (it requires restructuring the app's DB connection
  architecture, a deliberate follow-up rather than a quick patch).
- **Observer**: see "Operational readiness" above.

## Known deferred items

- **External hash-chain anchoring during voting.** Currently the root
  hash is only published at certification. A sophisticated attacker with
  full database access before certification could in principle tamper
  with historical ballots and regenerate a self-consistent alternate
  chain -- post-hoc verification alone can't catch that. A real fix
  (periodically publishing checkpoints somewhere outside the app's own
  database while voting is still open) is real additional work, not a
  quick patch, and is intentionally deferred rather than rushed.
- **Database-level role separation** (see Roles, above).
- **Security scanning pass** (Dependabot, Semgrep, manual OWASP ZAP) --
  deliberately saved for once the build itself is feature-complete.
