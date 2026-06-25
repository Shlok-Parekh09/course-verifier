export const meta = {
  name: 'analytics-max',
  description: 'Maximize the Analytics tab: professional, emoji-free, new features, built in parallel',
  phases: [
    { title: 'Design', detail: 'parallel feature proposals across analytics dimensions' },
    { title: 'Synthesize', detail: 'one cohesive implementation spec + data contract' },
    { title: 'Implement', detail: 'backend + frontend-logic + markup/style in parallel (disjoint files)' },
    { title: 'Verify', detail: 'compile, syntax, emoji scan, ID/contract consistency' },
  ],
}

// ---- Shared context the agents need (current state, gathered by scouting) ----
const CTX = `
PROJECT: course-verifier (Flask dashboard). Working dir: C:\\\\Users\\\\meena shah\\\\Desktop\\\\course-verifier
GOAL: Maximize the Analytics tab. HARD CONSTRAINTS: (1) NO emoji anywhere in the Analytics tab — not in labels, headers, sub-tab buttons, KPI icons, insight cards, table headers, drilldown titles, search icons, close buttons, empty-states, tooltips. Replace every emoji with professional text/typography (initials, small caps labels, CSS shapes, or nothing). (2) Professional, polished, consistent — treat this as a business intelligence product. (3) Preserve all existing correct behavior and non-analytics code. (4) Do NOT touch files outside your assigned set.

CURRENT ANALYTICS BACKEND (dashboard.py):
- build_analytics_data() at dashboard.py ~lines 1047-1156. Returns dict:
  { course_category:{level:count}, pricing_category:{Free/Affordable/Mid/Premium:count}, variant_category:{Indian/International/Total Variants:count}, domain_pivot:{domain:{Total,Indian,International}}, country_pivot:{country:count} }
- It parses CombinedWork.xlsx (columns: Course name, Country, Course Type, Fees) and autonomous_verified_link_compile.pdf.json (list of variants each {country, domain, ...}).
- get_level() maps Course Type -> canonical degree labels: "Bachelor's Degree","Master's Degree","Diploma","Post Graduate Certificate","Post Graduate Diploma","Certificate","Other".
- parse_fee_tier() buckets Fees (INR): Free(0/free-text), Affordable<=50000, Mid<=200000, Premium>200000.
- api_analytics() at ~1159 returns jsonify({"status":"success","data":build_analytics_data()}) at /api/analytics and /api/analytics.json.
- build_analytics_data() powers the /api/analytics route (Firebase / public static exports were removed).
- global_courses (3727 docs) each has fields like: id, name, university, country, domain, status (Verified/Discrepancy/Error/Unverified), disc_reason, issue_category (verified/course_issue/website_issue), issue_sub_type, cost, fees, duration, mode, language, skills, has_nirf_badge, has_qs_badge, pdf_page, pdf_table, solved_attrs, cost_match, duration_match, mode_match, lang_match, country_match, uni_match, sk_match.
- /api/data.json (api_data) returns: stats{total,verified,discrepancies,errors,unverified,website_issues,course_issues,open_issues}, country_counts, country_status{country:{total,verified,discrepancies,errors}}, domain_counts(normalized), recent[courses with status in Discrepancy/Error], etc.
- rankings.db (SQLite) exists in the project — likely has university ranking data (QS/NIRF). Inspect it to power ranking intelligence.

CURRENT ANALYTICS FRONTEND (static/app.js analytics section ~lines 1122-1737):
- State: anCredentialChart, anPricingChart, anDomainChart, anStatusChart, analyticsData, lastAnalyticsHash, geoTableData. PALETTE, STATUS_COLORS.
- initAnalyticsSubTabs() — generic: queries .asubtab buttons (data-atab) and .atab-content divs; toggles active. Also wires #an-country-search input.
- populateAnalyticsKPIs(d, globalStats, ccOverride) -> sets #an-total,#an-indian,#an-intl,#an-matchrate,#an-variants-sub,#an-indian-pct,#an-countries-count,#an-verified-sub,#an-free,#an-free-sub.
- populateInsightCards(d, globalData) -> #insight-cards-row. CURRENTLY USES EMOJI icons: 🏆⚠️🌍🔬🏛️🚨 — MUST replace with professional non-emoji cards.
- populateSplitVisual(indianPct) -> #an-split-visual. CURRENTLY uses 🇮🇳 🌐 — remove.
- populateCredentialChart(courseCategory) -> #an-credential-chart doughnut + #an-credential-legend. onClick -> openAnalyticsDrilldownByCategory(label) -> jumpToCourses({domain:label}).
- populatePricingChart(pricingCategory) -> #an-pricing-chart bar. onClick -> jumpToCourses({search:firstword}).
- populateAnTopCountries(countryPivot) -> #an-top-countries hub list.
- countryStatusFor(name) reads globalData.country_status. renderGeoTable(search) -> #an-country-tbody. geoRowDrilldown(name,cnt) -> #geo-drilldown using globalData.recent.
- populateDomainTab(domainPivot) -> #an-domain-chart bar + #an-domain-tbody. domainRowDrilldown -> #dom-drilldown (uses 🚨/🔬 emoji — remove).
- populateVerificationTab(stats, recent) -> #verif-kpi-row, #an-status-chart doughnut, #an-disc-reasons (uses ✅ in empty-state — remove), #an-verif-country-tbody from country_status.
- renderAnalytics(d) orchestrates all of the above, merging analyticsData with globalData (effectiveCountryPivot, effectiveDomainPivot, effectiveCourseCategory fallbacks).
- fetchAnalyticsPayload(), fetchAnalytics(), refreshAnalyticsInBackground() — cached instant render + background refresh.
- initAnalyticsSubTabs() is called in DOMContentLoaded (~line 1803); fetchAnalytics chained after fetchData (~1806).
- Helpers available globally: el helpers, escHtml, escJs, getBadgeClass, getFlag(country), statusBadge(s), isValidCountry, jumpToCourses({search/domain/country/status}), getDomainCategory, openDrilldown/closeDrilldown.

CURRENT ANALYTICS MARKUP (templates/index.html ~lines 354-636):
- #tab-analytics > .analytics-wrap. Header .analytics-page-hdr with .analytics-icon (📊 — remove), h2 "Course Analytics", p. Subnav #analytics-subnav with .asubtab buttons: "📋 Overview"(atab-overview), "🌍 Geography"(atab-geography), "🔬 Specializations"(atab-domains), "✅ Verification"(atab-verification).
- .analytics-kpi-row: 4 .a-stat-card (a-blue/a-green/a-purple/a-orange) each with .a-stat-icon (📚🇮🇳🌐✅ — remove) + .a-stat-body(.a-stat-val #an-* , .a-stat-label, .a-stat-sub #an-*).
- atab-overview: #insight-cards-row; .an-overview-grid with cards: Academic Credential Mix (#an-credential-chart + #an-credential-legend), India vs World (#an-split-visual + #an-top-countries + .an-cta-btn), Cost-Access Intelligence (#an-pricing-chart).
- atab-geography: .an-section-hdr + search (.an-search-icon 🔍 — remove) + table (#an-country-tbody) + #geo-drilldown panel (close button ✕ — remove).
- atab-domains: Domain Saturation card (#an-domain-chart, title has 📊 — remove) + domain table (#an-domain-tbody, headers 🇮🇳🌐✅⚠️ — remove) + #dom-drilldown.
- atab-verification: .verif-kpi-row #verif-kpi-row + grid: Verification Status Breakdown (#an-status-chart), Top Discrepancy Reasons (#an-disc-reasons, title ⚠️ — remove), Verification Rate by Country table (#an-verif-country-tbody, headers ✅⚠️❌ — remove) + #verif-drilldown.
- Cache-buster: index.html references /static/app.js?v=12 and /static/style.css?v=10. The markup agent MUST bump app.js to ?v=13 so the new JS loads.
- analytics CSS classes live in static/style.css (e.g. .analytics-wrap, .a-stat-card, .an-card, .an-badge, .an-legend-item, .an-hub-row, .geo-*, .dom-*, .verif-kpi-card, .disc-reason-*, .drilldown-panel, etc.). Reuse the existing dark/light CSS-variable theme (var(--green)/--accent/--red/--blue/--purple/--bg-hover/--text-1/2/3). Do not invent a new color system.

NEW FUNCTIONALITY TO CONSIDER (design agents — pick the best, you are not limited to these):
- Rankings intelligence from rankings.db (QS/NIRF badge / rank per university) -> university leaderboard, ranked-vs-unranked credential mix.
- Affordability / Cost-Access Index (numeric score), median fee, fee distribution histogram.
- Specialization Saturation Index (concentration), Geographic Concentration (Herfindahl-Hirschman over countries).
- Data-Quality Health score (verified rate, error rate, completeness).
- Verification Quality Score per country / domain / credential level (heatmapped table).
- Discrepancy reason Pareto / clustering (top reasons, reason-to-attribute mapping from pdf_table/disc_reason).
- Credential ladder analysis: level -> avg cost, level -> verification rate, level -> India/Intl split.
- Comparative benchmark panel: India vs International across many metrics side by side.
- Cross-cutting FILTERS in the Analytics tab (by credential level, country, cost tier) that recompute all charts client-side.
- Export analytics snapshot (CSV/JSON download) and a print-friendly summary.
- Top universities leaderboard; per-university verification rate.
- Anomaly/outlier flags (outlier fees, outlier low/high verification rates).
- A "Key Findings" / executive summary auto-narrative panel (professional text, no emoji).
- Trend-over-time if any timestamp/iteration data exists (inspect).
`;

