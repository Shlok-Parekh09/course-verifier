const fs = require("fs");

const nodes = [];
const edges = [];

function fileNode(id, name, path, type, summary, tags, complexity, languageNotes) {
  const n = { id, type, name, filePath: path, summary, tags, complexity };
  if (languageNotes) n.languageNotes = languageNotes;
  nodes.push(n);
}
function fnNode(path, name, start, end, summary, tags, complexity) {
  const id = `function:${path}:${name}`;
  nodes.push({ id, type: "function", name, filePath: path, lineRange: [start, end], summary, tags, complexity });
  return id;
}
function edge(source, target, type, weight, direction) {
  if (direction === undefined) direction = "forward";
  if (source === target) return;
  edges.push({ source, target, type, direction, weight });
}

fileNode("file:.understand-anything/.understandignore", ".understandignore", ".understand-anything/.understandignore", "file",
  "Ignore-file controlling which project paths the understand-anything scanner skips during analysis.",
  ["configuration", "tooling", "ignore-list"], "simple");

fileNode("file:bench.py", "bench.py", "bench.py", "file",
  "Lightweight benchmarking script used to time course-loading or verification routines for performance checks.",
  ["benchmark", "utility", "performance"], "simple");

fileNode("file:check_db.py", "check_db.py", "check_db.py", "file",
  "Diagnostic script that queries the SQLite rankings database and prints table/row counts for sanity checks.",
  ["utility", "database", "diagnostic"], "simple");
edge("file:check_db.py", "file:rankings.db", "depends_on", 0.6);

fileNode("file:dashboard.py", "dashboard.py", "dashboard.py", "file",
  "Flask web dashboard backend: serves the local UI, exposes course/analytics/upload APIs, loads courses from PDFs and MongoDB, and syncs cached payloads to Cloudflare KV and MongoDB.",
  ["entry-point", "api-handler", "service", "middleware", "data-model"], "complex",
  "Large Flask app mixing request handlers, PDF parsing (fitz/pdfplumber), Mongo sync, and Cloudflare KV push in a single module.");
const dashFns = [
  ["_add_cors_headers", 39, 51, "Adds permissive CORS headers to every Flask response so the Firebase-hosted frontend can call the dashboard API cross-origin.", ["middleware","cors"], "simple"],
  ["clean_country", 83, 115, "Normalizes raw country strings (lowercasing, alias mapping, suffix stripping) into canonical country names used across filters and charts.", ["utility","normalization"], "moderate"],
  ["normalize_domain", 138, 148, "Trims and lowercases a domain string and strips a leading www. for consistent domain keys.", ["utility","normalization"], "simple"],
  ["_attr_is_match", 168, 192, "Heuristic comparing a PDF-extracted attribute against a verification source attribute to decide whether they match.", ["validation","heuristic"], "moderate"],
  ["_derived_classification", 263, 291, "Computes a derived verification classification (verified/mismatch/error) from a course issue and attribute state.", ["data-model","classification"], "moderate"],
  ["compute_stats", 307, 326, "Aggregates course records into summary statistics (counts by status, country, domain) for dashboard KPIs.", ["data-model","statistics"], "moderate"],
  ["save_courses", 328, 507, "Persists the in-memory course list to MongoDB (bulk upsert), writes static JSON exports, and prints status glyphs; the main write path.", ["serialization","persistence","api-handler"], "complex"],
  ["derive_issue_sub_type", 519, 583, "Classifies a course issue into a fine-grained sub-type based on attribute keys and mismatch patterns.", ["classification","issue-tracking"], "complex"],
  ["load_courses", 585, 809, "Loads courses from MongoDB (or SQLite fallback), merges PDF-extracted ranking tables, and primes the in-memory cache on startup and stale refresh.", ["data-model","persistence"], "complex"],
  ["_get_cached_data_payload", 904, 1018, "Builds and memoizes the full dashboard data payload (courses plus stats), keyed by a cache key, to avoid recomputing on every request.", ["caching","serialization"], "complex"],
  ["_push_cached_payloads_to_mongo", 1027, 1054, "Pushes the cached dashboard payloads (courses, analytics) to MongoDB so hosted frontends can read fresh data.", ["persistence","sync"], "moderate"],
  ["_push_to_cloudflare_kv", 1056, 1083, "Writes a key/value pair to a Cloudflare KV namespace via the API, used to mirror dashboard payloads at the edge.", ["persistence","edge-cache"], "moderate"],
  ["delete_course", 1093, 1123, "Handles course deletion: removes from memory, persists the change, and invalidates the data cache.", ["api-handler","persistence"], "moderate"],
  ["solve_course_issue", 1126, 1194, "Resolves a single course issue by applying a solver action, updating attributes, and reclassifying the course.", ["api-handler","issue-tracking"], "complex"],
  ["api_reclassify", 1197, 1237, "API endpoint that re-runs derived classification on a course and returns the updated status.", ["api-handler","classification"], "moderate"],
  ["build_analytics_data", 1242, 1317, "Computes the analytics payload (credential splits, pricing buckets, country/domain breakdowns) for the analytics tab.", ["data-model","statistics"], "complex"],
  ["upload_data", 1331, 1621, "Handles multipart PDF uploads: saves files, parses ranking tables, merges into course state, persists, and refreshes caches.", ["api-handler","pdf-parsing","persistence"], "complex"],
];
for (const [name, s, e, sum, tags, cx] of dashFns) {
  const id = fnNode("dashboard.py", name, s, e, sum, tags, cx);
  edge("file:dashboard.py", id, "contains", 1.0);
}
edge("file:dashboard.py", "file:templates/index.html", "depends_on", 0.6);
edge("file:dashboard.py", "file:static/app.js", "depends_on", 0.6);
edge("file:dashboard.py", "file:static/style.css", "depends_on", 0.6);
edge("file:dashboard.py", "file:rankings.db", "depends_on", 0.6);

