/* ================================================================
   COURSE VERIFIER  ·  APP.JS  v6
   ================================================================ */

'use strict';

// Production API is the hosted Vercel deployment; locally the Flask app
// serves the API on the same origin, so no base URL is needed.
// Detect local robustly: the Flask dev server binds 0.0.0.0:5000, so accessing
// it via 0.0.0.0, a LAN IP, or the machine name must still count as local —
// otherwise the frontend silently pulls stale data from the Vercel deploy.
const _h = window.location.hostname;
const isLocalEnv =
    _h === 'localhost' || _h === '127.0.0.1' || _h === '0.0.0.0' ||
    _h.endsWith('.local') ||
    /^(10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.)/.test(_h) || // private/LAN IPv4
    window.location.port === '5000';
let API_BASE_URL = isLocalEnv ? '' : 'https://course-verifier.vercel.app';
if (API_BASE_URL.endsWith('/')) {
    API_BASE_URL = API_BASE_URL.slice(0, -1);
}

// ── State ────────────────────────────────────────────────────────
let globalData = null;
let currentFilter = { type: null, value: null };   // Dashboard bar-chart filter (filtered table panel)
let countryDataList = [];
let allCoursesData = [];
let recentData = [];
let currentPage = 1;
let currentRecentPage = 1;
const PAGE_SIZE = 100;
const RECENT_PAGE_SIZE = 30;
let lastDataHash = '';
// Change-detection hashes for poll-driven renders. Mirrors the lastDataHash
// pattern in updateRecentVerifications: skip the expensive re-render when the
// underlying payload is byte-identical to the previous poll.
let lastStatsHash = '';
let lastCountryHash = '';
let lastBarHash = '';
let firstDataFetch = true;

// ── Tab filter state (real, client-side, never fabricated) ───────
let verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all' };
let courseFilter       = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any' };

// ── Domain category by course idx (ID number) ───────────────────
// These ranges are fixed per the curriculum structure.
const DOMAIN_RANGES = [
    { label: 'Free',                  min: 1,    max: 25   },
    { label: 'Free to Audit',         min: 26,   max: 48   },
    { label: 'High Value Low Cost',   min: 49,   max: 100  },
    { label: 'Foundational',          min: 101,  max: 601  },
    { label: 'Network Infrastructure',min: 602,  max: 1585 },
    { label: 'System & Endpoint',     min: 1586, max: 1890 },
    { label: 'Cyber Forensics',       min: 1891, max: 2634 },
    { label: 'Data & Application',    min: 2635, max: 2965 },
    { label: 'Legal & Ethical',       min: 2966, max: 3727 },
];

function getDomainCategory(idxRaw) {
    const idx = parseInt(idxRaw, 10);
    if (isNaN(idx)) return 'Uncategorised';
    for (const r of DOMAIN_RANGES) {
        if (idx >= r.min && idx <= r.max) return r.label;
    }
    return 'Uncategorised';
}

const ALL_DOMAIN_LABELS = DOMAIN_RANGES.map(r => r.label);

// ── Academic-domain normalizer (mirrors backend normalize_domain) ──────
// The raw `domain` field arrives as a mix of Title Case ("Bachelors") and
// UPPERCASE ("BACHELORS DEGREE"); these are the same degree. Collapse them to
// one canonical label so the Dashboard breakdown, the analytics credential
// chart, and the filtered-table drill-down all agree.
const _CANON_DOMAIN_FRAGMENTS = [
    ['post graduate diploma', "Post Graduate Diploma"],
    ['post grad diploma',     "Post Graduate Diploma"],
    ['graduate diploma',      "Post Graduate Diploma"],
    ['post graduate certificate', "Post Graduate Certificate"],
    ['post grad certificate', "Post Graduate Certificate"],
    ['post grad cert',        "Post Graduate Certificate"],
    ['bachelor',              "Bachelor's Degree"],
    ['master',                "Master's Degree"],
    ['pg',                    "Master's Degree"],
    ['diploma',               "Diploma"],
    ['certificate',           "Certificate"],
    ['cert',                  "Certificate"],
    ['free to audit',         "Free to Audit"],
    ['high value low cost',   "High Value Low Cost"],
    ['free',                  "Free"],
];
function normalizeDomain(raw) {
    if (!raw) return 'Other';
    const k = String(raw).toLowerCase().replace('gradiuate', 'graduate').trim();
    if (!k || ['unknown', 'unknown domain', 'none', 'null'].includes(k)) return 'Other';
    for (const [frag, label] of _CANON_DOMAIN_FRAGMENTS) {
        if (k.includes(frag)) return label;
    }
    return 'Other';
}

const ATTR_TO_MATCH = {
    Cost: 'cost_match', Duration: 'duration_match', Mode: 'mode_match',
    Language: 'lang_match', Country: 'country_match', University: 'uni_match', Skills: 'sk_match'
};
const SUBTYPE_LABELS = {
    '404_not_found': '404 Not Found', 'ssl_error': 'SSL Error', 'timeout': 'Timeout',
    'blocked_by_waf': 'Blocked by WAF', 'dns_fail': 'DNS Fail', 'login_required': 'Login Required',
    'redirect_loop': 'Redirect Loop', 'server_error': 'Server Error', 'site_down': 'Site Down',
    'multiple_mismatches': 'Multiple Mismatches', 'cost_mismatch': 'Cost Mismatch',
    'duration_mismatch': 'Duration Mismatch', 'university_mismatch': 'University Mismatch',
    'country_mismatch': 'Country Mismatch', 'mode_mismatch': 'Mode Mismatch',
    'language_mismatch': 'Language Mismatch', 'skills_mismatch': 'Skills Mismatch',
    'name_mismatch': 'Name Mismatch', 'course_discontinued': 'Discontinued',
    'course_replaced': 'Replaced', 'wrong_url': 'Wrong URL', 'perfect_match': 'Perfect Match'
};
let barChart, mapChart, lineChart;
let barMode = 'domain'; // 'domain' | 'country'

// ── Country flag emoji helper ─────────────────────────────────────
const FLAG_MAP = {
    'India': '🇮🇳', 'United States': '🇺🇸', 'Australia': '🇦🇺',
    'United Kingdom': '🇬🇧', 'Canada': '🇨🇦', 'Germany': '🇩🇪',
    'France': '🇫🇷', 'Singapore': '🇸🇬', 'South Africa': '🇿🇦',
    'New Zealand': '🇳🇿', 'UAE': '🇦🇪', 'China': '🇨🇳',
    'Japan': '🇯🇵', 'Netherlands': '🇳🇱', 'Switzerland': '🇨🇭',
    'Brazil': '🇧🇷', 'Italy': '🇮🇹', 'Spain': '🇪🇸',
    'Ireland': '🇮🇪', 'Sweden': '🇸🇪', 'Denmark': '🇩🇰',
};
function getFlag(name) {
    if (!name) return '🌐';
    for (const [key, flag] of Object.entries(FLAG_MAP)) {
        if (name.toLowerCase().includes(key.toLowerCase()) || key.toLowerCase().includes(name.toLowerCase())) return flag;
    }
    return '🌐';
}

// ================================================================
//  THEME
// ================================================================
function initTheme() {
    const toggle = document.getElementById('theme-toggle');
    const label = document.getElementById('theme-label');
    const saved = localStorage.getItem('cvTheme') || 'dark';
    if (saved === 'light') {
        document.body.classList.add('light-mode');
        if (label) label.textContent = 'Light';
    }
    if (toggle) {
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('light-mode');
            const isLight = document.body.classList.contains('light-mode');
            localStorage.setItem('cvTheme', isLight ? 'light' : 'dark');
            if (label) label.textContent = isLight ? 'Light' : 'Dark';
        });
    }

    // Dashboard KPI cards drill through to the Verification tab with a
    // real filter applied (no more loose single-field flag).
    document.getElementById('kpi-card-discrepancies')?.addEventListener('click', () =>
        jumpToVerification({ status: 'Discrepancy' }));
    document.getElementById('kpi-card-website-issues')?.addEventListener('click', () =>
        jumpToVerification({ status: 'Error', category: 'website_issue' }));
}

// ================================================================
//  TABS
// ================================================================
function switchTab(targetId) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('#nav-tabs a').forEach(a => a.classList.remove('active'));
    const content = document.getElementById(targetId);
    if (content) content.classList.add('active');
    const link = document.querySelector(`#nav-tabs a[data-target="${targetId}"]`);
    if (link) link.classList.add('active');
    if (targetId === 'tab-courses') loadAllCourses();
    // Re-fetch analytics every time the tab is opened so data is always fresh
    if (targetId === 'tab-analytics') fetchAnalytics();
}

function initTabs() {
    document.querySelectorAll('#nav-tabs a').forEach(a => {
        a.addEventListener('click', e => {
            e.preventDefault();
            switchTab(a.getAttribute('data-target'));
        });
    });
}

// ================================================================
//  CHARTS INIT
// ================================================================
function initCharts() {
    Chart.defaults.color = '#9499b0';
    Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
    Chart.defaults.font.family = "'Inter', sans-serif";

    // Register the annotation plugin if it loaded (used by the fee-histogram
    // median line). chartjs-plugin-annotation usually auto-registers, but
    // guard in case the CDN failed or the UMD build didn't.
    if (window.ChartAnnotation) { try { Chart.register(window.ChartAnnotation); } catch (e) {} }

    // 1. Country Line Chart
    const lCtx = document.getElementById('countryLineChart')?.getContext('2d');
    if (lCtx) {
        lineChart = new Chart(lCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Courses',
                    data: [],
                    borderColor: '#f46a22',
                    backgroundColor: 'rgba(244,106,34,0.10)',
                    tension: 0.45,
                    fill: true,
                    pointBackgroundColor: '#f46a22',
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' } },
                    x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { maxRotation: 45 } }
                }
            }
        });
    }

    // 2b. Issue Category Doughnut
    const iCtx = document.getElementById('issuePieChart')?.getContext('2d');
    if (iCtx) {
        window.issueChart = new Chart(iCtx, {
            type: 'doughnut',
            data: {
                labels: ['Website Issues', 'Course Issues', 'Verified'],
                datasets: [{
                    data: [0, 0, 0],
                    backgroundColor: ['#f16b6b', '#f5a623', '#1dda9f'],
                    borderWidth: 0,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 18, font: { size: 11 } }
                    }
                }
            }
        });
    }

    // 3. Horizontal Bar Chart
    const bCtx = document.getElementById('coursesBarChart')?.getContext('2d');
    if (bCtx) {
        barChart = new Chart(bCtx, {
            type: 'bar',
            data: { labels: [], datasets: [{ label: 'Courses', data: [], backgroundColor: 'rgba(244,106,34,0.75)', hoverBackgroundColor: '#f46a22', borderRadius: 5 }] },
            options: {
                indexAxis: 'y',
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: 'rgba(255,255,255,0.04)' } },
                    y: { ticks: { autoSkip: false }, grid: { display: false } }
                },
                plugins: { legend: { display: false } },
                onClick: (_, els) => {
                    if (els.length) {
                        applyFilter(barMode, barChart.data.labels[els[0].index]);
                    }
                }
            }
        });
    }

    // 4. Choropleth Map
    const mCtx = document.getElementById('countryMapChart')?.getContext('2d');
    if (mCtx) {
        fetch('https://unpkg.com/world-atlas/countries-110m.json').then(r => r.json()).then(topo => {
            let countries = ChartGeo.topojson.feature(topo, topo.objects.countries).features;
            countries = countries.filter(d => d.properties.name !== 'Antarctica');
            mapChart = new Chart(mCtx, {
                type: 'choropleth',
                data: {
                    labels: countries.map(d => d.properties.name),
                    datasets: [{
                        label: 'Courses',
                        data: countries.map(d => ({ feature: d, value: 0 })),
                        // Visible borders so all country outlines show even at 0 courses
                        borderColor: 'rgba(148,163,184,0.35)',
                        borderWidth: 1.2
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    showOutline: false, showGraticule: false,
                    layout: { padding: 0 },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => {
                                    const name = ctx.raw?.feature?.properties?.name || ctx.label || 'Unknown';
                                    const count = ctx.raw?.feature?._realCount ?? 0;
                                    return `${name}: ${Math.round(count)} courses`;
                                }
                            }
                        }
                    },
                    scales: {
                        projection: { axis: 'x', projection: 'equirectangular' },
                        color: {
                            axis: 'x',
                            // v = 0..1 (chart-geo normalises our compressed values)
                            // v=0  → dark slate (country is visible but has no courses)
                            // v>0  → sky-blue (few) to deep indigo (many)
                            interpolate: (v) => {
                                if (v <= 0) {
                                    // Dark slate — country outline is visible, fill is muted
                                    return 'rgba(251, 251, 251, 0.7)';
                                }
                                // sqrt curve: spreads small values so they get noticeable colour
                                const t = Math.pow(v, 0.5);
                                // sky-blue rgb(147,197,253) → deep indigo rgb(67,56,202)
                                const r = Math.round(147 - t * (147 - 67));
                                const g = Math.round(197 - t * (197 - 56));
                                const b = Math.round(253 - t * (253 - 202));
                                // opacity: 0.45 for fewest courses → 1.0 for most
                                const a = (0.45 + t * 0.55).toFixed(2);
                                return `rgba(${r},${g},${b},${a})`;
                            },
                            // missing = country not matched at all: same dark slate
                            missing: 'rgba(254, 2, 2, 0.7)'
                        }
                    }
                }
            });
            if (globalData) updateMapChart(globalData.country_counts);
        }).catch(() => { });
    }

    // ── Bar pill toggle ──────────────────────────────────────────
    document.querySelectorAll('#bar-toggle-pills button').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#bar-toggle-pills button').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            barMode = btn.dataset.val;
            updateBarChart();
        });
    });

    // ── Clear filter ─────────────────────────────────────────────
    document.getElementById('clear-filter')?.addEventListener('click', () => applyFilter(null, null));
}

// ================================================================
//  DATA UPDATES
// ================================================================
function updateCards(stats) {
    document.getElementById('total-count').textContent = stats.total || 0;
    document.getElementById('verified-count').textContent = stats.verified || 0;
    document.getElementById('discrepancy-count').textContent = stats.discrepancies || 0;

    const wCount = document.getElementById('website-issue-count');
    if (wCount) wCount.textContent = stats.website_issues || 0;

    // Extra Dashboard KPI cards — all populated from real stats only.
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set('error-count', stats.errors || 0);
    set('course-issue-count', stats.course_issues || 0);
    set('open-issue-count', stats.open_issues || 0);

    // Dynamic trend % labels
    const t = stats.total || 1;
    document.getElementById('kpi-verified-trend').textContent = `↑ ${Math.round((stats.verified || 0) / t * 100)}% match rate`;
    document.getElementById('kpi-disc-trend').textContent = `⚠ ${Math.round((stats.discrepancies || 0) / t * 100)}% flagged`;

    const kpiWebTrend = document.getElementById('kpi-webissue-trend');
    if (kpiWebTrend) kpiWebTrend.textContent = `🔗 ${Math.round((stats.website_issues || 0) / t * 100)}% site broken`;

    set('kpi-err-trend', `✕ ${Math.round((stats.errors || 0) / t * 100)}% failed`);
    set('kpi-courseissue-trend', `📋 ${Math.round((stats.course_issues || 0) / t * 100)}% mismatch`);
    set('kpi-openissue-trend', stats.open_issues ? `${stats.open_issues} open` : '✓ none open');

    document.getElementById('kpi-total-trend').textContent = `— ${t} records`;

    // Sticky KPI strips on the Verification & All Courses tabs share the same
    // four real numbers so the headline parameters are always visible.
    renderKpiStrip('vf', stats);
    renderKpiStrip('cf', stats);
}

function renderKpiStrip(prefix, stats) {
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    set(prefix + '-total', stats ? (stats.total ?? '—') : '—');
    set(prefix + '-verified', stats ? (stats.verified ?? '—') : '—');
    set(prefix + '-disc', stats ? (stats.discrepancies ?? '—') : '—');
    set(prefix + '-web', stats ? (stats.website_issues ?? '—') : '—');
}

function updateIssuePieChart(stats, animate = true) {
    if (!window.issueChart) return;
    window.issueChart.data.datasets[0].data = [
        stats.website_issues || 0, stats.course_issues || 0, stats.verified || 0
    ];
    if (animate) window.issueChart.update(); else window.issueChart.update('none');
}

function updateBarChart(animate = true) {
    if (!barChart || !globalData) return;
    const src = barMode === 'domain' ? globalData.domain_counts : globalData.country_counts;
    let entries = Object.entries(src || {}).sort((a, b) => b[1] - a[1]);
    if (barMode === 'country') entries = entries.slice(0, 12);
    barChart.data.labels = entries.map(e => e[0]);
    barChart.data.datasets[0].data = entries.map(e => e[1]);
    if (animate) barChart.update(); else barChart.update('none');
}

// ── Shared country name validator ───────────────────────────────
function isValidCountry(k) {
    if (!k) return false;
    const s = String(k).trim().toLowerCase();
    return s !== '' &&
        s !== 'undefined' &&
        s !== 'unknown' &&
        s !== 'null' &&
        !s.startsWith('not found');
}

function updateLineChart(countryCounts, animate = true) {
    if (!lineChart) return;
    const sorted = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])
        .slice(0, 20);
    countryDataList = sorted;
    lineChart.data.labels = sorted.map(x => x[0]);
    lineChart.data.datasets[0].data = sorted.map(x => x[1]);
    if (animate) lineChart.update(); else lineChart.update('none');
}