const FEATURE_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    features: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          purpose: { type: 'string' },
          chart_type: { type: 'string', description: 'doughnut|bar|line|table|kpi|score-gauge|heatmap|narrative|none' },
          element_id: { type: 'string', description: 'proposed unique DOM id, prefixed with "an-"' },
          professional_copy: { type: 'string', description: 'exact no-emoji label/sublabel text' },
          data_fields: { type: 'array', items: { type: 'string' }, description: 'JSON field names this feature consumes from /api/analytics or /api/data' },
        },
        required: ['name', 'purpose', 'chart_type', 'element_id', 'professional_copy', 'data_fields'],
      },
    },
    new_data_fields: {
      type: 'array',
      description: 'New fields build_analytics_data must produce to power these features',
      items: {
        type: 'object',
        properties: {
          field: { type: 'string' },
          source: { type: 'string', description: 'CombinedWork.xlsx | variants json | global_courses | rankings.db | derived' },
          computation: { type: 'string' },
        },
        required: ['field', 'source', 'computation'],
      },
    },
    emoji_to_remove: { type: 'array', items: { type: 'string' }, description: 'specific emoji currently used in this dimension that must go' },
    notes: { type: 'string' },
  },
  required: ['dimension', 'features', 'new_data_fields', 'emoji_to_remove', 'notes'],
};

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    py_compile_ok: { type: 'boolean' },
    js_syntax_ok: { type: 'boolean' },
    emoji_violations: { type: 'array', items: { type: 'string' }, description: 'file:line of any emoji remaining in the analytics tab' },
    id_mismatches: { type: 'array', items: { type: 'string' }, description: 'element ids referenced in app.js but missing in index.html analytics section, or vice versa' },
    data_field_mismatches: { type: 'array', items: { type: 'string' }, description: 'fields app.js reads from analytics data that build_analytics_data does not produce' },
    analytics_json_fields: { type: 'array', items: { type: 'string' }, description: 'top-level keys present in the live /api/analytics.json data after the change' },
    style_class_issues: { type: 'array', items: { type: 'string' } },
    overall_ok: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
  },
  required: ['py_compile_ok', 'js_syntax_ok', 'emoji_violations', 'id_mismatches', 'data_field_mismatches', 'analytics_json_fields', 'overall_ok', 'issues'],
};

