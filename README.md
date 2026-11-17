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
| Audit (§21) | Every write endpoint records an entry in `audit_logs`. |

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

The API docs are then at `http://localhost:8000/docs`. Send `X-User-Email: ro@fuo.edu.ng` with each request.

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

**Sign-in is development-only.** The portal stores the user's email in an httpOnly cookie and forwards it as `X-User-Email`. Replace this with university SSO in `frontend/src/lib/api.ts`, `frontend/src/app/actions.ts` and `backend/furis/api/deps.py` at the same time.

## Neon (§11.4)

1. Create the project `furis-production` with the database `furis_db` and two branches, `main` and `development`.
2. Copy `backend/.env.example` to `backend/.env`. Set `FURIS_DATABASE_URL` to the **pooled** string and `FURIS_DATABASE_URL_DIRECT` to the **direct** string, which Alembic uses.
3. Run `alembic upgrade head`.

## Before the pilot

- [ ] **Set the Fountain University identifiers.** Put the verified OpenAlex institution ID and ROR ID in `FURIS_FU_OPENALEX_INSTITUTION_IDS` and `FURIS_FU_ROR_IDS`. Until then, FU affiliation is detected from affiliation text only.
- [ ] **Set the contact address.** Set `FURIS_CONTACT_EMAIL` to a Research Office mailbox, and add `FURIS_OPENALEX_API_KEY` if you have one.
- [ ] **Replace dev authentication.** `FURIS_AUTH_MODE=dev_header` trusts a request header. Replace `api/deps.py::current_user` with university SSO/OIDC before real staff data goes on a reachable server.
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