function updateMapChart(countryCounts, animate = true) {
    if (!mapChart || !mapChart.data?.datasets?.[0]?.data?.length) return;

    // First pass: collect raw counts and store on feature for tooltip
    mapChart.data.datasets[0].data.forEach(d => {
        const name = d.feature.properties.name;
        let val = 0;
        for (const [c, cnt] of Object.entries(countryCounts || {})) {
            if (c.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(c.toLowerCase())) {
                val += cnt;
            }
        }
        // Store the real count on the feature so the tooltip can read it
        d.feature._realCount = val;
        d.value = val;
    });

    // Second pass: sqrt-compress values so dominant countries (e.g. India)
    // don't bleach out all others on the choropleth color scale.
    const vals = mapChart.data.datasets[0].data.map(d => d.value).filter(v => v > 0);
    const commit = () => { if (animate) mapChart.update(); else mapChart.update('none'); };
    if (vals.length === 0) { commit(); return; }
    const maxSqrt = Math.sqrt(Math.max(...vals));
    mapChart.data.datasets[0].data.forEach(d => {
        // Compressed display value, real count preserved in d.feature._realCount
        d.value = d.value > 0 ? (Math.sqrt(d.value) / maxSqrt) * 100 : 0;
    });

    commit();
}

function updateCountryLeaderboard(countryCounts, containerId = 'country-list') {
    const el = document.getElementById(containerId);
    if (!el) return;
    const entries = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt]) => `
        <div class="country-row" onclick="applyFilter('country','${name.replace(/'/g, "\\'")}')">
            <span class="c-flag">${getFlag(name)}</span>
            <span class="c-name">${name}</span>
            <div class="c-bar-wrap"><div class="c-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div>
            <span class="c-count">${cnt}</span>
        </div>
    `).join('');
}

// ================================================================
//  DASHBOARD BAR-CHART FILTER (filtered detail panel)
// ================================================================
function applyFilter(type, value) {
    currentFilter = { type, value };
    const badge = document.getElementById('active-filter-badge');
    const panel = document.getElementById('course-details-panel');
    if (value && type) {
        if (badge) badge.textContent = `${type}: ${value}`;
        renderFilteredTable(type, value);
        if (panel) panel.style.display = 'flex';
    } else {
        if (badge) badge.textContent = '';
        if (panel) panel.style.display = 'none';
    }
}

function renderFilteredTable(type, value) {
    const tbody = document.getElementById('course-details-body');
    if (!tbody || !globalData?.recent) return;
    const filtered = globalData.recent.filter(c =>
        type === 'domain' ? normalizeDomain(c.domain) === value :
            type === 'country' ? c.country === value : true
    );
    tbody.innerHTML = filtered.length === 0
        ? '<tr><td colspan="5" class="empty-state">No courses found</td></tr>'
        : filtered.map(c => `
            <tr onclick="showCourseModal('${c.id || ''}', '${escJs(c.name)}', '${escJs(c.university || '')}')">
                <td class="course-name-cell" title="${escHtml(c.name)}"><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td>${c.has_qs_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
                <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            </tr>`).join('');
}

// ================================================================
//  TAB FILTERS  (real, client-side, no dummy data)
// ================================================================
function populateSelect(selectId, values) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const current = sel.value;
    const first = sel.querySelector('option');            // keep the "All …" option
    sel.innerHTML = '';
    if (first) sel.appendChild(first);
    [...values].filter(Boolean).sort().forEach(v => {
        const o = document.createElement('option');
        o.value = v; o.textContent = v;
        sel.appendChild(o);
    });
    sel.value = [...sel.options].some(o => o.value === current) ? current : (first ? first.value : 'all');
}

function populateSubtypeSelect(selectId) {
    const sel = document.getElementById(selectId);
    if (!sel) return;
    const wsc = globalData?.website_sub_counts || {};
    const csc = globalData?.course_sub_counts || {};
    const keys = [...new Set([...Object.keys(wsc), ...Object.keys(csc)])].filter(k => k);
    const current = sel.value;
    sel.innerHTML = '<option value="all">All Sub-Types</option>';
    if (keys.length === 0) { sel.hidden = true; sel.value = 'all'; return; }
    sel.hidden = false;
    keys.sort().forEach(k => {
        const o = document.createElement('option');
        o.value = k; o.textContent = SUBTYPE_LABELS[k] || k.replace(/_/g, ' ');
        sel.appendChild(o);
    });
    sel.value = [...sel.options].some(o => o.value === current) ? current : 'all';
}

function refreshFilterOptions() {
    // Countries: dynamic from data
    const vCountries = new Set();
    recentData.forEach(c => { if (c.country) vCountries.add(c.country); });
    populateSelect('vf-country', vCountries);

    const cCountries = new Set();
    allCoursesData.forEach(c => { if (c.country) cCountries.add(c.country); });
    populateSelect('cf-country', cCountries);

    // Domain: always the 9 fixed idx-based categories
    populateSelect('vf-domain', ALL_DOMAIN_LABELS);
    populateSelect('cf-domain', ALL_DOMAIN_LABELS);

    populateSubtypeSelect('vf-subtype');
    populateSubtypeSelect('cf-subtype');
}

function getFilteredVerificationData() {
    const f = verificationFilter;
    const q = f.search.trim().toLowerCase();
    return recentData.filter(c => {
        if (f.status !== 'all' && c.status !== f.status) return false;
        if (f.category !== 'all' && c.issue_category !== f.category) return false;
        if (f.subtype !== 'all' && (c.issue_sub_type || '') !== f.subtype) return false;
        if (f.country !== 'all' && c.country !== f.country) return false;
        // Domain filter uses idx-based category
        if (f.domain !== 'all' && getDomainCategory(c.id) !== f.domain) return false;
        if (f.attr !== 'all') { const key = ATTR_TO_MATCH[f.attr]; if (key && c[key] !== false) return false; }
        if (q && !`${c.name} ${c.university || ''} ${c.country || ''} ${c.status || ''} ${c.disc_reason || ''} ${getDomainCategory(c.id)} ${normalizeDomain(c.domain)}`.toLowerCase().includes(q)) return false;
        return true;
    });
}

function getFilteredCourseData() {
    const f = courseFilter;
    const q = f.search.trim().toLowerCase();
    return allCoursesData.filter(c => {
        if (f.status !== 'all' && c.status !== f.status) return false;
        if (f.category !== 'all' && c.issue_category !== f.category) return false;
        if (f.subtype !== 'all' && (c.issue_sub_type || '') !== f.subtype) return false;
        if (f.country !== 'all' && c.country !== f.country) return false;
        // Domain filter uses idx-based category
        if (f.domain !== 'all' && getDomainCategory(c.id) !== f.domain) return false;
        if (f.qs === 'yes' && !c.has_qs_badge) return false;
        if (f.qs === 'no' && c.has_qs_badge) return false;
        if (f.nirf === 'yes' && !c.has_nirf_badge) return false;
        if (f.nirf === 'no' && c.has_nirf_badge) return false;
        if (q && !`${c.name} ${c.university || ''} ${c.country || ''} ${c.domain || ''} ${c.status || ''} ${c.disc_reason || ''} ${getDomainCategory(c.id)} ${normalizeDomain(c.domain)}`.toLowerCase().includes(q)) return false;
        return true;
    });
}

function syncVerificationFilters() {
    const f = verificationFilter;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    set('vf-search', f.search); set('vf-status', f.status); set('vf-category', f.category);
    set('vf-subtype', f.subtype); set('vf-country', f.country); set('vf-domain', f.domain); set('vf-attr', f.attr);
}

function syncCourseFilters() {
    const f = courseFilter;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    set('cf-search', f.search); set('cf-status', f.status); set('cf-category', f.category);
    set('cf-subtype', f.subtype); set('cf-country', f.country); set('cf-domain', f.domain);
    set('cf-qs', f.qs); set('cf-nirf', f.nirf);
}

function applyVerificationFilter() { currentRecentPage = 1; renderRecentPage(); }
function applyCourseFilter() { currentPage = 1; renderCoursesPage(); }

function jumpToVerification(partial) {
    verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', ...partial };
    syncVerificationFilters();
    switchTab('tab-verification');
    applyVerificationFilter();
}

function jumpToCourses(partial) {
    courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', ...partial };
    syncCourseFilters();
    switchTab('tab-courses');
    applyCourseFilter();
}

function initFilters() {
    // Debounce the text search so each keystroke doesn't fully re-render
    // thousands of rows; selects apply immediately (change event is discrete).
    const debounce = (fn, ms) => {
        let t = null;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
    };
    const wire = (id, key, stateObj, applyFn, isText) => {
        const el = document.getElementById(id);
        if (!el) return;
        const apply = isText ? debounce(applyFn, 120) : applyFn;
        const handler = () => { stateObj[key] = isText ? el.value.trim() : el.value; apply(); };
        el.addEventListener('input', handler);
        el.addEventListener('change', handler);
    };
    wire('vf-search', 'search', verificationFilter, applyVerificationFilter, true);
    wire('vf-status', 'status', verificationFilter, applyVerificationFilter, false);
    wire('vf-category', 'category', verificationFilter, applyVerificationFilter, false);
    wire('vf-subtype', 'subtype', verificationFilter, applyVerificationFilter, false);
    wire('vf-country', 'country', verificationFilter, applyVerificationFilter, false);
    wire('vf-domain', 'domain', verificationFilter, applyVerificationFilter, false);
    wire('vf-attr', 'attr', verificationFilter, applyVerificationFilter, false);

    wire('cf-search', 'search', courseFilter, applyCourseFilter, true);
    wire('cf-status', 'status', courseFilter, applyCourseFilter, false);
    wire('cf-category', 'category', courseFilter, applyCourseFilter, false);
    wire('cf-subtype', 'subtype', courseFilter, applyCourseFilter, false);
    wire('cf-country', 'country', courseFilter, applyCourseFilter, false);
    wire('cf-domain', 'domain', courseFilter, applyCourseFilter, false);
    wire('cf-qs', 'qs', courseFilter, applyCourseFilter, false);
    wire('cf-nirf', 'nirf', courseFilter, applyCourseFilter, false);

    document.getElementById('vf-reset')?.addEventListener('click', () => {
        verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all' };
        syncVerificationFilters(); applyVerificationFilter();
    });
    document.getElementById('cf-reset')?.addEventListener('click', () => {
        courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any' };
        syncCourseFilters(); applyCourseFilter();
    });

    // Sticky KPI strip cards cross-filter their own tab.
    document.querySelectorAll('#vf-kpi-strip .kpi-strip-card').forEach(card => {
        card.addEventListener('click', () => {
            const partial = {};
            if (card.dataset.status) partial.status = card.dataset.status;
            if (card.dataset.category) partial.category = card.dataset.category;
            verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', ...partial };
            syncVerificationFilters(); applyVerificationFilter();
        });
    });
    document.querySelectorAll('#cf-kpi-strip .kpi-strip-card').forEach(card => {
        card.addEventListener('click', () => {
            const partial = {};
            if (card.dataset.status) partial.status = card.dataset.status;
            if (card.dataset.category) partial.category = card.dataset.category;
            courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', ...partial };
            syncCourseFilters(); applyCourseFilter();
        });
    });
}

// ================================================================
//  RECENT VERIFICATIONS  (Verification tab)
// ================================================================
function updateRecentVerifications(recent) {
    if (!recent) return;
    // Content hash (not just length) so solve/upload changes re-render even
    // when the row count is unchanged.
    const hash = JSON.stringify(recent.map(c => `${c.id}:${c.status}:${(c.solved_attrs || []).join('.')}`));
    if (hash === lastDataHash) return;
    lastDataHash = hash;
    recentData = [...recent].sort((a, b) => parseInt(a.id || '9') - parseInt(b.id || '9'));
    refreshFilterOptions();
    renderRecentPage();
}

function renderRecentPage() {
    const tbody = document.getElementById('recent-verifications-body');
    const info = document.getElementById('recent-page-info');
    const countEl = document.getElementById('vf-count');
    if (!tbody) return;
    const filteredData = getFilteredVerificationData();
    const totalPages = Math.ceil(filteredData.length / RECENT_PAGE_SIZE) || 1;
    if (currentRecentPage > totalPages) currentRecentPage = totalPages;
    const start = (currentRecentPage - 1) * RECENT_PAGE_SIZE;
    const slice = filteredData.slice(start, start + RECENT_PAGE_SIZE);
    tbody.innerHTML = slice.length === 0
        ? '<tr><td colspan="7" class="empty-state">No courses match the current filters.</td></tr>'
        : slice.map(c => {
            const issueLabel = c.issue_category ? (c.issue_sub_type || c.issue_category).replace(/_/g, ' ') : c.status;
            const badgeCls = c.issue_category === 'website_issue' ? 'badge-error' :
                c.issue_category === 'course_issue' ? 'badge-discrepancy' :
                    getBadgeClass(c.status);
            const domainCat = getDomainCategory(c.id);
            const domClick  = `event.stopPropagation();verificationFilter.domain='${escJs(domainCat)}';syncVerificationFilters();applyVerificationFilter();`;
            const fullName = escHtml(c.name);
            return `
            <tr onclick="showCourseModal('${c.id || ''}','${escJs(c.name)}','${escJs(c.university || '')}')">
                <td class="col-idx">${c.id || '—'}</td>
                <td class="course-name-cell" title="${fullName}"><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university || '—')}</td>
                <td><span class="domain-pill cell-filter" title="Filter by domain" onclick="${domClick}">${escHtml(domainCat)}</span></td>
                <td><span class="badge ${badgeCls}" title="${escHtml(c.issue_category || '')}">${issueLabel}</span></td>
                <td style="max-width:240px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${escHtml(c.disc_reason || '')}">${escHtml(c.disc_reason || '—')}</td>
                <td>${c.pdf_page || '—'}</td>
            </tr>`;
        }).join('');
    if (info) info.textContent = `Page ${currentRecentPage} of ${totalPages} · ${filteredData.length} courses`;
    if (countEl) countEl.textContent = `Showing ${slice.length} of ${filteredData.length}`;
}

document.getElementById('recent-prev-page')?.addEventListener('click', () => {
    if (currentRecentPage > 1) { currentRecentPage--; renderRecentPage(); }
});
document.getElementById('recent-next-page')?.addEventListener('click', () => {
    const max = Math.ceil(getFilteredVerificationData().length / RECENT_PAGE_SIZE);
    if (currentRecentPage < max) { currentRecentPage++; renderRecentPage(); }
});

// ================================================================
//  ALL COURSES
// ================================================================
async function loadAllCourses() {
    const tbody = document.getElementById('all-courses-body');
    if (allCoursesData.length > 0) { renderCoursesPage(); return; }
    if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Loading…</td></tr>';
    try {
        const res = await fetch(API_BASE_URL + '/api/courses.json');
        const data = await res.json();
        allCoursesData = (data.courses || []).sort((a, b) => parseInt(a.id || '9') - parseInt(b.id || '9'));
        // NOTE: recentData is owned by /api/data.json (fetchData). Do not
        // overwrite it from courses.json (which has no `recent` field) — that
        // would wipe the Verification tab's data.
        refreshFilterOptions();
        renderCoursesPage();
    } catch (e) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="empty-state" style="color:var(--red);">Error loading courses</td></tr>';
    }
}

function renderCoursesPage() {
    const tbody = document.getElementById('all-courses-body');
    const info = document.getElementById('page-info');
    const countEl = document.getElementById('cf-count');
    if (!tbody) return;
    const filteredData = getFilteredCourseData();
    const totalPages = Math.ceil(filteredData.length / PAGE_SIZE) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    const start = (currentPage - 1) * PAGE_SIZE;
    const slice = filteredData.slice(start, start + PAGE_SIZE);
    tbody.innerHTML = slice.length === 0
        ? '<tr><td colspan="8" class="empty-state">No courses match the current filters.</td></tr>'
        : slice.map(c => {
            const issueLabel = c.issue_category ? (c.issue_sub_type || c.issue_category).replace(/_/g, ' ') : c.status;
            const badgeCls = c.issue_category === 'website_issue' ? 'badge-error' :
                c.issue_category === 'course_issue' ? 'badge-discrepancy' :
                    getBadgeClass(c.status);
            const statusClick = `event.stopPropagation();courseFilter.status='${c.status}';syncCourseFilters();applyCourseFilter();`;
            const domainCat   = getDomainCategory(c.id);
            const domainClick = `event.stopPropagation();courseFilter.domain='${escJs(domainCat)}';syncCourseFilters();applyCourseFilter();`;
            return `<tr onclick="showCourseModal('${c.id}')">
            <td class="col-idx">${c.id}</td>
            <td class="course-name-cell" title="${escHtml(c.name)}"><strong>${escHtml(c.name)}</strong></td>
            <td>${escHtml(c.university || '—')}</td>
            <td>
                <span class="domain-pill cell-filter" title="Filter by domain category" onclick="${domainClick}">${escHtml(domainCat)}</span>
                ${c.domain && c.domain !== domainCat ? `<div style="font-size:0.72rem;color:var(--text-3);margin-top:2px;">${escHtml(c.domain)}</div>` : ''}
            </td>
            <td>${escHtml(c.country || '—')}</td>
            <td>${c.has_qs_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td><span class="badge ${badgeCls} cell-filter" title="Filter by status" onclick="${statusClick}">${issueLabel}</span></td>
        </tr>`;
        }).join('');
    if (info) info.textContent = `Page ${currentPage} of ${totalPages} · ${filteredData.length} courses`;
    if (countEl) countEl.textContent = `Showing ${slice.length} of ${filteredData.length}`;
}

document.getElementById('prev-page')?.addEventListener('click', () => {
    if (currentPage > 1) { currentPage--; renderCoursesPage(); }
});
document.getElementById('next-page')?.addEventListener('click', () => {
    const max = Math.ceil(getFilteredCourseData().length / PAGE_SIZE);
    if (currentPage < max) { currentPage++; renderCoursesPage(); }
});