// ---- Phase 1: Design (parallel proposals) ----
phase('Design');
const DIMS = [
  { key: 'overview-cost', prompt: `You are a BI design agent for the Analytics OVERVIEW + COST-ACCESS dimension of a course-verification dashboard. Propose professional, emoji-free enhancements and NEW features for: the KPI strip, the auto-insight cards, the India-vs-World split, the Cost-Access chart, and a new executive "Key Findings" narrative. Suggest new cost metrics (affordability index, median fee, fee histogram, free-vs-paid ratio). Return structured features + the new backend data fields needed. CONTEXT:\n${CTX}` },
  { key: 'geography', prompt: `You are a BI design agent for the Analytics GEOGRAPHY dimension. Propose professional, emoji-free enhancements + NEW features for: the geographic footprint table, country drilldown, and new geography intelligence (concentration/Herfindahl index, regional groupings, top/most-problematic countries, per-country quality score, a comparative country comparison). Return structured features + new backend data fields. CONTEXT:\n${CTX}` },
  { key: 'verification-quality', prompt: `You are a BI design agent for the Analytics VERIFICATION & QUALITY dimension. Propose professional, emoji-free enhancements + NEW features for: verification KPIs, status doughnut, discrepancy-reason Pareto/clustering, verification-rate-by-country table, and new quality intelligence (data-quality health score, reason-to-attribute mapping, anomaly/outlier flags, verification quality score per country/domain). Return structured features + new backend data fields. CONTEXT:\n${CTX}` },
  { key: 'credential-academic', prompt: `You are a BI design agent for the Analytics CREDENTIAL & ACADEMIC dimension (Specializations sub-tab + credential mix). Propose professional, emoji-free enhancements + NEW features for: domain/specialization table+chart, credential mix doughnut, and new academic intelligence (credential ladder: level->avg cost, level->verification rate, level->India/Intl; specialization saturation index; top universities leaderboard). Return structured features + new backend data fields. CONTEXT:\n${CTX}` },
  { key: 'novel-rankings-filters-export', prompt: `You are a BI design agent for NOVEL Analytics features. Propose professional, emoji-free NEW features that elevate this to a true BI product: (a) rankings intelligence from rankings.db (inspect the SQLite schema first — university QS/NIRF ranks/badges -> ranked-vs-unranked mix, university leaderboard), (b) cross-cutting client-side FILTERS in the Analytics tab (by credential level, country, cost tier) that recompute all charts, (c) export snapshot (CSV/JSON download) + print-friendly summary, (d) comparative India-vs-International benchmark panel across many metrics, (e) any other high-value novel analytics. Return structured features + new backend data fields. CONTEXT:\n${CTX}` },
];
const proposals = (await parallel(DIMS.map(d => () => agent(d.prompt, { label: `design:${d.key}`, phase: 'Design', schema: FEATURE_SCHEMA })))).filter(Boolean);
log(`Design: ${proposals.length}/${DIMS.length} dimension proposals returned`);

