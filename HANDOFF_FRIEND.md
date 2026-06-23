# Handoff — Dashboard solve feature + hosting + PDF upload

For the Firebase-hosting maintainer. Read this before/after pulling `main`.

## 1. What changed on the Flask dashboard side (already in this PR)

- **Solve buttons** in the course modal (Verification tab): per-attribute green ✓ Solve ticks, a **Solve all** button, and a **Solved** button for broken-site courses. Solving marks the course Verified when no open issues remain.
- **Open Issues** KPI card (decrements on every solve).
- **Real-time for multiple users**: dashboard polls `/api/data.json` every 5s; solves persist to Firestore + `1.json` + `public/api/data.json`.
- New endpoint: `POST /api/course/<id>/solve` body `{ "attr": "Cost" | "_all" | "_website", "unsolve": false }`.
- **CORS** is now enabled on the Flask API (`Access-Control-Allow-Origin: *`, or `CORS_ALLOW_ORIGIN` env to lock it down). This lets the Firebase-hosted static site call the Flask API cross-origin.
- **PDF upload** (`POST /api/upload`) now also sets `issue_category` (`course_issue` / `verified`) so uploaded discrepancies flow into Open Issues and become solvable per-attribute.

## 2. Hosting — what was fixed

Both Firebase Hosting workflows were failing on **every** PR/merge because they ran `npm ci && npm run build` but the repo has **no `package.json`** (the site is a pure static `public/` directory). Fixed both to skip the npm build step and deploy `public/` as-is:

- `.github/workflows/firebase-hosting-pull-request.yml` (PR preview)
- `.github/workflows/firebase-hosting-merge.yml` (live deploy on push to `main`)

The deploy still uses `FirebaseExtended/action-hosting-deploy@v0` with project `aakyarepatse` and your `FIREBASE_SERVICE_ACCOUNT_AAKYAREPATSE` secret — untouched.

## 3. What the Firebase-hosted static site still needs (your side)

The hosted site (`public/index.html` + `public/static/app.js`) was **intentionally not modified**. It currently reads the static `public/api/data.json`, so it does **not** get live solves or the Solve buttons. To make the hosted site real-time + solvable, pick one:

**Option A — point the hosted site at the Flask API (recommended, simplest):**
1. In `public/static/app.js`, change the data fetches from `/api/data.json` (static) to the live Flask API URL, e.g. `https://<your-flask-host>/api/data.json`. Add a configurable base: `const API = window.__API_BASE__ || 'https://<your-flask-host>'`.
2. Add the same Solve buttons + `solveCourse()` logic from `static/app.js` (the Flask dashboard copy in this repo) into `public/static/app.js`.
3. CORS is already enabled on the Flask side, so cross-origin `fetch` to `/api/course/<id>/solve` will work.
4. Rebuild/redeploy Firebase hosting (happens automatically on merge to `main`).

**Option B — read Firestore directly with the Firebase JS SDK:**
Add the Firebase JS SDK to `public/index.html`, listen to the `courses` collection (real-time `onSnapshot`), and render. Solves write to Firestore already, so this gives true real-time without polling. More work, but no dependency on the Flask host being up.

## 4. PDF upload usage

- Endpoint: `POST /api/upload` with multipart field `files[]` (one or more PDFs).
- Each PDF page is parsed for a course ID + an attribute MATCH/FALSE table; matched courses in the DB are updated with `cost_match`, `duration_match`, … and `issue_category`.
- After upload, courses with mismatches appear in **Open Issues** and can be solved per-attribute in the modal.
- This runs on the Flask dashboard only. If you want upload from the hosted static site, point it at `POST <flask-host>/api/upload` (CORS is enabled).

## 5. Merge + deploy order

1. Merge this PR (`feat/dashboard-solve-issues` → `main`).
2. `git pull origin main` locally.
3. Run the Flask dashboard (`python dashboard.py`) — Solve buttons only work there (they hit the Flask API).
4. On merge to `main`, the Firebase Hosting live deploy runs automatically (now without the broken npm step).
5. Apply Option A or B above to make the hosted static site real-time.

## 6. Notes / gotchas

- Solve buttons work **only where the Flask API is reachable**. The static Firebase site by itself has no backend.
- `CORS_ALLOW_ORIGIN` defaults to `*`. Set it to your hosted site origin in the Flask host's env for production lockdown.
- The `public/api/data.json` static snapshot is rewritten by the Flask server on every solve/upload, but the hosted site only serves the version that was deployed — so without Option A/B the hosted numbers are stale until the next deploy.