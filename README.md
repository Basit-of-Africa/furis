# FURIS: Fountain University Research Intelligence System

This repository holds the MVP foundation from the project brief (§24, steps 4–7):

- the database schema
- the FastAPI backend
- the discovery, matching, deduplication and attribution engine
- the verification API
- pilot evaluation against a ground-truth dataset

It also includes the Next.js portal (§11.2 Layer 1) for the Research Office, faculty administrators and researchers.

> **Principle:** discover broadly, match carefully, attribute correctly, report transparently.

## What it does

```
staff CSV ─► researcher registry ─► name variants (generated / confirmed / discovered)
                                        │
          ┌─────────────────────────────┼──────────────────────────────┐
     ORCID works            OpenAlex (orcid, author id,        Crossref (orcid,
   (researcher-claimed)      raw_author_name.search)            query.author)
          └─────────────────────────────┼──────────────────────────────┘
                                        ▼   every query logged in search_runs
                      dedup: DOI ► exact title+year ► fuzzy (flag only)
                                        ▼
            identity match per authorship (identifiers ► name + evidence)
                                        ▼
       attribution suggestion (affiliation × employment dates, policy draft-0)
                                        ▼
         human review: authorship (researcher or RO) ─► attribution (RO only)
                                        ▼
                         analytics: counts only reviewed FU output
```

### Rules enforced in the code

| Brief | Where it is enforced |
|---|---|
| Authorship and attribution are separate (§6.2) | `identity_matches` and `institutional_attributions` are separate tables with separate endpoints and permissions. FU-output statuses are refused until authorship is confirmed. |
| Nothing auto-claimed (§6.4, §9.4) | The engine only *suggests*. `confirmed_fu_output` can be set only by Research Office or Super Admin, and needs written evidence. |
| Similar name ≠ identity (§6.3) | An unexplained given name or initial in a byline is a **conflict**, not a weak match. A byline ORCID that differs from the researcher's verified ORCID is **rejected** and the rejection is kept. Two fitting bylines on one paper cap the match at medium. |
| raw_author_name pitfall (§7.5) | Each authorship is inspected separately. A hit that combines "Abdul" from one author with "Ajibade" from another does not match. |
| Profile contamination (§8.1) | If an identifier matches but the byline name conflicts, the match is downgraded and flagged. |
| Provenance (§6.5, §10.3) | Every source record is kept with its raw JSON and retrieval date. Canonical fields are filled only where empty and never overwritten. Citation counts are stored per source. |
| Discovered variants (§7.2, §7.6) | Names seen on identifier-backed matches become *pending* Category 3 variants. They are never searched until confirmed. |
| Fuzzy duplicates (§10.1) | Fuzzy duplicates are flagged in `duplicate_candidates` for review, never merged silently. Short generic titles are never merged on title alone. |
| Audit (§21) | Every write endpoint records an entry in `audit_logs`, as do sign-ins and refused sign-ins. |

## Quick start (local, SQLite)

```bash
cd backend && pip install -e '.[dev]'
```

```bash
pytest
```

```bash
alembic upgrade head
```

```bash
python -m furis.cli create-user ro@fuo.edu.ng "Research Office" research_office
```

```bash
python -m furis.cli import-staff ../samples/staff_template.csv
```

```bash
python -m furis.cli discover --all
```

```bash
uvicorn furis.main:app --reload
```

The API docs are then at `http://localhost:8000/docs`. In local development mode, send `X-User-Email: ro@fuo.edu.ng` with each request; otherwise use the session token from `/auth/...` as `Authorization: Bearer`.

## Portal (Next.js)

```bash
cd frontend && npm install
```

```bash
cp .env.example .env.local
```

```bash
npm run build && npm start
```

The portal runs at `http://localhost:3000`. Set `FURIS_API_URL` in `.env.local` to the backend address. Only the Next.js server calls the API; the browser never does.

| Page | Who sees it | What it does |
|---|---|---|
| Dashboard | Admins, faculty admins | Headline counts, confirmed FU output by year (chart plus table view), output by faculty, ORCID coverage, search-run health |
| Review queue: Authorship | Everyone (scoped by role) | Candidates sorted by confidence, with the evidence behind each match; confirm or reject |
| Review queue: Attribution | Research Office, Super Admin | Confirmed authorships with no attribution decision; FU output needs written evidence |
| Publications | Everyone (scoped) | Filter by authorship status, attribution status and year |
| Publication detail | Everyone (scoped) | Per-researcher evidence and decisions, authors, affiliation evidence, per-source citations, decision history with reviewer names |
| Researchers | Admins, faculty admins | Registry search, add a researcher, CSV import, faculties and departments |
| Researcher profile | Admins, faculty admins, the researcher | Identifiers (verify), employment history, name variants, discovered names to confirm, publications, latest discovery run, "Run discovery" |
| Duplicates | Research Office, Super Admin | Side-by-side possible duplicates; merge or keep separate |

Researchers sign in to "Is this your publication?", their own queue. They can confirm authorship and the names they publish under, but cannot decide attribution.

## Single sign-on

FURIS works with any OpenID Connect provider: Google Workspace, Microsoft Entra ID (Microsoft 365), Keycloak and others.

1. The portal runs the authorization-code flow with PKCE, as a confidential client, so the secret stays on the server.
2. The **API** verifies the ID token: signature against the provider's published keys, issuer, audience, expiry, nonce and email domain.
3. The email must belong to an **existing, active** FURIS account. Signing in never creates an account; administrators create accounts and assign roles.
4. The API issues its own short-lived session token (8 hours by default). The portal keeps it in an httpOnly cookie.
5. Deactivating a user ends their sessions immediately.

**Setup**

