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
let verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', courseType: 'all' };
let courseFilter       = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all' };

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
    'name_mismatch': 'Name Mismatch', 'qs_mismatch': 'QS Ranking Mismatch',
    'nirf_mismatch': 'NIRF Ranking Mismatch', 'free_box_mismatch': 'Free Box Mismatch',
    'scholarship_box_mismatch': 'Scholarship Box Mismatch',
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
    // Re-fetch analytics every time the tab is opened so data is always fresh.
    // Also ensure allCoursesData is loaded for drilldown accuracy.
    if (targetId === 'tab-analytics') {
        if (allCoursesData.length === 0) loadAllCourses(true);
        fetchAnalytics();
    }
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
        // Course type filter (Bachelors, Masters, Diploma, etc.)
        if (f.courseType !== 'all' && normalizeDomain(c.domain) !== f.courseType) return false;
        if (f.attr !== 'all') {
            // Check both basic attributes and QS/NIRF from pdf_table
            if (ATTR_TO_MATCH[f.attr]) {
                const key = ATTR_TO_MATCH[f.attr];
                if (key && c[key] !== false) return false;
            } else {
                // QS/NIRF/Free Box — check pdf_table rows
                const pdfTable = c.pdf_table || [];
                const attrLower = f.attr.toLowerCase();
                const hasMismatch = pdfTable.some(r => {
                    const rowAttr = (r.attribute || '').toLowerCase();
                    return rowAttr.includes(attrLower.replace(' ranked', '').replace(' box', '')) && r.status === 'FALSE';
                });
                if (!hasMismatch) return false;
            }
        }
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
        // Course type filter (Bachelors, Masters, Diploma, etc.)
        if (f.courseType !== 'all' && normalizeDomain(c.domain) !== f.courseType) return false;
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
    set('vf-search', f.search); set('vf-course-type', f.courseType); set('vf-status', f.status); set('vf-category', f.category);
    set('vf-subtype', f.subtype); set('vf-country', f.country); set('vf-domain', f.domain); set('vf-attr', f.attr);
}

function syncCourseFilters() {
    const f = courseFilter;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.value = v; };
    set('cf-search', f.search); set('cf-course-type', f.courseType); set('cf-status', f.status); set('cf-category', f.category);
    set('cf-subtype', f.subtype); set('cf-country', f.country); set('cf-domain', f.domain);
    set('cf-qs', f.qs); set('cf-nirf', f.nirf);
}

function applyVerificationFilter() { currentRecentPage = 1; renderRecentPage(); }
function applyCourseFilter() { currentPage = 1; renderCoursesPage(); }

function jumpToVerification(partial) {
    verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', courseType: 'all', ...partial };
    syncVerificationFilters();
    switchTab('tab-verification');
    applyVerificationFilter();
}