// ---- Phase 2: Synthesize one cohesive spec / data contract ----
phase('Synthesize');
const spec = await agent(
  `You are the Analytics lead. Merge these dimension proposals into ONE cohesive, professional, emoji-free implementation spec for the Analytics tab. CONTEXT:\n${CTX}\n\nPROPOSALS (JSON):\n${JSON.stringify(proposals, null, 2)}\n\nProduce a detailed spec that BOTH the backend and frontend will implement against. It MUST include:\n1. FINAL SUB-TAB STRUCTURE (keep Overview/Geography/Specializations/Verification; add new sub-tabs only if clearly justified — name them with professional no-emoji text and give their data-atab id).\n2. For EACH chart/KPI/table/narrative: exact DOM element id (prefix an-), chart type, exact professional no-emoji label + sublabel, and the JSON data fields it consumes.\n3. THE DATA CONTRACT: the exact JSON object build_analytics_data() must return (every top-level key + nested shape), including all NEW fields needed by the new features. Be explicit about field names and types so backend and frontend agree.\n4. Which existing analytics functions in app.js to KEEP vs REWRITE vs ADD, and the new function names.\n5. The exact list of every emoji currently in the analytics tab that must be removed, and the professional replacement for each.\n6. CSS notes: which new classes to add to style.css and which existing ones to restyle (reuse the CSS-variable theme; no emoji).\n7. Keep it realistic: only require data that can actually be computed from CombinedWork.xlsx, the variants json, global_courses, country_status, and rankings.db. Note any feature that should gracefully no-op when its source is missing.\n8. Preserve existing correct behaviors: credential doughnut drilldown -> jumpToCourses({domain}); pricing bar drilldown -> jumpToCourses({search}); geo/domain/verif drilldowns using globalData.recent and country_status.\nReturn the spec as a single well-structured markdown document (this string is passed verbatim to the implementers).`,
  { label: 'synthesize', phase: 'Synthesize', effort: 'high' }
);
log('Synthesize: implementation spec produced');