// ================================================================
//  MODAL
// ================================================================
async function showCourseModal(courseId, fallbackName, fallbackUni) {
    if (allCoursesData.length === 0) {
        try {
            const res = await fetch(API_BASE_URL + '/api/courses.json');
            const data = await res.json();
            allCoursesData = data.courses || [];
            refreshFilterOptions();
        } catch (e) { return; }
    }
    let c = allCoursesData.find(x => String(x.id) === String(courseId));
    if (!c && fallbackName) c = allCoursesData.find(x => x.name === fallbackName && (x.university || '') === (fallbackUni || ''));
    if (!c) { alert('Course not found.'); return; }

    document.getElementById('modal-course-title').textContent = c.name;

    // The backend is the single source of truth for issue classification —
    // no client-side re-heuristic and no fabricated attribute rows. If a
    // course has no pdf_table, show an honest empty state.
    const rows = (c.pdf_table && c.pdf_table.length) ? c.pdf_table : [];

    const tbody = document.getElementById('modal-table-body');
    currentModalCourseId = c.id;
    const solvedAttrs = Array.isArray(c.solved_attrs) ? c.solved_attrs : [];
    const falseRows = rows.filter(r => r.status === 'FALSE');
    const solvedCount = falseRows.filter(r => solvedAttrs.includes(r.attribute)).length;
    const isWebsiteIssue = c.issue_category === 'website_issue';
    const isCourseIssue = c.issue_category === 'course_issue';
    const hasOpenAttrs = falseRows.some(r => !solvedAttrs.includes(r.attribute));

    if (rows.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No PDF verification data for this course.</td></tr>';
    } else {
        tbody.innerHTML = rows.map(row => {
            const isFalse = row.status === 'FALSE';
            const solved = isFalse && solvedAttrs.includes(row.attribute);
            const attrJs = JSON.stringify(row.attribute).replace(/"/g, '&quot;');
            let action = '<span style="color:var(--text-3);font-size:0.75rem;">—</span>';
            if (isFalse) {
                action = solved
                    ? `<button class="solve-tick solved" title="Mark unsolved" onclick="solveCourse(${c.id},${attrJs},true)">✓ Solved</button>`
                    : `<button class="solve-tick" title="Mark this issue solved" onclick="solveCourse(${c.id},${attrJs},false)">✓ Solve</button>`;
            }
            const statusTxt = solved ? 'SOLVED' : row.status;
            const statusClr = (row.status === 'MATCH' || solved) ? 'var(--green)' : 'var(--red)';
            return `
            <tr style="border-bottom:1px solid var(--border);" class="${solved ? 'solved-row' : ''}">
                <td style="padding:10px 12px;color:var(--text-1);font-weight:600;font-size:0.85rem;">${row.attribute}</td>
                <td style="padding:10px 12px;color:var(--text-2);font-size:0.85rem;">${escHtml(row.original)}</td>
                <td style="padding:10px 12px;color:var(--text-2);font-size:0.85rem;">${escHtml(row.verified)}</td>
                <td style="padding:10px 12px;text-align:center;font-weight:700;font-size:0.8rem;letter-spacing:0.04em;color:${statusClr};">${statusTxt}</td>
                <td style="padding:6px 10px;text-align:center;">${action}</td>
            </tr>`;
        }).join('');
    }

    // Header solve controls
    const solveAllBtn = document.getElementById('solve-all-btn');
    const solveWebBtn = document.getElementById('solve-website-btn');
    const removeVerifBtn = document.getElementById('remove-from-verification-btn');
    const progress = document.getElementById('modal-solve-progress');
    if (solveAllBtn) {
        solveAllBtn.style.display = (isCourseIssue && hasOpenAttrs) ? '' : 'none';
        solveAllBtn.textContent = `✓ Solve all (${falseRows.length - solvedCount} open)`;
        solveAllBtn.onclick = () => solveCourse(c.id, '_all', false);
    }
    if (solveWebBtn) {
        solveWebBtn.style.display = isWebsiteIssue ? '' : 'none';
        solveWebBtn.onclick = () => solveCourse(c.id, '_website', false);
    }
    // "Remove from Verification" — shown ONLY once the course is actually
    // solved (Verified). Solving itself doesn't remove it; this button does.
    if (removeVerifBtn) {
        removeVerifBtn.style.display = (c.status === 'Verified') ? '' : 'none';
        removeVerifBtn.onclick = () => removeFromVerification(c.id);
    }
    if (progress) {
        if (isCourseIssue && falseRows.length > 0) {
            progress.style.display = '';
            progress.textContent = `Solved ${solvedCount}/${falseRows.length}`;
        } else {
            progress.style.display = 'none';
        }
    }

    // Delete is a real action locally; disabled on the hosted dashboard.
    const deleteBtn = document.getElementById('delete-course-btn');
    if (deleteBtn) deleteBtn.style.display = isLocalEnv ? '' : 'none';

    document.getElementById('course-modal').classList.add('open');
}

// ── Per-issue solving ─────────────────────────────────────────────
let currentModalCourseId = null;

async function solveCourse(courseId, attr, unsolve) {
    if (courseId == null) return;

    // 1. OPTIMISTIC UI UPDATE (Blazing Fast)
    const c = allCoursesData.find(x => String(x.id) === String(courseId));
    let originalDataStr = null;
    if (c) {
        originalDataStr = JSON.stringify(c); // Backup for rollback
        c.solved_attrs = c.solved_attrs || [];

        if (attr === '_website') {
            c.issue_category = unsolve ? 'website_issue' : 'verified';
            c.status = unsolve ? 'Error' : 'Verified';
            c.disc_reason = '';
        } else if (attr === '_all') {
            const falseRows = (c.pdf_table || []).filter(r => r.status === 'FALSE').map(r => r.attribute);
            if (unsolve) {
                c.solved_attrs = c.solved_attrs.filter(a => !falseRows.includes(a));
            } else {
                for (const a of falseRows) if (!c.solved_attrs.includes(a)) c.solved_attrs.push(a);
            }
            c.issue_category = unsolve ? 'course_issue' : 'verified';
            c.status = unsolve ? 'Discrepancy' : 'Verified';
        } else {
            if (unsolve) {
                c.solved_attrs = c.solved_attrs.filter(a => a !== attr);
            } else {
                if (!c.solved_attrs.includes(attr)) c.solved_attrs.push(attr);
            }
            const falseRows = (c.pdf_table || []).filter(r => r.status === 'FALSE').map(r => r.attribute);
            const unsolvedCount = falseRows.filter(a => !c.solved_attrs.includes(a)).length;
            c.issue_category = unsolvedCount === 0 ? 'verified' : 'course_issue';
            c.status = unsolvedCount === 0 ? 'Verified' : 'Discrepancy';
        }
        showCourseModal(courseId); // Instant UI refresh
    }

    // 2. BACKGROUND SYNC TO SERVER
    try {
        const res = await fetch(`${API_BASE_URL}/api/course/${courseId}/solve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attr, unsolve: !!unsolve })
        });

        const data = await res.json();
        if (data.status !== 'success') throw new Error(data.message || 'Solve failed');

        // Refresh stats
        const upd = data.course || {};
        if (c) Object.assign(c, {
            issue_category: upd.issue_category,
            issue_sub_type: upd.issue_sub_type,
            status: upd.status,
            disc_reason: upd.disc_reason,
            solved_attrs: upd.solved_attrs || []
        });
        // Update the course's row in place. It stays visible in the Verification
        // tab (now marked Verified) until the user clicks "Remove from
        // Verification" or the next poll syncs it out — a Verified course is
        // excluded from the server's recent list, so it leaves within 5s anyway.
        const rc = recentData.find(x => String(x.id) === String(courseId));
        if (rc) Object.assign(rc, {
            issue_category: upd.issue_category,
            issue_sub_type: upd.issue_sub_type,
            status: upd.status,
            disc_reason: upd.disc_reason,
            solved_attrs: upd.solved_attrs || []
        });

        if (data.stats) {
            // Every headline number updates the instant a solve is persisted —
            // the 4 KPI parameters, both sticky strips, and the issue doughnut.
            updateCards(data.stats);
            updateIssuePieChart(data.stats);
        }
        // Re-apply active filters so both tabs reflect the change immediately.
        applyVerificationFilter();
        applyCourseFilter();
        fetchData(); // Trigger full refresh
    } catch (e) {
        console.error('Solve error:', e);
        // Rollback on failure
        if (c && originalDataStr) {
            Object.assign(c, JSON.parse(originalDataStr));
            showCourseModal(courseId);
        }
        // Re-sync from server so any optimistic removal is undone if the solve
        // didn't actually persist.
        fetchData();
        alert('Network request failed. The API might be sleeping/offline. Please wait a few seconds and try again.');
    }
}

// Remove an already-solved (Verified) course from the Verification tab view.
// The course is already Verified server-side, so it's already excluded from the
// server's recent list — this just drops it from the client list immediately
// and closes the modal. (Re-openable from the All Courses tab if ever needed.)
function removeFromVerification(courseId) {
    recentData = recentData.filter(x => String(x.id) !== String(courseId));
    document.getElementById('course-modal').classList.remove('open');
    applyVerificationFilter();
}

async function deleteCourse() {
    const id = currentModalCourseId;
    if (id == null) return;
    const c = allCoursesData.find(x => String(x.id) === String(id));
    const name = c?.name || '';
    if (!confirm(`Delete course #${id} — "${name}"?\n\nThis reindexes all course IDs and cannot be undone.`)) return;
    try {
        const res = await fetch(`${API_BASE_URL}/api/course/${id}`, { method: 'DELETE' });
        const data = await res.json();
        if (data.status !== 'success') throw new Error(data.message || 'Delete failed');
        document.getElementById('course-modal').classList.remove('open');
        allCoursesData = [];        // force reload from server
        await loadAllCourses();
        fetchData();
    } catch (e) {
        alert('Delete failed: ' + (e.message || 'network error'));
    }
}

function initModal() {
    document.getElementById('close-modal')?.addEventListener('click', () =>
        document.getElementById('course-modal').classList.remove('open'));
    document.getElementById('delete-course-btn')?.addEventListener('click', deleteCourse);
    document.getElementById('course-modal')?.addEventListener('click', e => {
        if (e.target === document.getElementById('course-modal'))
            document.getElementById('course-modal').classList.remove('open');
    });
    // Analytics detail modal (single, reused) — close button + backdrop + Esc.
    const anModal = document.getElementById('an-modal');
    if (anModal) {
        document.getElementById('an-modal-close')?.addEventListener('click', closeAnalyticsModal);
        anModal.addEventListener('click', e => { if (e.target === anModal) closeAnalyticsModal(); });
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape' && anModal.classList.contains('open')) closeAnalyticsModal();
        });
    }
}

// ================================================================
//  MAIN DATA FETCH
// ================================================================
async function fetchData() {
    if (!globalData) document.body.dataset.loading = 'true';
    try {
        const res = await fetch(API_BASE_URL + '/api/data.json');
        const data = await res.json();
        if (data.status !== 'success') return;

        globalData = data;

        // ── Change-guarded, no-animation renders ──────────────────────
        // Only re-render the expensive visuals when their underlying data
        // actually changed since the last poll. A 5s tick that returns
        // identical data therefore produces zero visible flicker. The very
        // first fetch keeps Chart.js animations so the initial paint feels
        // alive; every subsequent poll uses update('none').
        const animate = firstDataFetch;
        const statsHash = JSON.stringify(data.stats);
        const countryHash = JSON.stringify(data.country_counts);
        const barSrc = barMode === 'domain' ? data.domain_counts : data.country_counts;
        const barHash = JSON.stringify(barSrc);

        if (statsHash !== lastStatsHash) {
            updateCards(data.stats);
            updateIssuePieChart(data.stats, animate);
            lastStatsHash = statsHash;
        }
        if (barHash !== lastBarHash) {
            updateBarChart(animate);
            lastBarHash = barHash;
        }
        if (countryHash !== lastCountryHash) {
            updateLineChart(data.country_counts, animate);
            updateMapChart(data.country_counts, animate);
            updateCountryLeaderboard(data.country_counts, 'country-list');
            lastCountryHash = countryHash;
        }

        // Real recent courses only — no fabricated fallback rows.
        // (Already content-hash guarded via lastDataHash.)
        updateRecentVerifications(data.recent || []);

        if (currentFilter.type) applyFilter(currentFilter.type, currentFilter.value);
        document.body.dataset.loading = 'false';
        firstDataFetch = false;
    } catch (e) {
        console.error('Data fetch error:', e);
    }
}

// ================================================================
//  ANALYTICS TAB  —  Full Enriched Implementation
//  Uses BOTH globalData (/api/data.json) AND analyticsData (/api/analytics.json)
// ================================================================
let anCredentialChart = null;
let anPricingChart = null;
let anDomainChart = null;
let anStatusChart = null;
let anFreePaidChart = null;
let anFeeHistogramChart = null;
let anIssueOriginChart = null;
let anDiscParetoChart = null;
let anCredentialCostChart = null;
let anRankedCredentialChart = null;
let anRankingMixChart = null;
let analyticsData = null;
let lastAnalyticsHash = '';
let geoTableData = [];
let geoRegionFilter = null; // when set, renderGeoTable only shows countries in this region

const PALETTE = ['#6366f1', '#818cf8', '#f43f5e', '#1dda9f', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'];
const STATUS_COLORS = { verified: '#1dda9f', discrepancy: '#f59e0b', error: '#f43f5e', unverified: '#6366f1' };

// ── Emoji-free country chip + region helpers ─────────────────────
const COUNTRY_INITIALS = {
    'India': 'IN', 'United States': 'US', 'Australia': 'AU',
    'United Kingdom': 'UK', 'Canada': 'CA', 'Germany': 'DE',
    'France': 'FR', 'Singapore': 'SG', 'South Africa': 'ZA',
    'New Zealand': 'NZ', 'UAE': 'AE', 'China': 'CN',
    'Japan': 'JP', 'Netherlands': 'NL', 'Switzerland': 'CH',
    'Brazil': 'BR', 'Italy': 'IT', 'Spain': 'ES',
    'Ireland': 'IE', 'Sweden': 'SE', 'Denmark': 'DK',
};
function countryInitials(name) {
    if (!name) return '';
    const n = String(name);
    for (const [k, v] of Object.entries(COUNTRY_INITIALS)) {
        if (n.toLowerCase().includes(k.toLowerCase()) || k.toLowerCase().includes(n.toLowerCase())) return v;
    }
    const parts = n.split(/[\s,()-]+/).filter(Boolean);
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
}
function initialsChip(name) {
    return `<span class="an-initials-chip" title="${escHtml(name)}">${escHtml(countryInitials(name))}</span>`;
}
const REGION_MAP = {
    'India': 'INDIA', 'Sri Lanka': 'SOUTH ASIA', 'Pakistan': 'SOUTH ASIA', 'Bangladesh': 'SOUTH ASIA', 'Nepal': 'SOUTH ASIA',
    'United States': 'NORTH AMERICA', 'Canada': 'NORTH AMERICA', 'Mexico': 'LATIN AMERICA',
    'United Kingdom': 'EUROPE', 'Germany': 'EUROPE', 'France': 'EUROPE', 'Italy': 'EUROPE', 'Spain': 'EUROPE',
    'Netherlands': 'EUROPE', 'Switzerland': 'EUROPE', 'Ireland': 'EUROPE', 'Sweden': 'EUROPE', 'Denmark': 'EUROPE',
    'Australia': 'EAST ASIA & PACIFIC', 'New Zealand': 'EAST ASIA & PACIFIC', 'China': 'EAST ASIA & PACIFIC',
    'Japan': 'EAST ASIA & PACIFIC', 'Singapore': 'EAST ASIA & PACIFIC', 'South Korea': 'EAST ASIA & PACIFIC',
    'UAE': 'MIDDLE EAST & AFRICA', 'Saudi Arabia': 'MIDDLE EAST & AFRICA', 'South Africa': 'MIDDLE EAST & AFRICA',
    'Brazil': 'LATIN AMERICA', 'Argentina': 'LATIN AMERICA'
};
function regionFor(name) {
    if (!name) return 'OTHER';
    for (const [k, v] of Object.entries(REGION_MAP)) {
        if (name.toLowerCase().includes(k.toLowerCase()) || k.toLowerCase().includes(name.toLowerCase())) return v;
    }
    return 'OTHER';
}
function anomalyChip(f) {
    const label = f === 'LOW-VERIF' ? 'LOW VERIFICATION'
        : f === 'HIGH-ISSUE' ? 'HIGH ISSUE RATE'
        : f === 'FEE-OUTLIER' ? 'FEE OUTLIER'
        : String(f).replace(/-/g, ' ').toUpperCase();
    const cls = f === 'FEE-OUTLIER' ? 'an-tag--fee'
        : f === 'HIGH-ISSUE' ? 'an-tag--high'
        : f === 'LOW-VERIF' ? 'an-tag--low'
        : 'an-tag--neutral';
    return `<span class="an-tag ${cls}">${escHtml(label)}</span>`;
}

// ── Reusable chart + viz helpers ────────────────────────────────
function drawCenter(chart, line1, line2) {
    const { ctx, width, height } = chart;
    ctx.save();
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = getComputedStyle(chart.canvas).getPropertyValue('--text-1') || '#fff';
    ctx.font = '700 22px Inter, system-ui, sans-serif';
    ctx.fillText(line1, width / 2, height / 2 - (line2 ? 8 : 0));
    if (line2) {
        ctx.font = '700 10px Inter, system-ui, sans-serif';
        ctx.fillStyle = getComputedStyle(chart.canvas).getPropertyValue('--text-3') || '#888';
        ctx.fillText(line2, width / 2, height / 2 + 14);
    }
    ctx.restore();
}
function renderHeatmapCell(value, max, opts) {
    opts = opts || {};
    const v = Number(value) || 0;
    const m = Number(max) || 1;
    const pct = m > 0 ? Math.max(0, Math.min(1, v / m)) : 0;
    let cls = 'an-heatmap-cell';
    if (v <= 0) cls += ' an-heatmap-cell--blank';
    else if (pct >= 0.66) cls += ' an-heatmap-cell--high';
    else if (pct >= 0.33) cls += ' an-heatmap-cell--med';
    else cls += ' an-heatmap-cell--low';
    const txt = opts.text != null ? opts.text : (v > 0 ? String(v) : '');
    return `<div class="${cls}" title="${escHtml(opts.title || '')}">${escHtml(String(txt))}</div>`;
}
function renderScoreGauge(elId, value, max, opts) {
    const el = document.getElementById(elId);
    if (!el) return;
    opts = opts || {};
    const maxv = Number(max) || 1;
    const v = Math.max(0, Math.min(maxv, Number(value) || 0));
    const pct = v / maxv;
    const r = 70, cx = 90, cy = 90;
    const circ = Math.PI * r;
    const dash = circ * pct;
    const color = opts.color || 'var(--accent)';
    const stats = opts.stats ? `<div class="an-score-gauge-stats">${opts.stats.map(s => `<div class="an-score-gauge-stat"><span class="an-stat-num">${escHtml(String(s.value))}</span><span class="an-stat-cap">${escHtml(s.label)}</span></div>`).join('')}</div>` : '';
    el.innerHTML = `
        <div class="an-score-gauge-svg">
            <svg viewBox="0 0 180 110" width="180" height="110" aria-hidden="true">
                <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="var(--bg-hover)" stroke-width="14" stroke-linecap="round"/>
                <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="${color}" stroke-width="14" stroke-linecap="round" stroke-dasharray="${dash} ${circ}" />
            </svg>
            <div class="an-score-gauge-value">${Math.round(v)}<span class="an-score-gauge-max">/${maxv}</span></div>
        </div>
        ${opts.gaugeLabel ? `<div class="an-score-gauge-label">${escHtml(opts.gaugeLabel)}</div>` : ''}
        ${opts.bandLabel ? `<div class="an-score-band" style="color:${color};">${escHtml(opts.bandLabel)}</div>` : ''}
        ${opts.sub ? `<div class="an-score-gauge-sub">${escHtml(opts.sub)}</div>` : ''}
        ${stats}`;
}
function medianOf(arr) { const s = [...arr].sort((a, b) => a - b); const n = s.length; if (!n) return null; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; }
function affordabilityIndex(pc) {
    const total = (pc.Free || 0) + (pc.Affordable || 0) + (pc.Mid || 0) + (pc.Premium || 0);
    if (!total) return null;
    return Math.round((100 * (pc.Free || 0) + 70 * (pc.Affordable || 0) + 45 * (pc.Mid || 0) + 15 * (pc.Premium || 0)) / total);
}
function anVal(id) { const e = document.getElementById(id); return e ? e.value : ''; }

// ── Sub-tab switching ────────────────────────────────────────────
function initAnalyticsSubTabs() {
    document.querySelectorAll('.asubtab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.asubtab').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.atab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const t = document.getElementById(btn.dataset.atab);
            if (t) t.classList.add('active');
        });
    });
    document.getElementById('an-country-search')?.addEventListener('input', e => {
        // Free-text search overrides the region filter.
        geoRegionFilter = null;
        document.querySelectorAll('.an-region-row.active-region').forEach(r => r.classList.remove('active-region'));
        renderGeoTable(e.target.value.toLowerCase());
    });
}