function jumpToCourses(partial) {
    courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all', ...partial };
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
    wire('vf-course-type', 'courseType', verificationFilter, applyVerificationFilter, false);
    wire('vf-status', 'status', verificationFilter, applyVerificationFilter, false);
    wire('vf-category', 'category', verificationFilter, applyVerificationFilter, false);
    wire('vf-subtype', 'subtype', verificationFilter, applyVerificationFilter, false);
    wire('vf-country', 'country', verificationFilter, applyVerificationFilter, false);
    wire('vf-domain', 'domain', verificationFilter, applyVerificationFilter, false);
    wire('vf-attr', 'attr', verificationFilter, applyVerificationFilter, false);

    wire('cf-search', 'search', courseFilter, applyCourseFilter, true);
    wire('cf-course-type', 'courseType', courseFilter, applyCourseFilter, false);
    wire('cf-status', 'status', courseFilter, applyCourseFilter, false);
    wire('cf-category', 'category', courseFilter, applyCourseFilter, false);
    wire('cf-subtype', 'subtype', courseFilter, applyCourseFilter, false);
    wire('cf-country', 'country', courseFilter, applyCourseFilter, false);
    wire('cf-domain', 'domain', courseFilter, applyCourseFilter, false);
    wire('cf-qs', 'qs', courseFilter, applyCourseFilter, false);
    wire('cf-nirf', 'nirf', courseFilter, applyCourseFilter, false);

    document.getElementById('vf-reset')?.addEventListener('click', () => {
        verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', courseType: 'all' };
        syncVerificationFilters(); applyVerificationFilter();
    });
    document.getElementById('cf-reset')?.addEventListener('click', () => {
        courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all' };
        syncCourseFilters(); applyCourseFilter();
    });

    // Sticky KPI strip cards cross-filter their own tab.
    document.querySelectorAll('#vf-kpi-strip .kpi-strip-card').forEach(card => {
        card.addEventListener('click', () => {
            const partial = {};
            if (card.dataset.status) partial.status = card.dataset.status;
            if (card.dataset.category) partial.category = card.dataset.category;
            verificationFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', attr: 'all', courseType: 'all', ...partial };
            syncVerificationFilters(); applyVerificationFilter();
        });
    });
    document.querySelectorAll('#cf-kpi-strip .kpi-strip-card').forEach(card => {
        card.addEventListener('click', () => {
            const partial = {};
            if (card.dataset.status) partial.status = card.dataset.status;
            if (card.dataset.category) partial.category = card.dataset.category;
            courseFilter = { search: '', status: 'all', category: 'all', subtype: 'all', country: 'all', domain: 'all', qs: 'any', nirf: 'any', courseType: 'all', ...partial };
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
async function loadAllCourses(force = false) {
    const tbody = document.getElementById('all-courses-body');
    if (allCoursesData.length > 0 && !force) { renderCoursesPage(); return; }
    if (tbody && (force || allCoursesData.length === 0)) tbody.innerHTML = '<tr><td colspan="8" class="empty-state">Loading…</td></tr>';
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
            const allFalseCount = falseRows.length;
            const unsolvedCount = falseRows.filter(a => !c.solved_attrs.includes(a)).length;
            c.issue_category = unsolvedCount === 0 ? 'verified' : 'course_issue';
            c.status = unsolvedCount === 0 ? 'Verified' : 'Discrepancy';
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
        // Stats already updated from solve response above — no extra
        // fetchData() needed. The 5s poll handles multi-user sync.
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
}

// ================================================================
//  SHARED DATA APPLY LOGIC
// ================================================================
function _applyData(data, animate) {
    if (!data || data.status !== 'success') return;
    globalData = data;

    const statsHash    = JSON.stringify(data.stats);
    const countryHash  = JSON.stringify(data.country_counts);
    const barSrc       = barMode === 'domain' ? data.domain_counts : data.country_counts;
    const barHash      = JSON.stringify(barSrc);

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
    updateRecentVerifications(data.recent || []);
    if (currentFilter.type) applyFilter(currentFilter.type, currentFilter.value);
    document.body.dataset.loading = 'false';
}

// ================================================================
//  MAIN DATA FETCH
// ================================================================
async function fetchData() {
    if (!globalData) document.body.dataset.loading = 'true';
    try {
        const res  = await fetch(API_BASE_URL + '/api/data.json');
        const data = await res.json();
        if (data.status !== 'success') return;
        const animate = firstDataFetch;
        firstDataFetch = false;
        _applyData(data, animate);
        // Cache for instant next-load on the static Firebase host
        try { localStorage.setItem('cv_data_cache', JSON.stringify({ts: Date.now(), data})); } catch(_) {}
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
let analyticsData = null;
let lastAnalyticsHash = '';
let geoTableData = [];

const PALETTE = ['#6366f1', '#818cf8', '#f43f5e', '#1dda9f', '#f59e0b', '#06b6d4', '#ec4899', '#8b5cf6'];
const STATUS_COLORS = { verified: '#1dda9f', discrepancy: '#f59e0b', error: '#f43f5e', unverified: '#6366f1' };

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
    document.getElementById('an-country-search')?.addEventListener('input', e =>
        renderGeoTable(e.target.value.toLowerCase()));
}

// ── Drill-down helpers ───────────────────────────────────────────
function closeDrilldown(id) {
    const el = document.getElementById(id);
    if (el) { el.style.animation = 'slideDown 0.2s ease'; setTimeout(() => el.style.display = 'none', 180); }
}

function openDrilldown(panelId, titleId, tbodyId, title, rows) {
    const panel = document.getElementById(panelId);
    const titleEl = document.getElementById(titleId);
    const tbody = document.getElementById(tbodyId);
    if (!panel || !titleEl || !tbody) return;
    titleEl.textContent = title;
    tbody.innerHTML = rows;
    panel.style.display = 'block';
    panel.style.animation = 'slideUp 0.25s ease';
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Status badge helper ──────────────────────────────────────────
function statusBadge(s) {
    const cls = getBadgeClass(s || '');
    return `<span class="badge ${cls}">${escHtml(s || '—')}</span>`;
}

// ── KPI cards ────────────────────────────────────────────────────
function populateAnalyticsKPIs(d, globalStats, ccOverride) {
    const el = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };

    // Authoritative total — always from dashboard stats
    const tot = globalStats?.total || 0;

    // Indian courses: from country_counts passed in or globalData fallback
    const cc = ccOverride || globalData?.country_counts || {};
    const indiaCount = Object.entries(cc)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    const intlCount = Math.max(0, tot - indiaCount);

    // Pricing
    const pricingCat = d.pricing_category || {};
    const freeCount = pricingCat['Free Courses'] || 0;
    const pricingTotal = Object.values(pricingCat).reduce((s, v) => s + (Number(v) || 0), 0);

    // Country count — from pivot if available, else from country_counts
    const pivotKeys = Object.keys(d.country_pivot || {}).filter(k => isValidCountry(k));
    const countryCnt = pivotKeys.length || Object.keys(cc).filter(k => isValidCountry(k)).length;

    // Verification match rate
    const vs = globalStats || {};
    const matchRate = vs.total ? ((vs.verified || 0) / vs.total * 100).toFixed(1) : '—';

    el('an-total', tot);
    el('an-indian', indiaCount);
    el('an-intl', intlCount);
    el('an-matchrate', matchRate + (matchRate !== '—' ? '%' : ''));
    el('an-variants-sub', `${Object.values(d.variant_category || {}).reduce((s, v) => s + (Number(v) || 0), 0)} delivery variants`);
    el('an-indian-pct', `${tot ? ((indiaCount / tot) * 100).toFixed(1) : '—'}% of total catalog`);
    el('an-countries-count', `${countryCnt} countries represented`);
    el('an-verified-sub', `${vs.verified || '—'} courses perfectly verified`);
    el('an-free', pricingTotal);
    el('an-free-sub', `${freeCount} fully free certifications`);
}


// ── Auto-insight cards ───────────────────────────────────────────
function populateInsightCards(d, globalData) {
    const container = document.getElementById('insight-cards-row');
    if (!container) return;

    const recent = globalData?.recent || [];
    const stats = globalData?.stats || {};
    const countryPivot = d.country_pivot || {};
    const domainPivot = d.domain_pivot || {};

    // Compute insights
    const tot = stats.total || 1;
    const matchPct = ((stats.verified || 0) / tot * 100).toFixed(1);
    const discPct = ((stats.discrepancies || 0) / tot * 100).toFixed(1);

    const topCountry = Object.entries(countryPivot).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1])[0];
    const topDomain = Object.entries(domainPivot).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0))[0];

    // Most problematic country (from recent)
    const countryIssues = {};
    recent.forEach(r => {
        if (isValidCountry(r.country) && (r.status || '').toLowerCase() !== 'verified') {
            countryIssues[r.country] = (countryIssues[r.country] || 0) + 1;
        }
    });
    const topIssueCountry = Object.entries(countryIssues).sort((a, b) => b[1] - a[1])[0];

    // Top university
    const uniCounts = {};
    recent.forEach(r => { if (r.university) uniCounts[r.university] = (uniCounts[r.university] || 0) + 1; });
    const topUni = Object.entries(uniCounts).sort((a, b) => b[1] - a[1])[0];

    const insights = [
        { icon: '🏆', color: 'var(--green)', label: 'Match Rate', value: `${matchPct}%`, sub: 'Courses perfectly verified' },
        { icon: '⚠️', color: 'var(--accent)', label: 'Discrepancy Rate', value: `${discPct}%`, sub: 'Need manual review' },
        { icon: '🌍', color: 'var(--blue)', label: 'Top Country', value: topCountry ? getFlag(topCountry[0]) + ' ' + topCountry[0] : '—', sub: topCountry ? `${topCountry[1]} courses` : '' },
        { icon: '🔬', color: 'var(--purple)', label: 'Top Domain', value: topDomain?.[0] || '—', sub: topDomain ? `${topDomain[1].Total || 0} courses` : '' },
        { icon: '🏛️', color: 'var(--blue)', label: 'Top University', value: topUni?.[0] || '—', sub: topUni ? `${topUni[1]} courses` : '' },
        { icon: '🚨', color: 'var(--red)', label: 'Most Issues', value: topIssueCountry ? getFlag(topIssueCountry[0]) + ' ' + topIssueCountry[0] : 'None', sub: topIssueCountry ? `${topIssueCountry[1]} flagged` : 'All clean!' },
    ];

    container.innerHTML = insights.map(ins => `
        <div class="insight-card" style="border-top:3px solid ${ins.color};">
            <div class="insight-icon">${ins.icon}</div>
            <div class="insight-body">
                <div class="insight-label">${ins.label}</div>
                <div class="insight-value" style="color:${ins.color};">${ins.value}</div>
                <div class="insight-sub">${ins.sub}</div>
            </div>
        </div>`).join('');
}

// ── India vs World split bar ─────────────────────────────────────
function populateSplitVisual(indianPct) {
    const el = document.getElementById('an-split-visual');
    if (!el) return;
    const intlPct = 100 - indianPct;
    el.innerHTML = `
        <div style="margin-bottom:8px;display:flex;justify-content:space-between;">
            <span style="font-size:0.78rem;font-weight:700;color:var(--green);">🇮🇳 India ${indianPct.toFixed(1)}%</span>
            <span style="font-size:0.78rem;font-weight:700;color:var(--blue);">🌐 International ${intlPct.toFixed(1)}%</span>
        </div>
        <div style="height:16px;border-radius:20px;overflow:hidden;display:flex;">
            <div style="flex:${Math.round(indianPct)};background:var(--green);border-radius:20px 0 0 20px;"></div>
            <div style="flex:${Math.round(intlPct)};background:var(--blue);border-radius:0 20px 20px 0;"></div>
        </div>
        <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
            <div style="background:var(--green-bg);border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:1.4rem;font-weight:900;color:var(--green);">${indianPct.toFixed(1)}%</div>
                <div style="font-size:0.7rem;color:var(--text-3);font-weight:700;text-transform:uppercase;">Indian Catalog</div>
            </div>
            <div style="background:var(--blue-bg);border-radius:10px;padding:12px;text-align:center;">
                <div style="font-size:1.4rem;font-weight:900;color:var(--blue);">${intlPct.toFixed(1)}%</div>
                <div style="font-size:0.7rem;color:var(--text-3);font-weight:700;text-transform:uppercase;">International</div>
            </div>
        </div>`;
}

// ── Credential doughnut ──────────────────────────────────────────
function populateCredentialChart(courseCategory) {
    const ctx = document.getElementById('an-credential-chart');
    if (!ctx) return;
    const entries = Object.entries(courseCategory || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    if (anCredentialChart) anCredentialChart.destroy();
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
                tooltip: { callbacks: { label: c => `${c.label}: ${c.raw} programs` } }
            },
            onClick: (e, els) => {
                if (!els.length) return;
                const label = entries[els[0].index][0];
                openAnalyticsDrilldownByCategory(label);
            }
        }
    });
    const legend = document.getElementById('an-credential-legend');
    if (legend) legend.innerHTML = entries.map(([label, val], i) => `
        <div class="an-legend-item" onclick="openAnalyticsDrilldownByCategory('${label.replace(/'/g, "\\'")}')">
            <div class="an-legend-dot" style="background:${PALETTE[i % PALETTE.length]}"></div>
            <div>
                <div class="an-legend-name">${escHtml(label)}</div>
                <div class="an-legend-val">${val} Courses</div>
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

// ── Top countries hub list ────────────────────────────────────────
function populateAnTopCountries(countryPivot) {
    const el = document.getElementById('an-top-countries');
    if (!el) return;
    const entries = Object.entries(countryPivot || {}).filter(([k]) => isValidCountry(k))
        .sort((a, b) => b[1] - a[1]).slice(0, 5);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt], i) => `
        <div class="an-hub-row" onclick="geoRowDrilldown('${name.replace(/'/g, "\\'")}', ${cnt})" title="Click to see courses">
            <div class="an-hub-rank">${i + 1}</div>
            <div class="an-hub-name">${getFlag(name)} ${escHtml(name)}</div>
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
    const total = geoTableData.reduce((s, [, v]) => s + v, 0) || 1;
    const max = geoTableData[0]?.[1] || 1;
    const rows = search ? geoTableData.filter(([k]) => k.toLowerCase().includes(search)) : geoTableData;

    tbody.innerHTML = rows.length === 0
        ? `<tr><td colspan="7" style="text-align:center;color:var(--text-3);padding:24px;">No results</td></tr>`
        : rows.map(([name, cnt], i) => {
            const st = countryStatusFor(name);
            const verified = st ? st.verified : 0;
            const issues = st ? (st.total - st.verified) : 0;
            return `<tr class="clickable-row" onclick="geoRowDrilldown('${name.replace(/'/g, "\\'")}', ${cnt})" title="Click to see courses">
                <td><span class="geo-rank">${(i + 1).toString().padStart(2, '0')}</span></td>
                <td><span style="font-size:1.1rem;margin-right:8px;">${getFlag(name)}</span><strong>${escHtml(name)}</strong></td>
                <td style="text-align:center;"><span class="geo-volume-badge">${cnt}</span></td>
                <td style="text-align:center;"><span style="color:var(--green);font-weight:700;">${st ? verified : '—'}</span></td>
                <td style="text-align:center;"><span style="color:var(--accent);font-weight:700;">${st ? issues : '—'}</span></td>
                <td style="text-align:right;"><span class="geo-share">${((cnt / total) * 100).toFixed(1)}%</span></td>
                <td><div class="geo-prog-wrap"><div class="geo-prog-bar" style="width:${Math.round(cnt / max * 100)}%"></div></div></td>
            </tr>`;
        }).join('');
}