// ---- Phase 3: Implement in parallel on DISJOINT files ----
phase('Implement');
const [backend, frontend, markup] = await parallel([
  () => agent(
    `BACKEND IMPLEMENTER. Edit ONLY dashboard.py. Do not touch any other file.\nYour job: make build_analytics_data() (and any new helper functions you add near it) produce EXACTLY the data contract in the spec. Inspect rankings.db (sqlite3) schema if the spec needs ranking fields. Use global_courses, CombinedWork.xlsx, autonomous_verified_link_compile.pdf.json, and country_status-style logic as sources. Keep the canonical degree labels and fee tiers exactly as they are unless the spec changes them. Gracefully no-op (empty/zero) any new field whose source file is missing so the route never 500s. When done, run: python -c "import py_compile; py_compile.compile('dashboard.py', doraise=True)" and fix until it passes. Then run a quick test: python -c "import dashboard, json; print(list(json.loads(dashboard.app.test_client().get('/api/analytics.json').get_data())['data'].keys()))" to confirm the new top-level keys are present. Return a concise summary of the fields you added/changed and the test output.\n\nIMPLEMENTATION SPEC:\n${spec}\n\nCONTEXT:\n${CTX}`,
    { label: 'impl:backend', phase: 'Implement', effort: 'high' }
  ),
  () => agent(
    `FRONTEND-LOGIC IMPLEMENTER. Edit ONLY static/app.js. Do not touch index.html, style.css, or dashboard.py.\nYour job: REWRITE the analytics section of app.js (roughly lines 1122-1737) to implement the spec — professional, ZERO emoji anywhere, polished. Keep the orchestration (renderAnalytics/fetchAnalytics/fetchAnalyticsPayload/refreshAnalyticsInBackground) and the initAnalyticsSubTabs wiring (it is generic for .asubtab/.atab-content; support any new sub-tabs the spec adds by ensuring their markup uses data-atab + matching ids — the markup agent adds those). Implement every new feature renderer the spec calls for, consuming EXACTLY the data-contract field names from the spec. Preserve existing correct behaviors (credential doughnut onClick -> openAnalyticsDrilldownByCategory -> jumpToCourses({domain}); pricing bar onClick -> jumpToCourses({search}); geo/domain/verif drilldowns from globalData.recent + country_status). Replace ALL emoji (insight card icons 🏆⚠️🌍🔬🏛️🚨, split 🇮🇳🌐, domain 🚨🔬, empty-state ✅, etc.) with professional non-emoji equivalents (initials/labels/CSS shapes/nothing). Do NOT break other tabs or non-analytics code. When done, run: node --check static/app.js (or node -c) and fix any syntax error. Return a concise summary of functions added/rewritten and the syntax-check result.\n\nIMPLEMENTATION SPEC:\n${spec}\n\nCONTEXT:\n${CTX}`,
    { label: 'impl:frontend', phase: 'Implement', effort: 'high' }
  ),
  () => agent(
    `MARKUP + STYLE IMPLEMENTER. Edit ONLY templates/index.html and static/style.css. Do not touch app.js or dashboard.py.\nYour job: rewrite the Analytics tab markup (index.html ~lines 354-636) and the analytics styles in style.css to implement the spec — professional, ZERO emoji anywhere (remove 📋🌍🔬✅📊🇮🇳🌐📚🔍✕⚠️❌🏆🚨🏛️🔬 and any others; replace with professional text/typography/CSS shapes). Add every canvas/table/KPI/narrative element with the EXACT element ids the spec defines, and add any new sub-tabs (with data-atab + matching .atab-content ids). Bump the app.js cache-buster in index.html from ?v=12 to ?v=13 so the new JS loads (the <script src="/static/app.js?v=..."> tag). Add/restyle analytics CSS classes per the spec, reusing the existing CSS-variable dark/light theme — no new color system, no emoji. Keep the rest of index.html and style.css intact. Return a concise summary of the markup + style changes and confirm the cache-buster bump.\n\nIMPLEMENTATION SPEC:\n${spec}\n\nCONTEXT:\n${CTX}`,
    { label: 'impl:markup', phase: 'Implement', effort: 'high' }
  ),
]);
log('Implement: backend + frontend + markup agents finished');