// ── Shared empty-state row helper ─────────────────────────────────
function emptyRow(colCount, msg) {
    return `<tr><td colspan="${colCount}" class="an-empty">${escHtml(msg)}</td></tr>`;
}

// ── Single analytics detail modal (reused for every detail view) ──
function openAnalyticsModal(title, kpisHTML, bodyHTML) {
    const overlay = document.getElementById('an-modal');
    if (!overlay) return;
    document.getElementById('an-modal-title').textContent = title;
    document.getElementById('an-modal-kpis').innerHTML = kpisHTML || '';
    document.getElementById('an-modal-body').innerHTML = bodyHTML || '';
    overlay.classList.add('open');
}

function closeAnalyticsModal() {
    document.getElementById('an-modal')?.classList.remove('open');
}

function modalKPIs(pairs) {
    return (pairs || []).map(([label, val]) =>
        `<div class="an-modal-kpi"><div class="an-modal-kpi-val">${escHtml(String(val))}</div><div class="an-modal-kpi-label">${escHtml(label)}</div></div>`
    ).join('');
}

// Compact, reusable courses table built from analytics_courses (the full
// matching course list — a real upgrade over the old globalData.recent drilldowns
// which only showed a handful of issue courses).
function coursesTable(rows) {
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) return '<div class="an-modal-empty">No matching course-level data available.</div>';
    const head = `<thead><tr>
        <th>#</th><th>Course</th><th>University</th><th>Country</th><th>Level</th><th>Cost</th><th>Status</th><th>Rank</th>
    </tr></thead>`;
    const body = list.map((r, i) => {
        const rank = r.qs_ranked && r.nirf_ranked ? 'QS · NIRF'
            : r.qs_ranked ? 'QS' : r.nirf_ranked ? 'NIRF' : '—';
        const cost = r.fee_inr != null
            ? `${Math.round(r.fee_inr).toLocaleString()} INR`
            : escHtml(r.cost_tier || '—');
        return `<tr>
            <td style="color:var(--text-3);">${i + 1}</td>
            <td class="course-name-cell" style="font-weight:600;" title="${escHtml(r.name || '')}">${escHtml(r.name || '—')}</td>
            <td>${escHtml(r.university || '—')}</td>
            <td>${escHtml(r.country || '—')}</td>
            <td>${escHtml(r.level || '—')}</td>
            <td style="text-align:right;">${cost}</td>
            <td>${statusBadge(r.status)}</td>
            <td style="text-align:center;">${rank}</td>
        </tr>`;
    }).join('');
    return `<table class="an-modal-table">${head}<tbody>${body}</tbody></table>`;
}

// ── Content composers (each fills the single #an-modal) ────────────
// Country detail — used by BOTH the Geography footprint row (sourceKey='geo',
// reads analyticsData.country_quality dict) and the Verification country row
// (sourceKey='verif', reads verification_quality.country_quality list).
function showCountryDetail(countryName, sourceKey) {
    const d = analyticsData || {};
    let q = {};
    if (sourceKey === 'verif') {
        const list = ((d.verification_quality || {}).country_quality) || [];
        q = list.find(r => r.country === countryName) || {};
    } else {
        q = (d.country_quality || {})[countryName] || {};
    }
    const courses = (d.analytics_courses || []).filter(r => r.country === countryName);
    const cnt = q.total || courses.length;
    const region = q.region || regionFor(countryName);
    const kpis = modalKPIs([
        ['Courses', cnt],
        ['Verified', q.verified ?? '—'],
        ['Discrepancies', q.discrepancies ?? '—'],
        ['Errors', q.errors ?? '—'],
        ['Verified Rate', q.verified_rate != null ? pct(q.verified_rate) : '—'],
        ['Median Fee', q.median_fee != null ? Math.round(q.median_fee).toLocaleString() : '—'],
        ['Free Courses', q.free_count ?? '—'],
        ['QS-Ranked Unis', q.qs_universities ?? '—'],
        ['NIRF-Ranked Unis', q.nirf_universities ?? '—'],
        ['Top Domain', q.top_domain || '—'],
        ['Top University', q.top_university || '—'],
    ]);
    openAnalyticsModal(`${countryName} — ${cnt} Courses · ${escHtml(region)}`, kpis, coursesTable(courses));
}

function showDomainDetail(domainName) {
    const d = analyticsData || {};
    const sat = (d.domain_saturation || []).find(s => s.domain === domainName) || {};
    const courses = (d.analytics_courses || []).filter(r => r.domain === domainName);
    const verified = courses.filter(r => (r.status || '') === 'Verified').length;
    const discrepancies = courses.filter(r => (r.status || '') === 'Discrepancy').length;
    const kpis = modalKPIs([
        ['Programs', sat.total || courses.length],
        ['Share', sat.share_pct != null ? sat.share_pct.toFixed(1) + '%' : '—'],
        ['Saturation', sat.saturation_label || '—'],
        ['HHI Contribution', sat.hhi_contribution != null ? sat.hhi_contribution : '—'],
        ['Verified', verified],
        ['Discrepancies', discrepancies],
    ]);
    openAnalyticsModal(`${domainName} — Domain Deep-Dive`, kpis, coursesTable(courses));
}

function showUniversityDetail(university) {
    const d = analyticsData || {};
    const lb = (d.university_leaderboard || []).find(r => r.university === university) || {};
    const courses = (d.analytics_courses || []).filter(r => r.university === university);
    const kpis = modalKPIs([
        ['Courses', lb.course_count || courses.length],
        ['Country', lb.country || '—'],
        ['Verified', lb.verified ?? '—'],
        ['Discrepancies', lb.discrepancies ?? '—'],
        ['Errors', lb.errors ?? '—'],
        ['Verified Rate', lb.verification_rate != null ? pct(lb.verification_rate) : '—'],
        ['QS', lb.qs_ranked ? 'Ranked' : '—'],
        ['NIRF', lb.nirf_ranked ? 'Ranked' : '—'],
    ]);
    openAnalyticsModal(`${university}`, kpis, coursesTable(courses));
}

function showAnomalyDetail(anomalyType) {
    const d = analyticsData || {};
    const labels = {
        outlier_fees: 'Outlier Fees', unverified_rank_claim: 'Unverified Rank Claim',
        all_attribute_mismatch: 'All-Attribute Mismatch', website_unreachable: 'Website Unreachable'
    };
    const a = (d.verification_quality || {}).anomalies?.find(x => x.type === anomalyType) || {};
    const samples = a.sample_ids || [];
    // Normalize sample entries (may be bare strings or {name,...} objects) into
    // analytics_courses-style rows for the shared coursesTable renderer.
    const rows = samples.map(s => {
        if (s == null) return null;
        if (typeof s === 'string' || typeof s === 'number')
            return { name: String(s), university: null, country: null, level: null, cost_tier: null, status: null };
        return {
            name: s.name || s.id || s.course || '—',
            university: s.university || null,
            country: s.country || null,
            level: s.level || null,
            cost_tier: s.cost_tier || null,
            fee_inr: s.fee_inr ?? null,
            status: s.status || null,
            qs_ranked: !!s.qs_ranked,
            nirf_ranked: !!s.nirf_ranked,
        };
    }).filter(Boolean);
    const kpis = modalKPIs([
        ['Type', labels[anomalyType] || anomalyType],
        ['Count', a.count ?? 0],
        ['Severity', a.severity || '—'],
        ['Samples Shown', rows.length],
    ]);
    openAnalyticsModal(`${labels[anomalyType] || anomalyType} — Anomaly Detail`, kpis, coursesTable(rows));
}

// ── Status badge helper ──────────────────────────────────────────
function statusBadge(s) {
    const cls = getBadgeClass(s || '');
    return `<span class="badge ${cls}">${escHtml(s || '—')}</span>`;
}

// ── KPI cards ────────────────────────────────────────────────────
// 6-card emoji-free KPI strip. Reads the canonical `Free` key from
// pricing_category (build emits 'Free', not 'Free Courses') and the
// cost_access block for affordability / free-vs-paid.
function populateAnalyticsKPIs(d, globalStats, ccOverride) {
    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

    const tot = globalStats?.total || 0;
    const cc = ccOverride || globalData?.country_counts || {};
    const indiaCount = Object.entries(cc)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    const intlCount = Math.max(0, tot - indiaCount);

    const pricingCat = d.pricing_category || {};
    const cost = d.cost_access || {};
    const fvp = cost.free_vs_paid || {};
    const freeCount = pricingCat['Free'] || fvp.free || 0;
    const paidCount = fvp.paid != null ? fvp.paid
        : Math.max(0, Object.values(pricingCat).reduce((s, v) => s + (Number(v) || 0), 0) - freeCount);

    const pivotKeys = Object.keys(d.country_pivot || {}).filter(k => isValidCountry(k));
    const countryCnt = pivotKeys.length || Object.keys(cc).filter(k => isValidCountry(k)).length;

    const vs = globalStats || {};
    const matchRate = vs.total ? ((vs.verified || 0) / vs.total * 100).toFixed(1) : '—';
    const affordability = cost.affordability_index;
    const ratio = fvp.ratio;

    set('an-total', tot);
    set('an-indian', indiaCount);
    set('an-intl', intlCount);
    set('an-matchrate', matchRate + (matchRate !== '—' ? '%' : ''));
    set('an-variants-sub', `${Object.values(d.variant_category || {}).reduce((s, v) => s + (Number(v) || 0), 0)} delivery variants`);
    set('an-indian-pct', `${tot ? ((indiaCount / tot) * 100).toFixed(1) : '—'}% of total catalog`);
    set('an-countries-count', `${countryCnt} countries represented`);
    set('an-verified-sub', `${vs.verified || '—'} courses perfectly verified`);
    set('an-affordability', affordability != null ? affordability : '—');
    set('an-affordability-sub', `based on ${paidCount} priced programs in INR`);
    set('an-free-paid-ratio', ratio != null ? Number(ratio).toFixed(2) : '—');
    set('an-free-paid-sub', `${freeCount} free of ${paidCount} priced`);
}


// ── Auto-insight cards (9 emoji-free accent-ruled cards) ─────────
function populateInsightCards(d, globalData) {
    const container = document.getElementById('insight-cards-row');
    if (!container) return;

    const recent = globalData?.recent || [];
    const stats = globalData?.stats || {};
    const countryPivot = d.country_pivot || {};
    const domainPivot = d.domain_pivot || {};

    const tot = stats.total || 1;
    const matchPct = ((stats.verified || 0) / tot * 100).toFixed(1);
    const discPct = ((stats.discrepancies || 0) / tot * 100).toFixed(1);

    const topCountry = Object.entries(countryPivot).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])[0];
    const topDomain = Object.entries(domainPivot).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0))[0];

    const countryIssues = {};
    recent.forEach(r => {
        if (isValidCountry(r.country) && (r.status || '').toLowerCase() !== 'verified') {
            countryIssues[r.country] = (countryIssues[r.country] || 0) + 1;
        }
    });
    const topIssueCountry = Object.entries(countryIssues).sort((a, b) => b[1] - a[1])[0];

    const uniCounts = {};
    recent.forEach(r => { if (r.university) uniCounts[r.university] = (uniCounts[r.university] || 0) + 1; });
    const topUni = Object.entries(uniCounts).sort((a, b) => b[1] - a[1])[0];

    const cost = d.cost_access || {};
    const fvp = cost.free_vs_paid || {};
    const rs = d.ranked_share || {};

    const cards = [
        { tag: 'MATCH RATE', color: 'var(--green)', value: `${matchPct}%`, sub: 'Courses perfectly verified' },
        { tag: 'DISCREPANCY RATE', color: 'var(--accent)', value: `${discPct}%`, sub: 'Require manual review' },
        { tag: 'TOP COUNTRY', color: 'var(--blue)', value: topCountry ? topCountry[0] : '—', sub: topCountry ? `${topCountry[1]} courses` : '' },
        { tag: 'TOP DOMAIN', color: 'var(--purple)', value: topDomain?.[0] || '—', sub: topDomain ? `${topDomain[1].Total || 0} courses` : '' },
        { tag: 'TOP UNIVERSITY', color: 'var(--blue)', value: topUni?.[0] || '—', sub: topUni ? `${topUni[1]} courses` : '' },
        { tag: 'MOST-FLAGGED COUNTRY', color: 'var(--red)', value: topIssueCountry ? topIssueCountry[0] : 'None', sub: topIssueCountry ? `${topIssueCountry[1]} flagged` : 'Portfolio is clean' },
        { tag: 'AFFORDABILITY INDEX', color: 'var(--green)', value: cost.affordability_index != null ? cost.affordability_index : '—', sub: 'Cost-access composite' },
        { tag: 'FREE-TO-PAID', color: 'var(--accent)', value: fvp.ratio != null ? Number(fvp.ratio).toFixed(2) : '—', sub: `${fvp.free || 0} free / ${fvp.paid || 0} paid` },
        { tag: 'QS-RANKED SHARE', color: 'var(--purple)', value: rs.qs_pct != null ? rs.qs_pct + '%' : '—', sub: 'Of catalog QS-ranked' },
    ];

    container.innerHTML = cards.map(c => `
        <div class="insight-card" style="border-left:3px solid ${c.color};">
            <div class="insight-tag" style="color:${c.color};">${escHtml(c.tag)}</div>
            <div class="insight-value" style="color:${c.color};">${escHtml(String(c.value))}</div>
            <div class="insight-sub">${escHtml(c.sub)}</div>
        </div>`).join('');
}