function geoRowDrilldown(countryName, cnt) {
    const sourceData = allCoursesData.length > 0 ? allCoursesData : (globalData?.recent || []);
    const matches = sourceData.filter(r =>
        (r.country || '').toLowerCase().includes(countryName.toLowerCase()) ||
        countryName.toLowerCase().includes((r.country || '').toLowerCase())
    );
    const rows = matches.length ? matches.map((r, i) => `<tr>
        <td style="color:var(--text-3);">${i + 1}</td>
        <td class="course-name-cell" style="font-weight:600;" title="${escHtml(r.name || r.course_name || '')}">${escHtml(r.name || r.course_name || '—')}</td>
        <td style="color:var(--text-2);">${escHtml(r.university || '—')}</td>
        <td>${escHtml(r.domain || '—')}</td>
        <td>${statusBadge(r.status)}</td>
    </tr>`).join('')
        : `<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet — run verification first</td></tr>`;

    openDrilldown('geo-drilldown', 'geo-drilldown-title', 'geo-drilldown-tbody',
        `${getFlag(countryName)} ${countryName} — ${cnt} Courses`, rows);
}

// ── Domain tab ───────────────────────────────────────────────────
function populateDomainTab(domainPivot) {
    const ctx = document.getElementById('an-domain-chart');
    const recent = globalData?.recent || [];
    const entries = Object.entries(domainPivot || {}).filter(([k]) => k && k !== 'Total')
        .sort((a, b) => (b[1].Total || 0) - (a[1].Total || 0));

    if (ctx) {
        if (anDomainChart) anDomainChart.destroy();
        anDomainChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: entries.map(([k]) => k),
                datasets: [{
                    label: 'Total Courses', data: entries.map(([, v]) => v.Total || 0),
                    backgroundColor: 'rgba(99,102,241,0.75)', hoverBackgroundColor: '#6366f1',
                    borderRadius: 8, borderSkipped: false
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 11, weight: '600' }, maxRotation: 30 } },
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { precision: 0 } }
                },
                animation: { duration: 900, easing: 'easeOutQuart' },
                onClick: (e, els) => {
                    if (els.length) domainRowDrilldown(entries[els[0].index][0]);
                }
            }
        });
    }

    const tbody = document.getElementById('an-domain-tbody');
    if (tbody) tbody.innerHTML = entries.map(([name, v]) => {
        const total = v.Total || 0, indian = v.Indian || 0, intl = v.International || 0;
        const ip = total ? Math.round(indian / total * 100) : 50;
        // Compute verified/issues from ALL courses (not just recent subset)
        const domAll = allCoursesData.filter(r => normalizeDomain(r.domain || '') === name);
        const domVerif = domAll.filter(r => (r.status || '').toLowerCase() === 'verified').length;
        const domIssues = domAll.filter(r => (r.status || '').toLowerCase() === 'discrepancy').length;
        return `<tr class="clickable-row" onclick="domainRowDrilldown('${name.replace(/'/g, "\\'")}')">
            <td><div style="font-weight:800;color:var(--text-1);">${escHtml(name)}</div>
                <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;">Click to explore</div></td>
            <td style="text-align:center;"><span class="dom-total">${total}</span></td>
            <td style="text-align:center;"><span class="dom-indian">${indian}</span></td>
            <td style="text-align:center;"><span class="dom-intl">${intl}</span></td>
            <td style="text-align:center;"><span style="color:var(--green);font-weight:700;">${domVerif || '—'}</span></td>
            <td style="text-align:center;"><span style="color:var(--accent);font-weight:700;">${domIssues || '—'}</span></td>
            <td><div class="dom-mix-bar"><div class="dom-mix-in" style="flex:${ip}"></div><div class="dom-mix-out" style="flex:${100 - ip}"></div></div></td>
        </tr>`;
    }).join('');
}

