# Certivote

Secure online voting system for Evelyn Hone College student elections
(sectional + campus-wide). See `certivote-project-brief.md` for the full
design spec and threat model this is built against.

## What's here so far

This is the foundation layer: the database schema, nothing else yet.
Deliberately built first because every other piece (registration desk,
OTP flow, voting UI, admin panel, results audit) depends on this being
right. In particular:

- `Voter` and `Ballot` are separate tables with **no foreign key between
  them**. This is the anonymity guarantee -- do not add one while
  extending this schema, even for convenience.
- `Ballot.hash` chains to the previous ballot's hash (`prev_hash`), giving
  tamper-evidence. Any edit to a past ballot breaks every hash after it.
- `Voter.section` is meant to be populated from an official roster import,
  not typed by a registrar at the desk -- that's what stops a registrar
  from quietly placing a voter in the wrong section's electorate.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL to your Neon connection string,
# generate a real SECRET_KEY

flask db init
flask db migrate -m "initial schema"
flask db upgrade

python run.py
```

## Build order from here (matches what was agreed before starting)

1. **Voter roster import + registration desk routes** -- CSV import of
   exam_number/section/full_name from the official roster; registrar
   endpoint to look up a voter by exam number (section auto-fills, not
   typed) and bind a phone number; two-person-approval re-bind endpoint
   for use during an open voting window.
2. **Election/position/candidate admin routes** -- create an election,
   add positions scoped to campus-wide or a specific section, add
   candidates per position, lock positions when voting opens.
3. **Voter-facing OTP + voting flow** -- request OTP by exam number
   (via Africa's Talking, sandbox mode during dev), verify OTP,
   single-use short-lived session, cast ballot (writes VoteStatus +
   Ballot in the same transaction), immediate SMS confirmation.
4. **Results / audit** -- post-election script that walks the hash
   chain, verifies integrity end-to-end, and outputs a public root hash
   plus the final tally per position.
5. Everything else from the open-questions list (downtime handling,
   data retention purge job, low-bandwidth frontend) layers on top of
   the above once the core loop is working end-to-end.

## Roles

- **Registrar**: registers voters, re-binds phone numbers (pre-election
  solo; during an open election requires a second admin's approval).
- **Super admin**: infrastructure access (deploy, backups, uptime).
  Intentionally has no query path to the voter-identity/ballot link and
  no write access to the `ballots` table -- enforce this with real
  database permissions once deployed, not just application code.
- **Observer**: read-only access to the audit log and hash chain, held
  by someone independent (a lecturer, a student rep) -- not the
  developer -- so "nobody can rig this" doesn't rest solely on trusting
  one person's word.