// ── India vs World split bar + benchmark table ───────────────────
function populateSplitVisual(indianPct, d) {
    const el = document.getElementById('an-split-visual');
    if (!el) return;
    const intlPct = 100 - indianPct;
    const bench = (d && d.benchmark_india_intl) || {};
    const labels = {
        courses: 'Total Courses', variant_share: 'Variant Share', verification_rate: 'Verification Rate',
        discrepancy_rate: 'Discrepancy Rate', error_rate: 'Error Rate', median_fee_inr: 'Median Fee (INR)',
        cost_access_index: 'Cost-Access Index', qs_ranked_share: 'QS-Ranked Share',
        nirf_ranked_share: 'NIRF-Ranked Share', top_specialization: 'Top Specialization',
        geographic_contribution_hhi: 'Geo Contribution HHI'
    };
    const fmt = (m, v) => {
        if (v == null) return '—';
        if (m === 'median_fee_inr') return Math.round(v).toLocaleString();
        if (typeof v === 'number') return (Math.round(v * 100) / 100).toString();
        return String(v);
    };
    let table = '';
    if (Object.keys(bench).length) {
        const rows = Object.keys(bench).map(m => {
            const r = bench[m];
            const delta = r.delta != null ? r.delta : '';
            return `<tr><td>${escHtml(r.label || labels[m] || m)}</td><td>${escHtml(String(fmt(m, r.india)))}</td><td>${escHtml(String(fmt(m, r.international)))}</td><td class="an-benchmark-delta">${escHtml(String(delta))}</td></tr>`;
        }).join('');
        table = `<div class="an-benchmark-table-wrap"><table class="an-benchmark-table"><thead><tr><th>Metric</th><th>India</th><th>International</th><th>Delta</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }
    el.innerHTML = `
        <div class="an-split-chips">
            <span class="an-split-chip an-split-chip--in">IN ${indianPct.toFixed(1)}%</span>
            <span class="an-split-chip an-split-chip--intl">INTL ${intlPct.toFixed(1)}%</span>
        </div>
        <div class="an-split-bar">
            <div class="an-split-bar-in" style="width:${indianPct.toFixed(1)}%"></div>
            <div class="an-split-bar-intl" style="width:${intlPct.toFixed(1)}%"></div>
        </div>
        <div class="an-split-grid">
            <div class="an-split-tile an-split-tile--in"><div class="an-split-num">${indianPct.toFixed(1)}%</div><div class="an-split-cap">Indian Catalog</div></div>
            <div class="an-split-tile an-split-tile--intl"><div class="an-split-num">${intlPct.toFixed(1)}%</div><div class="an-split-cap">International</div></div>
        </div>
        ${table}`;
}

// ── Credential doughnut (center stat + legend, onClick preserved) ─
function populateCredentialChart(courseCategory) {
    const ctx = document.getElementById('an-credential-chart');
    if (!ctx) return;
    const entries = Object.entries(courseCategory || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (anCredentialChart) anCredentialChart.destroy();
    const total = entries.reduce((s, [, v]) => s + v, 0);
    const dominant = entries[0]?.[0] || '—';
    const centerPlugin = {
        id: 'credentialCenter',
        afterDraw(chart) {
            drawCenter(chart, `${total}`, `DOMINANT: ${String(dominant).toUpperCase()}`);
        }
    };
    anCredentialChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: entries.map(e => e[0]),
            datasets: [{ data: entries.map(e => e[1]), backgroundColor: PALETTE, borderColor: 'transparent', borderWidth: 0, hoverOffset: 10 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '70%',
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => `${c.label}: ${c.raw} Programs` } }
            },
            onClick: (e, els) => {
                if (!els.length) return;
                const label = entries[els[0].index][0];
                openAnalyticsDrilldownByCategory(label);
            }
        },
        plugins: [centerPlugin]
    });
    const legend = document.getElementById('an-credential-legend');
    if (legend) legend.innerHTML = entries.map(([label, val], i) => `
        <div class="an-legend-item" onclick="openAnalyticsDrilldownByCategory('${escJs(label)}')">
            <div class="an-legend-dot" style="background:${PALETTE[i % PALETTE.length]}"></div>
            <div>
                <div class="an-legend-name">${escHtml(label)}</div>
                <div class="an-legend-val">${val} Programs</div>
            </div>
        </div>`).join('');
}

// ── Pricing bar chart ────────────────────────────────────────────
function populatePricingChart(pricingCategory) {
    const ctx = document.getElementById('an-pricing-chart');
    if (!ctx) return;
    const entries = Object.entries(pricingCategory || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (anPricingChart) anPricingChart.destroy();
    anPricingChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: entries.map(e => e[0]),
            datasets: [{
                label: 'Courses', data: entries.map(e => e[1]),
                backgroundColor: 'rgba(241,107,107,0.8)', hoverBackgroundColor: '#f16b6b',
                borderRadius: 8, borderSkipped: false
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 12, weight: '600' }, maxRotation: 30 } },
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { precision: 0 } }
            },
            animation: { duration: 900, easing: 'easeOutQuart' },
            // Drill into All Courses via a real cost text-search on the bucket's
            // first word (e.g. "Free Courses" → search "free" in cost). No
            // fabricated mapping; an empty result honestly shows the empty-state.
            onClick: (e, els) => {
                if (!els.length) return;
                const label = entries[els[0].index][0];
                const kw = label.split(' ')[0].toLowerCase();
                jumpToCourses({ search: kw });
            }
        }
    });
}

// ── Top countries hub list (flag-emoji replaced with initials chip) ─
function populateAnTopCountries(countryPivot) {
    const el = document.getElementById('an-top-countries');
    if (!el) return;
    const entries = Object.entries(countryPivot || {}).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1]).slice(0, 5);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt], i) => `
        <div class="an-hub-row clickable-row" onclick="showCountryDetail('${escJs(name)}','geo')" title="Click to see courses">
            <div class="an-hub-rank">${i + 1}</div>
            <div class="an-hub-name">${initialsChip(name)} ${escHtml(name)}</div>
            <div class="an-hub-bar-wrap"><div class="an-hub-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div>
            <div class="an-hub-count">${cnt}</div>
        </div>`).join('');
}

// ── Geography table ──────────────────────────────────────────────
// Per-country verified/issues come from the server `country_status` map
// (computed over ALL courses). The old code derived them from `recent`,
// which excludes Verified courses — so verified was always 0/—. country_status
// fixes that. We fall back to `recent` only if the map is absent (old server).
function countryStatusFor(name) {
    const cs = globalData?.country_status || {};
    if (cs[name]) return cs[name];
    const nl = String(name).toLowerCase();
    for (const k of Object.keys(cs)) {
        const kl = k.toLowerCase();
        if (kl === nl || kl.includes(nl) || nl.includes(kl)) return cs[k];
    }
    return null;
}

function renderGeoTable(search = '') {
    const tbody = document.getElementById('an-country-tbody');
    if (!tbody) return;
    const cq = (analyticsData && analyticsData.country_quality) || {};
    const anomalies = (analyticsData && analyticsData.geo_anomalies) || {};
    const total = geoTableData.reduce((s, [, v]) => s + v, 0) || 1;
    const max = geoTableData[0]?.[1] || 1;
    let rows = geoTableData;
    if (search) rows = rows.filter(([k]) => k.toLowerCase().includes(search));
    if (geoRegionFilter) rows = rows.filter(([k]) => regionFor(k) === geoRegionFilter);

    if (!rows.length) {
        const why = geoRegionFilter ? `No countries in region "${geoRegionFilter}".` : 'No countries match the current filter.';
        tbody.innerHTML = `<tr><td colspan="10" class="an-empty">${why}</td></tr>`;
        return;
    }
    tbody.innerHTML = rows.map(([name, cnt], i) => {
        const st = countryStatusFor(name);
        const verified = st ? st.verified : 0;
        const issues = st ? (st.total - st.verified) : 0;
        const q = cq[name] || {};
        const qs = q.quality_score;
        const rankedU = (q.qs_universities || 0) + (q.nirf_universities || 0);
        const region = q.region || regionFor(name);
        let flags = Array.isArray(q.anomaly_flags) ? q.anomaly_flags.slice() : [];
        if (anomalies.low_verification && anomalies.low_verification.includes(name) && !flags.includes('LOW-VERIF')) flags.push('LOW-VERIF');
        if (anomalies.high_issue_rate && anomalies.high_issue_rate.includes(name) && !flags.includes('HIGH-ISSUE')) flags.push('HIGH-ISSUE');
        if (anomalies.fee_outlier && anomalies.fee_outlier.includes(name) && !flags.includes('FEE-OUTLIER')) flags.push('FEE-OUTLIER');
        const chips = flags.map(anomalyChip).join('');
        return `<tr class="clickable-row" onclick="showCountryDetail('${escJs(name)}','geo')" title="Click to see courses">
            <td><span class="geo-rank">${(i + 1).toString().padStart(2, '0')}</span></td>
            <td>${initialsChip(name)} <strong>${escHtml(name)}</strong></td>
            <td>${escHtml(region)}</td>
            <td style="text-align:center;"><span class="geo-volume-badge">${cnt}</span></td>
            <td style="text-align:center;color:var(--green);font-weight:700;">${st ? verified : '—'}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${st ? issues : '—'}</td>
            <td style="text-align:right;"><span class="geo-share">${((cnt / total) * 100).toFixed(1)}%</span></td>
            <td style="text-align:center;">${qs != null ? qs : '—'}</td>
            <td style="text-align:center;">${rankedU || '—'}</td>
            <td><div class="geo-prog-wrap"><div class="geo-prog-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div>${chips ? `<div class="an-chip-row">${chips}</div>` : ''}</td>
        </tr>`;
    }).join('');
}

// ── Domain tab (saturation columns + saturation-colored bars) ────
function populateDomainTab(domainPivot, d) {
    const ctx = document.getElementById('an-domain-chart');
    const recent = globalData?.recent || [];
    const satMap = {};
    (d && d.domain_saturation || []).forEach(s => satMap[s.domain] = s);
    const satColor = { SATURATED: '#f43f5e', COMPETITIVE: '#f59e0b', NICHE: '#6366f1', EMERGING: '#1dda9f' };
    const entries = Object.entries(domainPivot || {}).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0));

    if (ctx) {
        if (anDomainChart) anDomainChart.destroy();
        anDomainChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: entries.map(([k]) => k),
                datasets: [{
                    label: 'Programs', data: entries.map(([, v]) => v.Total || 0),
                    backgroundColor: entries.map(([k]) => satColor[satMap[k]?.saturation_label] || 'rgba(99,102,241,0.75)'),
                    hoverBackgroundColor: entries.map(([k]) => satColor[satMap[k]?.saturation_label] || '#6366f1'),
                    borderRadius: 8, borderSkipped: false
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: c => {
                        const k = entries[c.dataIndex][0]; const s = satMap[k];
                        const share = s ? (s.share_pct != null ? s.share_pct.toFixed(1) : '?') : '?';
                        const sat = s ? s.saturation_label : '';
                        return `${k} — ${c.raw} programs (${share}%), ${sat}`;
                    } } }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11, weight: '600' }, maxRotation: 30 } },
                    y: { beginAtZero: true, title: { display: true, text: 'Programs' }, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { precision: 0 } }
                },
                animation: { duration: 900, easing: 'easeOutQuart' },
                onClick: (e, els) => {
                    if (els.length) showDomainDetail(entries[els[0].index][0]);
                }
            }
        });
    }

    const tbody = document.getElementById('an-domain-tbody');
    if (tbody) tbody.innerHTML = entries.map(([name, v]) => {
        const total = v.Total || 0, indian = v.Indian || 0, intl = v.International || 0;
        const ip = total ? Math.round(indian / total * 100) : 50;
        const sat = satMap[name]?.saturation_label;
        const share = satMap[name]?.share_pct;
        const domRecent = recent.filter(r => (r.domain || '').toLowerCase().includes(name.toLowerCase()));
        const domVerif = domRecent.filter(r => (r.status || '').toLowerCase() === 'verified').length;
        const domIssues = domRecent.filter(r => (r.status || '').toLowerCase() === 'discrepancy').length;
        const satBadge = sat ? `<span class="an-tag an-tag--${sat.toLowerCase()}">${escHtml(sat)}</span>` : '—';
        return `<tr class="clickable-row" onclick="showDomainDetail('${escJs(name)}')" title="Click to explore domain">
            <td><div style="font-weight:800;color:var(--text-1);">${escHtml(name)}</div>
                <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;">Click to explore</div></td>
            <td style="text-align:center;"><span class="dom-total">${total}</span></td>
            <td style="text-align:center;">${share != null ? share.toFixed(1) + '%' : '—'}</td>
            <td style="text-align:center;">${satBadge}</td>
            <td style="text-align:center;"><span class="dom-indian">${indian}</span></td>
            <td style="text-align:center;"><span class="dom-intl">${intl}</span></td>
            <td style="text-align:center;"><span style="color:var(--green);font-weight:700;">${domVerif || '—'}</span></td>
            <td style="text-align:center;"><span style="color:var(--accent);font-weight:700;">${domIssues || '—'}</span></td>
            <td><div class="dom-mix-bar"><div class="dom-mix-in" style="flex:${ip}"></div><div class="dom-mix-out" style="flex:${100 - ip}"></div></div></td>
        </tr>`;
    }).join('');
}

// ── Category drill-down (credential doughnut click) ──────────────
// Real cross-tab filter: jump to All Courses filtered by this domain/level.
function openAnalyticsDrilldownByCategory(catLabel) {
    jumpToCourses({ domain: catLabel });
}

// ── Overview: Key Findings narrative ─────────────────────────────
function populateKeyFindings(d) {
    const el = document.getElementById('an-key-findings-body');
    if (!el) return;
    const kf = d.key_findings || [];
    if (kf.length) {
        el.innerHTML = kf.map(f => `<div class="an-keyfindings-bullet">${escHtml(f)}</div>`).join('');
    } else {
        // Auto-narrative fallback from available blocks.
        const stats = d.stats || (globalData?.stats) || {};
        const conc = d.concentration || {};
        const rs = d.ranked_share || {};
        const dq = (d.verification_quality || {}).data_quality_health || {};
        const bullets = [];
        if (stats.total) bullets.push(`Catalog spans ${stats.total} courses across ${conc.top_country ? 'a footprint led by ' + conc.top_country : 'multiple countries'}${conc.top_domain ? ' with top specialization ' + conc.top_domain : ''}.`);
        if (stats.total) bullets.push(`Verification match rate is ${stats.total ? Math.round((stats.verified || 0) / stats.total * 100) : 0}% with ${stats.discrepancies || 0} discrepancies and ${stats.errors || 0} errors open.`);
        if (rs.qs_pct != null) bullets.push(`QS-ranked share of catalog is ${rs.qs_pct}%; NIRF-ranked share is ${rs.nirf_pct}%.`);
        if (dq.score != null) bullets.push(`Data-quality health composite is ${dq.score}/100.`);
        el.innerHTML = bullets.length ? bullets.map(b => `<div class="an-keyfindings-bullet">${escHtml(b)}</div>`).join('')
            : '<div class="an-empty">No findings yet — run verification to generate insights.</div>';
    }
}

// ── Overview: Affordability gauge ─────────────────────────────────
function populateAffordabilityGauge(d) {
    const cost = d.cost_access || {};
    const fvp = cost.free_vs_paid || {};
    const idx = cost.affordability_index;
    const band = idx == null ? '—' : idx >= 70 ? 'High Access' : idx >= 40 ? 'Moderate' : 'Limited';
    const paid = fvp.paid || 0;
    renderScoreGauge('an-affordability-gauge', idx || 0, 100, {
        color: idx >= 70 ? 'var(--green)' : idx >= 40 ? 'var(--accent)' : 'var(--red)',
        gaugeLabel: 'ACCESS INDEX',
        bandLabel: band,
        sub: `based on ${paid} priced programs in INR`
    });
}

// ── Overview: Free vs Paid doughnut ───────────────────────────────
function populateFreePaidChart(d) {
    const ctx = document.getElementById('an-free-paid-chart');
    if (!ctx) return;
    const fvp = (d.cost_access || {}).free_vs_paid || {};
    const free = fvp.free || 0, paid = fvp.paid || 0;
    const tot = free + paid || 1;
    if (anFreePaidChart) anFreePaidChart.destroy();
    const centerPlugin = {
        id: 'freePaidCenter', afterDraw(chart) {
            drawCenter(chart, `${Math.round(free / tot * 100)}% free`, `${free} of ${free + paid}`);
        }
    };
    anFreePaidChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['Free', 'Paid'], datasets: [{ data: [free, paid],
            backgroundColor: ['#1dda9f', '#6366f1'], borderColor: 'transparent', borderWidth: 0, hoverOffset: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '68%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${c.raw}` } } } },
        plugins: [centerPlugin]
    });
}

// ── Overview: Fee histogram ──────────────────────────────────────
function populateFeeHistogram(d) {
    const ctx = document.getElementById('an-fee-histogram');
    if (!ctx) return;
    const cost = d.cost_access || {};
    const hist = cost.fee_histogram || [];
    const sub = document.getElementById('an-fee-histogram-sub');
    if (sub) sub.textContent = `Median INR ${cost.median_fee_inr != null ? cost.median_fee_inr.toLocaleString() : '—'}, Mean INR ${cost.mean_fee_inr != null ? cost.mean_fee_inr.toLocaleString() : '—'}`;
    if (anFeeHistogramChart) anFeeHistogramChart.destroy();
    if (!hist.length) return;
    const median = cost.median_fee_inr;
    const maxFee = Math.max(...hist.map(h => h.max || 0).filter(v => v != null)) || 1;
    anFeeHistogramChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: hist.map(h => h.label),
            datasets: [{
                label: 'Programs', data: hist.map(h => h.count),
                backgroundColor: 'rgba(99,102,241,0.8)', hoverBackgroundColor: '#6366f1',
                borderRadius: 6, borderSkipped: false
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => `${c.label}: ${c.raw} programs` } },
                annotation: median != null ? { annotations: { medianLine: {
                    type: 'line', xMin: 0, xMax: hist.length - 1,
                    yMin: median, yMax: median, borderColor: '#f59e0b',
                    borderWidth: 2, borderDash: [5, 5], label: { display: true,
                        content: 'Median', position: 'end', color: '#f59e0b' }
                } } } : {}
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10, weight: '600' }, maxRotation: 30 } },
                y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { precision: 0 } }
            }
        }
    });
}