fileNode("file:fetch_mongo_to_local.py", "fetch_mongo_to_local.py", "fetch_mongo_to_local.py", "file",
  "Script that pulls the latest course documents from MongoDB Atlas into a local SQLite cache for offline use.",
  ["script","sync","database"], "simple");
{
  const id = fnNode("fetch_mongo_to_local.py", "main", 5, 28, "Connects to MongoDB, fetches all course documents, and writes them into the local SQLite database.", ["entry-point","sync"], "simple");
  edge("file:fetch_mongo_to_local.py", id, "contains", 1.0);
  edge("file:fetch_mongo_to_local.py", "file:rankings.db", "depends_on", 0.6);
}

fileNode("file:infinityfree/app.js", "app.js", "infinityfree/app.js", "file",
  "Frontend logic for the InfinityFree-hosted dashboard variant: fetches courses from Mongo, renders tables/charts, and handles issue solving and modals.",
  ["frontend","dashboard","api-handler","component"], "complex");
const infFns = [
  ["fetchAllCourses", 105, 145, "Fetches the full course list from the MongoDB data API and primes the global state used by the dashboard.", ["api-handler","fetch"], "moderate"],
  ["initFilters", 328, 393, "Wires up country/domain/status filter controls and re-renders tables on change.", ["event-handler","filtering"], "moderate"],
  ["renderDomainChart", 460, 500, "Renders a bar/donut chart of course counts by verification domain.", ["component","chart"], "moderate"],
  ["renderStatusDonut", 502, 548, "Renders a donut chart showing the verified/mismatch/error status split.", ["component","chart"], "moderate"],
  ["renderSolvedTab", 644, 701, "Renders the recently-solved issues tab from the solved-issues payload.", ["component","render"], "complex"],
  ["openModal", 746, 831, "Opens the course detail modal, populates attributes, and attaches solve/cancel handlers.", ["component","modal"], "complex"],
  ["solveAttr", 840, 898, "Sends a single-attribute solve action to the backend and updates the row in place.", ["api-handler","issue-tracking"], "complex"],
  ["solveAll", 900, 940, "Sends a bulk solve-all request for a course and refreshes the displayed state.", ["api-handler","issue-tracking"], "moderate"],
  ["initTopbarExtras", 979, 1006, "Initializes topbar extras (page title, connection status, theme toggle) for the hosted variant.", ["event-handler","component"], "moderate"],
];
for (const [name, s, e, sum, tags, cx] of infFns) {
  const id = fnNode("infinityfree/app.js", name, s, e, sum, tags, cx);
  edge("file:infinityfree/app.js", id, "contains", 1.0);
}

fileNode("file:infinityfree/index.html", "index.html", "infinityfree/index.html", "file",
  "HTML shell for the InfinityFree-hosted dashboard variant; loads app.js and style.css and lays out the dashboard structure.",
  ["frontend","markup","dashboard"], "moderate");
edge("file:infinityfree/index.html", "file:infinityfree/app.js", "depends_on", 0.6);
edge("file:infinityfree/index.html", "file:infinityfree/style.css", "depends_on", 0.6);