1. Register FURIS as a web application with the university's identity provider.
   - Redirect URI: `https://<portal>/auth/callback`
   - Post-logout redirect URI: `https://<portal>/login`
   - Scopes: `openid email profile`
2. Configure the API (`backend/.env`):

   | Setting | Value |
   |---|---|
   | `FURIS_ENVIRONMENT` | `production` |
   | `FURIS_AUTH_MODE` | `oidc` |
   | `FURIS_OIDC_ISSUER` | the provider's issuer URL |
   | `FURIS_OIDC_CLIENT_ID` | the client ID from step 1 |
   | `FURIS_OIDC_ALLOWED_EMAIL_DOMAINS` | e.g. `["fuo.edu.ng"]` |
   | `FURIS_SESSION_SECRET` | a long random value |

   Optionally pin the directory with `FURIS_OIDC_REQUIRED_CLAIMS`: `{"hd":"fuo.edu.ng"}` for Google, or `{"tid":"<tenant-id>"}` for Entra.
3. Configure the portal (`frontend/.env.local`):

   | Setting | Value |
   |---|---|
   | `APP_URL` | the portal's public https address |
   | `OIDC_ISSUER` | the same issuer as the API |
   | `OIDC_CLIENT_ID` | the same client ID as the API |
   | `OIDC_CLIENT_SECRET` | the client secret from step 1 |

| Provider | Issuer | Notes |
|---|---|---|
| Google Workspace | `https://accounts.google.com` | Set the OAuth consent screen to *Internal*, and add `{"hd":"fuo.edu.ng"}` |
| Microsoft Entra ID | `https://login.microsoftonline.com/<tenant-id>/v2.0` | Single-tenant app; the email is often in `preferred_username` (handled); add `{"tid":"<tenant-id>"}` |
| Keycloak | `https://<host>/realms/<realm>` | Confidential client with standard flow enabled |

**Safety checks**

- The API refuses to start in production unless sign-in is `oidc` with a session secret of at least 32 characters.
- The API refuses to start in `oidc` mode without an allowed email domain.
- Dev sign-in (`FURIS_AUTH_MODE=dev_header`, email only, no password) exists for local development. In that mode the login page shows a warning.

## Neon (§11.4)

1. Create the project `furis-production` with the database `furis_db` and two branches, `main` and `development`.
2. Copy `backend/.env.example` to `backend/.env`. Set `FURIS_DATABASE_URL` to the **pooled** string and `FURIS_DATABASE_URL_DIRECT` to the **direct** string, which Alembic uses.
3. Run `alembic upgrade head`.

## Before the pilot

- [ ] **Set the Fountain University identifiers.** Put the verified OpenAlex institution ID and ROR ID in `FURIS_FU_OPENALEX_INSTITUTION_IDS` and `FURIS_FU_ROR_IDS`. Until then, FU affiliation is detected from affiliation text only.
- [ ] **Set the contact address.** Set `FURIS_CONTACT_EMAIL` to a Research Office mailbox, and add `FURIS_OPENALEX_API_KEY` if you have one.
- [ ] **Configure single sign-on.** Register FURIS with the university's identity provider and set `FURIS_ENVIRONMENT=production` and `FURIS_AUTH_MODE=oidc` (see *Single sign-on*).
- [ ] **Replace the draft attribution policy.** `discovery/attribution.py` encodes conservative `draft-0` rules. Replace them with the policy the Research Office approves (§9.5) and change `POLICY_VERSION`. Every assessment records the version that produced it.
- [ ] **Check the data-source terms.** Review the ORCID public-API terms for the university's use (§21).
- [ ] **Verify ORCIDs.** Imported ORCIDs are stored **unverified** and are not used for deterministic matching until an admin calls `POST /identifiers/{id}/verify`.

## Calibration (§8.4, §17–18)

The confidence thresholds in `discovery/matching.py` are **provisional**:

| Confidence | Requires |
|---|---|
| High | score ≥ 0.8 |
| Medium | score ≥ 0.5 |
| Low | anything below 0.5 |

The score is built from these weights:

| Signal | Weight |
|---|---|
| Name | 0.6 |
| FU affiliation | 0.2 |
| Recurring co-author | 0.1 |
| Confirmed alias | 0.05 |

A full name alone is medium. A full name plus an FU affiliation is high. Initials alone are low.

Fill in `samples/ground_truth_template.csv` for the pilot researchers, then run:

```bash
python -m furis.cli evaluate ground_truth.csv --level high
```

The report includes precision, recall, F1, discovery coverage, attribution accuracy and false attribution rate. Predictions that are not in the ground truth are counted as `unlabelled`, not guessed.

## Layout

```
backend/furis/
  models.py              schema (§12) plus users, duplicate_candidates, institutional_attributions
  discovery/names.py     normalisation, variant generation, byline comparison
  discovery/sources/     OpenAlex, Crossref, ORCID adapters (retry/backoff, per-query cap)
  discovery/matching.py  identity resolution
  discovery/attribution.py  FU detection and attribution suggestions
  discovery/dedup.py     canonical publication resolution
  discovery/engine.py    orchestration and search-run logging
  evaluation.py          pilot metrics
  api/                   registry, discovery, publications/analytics, verification, duplicates
backend/alembic/         migrations (0001 = initial schema)
frontend/src/app/        Next.js App Router pages and server actions (all API calls server-side)
frontend/src/components/ review items, evidence panels, badges, forms, chart
samples/                 staff import and ground-truth CSV templates
```

## Not yet built

- Semantic Scholar adapter (the `Source` interface is ready for it).
- A production job queue; discovery currently runs from the CLI or a FastAPI background task.
- Topic and interest evidence in matching.
- Citation analytics, collaboration graph and ranking-framework indicators (later phases).