// ── Overview: Credential x Cost tier heatmap ──────────────────────
function populateCredentialCostHeatmap(d) {
    const el = document.getElementById('an-credential-cost-heatmap');
    if (!el) return;
    const tiers = ['Free', 'Affordable', 'Mid', 'Premium'];
    const ctl = (d.cost_access || {}).cost_tier_by_level || {};
    const levels = Object.keys(ctl);
    if (!levels.length) { el.innerHTML = '<div class="an-empty">No cost-tier breakdown available.</div>'; return; }
    const max = Math.max(1, ...levels.flatMap(l => tiers.map(t => ctl[l][t] || 0)));
    const body = levels.map(l => `<tr><td class="an-heatmap-rowhead">${escHtml(l)}</td>` +
        tiers.map(t => renderHeatmapCell(ctl[l][t] || 0, max, { title: `${l} · ${t}: ${ctl[l][t] || 0}` })).join('') + `</tr>`).join('');
    el.innerHTML = `<table class="an-heatmap"><thead><tr><th>Credential Level</th>${tiers.map(t => `<th>${escHtml(t)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
}

// ── Geography: concentration gauge ─────────────────────────────────
function populateGeoConcentration(d) {
    const g = d.geo_concentration || {};
    if (!g.hhi && g.hhi !== 0) { renderScoreGauge('an-geo-concentration', 0, 10000, { gaugeLabel: 'HHI', sub: 'No country data.' }); return; }
    const color = g.hhi >= 2500 ? 'var(--red)' : g.hhi >= 1500 ? 'var(--accent)' : 'var(--green)';
    renderScoreGauge('an-geo-concentration', g.hhi || 0, 10000, {
        color, gaugeLabel: 'HHI', bandLabel: g.label || '—',
        sub: 'Herfindahl-Hirschman across the country footprint.',
        stats: [
            { value: `${g.top1_share || 0}%`, label: 'TOP COUNTRY SHARE' },
            { value: `${g.top3_share || 0}%`, label: 'TOP 3 COUNTRIES SHARE' },
            { value: String(g.effective_countries || '—'), label: 'EFFECTIVE COUNTRIES' },
            { value: String(g.n_countries || 0), label: 'COUNTRIES REPRESENTED' }
        ]
    });
}

// ── Geography: regional groupings ─────────────────────────────────
function populateRegionalGroups(d) {
    const el = document.getElementById('an-regional-chart');
    if (!el) return;
    const regions = d.regional_groups || {};
    const order = ['INDIA', 'SOUTH ASIA', 'EAST ASIA & PACIFIC', 'EUROPE', 'NORTH AMERICA', 'MIDDLE EAST & AFRICA', 'LATIN AMERICA', 'OTHER'];
    const rows = order.filter(r => regions[r]).map(r => {
        const x = regions[r];
        const vr = x.verified_rate != null ? (x.verified_rate * 100).toFixed(0) : '—';
        return `<tr class="an-region-row" data-region="${escHtml(r)}" title="Click to filter the footprint table">
            <td><strong>${escHtml(r)}</strong></td>
            <td style="text-align:center;">${x.countries || 0}</td>
            <td style="text-align:center;">${x.total || 0}</td>
            <td style="text-align:center;color:var(--green);font-weight:700;">${x.verified || 0}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${x.discrepancies || 0}</td>
            <td style="text-align:center;color:var(--red);font-weight:700;">${x.errors || 0}</td>
            <td style="text-align:center;">${vr}%</td>
        </tr>`;
    });
    const present = order.filter(r => regions[r]);
    if (!present.length) { el.innerHTML = '<div class="an-empty">No regional data available.</div>'; return; }
    el.innerHTML = `<table class="an-benchmark-table"><thead><tr>
        <th>Region</th><th>Countries</th><th>Courses</th><th>Verified</th><th>Discrepancies</th><th>Verified Rate</th>
        </tr></thead><tbody>${rows.join('')}</tbody></table>`;
    el.querySelectorAll('.an-region-row').forEach(tr => {
        tr.addEventListener('click', () => {
            const region = tr.getAttribute('data-region');
            const search = document.getElementById('an-country-search');
            // Toggle: clicking the active region again clears the filter.
            if (geoRegionFilter === region) {
                geoRegionFilter = null;
                tr.classList.remove('active-region');
            } else {
                geoRegionFilter = region;
                el.querySelectorAll('.an-region-row').forEach(r => r.classList.remove('active-region'));
                tr.classList.add('active-region');
            }
            if (search) search.value = '';
            renderGeoTable('');
        });
    });
}

// ── Geography: most-problematic countries ─────────────────────────
function populateGeoProblemRanking(d) {
    const tbody = document.getElementById('an-geo-problem-tbody');
    if (!tbody) return;
    const rows = d.geo_problem_ranking || [];
    if (!rows.length) { tbody.innerHTML = `<tr><td colspan="6" class="an-empty">No country exceeds the issue threshold — portfolio is clean.</td></tr>`; return; }
    const maxRate = Math.max(...rows.map(r => r.issue_rate || 0)) || 1;
    tbody.innerHTML = rows.map((r, i) => {
        const pct = (r.issue_rate || 0) * 100;
        return `<tr class="an-problem-row clickable-row" onclick="showCountryDetail('${escJs(r.country)}','geo')" title="Click to drill into flagged courses">
            <td><span class="geo-rank">${(i + 1).toString().padStart(2, '0')}</span></td>
            <td>${initialsChip(r.country)} <strong>${escHtml(r.country)}</strong></td>
            <td style="text-align:center;">${r.total}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${r.issues}</td>
            <td><div class="an-issue-bar-wrap"><div class="an-issue-bar" style="width:${(pct / (maxRate * 100) * 100)}%"></div><span class="an-issue-pct">${pct.toFixed(1)}%</span></div></td>
            <td style="text-align:center;font-weight:800;">${r.quality_score != null ? r.quality_score : '—'}</td>
        </tr>`;
    }).join('');
}

// ── Geography: comparative country benchmark ─────────────────────
let geoCompareState = { a: null, b: null };
function populateGeoCompare(d) {
    const el = document.getElementById('an-geo-compare');
    const selA = document.getElementById('an-compare-a');
    const selB = document.getElementById('an-compare-b');
    if (!el) return;
    const cq = d.country_quality || {};
    const countries = Object.keys(cq).filter(c => isValidCountry(c)).sort();
    const seed = d.geo_comparison_seed || {};
    const buildOptions = (sel, chosen) => {
        if (!sel) return;
        const cur = chosen || sel.value;
        sel.innerHTML = `<option value="">Country A</option>` + countries.map(c =>
            `<option value="${escHtml(c)}" ${c === cur ? 'selected' : ''}>${escHtml(c)}</option>`).join('');
    };
    buildOptions(selA, geoCompareState.a || seed.country_a);
    buildOptions(selB, geoCompareState.b || seed.country_b);
    const render = () => {
        const a = cq[geoCompareState.a], b = cq[geoCompareState.b];
        if (!a && !b) { el.innerHTML = '<div class="an-empty">Select two countries to compare.</div>'; return; }
        const metrics = [
            ['TOTAL COURSES', a?.total, b?.total],
            ['VERIFIED RATE', a?.verified_rate != null ? (a.verified_rate * 100).toFixed(1) + '%' : '—', b?.verified_rate != null ? (b.verified_rate * 100).toFixed(1) + '%' : '—'],
            ['ISSUE RATE', a?.issue_rate != null ? (a.issue_rate * 100).toFixed(1) + '%' : '—', b?.issue_rate != null ? (b.issue_rate * 100).toFixed(1) + '%' : '—'],
            ['MEDIAN FEE', a?.median_fee != null ? Math.round(a.median_fee).toLocaleString() : '—', b?.median_fee != null ? Math.round(b.median_fee).toLocaleString() : '—'],
            ['FREE SHARE', a ? (a.total ? Math.round(a.free_count / a.total * 100) + '%' : '—') : '—', b ? (b.total ? Math.round(b.free_count / b.total * 100) + '%' : '—') : '—'],
            ['QS-RANKED UNIVERSITIES', a?.qs_universities ?? '—', b?.qs_universities ?? '—'],
            ['NIRF-RANKED UNIVERSITIES', a?.nirf_universities ?? '—', b?.nirf_universities ?? '—'],
            ['QUALITY SCORE', a?.quality_score ?? '—', b?.quality_score ?? '—'],
            ['TOP DOMAIN', a?.top_domain || '—', b?.top_domain || '—']
        ];
        const cols = ['TOTAL COURSES', 'VERIFIED RATE', 'ISSUE RATE', 'MEDIAN FEE', 'FREE SHARE', 'QS-RANKED UNIVERSITIES', 'NIRF-RANKED UNIVERSITIES', 'QUALITY SCORE', 'TOP DOMAIN'];
        const rowsHtml = cols.map((label, idx) => {
            const [_, av, bv] = metrics[idx];
            const delta = (av !== '—' && bv !== '—' && !isNaN(Number(String(av).replace(/[^0-9.-]/g, ''))) && !isNaN(Number(String(bv).replace(/[^0-9.-]/g, ''))))
                ? (Number(String(av).replace(/[^0-9.-]/g, '')) - Number(String(bv).replace(/[^0-9.-]/g, ''))) : '';
            return `<tr><td>${escHtml(label)}</td><td>${escHtml(String(av))}</td><td>${escHtml(String(bv))}</td><td class="an-benchmark-delta">${delta !== '' ? escHtml(String(delta)) : '—'}</td></tr>`;
        }).join('');
        el.innerHTML = `<table class="an-benchmark-table"><thead><tr><th>Metric</th><th>${escHtml(geoCompareState.a || 'Country A')}</th><th>${escHtml(geoCompareState.b || 'Country B')}</th><th>DELTA</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
    };
    if (selA) selA.onchange = () => { geoCompareState.a = selA.value || null; render(); };
    if (selB) selB.onchange = () => { geoCompareState.b = selB.value || null; render(); };
    geoCompareState.a = geoCompareState.a || seed.country_a || null;
    geoCompareState.b = geoCompareState.b || seed.country_b || null;
    render();
}

// ── Specializations: concentration gauge ──────────────────────────
function populateConcentrationGauge(d) {
    const s = d.specialization_hhi || {};
    if (s.value == null) { renderScoreGauge('an-concentration-gauge', 0, 10000, { gaugeLabel: 'HHI', sub: 'No specialization data.' }); return; }
    const color = s.value >= 2500 ? 'var(--red)' : s.value >= 1500 ? 'var(--accent)' : 'var(--green)';
    renderScoreGauge('an-concentration-gauge', s.value, 10000, {
        color, gaugeLabel: 'HHI', bandLabel: s.label || '—',
        sub: 'Herfindahl-Hirschman Index over specialization share; higher = fewer fields dominate.'
    });
}

// ── Specializations: credential ladder table ──────────────────────
function populateCredentialLadder(d) {
    const tbody = document.getElementById('an-credential-ladder-tbody');
    if (!tbody) return;
    const ladder = d.credential_ladder || {};
    const entries = Object.entries(ladder);
    if (!entries.length) { tbody.innerHTML = `<tr><td colspan="9" class="an-empty">No credential-level data available.</td></tr>`; return; }
    const maxRate = Math.max(1, ...entries.map(([, v]) => v.verification_rate || 0));
    tbody.innerHTML = entries.map(([level, x]) => {
        const vr = x.verification_rate;
        const vrPct = vr != null ? (vr * 100).toFixed(1) + '%' : '—';
        const rateColor = vr == null ? 'var(--text-3)' : vr >= 0.8 ? 'var(--green)' : vr >= 0.5 ? 'var(--accent)' : 'var(--red)';
        const ip = x.indian_pct != null ? x.indian_pct.toFixed(0) : '—';
        const avg = x.avg_cost_inr != null ? Math.round(x.avg_cost_inr).toLocaleString() : '—';
        const med = x.median_cost_inr != null ? Math.round(x.median_cost_inr).toLocaleString() : '—';
        const cov = x.verification_rate != null ? 'Matched' : 'No data';
        return `<tr class="an-ladder-row an-ladder-row--clickable" onclick="jumpToCourses({domain:'${escJs(level)}'})" title="Click to view programs">
            <td><strong>${escHtml(level)}</strong><div class="an-row-subtext">Click to view programs</div></td>
            <td style="text-align:center;">${x.count || 0}</td>
            <td style="text-align:center;">${avg}</td>
            <td style="text-align:center;">${med}</td>
            <td style="text-align:center;">${x.free_pct != null ? x.free_pct.toFixed(0) + '%' : '—'}</td>
            <td style="text-align:center;font-weight:700;color:${rateColor};">${vrPct}</td>
            <td style="text-align:center;">${ip}%</td>
            <td style="text-align:center;">${100 - (x.indian_pct || 0)}%</td>
            <td style="text-align:center;">${escHtml(cov)}</td>
        </tr>`;
    }).join('');
}

// ── Specializations: credential cost profile grouped bar ──────────
function populateCredentialCostChart(d) {
    const ctx = document.getElementById('an-credential-cost-chart');
    if (!ctx) return;
    const ladder = d.credential_ladder || {};
    const entries = Object.entries(ladder);
    if (anCredentialCostChart) anCredentialCostChart.destroy();
    if (!entries.length) return;
    const labels = entries.map(([l]) => l);
    const avg = entries.map(([, v]) => v.avg_cost_inr || 0);
    const med = entries.map(([, v]) => v.median_cost_inr || 0);
    anCredentialCostChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [
            { label: 'Average Cost', data: avg, backgroundColor: 'rgba(99,102,241,0.85)', hoverBackgroundColor: '#6366f1', borderRadius: 6 },
            { label: 'Median Cost', data: med, backgroundColor: 'rgba(29,218,159,0.85)', hoverBackgroundColor: '#1dda9f', borderRadius: 6 }
        ] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: true, labels: { color: 'var(--text-2)', font: { size: 11 } } },
                tooltip: { callbacks: { label: c => `${c.dataset.label}: INR ${Math.round(c.raw).toLocaleString()}` } } },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10, weight: '600' }, maxRotation: 30 } },
                y: { beginAtZero: true, title: { display: true, text: 'Cost (INR)' },
                    grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { callback: v => Math.round(v).toLocaleString() } }
            },
            onClick: (e, els) => { if (els.length) jumpToCourses({ domain: labels[els[0].index] }); }
        }
    });
}

// ── Specializations: credential verification heatmap ──────────────
function populateCredentialVerificationHeatmap(d) {
    const el = document.getElementById('an-credential-verification-heatmap');
    if (!el) return;
    const matrix = d.credential_verification_matrix || {};
    const levels = Object.keys(matrix);
    if (!levels.length) { el.innerHTML = '<div class="an-empty">No credential verification data available.</div>'; return; }
    const cols = ['verified_pct', 'discrepancy_pct', 'error_pct', 'unverified_pct'];
    const colLabels = ['Verified %', 'Discrepancy %', 'Error %', 'Unverified %'];
    const head = `<tr><th>Credential Level</th>${colLabels.map(c => `<th>${escHtml(c)}</th>`).join('')}<th>Programs</th></tr>`;
    const body = levels.map(l => {
        const x = matrix[l];
        const cells = cols.map(c => renderHeatmapCell(x[c] || 0, 100, { text: x[c] != null ? (x[c]).toFixed(1) : '' })).join('');
        return `<tr><td class="an-heatmap-rowhead">${escHtml(l)}</td>${cells}<td style="text-align:center;font-weight:700;">${x.total || 0}</td></tr>`;
    }).join('');
    el.innerHTML = `<table class="an-heatmap"><thead>${head}</thead><tbody>${body}</tbody></table>
        <div class="an-heatmap-footer">Percentages share within each credential level; blank cells indicate no courses at that tier.</div>`;
}

// ── Specializations: ranked vs unranked credential mix doughnut ──
function populateRankedCredentialMix(d) {
    const ctx = document.getElementById('an-ranked-credential-chart');
    if (!ctx) return;
    const mix = d.ranked_credential_mix || {};
    const levels = Object.keys(mix);
    if (anRankedCredentialChart) anRankedCredentialChart.destroy();
    let ranked = 0, unranked = 0;
    levels.forEach(l => { ranked += mix[l].ranked || 0; unranked += mix[l].unranked || 0; });
    const tot = ranked + unranked || 1;
    const centerPlugin = { id: 'rankedCredCenter', afterDraw(chart) {
        drawCenter(chart, `${Math.round(ranked / tot * 100)}% Ranked`, 'RANKED INSTITUTIONS'); } };
    anRankedCredentialChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['Ranked (QS/NIRF)', 'Unranked'], datasets: [{ data: [ranked, unranked],
            backgroundColor: ['#8b5cf6', 'rgba(255,255,255,0.12)'], borderColor: 'transparent', borderWidth: 0, hoverOffset: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '68%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${c.raw}` } } } },
        plugins: [centerPlugin]
    });
    const legend = document.getElementById('an-ranked-credential-legend');
    if (legend) legend.innerHTML = `
        <div class="an-legend-item an-legend-clickable" onclick="jumpToCourses({qs:'yes'})" title="Show QS-ranked courses">
            <div class="an-legend-dot" style="background:#8b5cf6"></div>
            <div><div class="an-legend-name">Ranked (QS/NIRF)</div><div class="an-legend-val">${ranked}</div></div>
        </div>
        <div class="an-legend-item an-legend-clickable" onclick="jumpToCourses({qs:'no',nirf:'no'})" title="Show unranked courses">
            <div class="an-legend-dot" style="background:rgba(255,255,255,0.12)"></div>
            <div><div class="an-legend-name">Unranked</div><div class="an-legend-val">${unranked}</div></div>
        </div>`;
}

// ── Specializations + Rankings: university leaderboard ────────────
function leaderboardRows(rows, withCountry, withStatus) {
    if (!rows.length) return `<tr><td colspan="${withStatus ? 8 : 6}" class="an-empty">No university-level data yet — run verification first.</td></tr>`;
    return rows.map((r, i) => {
        const vr = r.verification_rate != null ? (r.verification_rate * 100).toFixed(0) + '%' : '—';
        const cells = [`<td><span class="geo-rank">${(i + 1).toString().padStart(2, '0')}</span></td>`,
            `<td><strong>${escHtml(r.university)}</strong></td>`];
        if (withCountry) cells.push(`<td>${escHtml(r.country || '—')}</td>`);
        cells.push(`<td style="text-align:center;">${r.course_count || 0}</td>`);
        if (withStatus) {
            cells.push(`<td style="text-align:center;">${vr}</td>`,
                `<td style="text-align:center;">${r.qs_ranked ? '<span class="an-tag an-tag--ranked">QS</span>' : '—'}</td>`,
                `<td style="text-align:center;">${r.nirf_ranked ? '<span class="an-tag an-tag--ranked">NIRF</span>' : '—'}</td>`,
                `<td>${r.ranked ? '<span class="an-tag an-tag--ranked">RANKED</span>' : '<span class="an-tag an-tag--unranked">UNRANKED</span>'}</td>`);
        }
        return `<tr class="an-leaderboard-row clickable-row" onclick="showUniversityDetail('${escJs(r.university)}')" title="Click for university profile">${cells.join('')}</tr>`;
    }).join('');
}
function populateUniversityLeaderboard(d) {
    const tbody = document.getElementById('an-university-leaderboard');
    if (tbody) tbody.innerHTML = leaderboardRows(d.university_leaderboard || [], true, true);
    const tbodyR = document.getElementById('an-university-leaderboard-rank');
    if (tbodyR) {
        const rows = (d.university_leaderboard || []).map(r => ({
            university: r.university, course_count: r.course_count, verified: r.verified,
            discrepancies: r.discrepancies, errors: r.errors,
            verification_rate: r.verification_rate, qs_ranked: r.qs_ranked, nirf_ranked: r.nirf_ranked
        }));
        tbodyR.innerHTML = rows.length ? rows.map(r => `<tr class="an-leaderboard-row clickable-row" onclick="showUniversityDetail('${escJs(r.university)}')" title="Click for university profile">
            <td><strong>${escHtml(r.university)}</strong></td>
            <td style="text-align:center;">${r.course_count || 0}</td>
            <td style="text-align:center;color:var(--green);font-weight:700;">${r.verified || 0}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${r.discrepancies || 0}</td>
            <td style="text-align:center;color:var(--red);font-weight:700;">${r.errors || 0}</td>
            <td style="text-align:center;">${r.verification_rate != null ? (r.verification_rate * 100).toFixed(0) + '%' : '—'}</td>
            <td style="text-align:center;">${r.qs_ranked ? 'Yes' : 'No'}</td>
            <td style="text-align:center;">${r.nirf_ranked ? 'Yes' : 'No'}</td>
        </tr>`).join('') : `<tr><td colspan="8" class="an-empty">No university-level data yet — run verification first.</td></tr>`;
    }
}