function domainRowDrilldown(domainName) {
    const sourceData = allCoursesData.length > 0 ? allCoursesData : (globalData?.recent || []);
    const matches = sourceData.filter(r =>
        normalizeDomain(r.domain || '') === domainName);
    const rows = matches.length ? matches.map((r, i) => `<tr>
        <td style="color:var(--text-3);">${i + 1}</td>
        <td class="course-name-cell" style="font-weight:600;" title="${escHtml(r.name || r.course_name || '')}">${escHtml(r.name || r.course_name || '—')}</td>
        <td>${escHtml(r.university || '—')}</td>
        <td>${escHtml(r.country || '—')}</td>
        <td>${statusBadge(r.status)}</td>
        <td style="color:var(--text-3);font-size:0.78rem;">${escHtml(r.disc_reason || r.reason || '—')}</td>
    </tr>`).join('')
        : `<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet — run verification first</td></tr>`;

    openDrilldown('dom-drilldown', 'dom-drilldown-title', 'dom-drilldown-tbody',
        `🔬 ${domainName} — Domain Deep-Dive`, rows);
}

// ── Category drill-down (credential doughnut click) ──────────────
// Real cross-tab filter: jump to All Courses filtered by this domain/level.
function openAnalyticsDrilldownByCategory(catLabel) {
    jumpToCourses({ domain: catLabel });
}