fileNode("file:infinityfree/style.css", "style.css", "infinityfree/style.css", "file",
  "Stylesheet for the InfinityFree-hosted dashboard variant, covering layout, charts, modals, and responsive breakpoints.",
  ["frontend","styles","dashboard"], "complex");

fileNode("file:public/index.html", "index.html", "public/index.html", "file",
  "HTML shell for the Firebase-hosted public dashboard; loads the public app.js and style.css and renders the analytics-driven dashboard.",
  ["frontend","markup","dashboard"], "moderate");
edge("file:public/index.html", "file:public/static/app.js", "depends_on", 0.6);
edge("file:public/index.html", "file:public/static/style.css", "depends_on", 0.6);

fileNode("file:public/static/app.js", "app.js", "public/static/app.js", "file",
  "Frontend logic for the Firebase-hosted public dashboard: fetches courses/analytics, renders charts, tables, drilldowns, and the upload form.",
  ["frontend","dashboard","api-handler","component"], "complex");
const pubFns = [
  ["initCharts", 200, 363, "Initializes all Chart.js chart instances (issue pie, bar, line, map) with their default config and empty data.", ["component","chart"], "complex"],
  ["initFilters", 676, 738, "Wires verification and course filter controls (search, country, domain, status, subtype) and re-renders on change.", ["event-handler","filtering"], "complex"],
  ["showCourseModal", 868, 957, "Opens the course detail modal with PDF table, attributes, and issue list; attaches solve handlers.", ["component","modal"], "complex"],
  ["solveCourse", 962, 1056, "Submits a solve action for a course issue to the backend and reconciles the returned state in the UI.", ["api-handler","issue-tracking"], "complex"],
  ["fetchData", 1100, 1147, "Fetches the main courses payload from the API and dispatches initial rendering of all tabs.", ["api-handler","fetch"], "moderate"],
  ["populateInsightCards", 1244, 1295, "Computes and renders insight summary cards (top movers, mismatches) on the analytics tab.", ["component","analytics"], "complex"],
  ["populateDomainTab", 1473, 1525, "Renders the domain-breakdown analytics tab with per-domain metrics and drilldown rows.", ["component","analytics"], "complex"],
  ["populateVerificationTab", 1552, 1653, "Renders the verification analytics tab with status splits and per-country drilldowns.", ["component","analytics"], "complex"],
  ["renderAnalytics", 1660, 1723, "Drives the full analytics view: KPIs, charts, insight cards, and tab population.", ["component","analytics"], "complex"],
  ["fetchAnalytics", 1740, 1772, "Fetches the analytics payload from the API and triggers renderAnalytics.", ["api-handler","fetch"], "moderate"],
  ["initUpload", 1791, 1826, "Wires the PDF upload form: file selection, progress, and POST to the dashboard upload endpoint.", ["event-handler","upload"], "moderate"],
  ["renderCoursesPage", 819, 855, "Renders the paginated courses table from the loaded course list.", ["component","render"], "moderate"],
];
for (const [name, s, e, sum, tags, cx] of pubFns) {
  const id = fnNode("public/static/app.js", name, s, e, sum, tags, cx);
  edge("file:public/static/app.js", id, "contains", 1.0);
}

fileNode("file:public/static/style.css", "style.css", "public/static/style.css", "file",
  "Stylesheet for the Firebase-hosted public dashboard, covering layout, charts, KPI cards, modals, and responsive design.",
  ["frontend","styles","dashboard"], "complex");

fileNode("file:push_kv_manual.py", "push_kv_manual.py", "push_kv_manual.py", "file",
  "Manual CLI script that pushes a key/value pair to a Cloudflare KV namespace via the API, used for one-off cache updates.",
  ["script","edge-cache","cloudflare"], "simple");
{
  const id1 = fnNode("push_kv_manual.py", "push_to_kv", 13, 31, "POSTs a single key/value pair to the Cloudflare KV API endpoint.", ["api-handler","edge-cache"], "simple");
  const id2 = fnNode("push_kv_manual.py", "main", 33, 60, "Parses CLI args for key/value and invokes push_to_kv.", ["entry-point","cli"], "moderate");
  edge("file:push_kv_manual.py", id1, "contains", 1.0);
  edge("file:push_kv_manual.py", id2, "contains", 1.0);
}

fileNode("file:rankings.db", "rankings.db", "rankings.db", "file",
  "SQLite database storing the canonical course ranking data extracted from PDFs, queried by the dashboard and helper scripts.",
  ["database","data-model","persistence"], "moderate");