// ---- Phase 4: Verify ----
phase('Verify');
const verdict = await agent(
  `VERIFY the Analytics-tab upgrade. Working dir: C:\\\\Users\\\\meena shah\\\\Desktop\\\\course-verifier.\nRun these checks and report a structured verdict:\n1. python -c "import py_compile; py_compile.compile('dashboard.py', doraise=True)" -> py_compile_ok.\n2. node --check static/app.js -> js_syntax_ok (if node missing, try: python -c "import re,sys; t=open('static/app.js',encoding='utf-8').read(); print('balanced' if t.count('{')==t.count('}') and t.count('(')==t.count(')') else 'UNBALANCED')" and note it).\n3. Scan the analytics tab for EMOJI: grep static/app.js, templates/index.html, static/style.css for emoji characters (any char outside basic ASCII that is an emoji/pictograph — flags 🇮🇳, 📊📋🌍🔬✅🌐📚🔍✕⚠️❌🏆🚨🏛️ etc.). Use a python snippet to find non-ASCII lines within the analytics ranges (app.js ~1122-1740, index.html ~354-636, and analytics css classes). List each file:line in emoji_violations.\n4. ID consistency: extract element ids referenced in app.js analytics section (getElementById / canvas ids / #ids) and the ids defined in index.html analytics section (id="..." within #tab-analytics). List mismatches in id_mismatches.\n5. Data contract consistency: list the top-level keys build_analytics_data() returns (read dashboard.py) vs the fields app.js analytics reads from the analytics payload. List fields read by app.js but not produced by the backend in data_field_mismatches.\n6. Hit the live route: python -c "import dashboard,json; print(list(json.loads(dashboard.app.test_client().get('/api/analytics.json').get_data())['data'].keys()))" -> put keys in analytics_json_fields.\n7. Set overall_ok=true ONLY if py_compile_ok AND js_syntax_ok AND emoji_violations empty AND id_mismatches empty AND data_field_mismatches empty. Put any remaining problems in issues.\nBe strict and factual. CONTEXT:\n${CTX}`,
  { label: 'verify', phase: 'Verify', schema: VERDICT_SCHEMA, effort: 'high' }
);

return { proposalsCount: proposals.length, spec, backend, frontend, markup, verdict };