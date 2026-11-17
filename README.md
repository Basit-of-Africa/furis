# FURIS: Fountain University Research Intelligence System

This repository holds the MVP foundation from the project brief (§24, steps 4–7):

- the database schema
- the FastAPI backend
- the discovery, matching, deduplication and attribution engine
- the verification API
- pilot evaluation against a ground-truth dataset

It also includes the Next.js web app (§11.2 Layer 1), which has two parts:

- **Research Desk** (`/desk`, sign-in required): where the Research Desk officer, and later the team, discovers, verifies and manages publications.
- **Public research view** (`/`, no sign-in): where researchers and visitors see confirmed publications and confirmed Fountain University output. Researchers don't need accounts.

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

**Research Desk** (`/desk`)

| Page | What it does |
|---|---|
| Dashboard | Headline counts, confirmed FU output by year (chart plus table view), output by faculty, ORCID coverage, search-run health |
| Review queue: Authorship | Candidates sorted by confidence, with the evidence behind each match. The officer confirms or rejects each one and notes how it was checked. |
| Review queue: Attribution | Confirmed authorships still awaiting an attribution decision. Confirming FU output needs written evidence. |
| Publications and publication detail | Evidence, authors, affiliation text as published, per-source citation counts, decision history |
| Researchers and researcher profile | Registry, CSV import, identifiers, employment history, name variants, "Run discovery" |
| Duplicates | Possible duplicates side by side; merge or keep separate |
| Team (Super Administrator only) | Add team members, reset passwords, deactivate accounts |
| Your account | Change your password |

**Public research view** (`/`)

| Page | What it shows |
|---|---|
| Overview | Confirmed FU output count, by year and by faculty; recent output |
| Publications | Confirmed FU output, or every confirmed researcher publication; search and filters |
| Researchers | Researchers with at least one confirmed publication |
| Researcher | Their confirmed publications, split into FU output and other work (for example, from before joining FU) |

The public view never shows candidates, rejected matches, evidence, decision history, emails, staff numbers or employment dates. Turn it off with `FURIS_PUBLIC_VIEW=false`.

## Signing in

Only the Research Desk team signs in. There are two ways, chosen with `FURIS_AUTH_MODE`.

**`password` (default for deployment).** Research Desk accounts with passwords; no external provider is needed.

1. Set `FURIS_BOOTSTRAP_ADMIN_EMAIL` and `FURIS_BOOTSTRAP_ADMIN_PASSWORD` (12+ characters) on the API.
2. The first sign-in with exactly those details creates that account as Super Administrator and asks for a new password.
3. After that the account's own password applies, and the bootstrap settings can be removed.
4. The Super Administrator adds team members on the **Team** page. FURIS shows each new member a temporary password once, and they choose their own at first sign-in.

Passwords are stored as scrypt hashes. Five wrong attempts lock the account for 15 minutes. Changing or resetting a password ends that account's other sessions.

**`oidc`.** University single sign-on, if you'd rather use Google accounts later (see below).

`dev_header` (email only, no password) is for local development. The API refuses to start with it on Vercel or in production.

### Single sign-on (optional)

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

- On Vercel or in production, the API refuses to start unless sign-in is `password` or `oidc`, with a session secret of at least 32 characters.
- In `password` mode it refuses a bootstrap password shorter than 12 characters, or only one of the two bootstrap settings.
- In `oidc` mode it refuses to start without an allowed email domain.
- Dev sign-in (`FURIS_AUTH_MODE=dev_header`, email only, no password) exists for local development. In that mode the login page shows a warning.

## Deploying on Vercel and Neon

FURIS runs as two Vercel projects from this one repository, sharing one Neon database. Discovery runs on GitHub Actions, because Vercel stops long jobs partway.

```
Browser ─► Portal (Vercel, frontend/) ─► API (Vercel, backend/) ─► Neon (PostgreSQL)
                                                                      ▲
                       GitHub Actions: queued + weekly discovery ─────┘
```

**1. Neon.** Create the database, or use the one the Vercel integration created. You need two connection strings from the Neon console:

| String | Used by | Recognise it by |
|---|---|---|
| **Pooled** | The API | Host contains `-pooler` |
| **Direct** | Migrations and discovery jobs | Host without `-pooler` |