fileNode("file:scratch/update_app.py", "update_app.py", "scratch/update_app.py", "file",
  "One-off maintenance script that applies targeted string-replacement patches to infinityfree/app.js (state additions, sort logic, modal wiring).",
  ["script","maintenance","codegen"], "moderate");
edge("file:scratch/update_app.py", "file:infinityfree/app.js", "depends_on", 0.6);

fileNode("file:static/app.js", "app.js", "static/app.js", "file",
  "Frontend logic for the local Flask dashboard: fetches courses/analytics, renders charts, tables, drilldowns, modals, and the upload form.",
  ["frontend","dashboard","api-handler","component"], "complex");
const stFns = [
  ["initCharts", 200, 363, "Initializes all Chart.js chart instances (issue pie, bar, line, map) with default config and empty data.", ["component","chart"], "complex"],
  ["initFilters", 676, 738, "Wires verification and course filter controls (search, country, domain, status, subtype) and re-renders on change.", ["event-handler","filtering"], "complex"],
  ["showCourseModal", 868, 957, "Opens the course detail modal with PDF table, attributes, and issue list; attaches solve handlers.", ["component","modal"], "complex"],
  ["solveCourse", 962, 1057, "Submits a solve action for a course issue to the dashboard API and reconciles returned state in the UI.", ["api-handler","issue-tracking"], "complex"],
  ["_applyData", 1101, 1128, "Applies a freshly fetched data payload to global state and triggers re-render of all views.", ["state-management","render"], "moderate"],
  ["fetchData", 1133, 1147, "Fetches the main courses payload from the dashboard API and dispatches initial rendering.", ["api-handler","fetch"], "moderate"],
  ["populateInsightCards", 1244, 1295, "Computes and renders insight summary cards (top movers, mismatches) on the analytics tab.", ["component","analytics"], "complex"],
  ["populateDomainTab", 1473, 1525, "Renders the domain-breakdown analytics tab with per-domain metrics and drilldown rows.", ["component","analytics"], "complex"],
  ["populateVerificationTab", 1552, 1653, "Renders the verification analytics tab with status splits and per-country drilldowns.", ["component","analytics"], "complex"],
  ["renderAnalytics", 1660, 1723, "Drives the full analytics view: KPIs, charts, insight cards, and tab population.", ["component","analytics"], "complex"],
  ["fetchAnalytics", 1740, 1772, "Fetches the analytics payload from the dashboard API and triggers renderAnalytics.", ["api-handler","fetch"], "moderate"],
  ["initUpload", 1791, 1834, "Wires the PDF upload form: file selection, progress, and POST to the dashboard upload endpoint.", ["event-handler","upload"], "moderate"],
  ["renderCoursesPage", 819, 855, "Renders the paginated courses table from the loaded course list.", ["component","render"], "moderate"],
];
for (const [name, s, e, sum, tags, cx] of stFns) {
  const id = fnNode("static/app.js", name, s, e, sum, tags, cx);
  edge("file:static/app.js", id, "contains", 1.0);
}

fileNode("file:static/style.css", "style.css", "static/style.css", "file",
  "Stylesheet for the local Flask dashboard, covering layout, charts, KPI cards, modals, and responsive design.",
  ["frontend","styles","dashboard"], "complex");

fileNode("file:sync_solves_to_mongo.py", "sync_solves_to_mongo.py", "sync_solves_to_mongo.py", "file",
  "Script that reads solved issue records from the local SQLite cache and upserts them into MongoDB so hosted frontends see the latest solves.",
  ["script","sync","database"], "moderate");
{
  const id = fnNode("sync_solves_to_mongo.py", "sync_solves", 24, 77, "Pulls solved records from local SQLite and bulk-upserts them into the MongoDB courses collection.", ["sync","persistence"], "moderate");
  edge("file:sync_solves_to_mongo.py", id, "contains", 1.0);
  edge("file:sync_solves_to_mongo.py", "file:rankings.db", "depends_on", 0.6);
}

fileNode("file:templates/index.html", "index.html", "templates/index.html", "file",
  "Jinja2 HTML template for the local Flask dashboard; references static/app.js and static/style.css and lays out the dashboard structure.",
  ["frontend","markup","dashboard"], "moderate");
edge("file:templates/index.html", "file:static/app.js", "depends_on", 0.6);
edge("file:templates/index.html", "file:static/style.css", "depends_on", 0.6);

