# Plan: Bug fixes, UI updates, and Smart Solve Suggestions

## Scope
Update the **infinityfree/** dashboard and keep the **public/static** + **templates/** v6 dashboard in sync so the feature does not regress on the next deploy.

> Note: the two codebases have diverged (infinityfree is a simpler sidebar dashboard; public/static/templates are v6 with map/analytics/upload). The same suggestion engine can be shared; only the UI shell differs.

---

## Part 1 — Bug fixes

### infinityfree/ frontend
1. **Missing `config.js` reference** — `index.html` loads `config.js?v=5`, but the file does not exist. Remove the `<script>` tag to avoid a 404.
2. **Broken optimistic-update revert in `solveAttr`** — On save failure the code runs `Object.assign(c, { solved_attrs: c.solved_attrs, status: c.status })`, which rewrites the already-mutated values. Save the original state before the optimistic update and restore it on failure.
3. **Wrong debounce timer in Solved tab search** — `initFilters` reuses `cfTimer` for `sf-search`. Give Solved tab its own `sfTimer`.
4. **Incorrect empty-state `colspan`** — `vf-tbody` empty cell uses `colspan="7"` but the table has 10 columns; `cf-tbody` uses 8 for 10 columns; `sf-tbody` uses 7 for 9 columns. Align with actual column counts.
5. **Missing top-bar search element** — `initTopbarExtras()` expects `#topbar-search`, but the HTML has none. Add a top-bar global search input so the existing wiring works.
6. **Stale comments** — Comments in `fetchAllCourses()` still say "Vercel API"; update to "Cloudflare Worker" to match the actual `API_BASE_URL`.

### worker/ API
7. **Incomplete MongoDB fallback projection** — When KV is empty, `/api/get_courses` falls back to MongoDB with a projection that omits `pdf_page`, `cost`, `duration`, `mode`, `pdf_table`, and `solved_attrs`. The infinityfree dashboard breaks in that fallback. Expand the projection to include every field the dashboard reads.
8. **CORS header bug in `/api/pending_solves`** — The response spreads the `corsHeaders` function object instead of calling it (`...corsHeaders` vs `...corsHeaders()`). Fix the spread.

---

## Part 2 — UI updates

1. **Top-bar global search** — Add a compact search input to the top bar (left of the theme button). It will route to the All Courses tab and set the search filter, reusing the existing `initTopbarExtras` logic.
2. **Theme-aware polish** — Minor spacing/border-radius tweaks for the new top-bar controls so they match the existing glassmorphic style.

---

## Part 3 — Smart Solve Suggestions feature

### Goal
After a user resolves one or more attributes in a course, show a popup saying the same course exists on a different page / in a different domain (e.g. "Free" vs "Bachelor's Degree") with the same unresolved issue. The user can jump straight to that duplicate and solve it.

### Matching rules (approved)
A "duplicate course" matches when:
- Normalized `name` is the same
- Normalized `university` is the same
- Normalized `country` is the same
- AND (`pdf_page` differs OR `domain` differs)
- AND the duplicate still has an unsolved mismatching attribute whose name matches one of the attributes the user just resolved
- AND duplicate status is not already `Verified`

### Toggle (approved location: top bar)
- Add a toggle switch next to the theme button labelled "Suggest duplicates".
- Persist state in `localStorage` (`cv_suggest_duplicates`).
- When OFF: no popup is ever shown.
- When ON: popup appears after every successful solve that produces at least one eligible duplicate suggestion.

### Suggestion popup
- Modal/overlay titled "Same course also appears here".
- Shows a list of duplicates with: page number, domain, issue type, and a "Solve this too" button.
- Clicking an item opens that course's detail modal pre-scrolled to the matching attribute.
- Includes "Dismiss" and a secondary "Open all in Verification" link (filters the Verification tab to the same name).

### Integration points
- Hook into `solveAttr()` and `solveAll()` **after** a successful `mongoUpdateCourse()` call.
- Compute suggestions client-side from `allCourses` (no backend change required).
- If suggestions exist and the toggle is ON, render the popup; otherwise continue silently.

### State additions
```js
let suggestDuplicates = localStorage.getItem('cv_suggest_duplicates') !== 'false';
```

### v6 dashboards (public/static, templates)
- Port the same suggestion engine, toggle, and popup into `public/static/app.js` and `templates/index.html` (or the shared build output), adapting styling to the v6 navbar and modal system.

---

## Files to touch

| File | Change |
|------|--------|
| `infinityfree/index.html` | Remove `config.js`; add top-bar search + toggle |
| `infinityfree/style.css` | Style search, toggle, suggestion modal |
| `infinityfree/app.js` | Bug fixes + suggestion engine + popup logic |
| `worker/index.js` | Fix projection + CORS spread |
| `public/static/app.js` | Port bug fixes + suggestion engine |
| `public/static/style.css` | Port toggle + popup styles |
| `templates/index.html` | Port top-bar toggle markup |

---

## Open questions before implementation
None — all user decisions above were confirmed.

## Order of work
1. Fix worker projection + CORS bug.
2. Fix infinityfree bugs.
3. Add top-bar search + toggle UI.
4. Build suggestion engine and popup in infinityfree.
5. Port to public/static and templates.
6. Test against the `test5/test1.json` sample shape.

## Estimation
Small-to-medium change: ~4–6 files in infinityfree plus 3 ported files. Purely additive for the feature; no schema or backend API changes beyond the worker bug fixes.