// ── Specializations: academic findings ────────────────────────────
function populateAcademicFindings(d) {
    const el = document.getElementById('an-academic-findings-body');
    if (!el) return;
    const ladder = d.credential_ladder || {};
    const sat = d.domain_saturation || [];
    const hhi = d.specialization_hhi || {};
    const lb = d.university_leaderboard || [];
    const findings = [];
    const ladderEntries = Object.entries(ladder).sort((a, b) => (b[1].avg_cost_inr || 0) - (a[1].avg_cost_inr || 0));
    if (ladderEntries.length) {
        const [topLvl, topX] = ladderEntries[0];
        findings.push({ tag: 'CREDENTIAL COST', text: `Highest average cost is ${topLvl} at INR ${Math.round(topX.avg_cost_inr || 0).toLocaleString()} across ${topX.count} programs.` });
    }
    const saturated = sat.filter(s => s.saturation_label === 'SATURATED');
    if (saturated.length) findings.push({ tag: 'SATURATION', text: `${saturated.length} specialization${saturated.length > 1 ? 's are' : ' is'} saturated, led by ${saturated[0].domain} at ${saturated[0].share_pct}% of the catalog.` });
    if (hhi.value != null) findings.push({ tag: 'CONCENTRATION', text: `Specialization HHI is ${hhi.value}/10000 (${hhi.label}).` });
    if (lb.length) findings.push({ tag: 'LEADERBOARD', text: `Top institution is ${lb[0].university} with ${lb[0].course_count} programs${lb[0].ranked ? ' (ranked)' : ' (unranked)'}.` });
    el.innerHTML = findings.length ? findings.map(f => `<div class="an-keyfindings-bullet"><span class="an-tag an-tag--key">${escHtml(f.tag)}</span> ${escHtml(f.text)}</div>`).join('')
        : '<div class="an-empty">No academic findings yet — run verification to generate insights.</div>';
}

// ── Rankings: ranking-mix doughnut ────────────────────────────────
function populateRankingMix(d) {
    const ctx = document.getElementById('an-ranking-mix');
    if (!ctx) return;
    const rm = d.ranking_mix || {};
    const qs = rm.qs_ranked || 0, nirf = rm.nirf_ranked || 0, both = rm.both || 0, un = rm.unranked || 0;
    if (anRankingMixChart) anRankingMixChart.destroy();
    const tot = qs + nirf + both + un || 1;
    const centerPlugin = { id: 'rankMixCenter', afterDraw(chart) {
        drawCenter(chart, `${Math.round((qs + nirf + both) / tot * 100)}%`, 'RANKED'); } };
    anRankingMixChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['QS Ranked', 'NIRF Ranked', 'Both QS and NIRF', 'Unranked'],
            datasets: [{ data: [qs, nirf, both, un], backgroundColor: ['#8b5cf6', '#06b6d4', '#1dda9f', 'rgba(255,255,255,0.12)'],
                borderColor: 'transparent', borderWidth: 0, hoverOffset: 8 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '66%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${c.raw} (${(c.raw / tot * 100).toFixed(1)}%)` } } } },
        plugins: [centerPlugin]
    });
    const sub = document.getElementById('an-ranking-mix-sub');
    if (sub) sub.textContent = `${qs + nirf + both} courses (${Math.round((qs + nirf + both) / tot * 100)}%)`;
}

// ── Rankings: ranked vs unranked table ────────────────────────────
function populateRankedVsUnranked(d) {
    const el = document.getElementById('an-ranked-vs-unranked');
    if (!el) return;
    const rows = d.ranked_vs_unranked_metrics || [];
    if (!rows.length) { el.innerHTML = '<div class="an-empty">No ranking comparison available.</div>'; return; }
    el.innerHTML = `<table class="an-benchmark-table"><thead><tr>
        <th>Cohort</th><th>Courses</th><th>Verification rate</th><th>Discrepancy rate</th><th>Median fee INR</th>
        </tr></thead><tbody>${rows.map(r => `<tr>
        <td><strong>${escHtml(r.cohort)}</strong></td>
        <td style="text-align:center;">${r.courses || 0}</td>
        <td style="text-align:center;">${pct(r.verification_rate)}</td>
        <td style="text-align:center;">${pct(r.discrepancy_rate)}</td>
        <td style="text-align:center;">${r.median_fee_inr != null ? Math.round(r.median_fee_inr).toLocaleString() : '—'}</td>
        </tr>`).join('')}</tbody></table>`;
}

// ── Filter bar ────────────────────────────────────────────────────
let analyticsFilters = { level: '', country: '', cost: '', ranking: '' };
function initAnalyticsFilters(d) {
    const bar = document.getElementById('an-filter-bar');
    if (!bar) return;
    const facets = d.filter_facets || {};
    const fillSelect = (id, placeholder, opts) => {
        const sel = document.getElementById(id);
        if (!sel) return;
        const cur = sel.value;
        sel.innerHTML = `<option value="">${escHtml(placeholder)}</option>` +
            (opts || []).map(o => `<option value="${escHtml(o)}">${escHtml(o)}</option>`).join('');
        if (cur) sel.value = cur;
    };
    fillSelect('an-filter-level', 'Level: All...', facets.levels);
    fillSelect('an-filter-country', 'Country: All', facets.countries);
    fillSelect('an-filter-cost', 'Cost Tier: All...', facets.cost_tiers);
    fillSelect('an-filter-ranking', 'Ranking: All...', facets.ranking);
    const wire = (id, key) => { const sel = document.getElementById(id); if (sel) sel.onchange = () => { analyticsFilters[key] = sel.value; applyAnalyticsFilter(d); }; };
    wire('an-filter-level', 'level'); wire('an-filter-country', 'country');
    wire('an-filter-cost', 'cost'); wire('an-filter-ranking', 'ranking');
    const reset = document.getElementById('an-filter-reset');
    if (reset) reset.onclick = () => {
        analyticsFilters = { level: '', country: '', cost: '', ranking: '' };
        ['an-filter-level', 'an-filter-country', 'an-filter-cost', 'an-filter-ranking'].forEach(id => { const s = document.getElementById(id); if (s) s.value = ''; });
        applyAnalyticsFilter(d);
    };
}
function applyAnalyticsFilter(d) {
    const courses = d.analytics_courses || [];
    const chips = document.getElementById('an-filter-chips');
    const active = Object.entries(analyticsFilters).filter(([, v]) => v);
    if (chips) chips.innerHTML = active.map(([k, v]) => `<span class="an-filter-chip">${escHtml(v)} <span class="an-filter-chip-x" data-key="${escHtml(k)}">×</span></span>`).join('');
    if (chips) chips.querySelectorAll('.an-filter-chip-x').forEach(x => x.onclick = () => {
        const k = x.dataset.key; analyticsFilters[k] = '';
        const sel = document.getElementById('an-filter-' + (k === 'cost' ? 'cost' : k));
        if (sel) sel.value = ''; applyAnalyticsFilter(d);
    });
    if (!courses.length) return; // no client-side recomputation possible
    let filtered = courses;
    if (analyticsFilters.level) filtered = filtered.filter(r => r.level === analyticsFilters.level);
    if (analyticsFilters.country) filtered = filtered.filter(r => r.country === analyticsFilters.country);
    if (analyticsFilters.cost) filtered = filtered.filter(r => r.cost_tier === analyticsFilters.cost);
    if (analyticsFilters.ranking === 'QS Ranked') filtered = filtered.filter(r => r.qs_ranked);
    else if (analyticsFilters.ranking === 'NIRF Ranked') filtered = filtered.filter(r => r.nirf_ranked);
    else if (analyticsFilters.ranking === 'Unranked') filtered = filtered.filter(r => !r.qs_ranked && !r.nirf_ranked);
    // Recompute KPIs + status chart from the filtered subset.
    const stats = {
        total: filtered.length,
        verified: filtered.filter(r => r.status === 'Verified').length,
        discrepancies: filtered.filter(r => r.status === 'Discrepancy').length,
        errors: filtered.filter(r => r.status === 'Error').length,
    };
    populateAnalyticsKPIs({ ...d, analytics_courses: filtered }, stats, null);
    const indiaCount = filtered.filter(r => (r.country || '').toLowerCase().includes('india')).length;
    const realTotal = stats.total || 1;
    populateSplitVisual((indiaCount / realTotal) * 100, d);
}

// ── Export bar ────────────────────────────────────────────────────
function initAnalyticsExport(d) {
    const bar = document.getElementById('an-export-bar');
    if (!bar) return;
    const snapshot = () => {
        const courses = (d.analytics_courses || []).filter(r => {
            if (analyticsFilters.level && r.level !== analyticsFilters.level) return false;
            if (analyticsFilters.country && r.country !== analyticsFilters.country) return false;
            if (analyticsFilters.cost && r.cost_tier !== analyticsFilters.cost) return false;
            if (analyticsFilters.ranking === 'QS Ranked' && !r.qs_ranked) return false;
            if (analyticsFilters.ranking === 'NIRF Ranked' && !r.nirf_ranked) return false;
            if (analyticsFilters.ranking === 'Unranked' && (r.qs_ranked || r.nirf_ranked)) return false;
            return true;
        });
        return courses;
    };
    const csvBtn = document.getElementById('an-export-csv');
    if (csvBtn) csvBtn.onclick = () => {
        const rows = snapshot();
        if (!rows.length) return;
        const cols = ['name', 'university', 'country', 'level', 'domain', 'cost_tier', 'fee_inr', 'status', 'qs_ranked', 'nirf_ranked', 'issue_category', 'disc_reason'];
        const csv = [cols.join(',')].concat(rows.map(r => cols.map(c => `"${String(r[c] != null ? r[c] : '').replace(/"/g, '""')}"`).join(','))).join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'analytics_snapshot.csv'; a.click();
    };
    const jsonBtn = document.getElementById('an-export-json');
    if (jsonBtn) jsonBtn.onclick = () => {
        const blob = new Blob([JSON.stringify({ snapshot: snapshot(), pivots: { country_pivot: d.country_pivot, domain_pivot: d.domain_pivot, pricing_category: d.pricing_category } }, null, 2)], { type: 'application/json' });
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
        a.download = 'analytics_snapshot.json'; a.click();
    };
    const printBtn = document.getElementById('an-export-print');
    if (printBtn) printBtn.onclick = () => window.print();
}

// ── Verification tab ─────────────────────────────────────────────
// Consumes the `verification_quality.*` block from the analytics payload
// (computed over ALL courses incl. Verified) instead of globalData.recent,
// which excluded Verified courses and understated match rates.

function populateVerifKPIs(d) {
    const row = document.getElementById('an-verif-kpi-row');
    if (!row) return;
    const vq = (d && d.verification_quality) || {};
    const sc = vq.status_counts || {};
    const dq = vq.data_quality_health || {};
    const tot = sc.total || 0;
    const cards = [
        { label: 'Verified', sub: 'Perfectly matched', val: sc.verified || 0, color: 'var(--green)' },
        { label: 'Discrepancies', sub: 'Require review', val: sc.discrepancies || 0, color: 'var(--accent)' },
        { label: 'Errors', sub: 'Page unreachable', val: sc.errors || 0, color: 'var(--red)' },
        { label: 'Data Quality', sub: 'Composite 0-100', val: dq.score != null ? dq.score : '—', color: 'var(--blue)' },
    ];
    row.innerHTML = cards.map(k => {
        const pct = tot ? (Number(k.val) || 0) / tot : 0;
        const bar = (k.label === 'Data Quality') ? (Number(k.val) || 0) / 100 : pct;
        return `<div class="verif-kpi-card" style="border-left:4px solid ${k.color};">
            <div class="verif-kpi-val" style="color:${k.color};">${escHtml(String(k.val))}</div>
            <div class="verif-kpi-label">${escHtml(k.label)}</div>
            <div class="verif-kpi-bar-wrap"><div class="verif-kpi-bar" style="width:${Math.max(0, Math.min(100, bar * 100)).toFixed(1)}%;background:${k.color};"></div></div>
            <div class="verif-kpi-sub">${escHtml(k.sub)}</div>
        </div>`;
    }).join('');
}

function populateStatusChart(d) {
    const ctx = document.getElementById('an-status-chart');
    if (!ctx) return;
    const sc = ((d && d.verification_quality) || {}).status_counts || {};
    const v = sc.verified || 0, dis = sc.discrepancies || 0, er = sc.errors || 0, un = sc.unverified || 0;
    const tot = (v + dis + er + un) || 1;
    if (anStatusChart) anStatusChart.destroy();
    const centerPlugin = {
        id: 'verifStatusCenter',
        afterDraw(chart) { drawCenter(chart, `${Math.round(v / tot * 100)}%`, 'VERIFIED'); }
    };
    anStatusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Verified', 'Discrepancy', 'Error'],
            datasets: [{
                data: [v, dis, er],
                backgroundColor: ['#1dda9f', '#f59e0b', '#f43f5e'],
                borderColor: 'transparent', borderWidth: 0, hoverOffset: 10
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '68%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => {
                const n = c.raw;
                return `${c.label}: ${n} (${(n / tot * 100).toFixed(1)}%)`;
            } } } }
        },
        plugins: [centerPlugin]
    });
    const legend = document.getElementById('an-status-legend');
    if (legend) {
        const items = [['Verified', v, '#1dda9f'], ['Discrepancy', dis, '#f59e0b'], ['Error', er, '#f43f5e']];
        legend.innerHTML = items.map(([l, n, c]) => `<div class="an-legend-item">
            <div class="an-legend-dot" style="background:${c}"></div>
            <div><div class="an-legend-name">${escHtml(l)}</div>
            <div class="an-legend-val">${n} (${tot ? (n / tot * 100).toFixed(1) : 0}%)</div></div>
        </div>`).join('');
    }
}

function populateIssueOriginChart(d) {
    const ctx = document.getElementById('an-issue-origin-chart');
    if (!ctx) return;
    const vq = (d && d.verification_quality) || {};
    const ic = vq.issue_category_counts || {};
    const labels = ['Course Content Issue', 'Website Unreachable', 'Verified'];
    const vals = [ic.course_issue || 0, ic.website_issue || 0, ic.verified || 0];
    if (anIssueOriginChart) anIssueOriginChart.destroy();
    anIssueOriginChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{ data: vals, backgroundColor: ['#f59e0b', '#f43f5e', '#1dda9f'],
                borderColor: 'transparent', borderWidth: 0, hoverOffset: 8 }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '62%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${c.raw}` } } }
        }
    });
}

function populateDiscPareto(d) {
    const ctx = document.getElementById('an-disc-pareto-chart');
    if (!ctx) return;
    const vq = (d && d.verification_quality) || {};
    const data = vq.disc_reason_pareto || [];
    if (anDiscParetoChart) anDiscParetoChart.destroy();
    const wrap = ctx.parentElement;
    // Clear any orphaned empty-state from a previous render before deciding
    // whether to draw the chart or show the empty message.
    wrap.querySelector('.an-disc-empty')?.remove();
    if (!data.length) {
        const empty = document.createElement('div');
        empty.className = 'an-empty an-disc-empty';
        empty.textContent = 'No discrepancy reasons found — portfolio is clean.';
        wrap.appendChild(empty);
        return;
    }
    const labels = data.map(r => r.reason);
    const counts = data.map(r => r.count);
    const cum = data.map(r => r.cumulative_pct);
    anDiscParetoChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { type: 'bar', label: 'Count', data: counts, backgroundColor: 'rgba(245,158,11,0.85)',
                    hoverBackgroundColor: '#f59e0b', borderRadius: 6, yAxisID: 'y' },
                { type: 'line', label: 'Cumulative %', data: cum, borderColor: '#6366f1',
                    backgroundColor: 'rgba(99,102,241,0.1)', tension: 0.35, fill: false,
                    yAxisID: 'y1', pointRadius: 4, pointBackgroundColor: '#6366f1' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: true, labels: { color: 'var(--text-2)', font: { size: 11 } } },
                tooltip: { callbacks: { label: c => {
                    if (c.dataset.label === 'Cumulative %') return `Cumulative: ${c.raw}%`;
                    return `${c.label}: ${c.raw}`;
                } } }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 10, weight: '600' }, maxRotation: 40, minRotation: 0 } },
                y: { beginAtZero: true, position: 'left', title: { display: true, text: 'Count' },
                    grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { precision: 0 } },
                y1: { beginAtZero: true, endAtMaximum: true, max: 100, position: 'right',
                    title: { display: true, text: 'Cumulative %' }, grid: { drawOnChartArea: false },
                    ticks: { callback: v => v + '%' } }
            }
        }
    });
}