fileNode("file:worker/index.js", "index.js", "worker/index.js", "file",
  "Cloudflare Worker entry that proxies course data requests to MongoDB Atlas via the Data API, with CORS handling for hosted frontends.",
  ["entry-point","api-handler","edge-cache","cloudflare"], "moderate");
{
  const id = fnNode("worker/index.js", "mongoRequest", 14, 32, "POSTs an action to the MongoDB Atlas Data API and returns the parsed JSON response.", ["api-handler","fetch"], "moderate");
  edge("file:worker/index.js", id, "contains", 1.0);
}

fileNode("file:worker/src/index.js", "index.js", "worker/src/index.js", "file",
  "Source variant of the Cloudflare Worker with CORS helpers and a JSON response helper; near-duplicate of worker/index.js used during development.",
  ["entry-point","api-handler","cloudflare"], "moderate");
{
  const id = fnNode("worker/src/index.js", "jsonResponse", 22, 32, "Builds a JSON Response with CORS headers for the Worker fetch handler.", ["utility","serialization"], "simple");
  edge("file:worker/src/index.js", id, "contains", 1.0);
}
edge("file:worker/index.js", "file:worker/src/index.js", "related", 0.5);

fileNode("config:worker/wrangler.toml", "wrangler.toml", "worker/wrangler.toml", "config",
  "Cloudflare Wrangler configuration defining the Worker deployment and KV namespace binding.",
  ["configuration","cloudflare","deployment","build-system"], "simple");
edge("config:worker/wrangler.toml", "file:worker/index.js", "configures", 0.6);

edge("file:static/app.js", "file:public/static/app.js", "related", 0.5);
edge("file:static/app.js", "file:infinityfree/app.js", "related", 0.5);
edge("file:public/static/app.js", "file:infinityfree/app.js", "related", 0.5);
edge("file:templates/index.html", "file:public/index.html", "related", 0.5);
edge("file:templates/index.html", "file:infinityfree/index.html", "related", 0.5);
edge("file:public/index.html", "file:infinityfree/index.html", "related", 0.5);

const filesOrder = [
  ".understand-anything/.understandignore","bench.py","check_db.py","dashboard.py","fetch_mongo_to_local.py",
  "infinityfree/app.js","infinityfree/index.html","infinityfree/style.css","public/index.html","public/static/app.js","public/static/style.css",
  "push_kv_manual.py","rankings.db","scratch/update_app.py","static/app.js","static/style.css","sync_solves_to_mongo.py","templates/index.html","worker/index.js","worker/src/index.js","worker/wrangler.toml"
];
const part1Files = new Set(filesOrder.slice(0,11));
const part2Files = new Set(filesOrder.slice(11));

const p1Nodes = nodes.filter(n => part1Files.has(n.filePath));
const p2Nodes = nodes.filter(n => part2Files.has(n.filePath));
const p1NodeIds = new Set(p1Nodes.map(n=>n.id));
const allKnownIds = new Set(nodes.map(n=>n.id));

const p1Edges = edges.filter(e => p1NodeIds.has(e.source));
const p2Edges = edges.filter(e => !p1NodeIds.has(e.source));

const allBatchPaths = new Set(filesOrder);
function isValidTarget(t) {
  if (allKnownIds.has(t)) return true;
  if (t.indexOf("file:") === 0) {
    return allBatchPaths.has(t.slice(5));
  }
  if (t.indexOf("config:") === 0) {
    return allBatchPaths.has(t.slice(7));
  }
  return false;
}
for (const e of edges) {
  if (!isValidTarget(e.target)) {
    console.error("BAD EDGE TARGET:", JSON.stringify(e));
    process.exit(1);
  }
}

fs.writeFileSync("C:/Users/meena shah/Desktop/course-verifier/.understand-anything/intermediate/batch-6-part-1.json", JSON.stringify({nodes:p1Nodes, edges:p1Edges}, null, 2));
fs.writeFileSync("C:/Users/meena shah/Desktop/course-verifier/.understand-anything/intermediate/batch-6-part-2.json", JSON.stringify({nodes:p2Nodes, edges:p2Edges}, null, 2));

console.log("TOTAL nodes:", nodes.length, "edges:", edges.length);
console.log("PART1 nodes:", p1Nodes.length, "edges:", p1Edges.length);
console.log("PART2 nodes:", p2Nodes.length, "edges:", p2Edges.length);
console.log("imports edges:", edges.filter(e => e.type === "imports").length, "(expected 0)");