// ── Verification tab ─────────────────────────────────────────────
function populateVerificationTab(stats, recent) {
    // KPI row
    const kpiRow = document.getElementById('verif-kpi-row');
    if (kpiRow) {
        const tot = stats.total || 1;
        const verKpis = [
            { label: 'Verified', val: stats.verified || 0, pct: (stats.verified || 0) / tot, color: 'var(--green)' },
            { label: 'Discrepancies', val: stats.discrepancies || 0, pct: (stats.discrepancies || 0) / tot, color: 'var(--accent)' },
            { label: 'Errors', val: stats.errors || 0, pct: (stats.errors || 0) / tot, color: 'var(--red)' },
        ];
        kpiRow.innerHTML = verKpis.map(k => `
            <div class="verif-kpi-card" style="border-left:4px solid ${k.color};">
                <div style="font-size:1.8rem;font-weight:900;color:${k.color};">${k.val}</div>
                <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-3);">${k.label}</div>
                <div style="margin-top:8px;height:4px;background:var(--bg-hover);border-radius:20px;overflow:hidden;">
                    <div style="height:4px;width:${(k.pct * 100).toFixed(1)}%;background:${k.color};border-radius:20px;"></div>
                </div>
                <div style="font-size:0.72rem;color:var(--text-2);margin-top:4px;">${(k.pct * 100).toFixed(1)}% of total</div>
            </div>`).join('');
    }

    // Status doughnut
    const ctx = document.getElementById('an-status-chart');
    if (ctx) {
        if (anStatusChart) anStatusChart.destroy();
        anStatusChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Verified', 'Discrepancy', 'Error'],
                datasets: [{
                    data: [stats.verified || 0, stats.discrepancies || 0, stats.errors || 0],
                    backgroundColor: ['#1dda9f', '#f59e0b', '#f43f5e'],
                    borderColor: 'transparent', borderWidth: 0, hoverOffset: 10
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: '68%',
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `${c.label}: ${c.raw}` } } }
            }
        });
    }

    // Discrepancy reasons — use course_issue_list from /api/data.json when
    // available (computed over ALL course_issue courses, not just the recent
    // page subset), falling back to the recent list.
    const courseIssues = globalData?.course_issue_list || recent;
    const reasons = {};
    courseIssues.forEach(r => {
        if (r.disc_reason || r.reason) {
            const key = (r.disc_reason || r.reason || '').trim();
            if (key) reasons[key] = (reasons[key] || 0) + 1;
        }
    });
    const topReasons = Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 8);
    const discEl = document.getElementById('an-disc-reasons');
    if (discEl) {
        discEl.innerHTML = topReasons.length ? topReasons.map(([reason, cnt]) => `
            <div class="disc-reason-row">
                <div class="disc-reason-text">${escHtml(reason)}</div>
                <div class="disc-reason-right">
                    <div class="disc-reason-bar-wrap">
                        <div class="disc-reason-bar" style="width:${Math.round(cnt / topReasons[0][1] * 100)}%"></div>
                    </div>
                    <span class="disc-reason-count">${cnt}</span>
                </div>
            </div>`).join('')
            : `<div style="padding:32px;text-align:center;color:var(--text-3);">✅ No discrepancy reasons found — all clean!</div>`;
    }

    // Verification by country table — from server `country_status` (computed
    // over ALL courses, incl. Verified). The old code scanned `recent`, which
    // excluded Verified courses, so verified was always 0 and verified-only
    // countries were missing entirely.
    const csMap = globalData?.country_status || {};
    const vcEntries = Object.entries(csMap)
        .filter(([c]) => isValidCountry(c))
        .map(([c, st]) => [c, { total: st.total || 0, verified: st.verified || 0, discrepancy: st.discrepancies || 0, error: st.errors || 0 }])
        .sort((a, b) => b[1].total - a[1].total);
    const vcTbody = document.getElementById('an-verif-country-tbody');
    if (vcTbody) {
        vcTbody.innerHTML = vcEntries.length ? vcEntries.map(([country, st]) => {
            const rate = st.total ? (st.verified / st.total * 100).toFixed(0) : 0;
            const rateColor = rate >= 80 ? 'var(--green)' : rate >= 50 ? 'var(--accent)' : 'var(--red)';
            return `<tr class="clickable-row" onclick="geoRowDrilldown('${country.replace(/'/g, "\\'")}', ${st.total})">
                <td>${getFlag(country)} <strong>${escHtml(country)}</strong></td>
                <td style="text-align:center;">${st.total}</td>
                <td style="text-align:center;color:var(--green);font-weight:700;">${st.verified}</td>
                <td style="text-align:center;color:var(--accent);font-weight:700;">${st.discrepancy}</td>
                <td style="text-align:center;color:var(--red);font-weight:700;">${st.error}</td>
                <td>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <div style="flex:1;height:6px;background:var(--bg-hover);border-radius:20px;overflow:hidden;">
                            <div style="height:6px;width:${rate}%;background:${rateColor};border-radius:20px;"></div>
                        </div>
                        <span style="font-weight:800;font-size:0.83rem;color:${rateColor};min-width:36px;">${rate}%</span>
                    </div>
                </td>
            </tr>`;
        }).join('')
            : `<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:24px;">No verification data available — run verification first</td></tr>`;
    }
}