function populateReasonAttributeHeatmap(d) {
    const el = document.getElementById('an-reason-attribute-heatmap');
    if (!el) return;
    const vq = (d && d.verification_quality) || {};
    const matrix = vq.reason_attribute_matrix || {};
    const reasons = Object.keys(matrix);
    if (!reasons.length) { el.innerHTML = '<div class="an-empty">No mismatch data available.</div>'; return; }
    const attrs = ['Cost', 'Duration', 'Mode', 'Language', 'Country', 'University', 'Skills'];
    const max = Math.max(1, ...reasons.flatMap(r => attrs.map(a => matrix[r][a] || 0)));
    const head = `<tr><th>Reason Cluster</th>${attrs.map(a => `<th>${escHtml(a)}</th>`).join('')}<th>Total</th></tr>`;
    const body = reasons.map(r => {
        const rowTot = attrs.reduce((s, a) => s + (matrix[r][a] || 0), 0);
        return `<tr><td class="an-heatmap-rowhead" title="${escHtml(r)}">${escHtml(r)}</td>` +
            attrs.map(a => renderHeatmapCell(matrix[r][a] || 0, max, { title: `${(matrix[r][a] || 0)} mismatches` })).join('') +
            `<td class="an-heatmap-total">${rowTot}</td></tr>`;
    }).join('');
    el.innerHTML = `<table class="an-heatmap"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function populateAttributeMatchBar(d) {
    const el = document.getElementById('an-attribute-match-bar');
    if (!el) return;
    const rates = ((d && d.verification_quality) || {}).attribute_match_rates || [];
    if (!rates.length) { el.innerHTML = '<div class="an-empty">No attribute data available.</div>'; return; }
    const sorted = [...rates].sort((a, b) => (b.match_rate || 0) - (a.match_rate || 0));
    const max = sorted[0]?.match_rate || 1;
    el.innerHTML = sorted.map(r => {
        const pct = (r.match_rate || 0) * 100;
        const color = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--accent)' : 'var(--red)';
        return `<div class="an-attr-row" onclick="jumpToVerification({attr:'${escJs(r.attribute)}'})" title="Click to review failing rows">
            <div class="an-attr-label">${escHtml(r.attribute)} — ${pct.toFixed(1)}% matched (${r.matched}/${r.total})</div>
            <div class="an-attr-bar-wrap"><div class="an-attr-bar" style="width:${(pct / (max * 100) * 100)}%;background:${color};"></div></div>
        </div>`;
    }).join('');
}

function populateVerifCountryTable(d) {
    const tbody = document.getElementById('an-verif-country-tbody');
    if (!tbody) return;
    const vq = (d && d.verification_quality) || {};
    const rows = vq.country_quality || [];
    const anomalies = vq.country_quality_anomalies || {};
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="an-empty">No verification data available — run verification first.</td></tr>`;
        return;
    }
    tbody.innerHTML = rows.map(r => {
        const rate = r.verification_rate != null ? (r.verification_rate * 100).toFixed(0) : 0;
        const rateColor = rate >= 80 ? 'var(--green)' : rate >= 50 ? 'var(--accent)' : 'var(--red)';
        const q = r.quality_score != null ? r.quality_score : '—';
        const qColor = q >= 70 ? 'var(--green)' : q >= 40 ? 'var(--accent)' : 'var(--red)';
        const flag = anomalies[r.country];
        const flagTag = flag === 'LOW' ? '<span class="an-tag an-tag--low">LOW</span>'
            : flag === 'HIGH' ? '<span class="an-tag an-tag--high">HIGH</span>' : '';
        return `<tr class="clickable-row" onclick="showCountryDetail('${escJs(r.country)}','verif')" title="Click for country profile">
            <td>${initialsChip(r.country)} <strong>${escHtml(r.country)}</strong></td>
            <td style="text-align:center;">${r.total}</td>
            <td style="text-align:center;color:var(--green);font-weight:700;">${r.verified}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${r.discrepancies}</td>
            <td style="text-align:center;color:var(--red);font-weight:700;">${r.errors}</td>
            <td>
                <div style="display:flex;align-items:center;gap:8px;">
                    <div style="flex:1;height:6px;background:var(--bg-hover);border-radius:20px;overflow:hidden;">
                        <div style="height:6px;width:${rate}%;background:${rateColor};border-radius:20px;"></div>
                    </div>
                    <span style="font-weight:800;font-size:0.78rem;color:${rateColor};min-width:34px;">${rate}%</span>
                </div>
            </td>
            <td style="text-align:center;font-weight:800;color:${qColor};">${q}</td>
            <td style="text-align:center;">${flagTag}</td>
        </tr>`;
    }).join('');
}

function populateDQHealthGauge(d) {
    const el = document.getElementById('an-dq-health-gauge');
    if (!el) return;
    const dq = ((d && d.verification_quality) || {}).data_quality_health || {};
    renderScoreGauge('an-dq-health-gauge', dq.score || 0, 100, {
        color: 'var(--blue)', gaugeLabel: 'DQ SCORE',
        sub: 'Composite of verification rate, error rate and attribute completeness.',
        stats: [
            { value: pct(dq.verified_rate, 0), label: 'VERIFICATION RATE' },
            { value: pct(dq.error_rate, 0), label: 'ERROR RATE (INVERTED)' },
            { value: pct(dq.attribute_completeness, 0), label: 'ATTRIBUTE COMPLETENESS' }
        ]
    });
}

function populateAnomalyPanel(d) {
    const el = document.getElementById('an-anomaly-panel');
    if (!el) return;
    const vq = (d && d.verification_quality) || {};
    const anomalies = vq.anomalies || [];
    const labels = {
        outlier_fees: 'Outlier Fees', unverified_rank_claim: 'Unverified Rank Claim',
        all_attribute_mismatch: 'All-Attribute Mismatch', website_unreachable: 'Website Unreachable'
    };
    if (!anomalies.length) { el.innerHTML = '<div class="an-empty">No anomalies detected.</div>'; return; }
    el.innerHTML = `<table class="an-anomaly-table"><thead>
        <tr><th>Type</th><th>Count</th><th>Severity</th><th>Review</th></tr></thead><tbody>` +
        anomalies.map(a => {
            const sev = a.severity || 'Low';
            const sevCls = sev === 'High' ? 'an-severity--high' : sev === 'Med' ? 'an-severity--med' : 'an-severity--low';
            const samples = (a.sample_ids || []).slice(0, 3).map(s => {
                if (s == null) return '<div class="an-anomaly-sample">—</div>';
                if (typeof s === 'string' || typeof s === 'number')
                    return `<div class="an-anomaly-sample">${escHtml(String(s))}</div>`;
                const name = s.name || s.id || s.course || '—';
                const meta = (s.country || s.domain) ? `${escHtml(s.country || '—')} · ${escHtml(s.domain || '—')}` : '';
                return `<div class="an-anomaly-sample">${escHtml(name)}${meta ? ` <span class="an-anomaly-meta">${meta}</span>` : ''}</div>`;
            }).join('');
            return `<tr class="clickable-row" onclick="showAnomalyDetail('${escJs(a.type)}')" title="Click to review all flagged courses">
                <td class="an-anomaly-type"><strong>${escHtml(labels[a.type] || a.type)}</strong></td>
                <td style="text-align:center;font-weight:800;">${a.count || 0}</td>
                <td><span class="an-severity ${sevCls}">${escHtml(sev)}</span></td>
                <td class="an-anomaly-review">${samples || '—'}</td>
            </tr>`;
        }).join('') + `</tbody></table>`;
}

function populateDomainQualityTable(d) {
    const tbody = document.getElementById('an-domain-quality-table');
    if (!tbody) return;
    const rows = ((d && d.verification_quality) || {}).domain_quality || [];
    if (!rows.length) { tbody.innerHTML = `<tr><td colspan="7" class="an-empty">No domain-level data available.</td></tr>`; return; }
    const max = Math.max(1, ...rows.map(r => r.quality_score || 0));
    tbody.innerHTML = rows.map(r => {
        const vr = pct(r.verification_rate, 0);
        return `<tr>
            <td><strong>${escHtml(r.domain)}</strong></td>
            <td style="text-align:center;">${r.total}</td>
            <td style="text-align:center;color:var(--green);font-weight:700;">${r.verified}</td>
            <td style="text-align:center;color:var(--accent);font-weight:700;">${r.discrepancies}</td>
            <td style="text-align:center;color:var(--red);font-weight:700;">${r.errors}</td>
            <td style="text-align:center;">${vr}</td>
            <td class="an-heat-cell">${renderHeatmapCell(r.quality_score || 0, max, { text: r.quality_score })}</td>
        </tr>`;
    }).join('');
}

function populateVerifFindings(d) {
    const el = document.getElementById('an-verif-key-findings-body');
    if (!el) return;
    const vq = (d && d.verification_quality) || {};
    const sc = vq.status_counts || {};
    const dq = vq.data_quality_health || {};
    const pareto = vq.disc_reason_pareto || [];
    const rates = vq.attribute_match_rates || [];
    const anomalies = vq.anomalies || [];
    const findings = [];
    const tot = sc.total || 0;
    if (tot) findings.push(`${sc.verified || 0} of ${tot} courses verified (${tot ? Math.round((sc.verified || 0) / tot * 100) : 0}%), with ${sc.discrepancies || 0} discrepancies and ${sc.errors || 0} errors requiring attention.`);
    if (pareto.length) findings.push(`The leading discrepancy cluster is "${pareto[0].reason}" (${pareto[0].count} cases), accounting for ${pareto[0].cumulative_pct}% of the cumulative total.`);
    const lowAttr = [...rates].sort((a, b) => (a.match_rate || 0) - (b.match_rate || 0))[0];
    if (lowAttr) findings.push(`Lowest attribute verification is ${lowAttr.attribute} at ${(lowAttr.match_rate * 100).toFixed(1)}% matched (${lowAttr.matched}/${lowAttr.total}).`);
    const highAnom = anomalies.find(a => (a.count || 0) > 0 && (a.severity === 'High'));
    if (highAnom) findings.push(`${highAnom.count} high-severity ${highAnom.type.replace(/_/g, ' ')} anomalies flagged for review.`);
    findings.push(`Data-quality health score is ${dq.score || 0}/100 (verification rate ${pct(dq.verified_rate, 0)}, error rate ${pct(dq.error_rate, 0)}, completeness ${pct(dq.attribute_completeness, 0)}).`);
    el.innerHTML = findings.map(f => `<div class="an-keyfindings-bullet">${escHtml(f)}</div>`).join('') ||
        '<div class="an-empty">No verification findings yet — run verification first.</div>';
}


// -- Main fetch ----------------------------------------------------------
// Renders every Analytics section from a given analytics payload `d`,
// merging it with the live globalData. Pure/synchronous so the cached path
// can paint instantly on tab re-open. Extracted from the old fetchAnalytics.
function renderAnalytics(d) {
    // Always-available data from the dashboard
    const recent = globalData?.recent || [];
    const stats = globalData?.stats || {};
    const countryCounts = globalData?.country_counts || {};
    const domainCounts = globalData?.domain_counts || {};

    // Merge: prefer analytics data; fall back to globalData equivalents
    const effectiveCountryPivot = Object.keys(d.country_pivot || {}).length > 0
        ? d.country_pivot
        : Object.fromEntries(Object.entries(countryCounts).filter(([k]) => isValidCountry(k)));

    let effectiveDomainPivot = d.domain_pivot || {};
    if (Object.keys(effectiveDomainPivot).length === 0 && Object.keys(domainCounts).length > 0) {
        effectiveDomainPivot = {};
        Object.entries(domainCounts).forEach(([dom, total]) => {
            const dr = recent.filter(r => (r.domain || '').toLowerCase().includes(dom.toLowerCase()));
            // Real Indian count from the data only — never an assumed percentage.
            const ind = dr.filter(r => (r.country || '').toLowerCase().includes('india')).length;
            effectiveDomainPivot[dom] = { Total: total, Indian: ind, International: total - ind };
        });
    }

    const effectiveCourseCategory = Object.keys(d.course_category || {}).length > 0
        ? d.course_category : domainCounts;

    // Populate all sections
    populateAnalyticsKPIs(d, stats, countryCounts);
    populateKeyFindings(d);
    populateInsightCards({ ...d, country_pivot: effectiveCountryPivot, domain_pivot: effectiveDomainPivot }, globalData);
    populateCredentialChart(effectiveCourseCategory);
    populatePricingChart(d.pricing_category);

    // India vs World - always from country_counts (truth)
    const realTotal = stats.total || Object.values(countryCounts).reduce((s, v) => s + v, 0) || 1;
    const indiaTotal = Object.entries(countryCounts)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    populateSplitVisual((indiaTotal / realTotal) * 100, d);

    populateAnTopCountries(effectiveCountryPivot);
    populateAffordabilityGauge(d);
    populateFreePaidChart(d);
    populateFeeHistogram(d);
    populateCredentialCostHeatmap(d);

    // Geography
    geoTableData = Object.entries(effectiveCountryPivot)
        .filter(([k]) => isValidCountry(k)).sort((a, b) => b[1] - a[1]);
    renderGeoTable();
    populateGeoConcentration(d);
    populateRegionalGroups(d);
    populateGeoProblemRanking(d);
    populateGeoCompare(d);

    // Specializations
    const dSat = { ...d, domain_pivot: effectiveDomainPivot };
    populateConcentrationGauge(dSat);
    populateDomainTab(effectiveDomainPivot, dSat);
    populateCredentialLadder(d);
    populateCredentialCostChart(d);
    populateCredentialVerificationHeatmap(d);
    populateRankedCredentialMix(d);
    populateUniversityLeaderboard(d);
    populateAcademicFindings(d);

    // Verification
    populateVerifKPIs(d);
    populateStatusChart(d);
    populateIssueOriginChart(d);
    populateDiscPareto(d);
    populateReasonAttributeHeatmap(d);
    populateAttributeMatchBar(d);
    populateVerifCountryTable(d);
    populateDQHealthGauge(d);
    populateAnomalyPanel(d);
    populateDomainQualityTable(d);
    populateVerifFindings(d);

    // Rankings
    populateRankingMix(d);
    populateRankedVsUnranked(d);

    // Persistent controls
    initAnalyticsFilters(d);
    initAnalyticsExport(d);

    console.log('[Analytics] OK - total:', realTotal, '| countries:', geoTableData.length, '| india:', indiaTotal);
}

// Fetch /api/analytics.json and return the parsed `data` payload, or null on
// failure. Updates lastAnalyticsHash when a payload is successfully read.
async function fetchAnalyticsPayload() {
    try {
        const res = await fetch(API_BASE_URL + '/api/analytics.json');
        const json = await res.json();
        if (json.status === 'success' && json.data) {
            return json.data;
        }
    } catch (e) {
        console.warn('[Analytics] analytics.json not available, using dashboard data only');
    }
    return null;
}

async function fetchAnalytics() {
    // Wait for dashboard data if not yet ready (very first call only).
    if (!globalData && !analyticsData) {
        let waited = 0;
        await new Promise(resolve => {
            const poll = setInterval(() => {
                waited += 100;
                if (globalData || waited >= 6000) { clearInterval(poll); resolve(); }
            }, 100);
        });
    }

    // Cached path: render the last-known payload synchronously (instant tab
    // switch), then re-fetch in the background and re-render only if the
    // JSON actually changed.
    if (analyticsData) {
        renderAnalytics(analyticsData);
        refreshAnalyticsInBackground();
        return;
    }

    // First load: fetch then render.
    const payload = await fetchAnalyticsPayload();
    if (payload) {
        analyticsData = payload;
        lastAnalyticsHash = JSON.stringify(payload);
        renderAnalytics(payload);
    } else {
        // No analytics available yet — render with the empty-shape defaults
        // so the tab still shows dashboard-derived data.
        renderAnalytics({ course_category: {}, pricing_category: {}, variant_category: {}, country_pivot: {}, domain_pivot: {} });
    }
}

// Background refresh used by the cached path. Non-blocking: does not await.
async function refreshAnalyticsInBackground() {
    const payload = await fetchAnalyticsPayload();
    if (!payload) return;
    const hash = JSON.stringify(payload);
    if (hash === lastAnalyticsHash) return;
    analyticsData = payload;
    lastAnalyticsHash = hash;
    renderAnalytics(payload);
}




// ================================================================
//  UPLOAD
// ================================================================
function initUpload() {
    const input = document.getElementById('pdf-upload-global');
    const label = document.getElementById('upload-label-global');
    if (!input) return;

    if (!isLocalEnv && label) label.style.display = 'none';

    input.addEventListener('change', async () => {
        if (!input.files.length) return;
        if (!isLocalEnv) { alert('Upload is only available on the local dashboard.'); input.value = ''; return; }
        const orig = label.textContent;
        label.textContent = 'Uploading…';
        const fd = new FormData();
        for (const f of input.files) fd.append('files[]', f);
        try {
            const res = await fetch(API_BASE_URL + '/api/upload', { method: 'POST', body: fd });
            const result = await res.json();
            alert(result.status === 'success' ? `✓ ${result.message}` : `✗ ${result.message}`);
            if (result.status === 'success') { allCoursesData = []; fetchData(); }
        } catch (e) { alert('Upload failed.'); }
        finally { label.textContent = orig; input.value = ''; }
    });
}

// ================================================================
//  HELPERS
// ================================================================
function getBadgeClass(status) {
    switch ((status || '').toLowerCase()) {
        case 'verified': return 'badge-verified';
        case 'error': return 'badge-error';
        case 'discrepancy': return 'badge-discrepancy';
        default: return 'badge-open';
    }
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Format a 0..1 fraction as a percentage string, or '—' when null/undefined/NaN.
function pct(frac, digits) {
    const n = Number(frac);
    if (frac == null || !isFinite(n)) return '—';
    return (n * 100).toFixed(digits == null ? 1 : digits) + '%';
}

function escJs(str) {
    if (!str) return '';
    return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ================================================================
//  INIT
// ================================================================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initCharts();
    initFilters();
    initModal();
    initUpload();
    initAnalyticsSubTabs();

    // Chain: fetch dashboard data first, then analytics (analytics needs globalData)
    fetchData().then(() => fetchAnalytics());

    // Periodic refresh for dashboard data; analytics refreshes on tab click.
    // 5s poll keeps every viewer (multiple users) in sync in near-real time —
    // any Solved action is persisted server-side and shows up here within 5s.
    setInterval(fetchData, 5000);
});