**2. GitHub secrets.** In the repository's Settings → Secrets and variables → Actions:

| Name | Type | Value |
|---|---|---|
| `NEON_DATABASE_URL` | Secret | the **direct** string |
| `FURIS_CONTACT_EMAIL` | Variable | a Research Office mailbox (optional; gives faster OpenAlex and Crossref access) |

**3. Create the tables.** In the Actions tab, run **Database migrations** with *Run workflow*. Run it again whenever a change adds a migration.

**4. First administrator.** Nothing to do in the database: the first sign-in with the bootstrap settings from step 5 creates the account.

**5. API project on Vercel.** Import the repository with **Root Directory `backend`**.
- Attach the Neon integration to **this** project. The API reads its `DATABASE_URL` variable, the pooled string.
- Set these environment variables:

  | Variable | Value |
  |---|---|
  | `FURIS_ENVIRONMENT` | `production` |
  | `FURIS_AUTH_MODE` | `password` |
  | `FURIS_SESSION_SECRET` | a long random value |
  | `FURIS_BOOTSTRAP_ADMIN_EMAIL` | the Research Desk officer's email |
  | `FURIS_BOOTSTRAP_ADMIN_PASSWORD` | a temporary password of 12+ characters, replaced at first sign-in |
  | `FURIS_BOOTSTRAP_ADMIN_NAME` | optional; the officer's name |

- Generate the session secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`, or any password manager's 48-character generator.
- The API refuses to start on Vercel without a sign-in mode and a session secret.
- On Vercel, "Run discovery" automatically queues the job instead of running it.

**6. Web app project on Vercel.** Import the repository again with **Root Directory `frontend`**. Don't attach Neon here; the web app never talks to the database. Set these environment variables:

| Variable | Value |
|---|---|
| `FURIS_API_URL` | the API project's address |
| `APP_URL` | the web app's address |

Then:
- The public research view is at `/`.
- The officer signs in at `/desk`.
- Once the officer has chosen their own password, remove the two `FURIS_BOOTSTRAP_ADMIN_*` variables from the API project.

**7. Single sign-on, only if you switch to it later.** Add the `OIDC_*` variables to the web app and `https://<web app address>/auth/callback` to the provider's redirect URIs (see *Single sign-on*).

**8. Start discovery straight away (recommended).** Without this, "Run discovery" waits for GitHub's hourly schedule, which can run late or be skipped.
1. In GitHub, go to your profile → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Set **Repository access** to *Only select repositories* → `furis`.
3. Under **Permissions → Repository permissions**, set **Actions** to *Read and write*. Leave everything else as *No access*.
4. Choose an expiry (for example, one year) and generate the token.
5. On the **backend** Vercel project, add the token as `FURIS_GITHUB_TOKEN`, then redeploy.

Then "Run discovery" starts the GitHub job immediately, and results usually arrive within a few minutes.

**9. Discovery.** The **Discovery** workflow processes queued requests every hour and rediscovers everyone on Mondays. You can also start it by hand from the Actions tab.
- Job logs are public, because this repository is public. The command-line tool keeps staff names out of them.
- GitHub pauses scheduled workflows after 60 days without repository activity. Re-enable it from the Actions tab if that happens.

**Local development** still uses `backend/.env`, with `FURIS_DATABASE_URL` and `FURIS_DATABASE_URL_DIRECT` (Neon's `DATABASE_URL` and `DATABASE_URL_UNPOOLED` are also accepted), and then `alembic upgrade head`.

## Before the pilot

- [ ] **Set the Fountain University identifiers.** Put the verified OpenAlex institution ID and ROR ID in `FURIS_FU_OPENALEX_INSTITUTION_IDS` and `FURIS_FU_ROR_IDS`. Until then, FU affiliation is detected from affiliation text only.
- [ ] **Set the contact address.** Set `FURIS_CONTACT_EMAIL` to a Research Office mailbox, and add `FURIS_OPENALEX_API_KEY` if you have one.
- [ ] **Set up sign-in.** Deploy with `FURIS_AUTH_MODE=password` and the bootstrap settings (see *Signing in*), then remove the bootstrap settings once the officer has chosen a password.
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
- Topic and interest evidence in matching.
- Citation analytics, collaboration graph and ranking-framework indicators (later phases).