// -- Main fetch ----------------------------------------------------------
// Renders every Analytics section from a given analytics payload `d`,
// merging it with the live globalData. Pure/synchronous so the cached path
// can paint instantly on tab re-open. Extracted from the old fetchAnalytics.
function renderAnalytics(d) {
    // Always-available data from the dashboard (live /api/data.json)
    const recent = globalData?.recent || [];
    const stats = globalData?.stats || {};
    const countryCounts = globalData?.country_counts || {};
    const domainCounts = globalData?.domain_counts || {};

    // Analytics data (from /api/analytics.json) is now built from the same
    // global_courses as /api/data.json, so they should always agree.
    // Fall back to globalData equivalents ONLY if analytics is missing a section.
    const effectiveCountryPivot = Object.keys(d.country_pivot || {}).length > 0
        ? d.country_pivot
        : Object.fromEntries(Object.entries(countryCounts).filter(([k]) => isValidCountry(k)));

    let effectiveDomainPivot = d.domain_pivot || {};
    if (Object.keys(effectiveDomainPivot).length === 0) {
        // Build from ALL courses data (not just recent) for accurate counts
        effectiveDomainPivot = {};
        allCoursesData.forEach(c => {
            const dom = normalizeDomain(c.domain || '');
            if (!dom || dom === 'Other') return;
            if (!effectiveDomainPivot[dom]) effectiveDomainPivot[dom] = { Total: 0, Indian: 0, International: 0 };
            effectiveDomainPivot[dom].Total++;
            if ((c.country || '').toLowerCase().includes('india')) effectiveDomainPivot[dom].Indian++;
            else effectiveDomainPivot[dom].International++;
        });
    }

    // Course category: prefer analytics payload; fall back to allCoursesData
    const effectiveCourseCategory = Object.keys(d.course_category || {}).length > 0
        ? d.course_category
        : (() => {
            const cc = {};
            allCoursesData.forEach(c => {
                const lvl = normalizeDomain(c.domain || '');
                if (lvl && lvl !== 'Other') cc[lvl] = (cc[lvl] || 0) + 1;
            });
            return cc;
        })();

    // Populate all sections
    populateAnalyticsKPIs(d, stats, countryCounts);
    populateInsightCards({ ...d, country_pivot: effectiveCountryPivot, domain_pivot: effectiveDomainPivot }, globalData);
    populateCredentialChart(effectiveCourseCategory);
    populatePricingChart(d.pricing_category);

    // India vs World - always from country_counts (truth from /api/data.json)
    const realTotal = stats.total || Object.values(countryCounts).reduce((s, v) => s + v, 0) || 1;
    const indiaTotal = Object.entries(countryCounts)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s, [, v]) => s + (Number(v) || 0), 0);
    populateSplitVisual((indiaTotal / realTotal) * 100);

    populateAnTopCountries(effectiveCountryPivot);

    geoTableData = Object.entries(effectiveCountryPivot)
        .filter(([k]) => isValidCountry(k)).sort((a, b) => b[1] - a[1]);
    renderGeoTable();

    populateDomainTab(effectiveDomainPivot);
    populateVerificationTab(stats, recent);

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
            if (result.status === 'success') {
                // ── Instant KPI update from the response (no second fetch needed) ──
                if (result.data_payload) {
                    // Reset hash caches to force re-render
                    lastStatsHash = '';
                    lastCountryHash = '';
                    lastBarHash = '';
                    _applyData(result.data_payload, false);
                }
                // Merge returned courses directly into allCoursesData
                const updatedMap = {};
                (result.verified_courses || []).forEach(c => { updatedMap[c.id] = c; });
                allCoursesData = allCoursesData.map(c =>
                    updatedMap[c.id] !== undefined ? updatedMap[c.id] : c
                );
                currentPage = 1;
                renderCoursesPage();
                // Show non-blocking success message after update
                label.textContent = `✓ ${result.updates} updated`;
                setTimeout(() => { label.textContent = orig; }, 3000);
            } else {
                alert(`✗ ${result.message}`);
            }
        } catch (e) { alert('Upload failed: ' + (e.message || 'network error')); }
        finally { input.value = ''; }
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

    // ── Tier 1: Server-pre-embedded data (instant, 0 ms latency) ─────────
    // The Flask index route embeds the current payload into window.__INITIAL_DATA__.
    // Consuming it here paints real KPI numbers before any network request fires.
    if (window.__INITIAL_DATA__ && window.__INITIAL_DATA__.status === 'success') {
        _applyData(window.__INITIAL_DATA__, true /*animate*/);
        firstDataFetch = false;
    }

    // ── Tier 2: localStorage cache (instant, 0 ms, for static/Firebase host) ──
    // When the static site serves the page (no Flask pre-embed), use the
    // localStorage snapshot from the previous session for an instant first paint.
    if (!globalData) {
        try {
            const cached = JSON.parse(localStorage.getItem('cv_data_cache') || 'null');
            // Accept cache up to 10 minutes old
            if (cached && cached.data && (Date.now() - cached.ts) < 10 * 60 * 1000) {
                _applyData(cached.data, true);
                firstDataFetch = false;
            }
        } catch (_) {}
    }

    // ── Tier 3: Live fetch (always runs initially to ensure fresh data) ──────
    fetchData().then(() => fetchAnalytics());

    // Polling has been removed per user request. 
    // Data now only updates on initial load and immediately after a successful upload/solve action.
});