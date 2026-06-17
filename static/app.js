/* ================================================================
   COURSE VERIFIER  ·  APP.JS  v5
   ================================================================ */

'use strict';

// ── State ────────────────────────────────────────────────────────
let globalData       = null;
let currentFilter    = { type: null, value: null };
let countryDataList  = [];
let allCoursesData   = [];
let recentData       = [];
let currentPage      = 1;
let currentRecentPage = 1;
const PAGE_SIZE       = 100;
const RECENT_PAGE_SIZE = 30;
let lastDataHash     = '';

let statusChart, barChart, mapChart, lineChart;
let authorDomainChart, authorAccuracyChart;
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
    const label  = document.getElementById('theme-label');
    const saved  = localStorage.getItem('cvTheme') || 'dark';
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
    if (targetId === 'tab-author' && globalData) populateAuthorTab(globalData);
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
    Chart.defaults.color          = '#9499b0';
    Chart.defaults.borderColor    = 'rgba(255,255,255,0.06)';
    Chart.defaults.font.family    = "'Inter', sans-serif";

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

    // 2. Status Doughnut
    const pCtx = document.getElementById('statusPieChart')?.getContext('2d');
    if (pCtx) {
        statusChart = new Chart(pCtx, {
            type: 'doughnut',
            data: {
                labels: ['Verified', 'Discrepancies', 'Errors', 'Unverified'],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: ['#1dda9f', '#f46a22', '#f16b6b', '#3d4268'],
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
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: {
                            label: ctx => {
                                const name  = ctx.raw?.feature?.properties?.name || ctx.label || 'Unknown';
                                const count = ctx.raw?.feature?._realCount ?? 0;
                                return `${name}: ${Math.round(count)} courses`;
                            }
                        }}
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
        }).catch(() => {});
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

// ── Author charts (lazy-init) ─────────────────────────────────────
function initAuthorCharts(domainData, stats) {
    const dCtx = document.getElementById('authorDomainChart')?.getContext('2d');
    if (dCtx) {
        if (authorDomainChart) authorDomainChart.destroy();
        const entries = Object.entries(domainData).sort((a,b) => b[1]-a[1]).slice(0, 8);
        authorDomainChart = new Chart(dCtx, {
            type: 'bar',
            data: {
                labels: entries.map(e => e[0]),
                datasets: [{
                    label: 'Courses',
                    data: entries.map(e => e[1]),
                    backgroundColor: [
                        '#f46a22','#c084fc','#1dda9f','#6eb4ff',
                        '#f5a623','#f16b6b','#60a5fa','#34d399'
                    ],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false }, ticks: { font: { size: 10 } } },
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' } }
                }
            }
        });
    }

    const aCtx = document.getElementById('authorAccuracyChart')?.getContext('2d');
    if (aCtx) {
        if (authorAccuracyChart) authorAccuracyChart.destroy();
        const total = (stats.total || 1);
        authorAccuracyChart = new Chart(aCtx, {
            type: 'doughnut',
            data: {
                labels: ['Matched', 'Discrepancy', 'Error'],
                datasets: [{
                    data: [stats.verified || 0, stats.discrepancies || 0, (stats.errors||0)+(stats.unverified||0)],
                    backgroundColor: ['#1dda9f', '#f5a623', '#f16b6b'],
                    borderWidth: 0,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                cutout: '68%',
                plugins: {
                    legend: { position: 'bottom', labels: { usePointStyle: true, padding: 16, font: { size: 11 } } }
                }
            }
        });
    }
}

// ================================================================
//  DATA UPDATES
// ================================================================
function updateCards(stats) {
    document.getElementById('total-count').textContent        = stats.total || 0;
    document.getElementById('verified-count').textContent     = stats.verified || 0;
    document.getElementById('discrepancy-count').textContent  = stats.discrepancies || 0;
    document.getElementById('error-count').textContent        = (stats.errors || 0) + (stats.unverified || 0);

    // Dynamic trend % labels
    const t = stats.total || 1;
    document.getElementById('kpi-verified-trend').textContent  = `↑ ${Math.round((stats.verified||0)/t*100)}% match rate`;
    document.getElementById('kpi-disc-trend').textContent      = `⚠ ${Math.round((stats.discrepancies||0)/t*100)}% flagged`;
    document.getElementById('kpi-err-trend').textContent       = `✕ ${Math.round(((stats.errors||0)+(stats.unverified||0))/t*100)}% failed`;
    document.getElementById('kpi-total-trend').textContent     = `— ${t} records`;
}

function updatePieChart(stats) {
    if (!statusChart) return;
    statusChart.data.datasets[0].data = [
        stats.verified, stats.discrepancies, stats.errors, stats.unverified
    ];
    statusChart.update();
}

function updateBarChart() {
    if (!barChart || !globalData) return;
    const src = barMode === 'domain' ? globalData.domain_counts : globalData.country_counts;
    let entries = Object.entries(src || {}).sort((a,b) => b[1]-a[1]);
    if (barMode === 'country') entries = entries.slice(0, 12);
    barChart.data.labels                = entries.map(e => e[0]);
    barChart.data.datasets[0].data      = entries.map(e => e[1]);
    barChart.update();
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

function updateLineChart(countryCounts) {
    if (!lineChart) return;
    const sorted = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a,b) => b[1]-a[1])
        .slice(0, 20);
    countryDataList = sorted;
    lineChart.data.labels               = sorted.map(x => x[0]);
    lineChart.data.datasets[0].data     = sorted.map(x => x[1]);
    lineChart.update();
}

function updateMapChart(countryCounts) {
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
    if (vals.length === 0) { mapChart.update(); return; }
    const maxSqrt = Math.sqrt(Math.max(...vals));
    mapChart.data.datasets[0].data.forEach(d => {
        // Compressed display value, real count preserved in d.feature._realCount
        d.value = d.value > 0 ? (Math.sqrt(d.value) / maxSqrt) * 100 : 0;
    });

    mapChart.update();
}

function updateCountryLeaderboard(countryCounts, containerId = 'country-list') {
    const el = document.getElementById(containerId);
    if (!el) return;
    const entries = Object.entries(countryCounts || {})
        .filter(([k]) => isValidCountry(k))
        .sort((a,b) => b[1]-a[1])
        .slice(0, 15);
    const max = entries[0]?.[1] || 1;
    el.innerHTML = entries.map(([name, cnt]) => `
        <div class="country-row" onclick="applyFilter('country','${name.replace(/'/g,"\\'")}')">
            <span class="c-flag">${getFlag(name)}</span>
            <span class="c-name">${name}</span>
            <div class="c-bar-wrap"><div class="c-bar" style="width:${Math.round(cnt/max*100)}%"></div></div>
            <span class="c-count">${cnt}</span>
        </div>
    `).join('');
}

// ================================================================
//  FILTER
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
        type === 'domain'  ? c.domain  === value :
        type === 'country' ? c.country === value : true
    );
    tbody.innerHTML = filtered.length === 0
        ? '<tr><td colspan="5" style="text-align:center;">No courses found</td></tr>'
        : filtered.map(c => `
            <tr onclick="showCourseModal('${c.id || ''}', '${escHtml(c.name)}', '${escHtml(c.university || '')}')">
                <td><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td>${c.has_qs_badge   ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
                <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            </tr>`).join('');
}

// ================================================================
//  AUTHOR TAB
// ================================================================
function populateAuthorTab(data) {
    const stats = data.stats || {};
    const countries = Object.keys(data.country_counts || {})
        .filter(k => k && k !== 'Unknown').length;

    const el = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    el('a-total',     stats.total      || 0);
    el('a-verified',  stats.verified   || 0);
    el('a-disc',      stats.discrepancies || 0);
    el('a-countries', countries);

    updateCountryLeaderboard(data.country_counts, 'author-country-list');
    initAuthorCharts(data.domain_counts || {}, stats);
}

// ================================================================
//  RECENT VERIFICATIONS
// ================================================================
function updateRecentVerifications(recent) {
    if (!recent) return;
    const hash = JSON.stringify(recent.length);
    if (hash === lastDataHash) return;
    lastDataHash = hash;
    recentData = [...recent].sort((a,b) => parseInt(a.id||'9') - parseInt(b.id||'9'));
    currentRecentPage = 1;
    renderRecentPage();
}

function renderRecentPage() {
    const tbody = document.getElementById('recent-verifications-body');
    const info  = document.getElementById('recent-page-info');
    if (!tbody) return;
    const total  = Math.ceil(recentData.length / RECENT_PAGE_SIZE) || 1;
    const start  = (currentRecentPage - 1) * RECENT_PAGE_SIZE;
    const slice  = recentData.slice(start, start + RECENT_PAGE_SIZE);
    tbody.innerHTML = slice.length === 0
        ? '<tr><td colspan="5" style="text-align:center;">No verifications yet.</td></tr>'
        : slice.map(c => `
            <tr onclick="showCourseModal('${c.id||''}','${escHtml(c.name)}','${escHtml(c.university||'')}')">
                <td><strong>${escHtml(c.name)}</strong></td>
                <td>${escHtml(c.university||'—')}</td>
                <td><span class="badge ${getBadgeClass(c.status)}">${c.status}</span></td>
                <td style="max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${escHtml(c.disc_reason||'—')}</td>
                <td>${c.pdf_page||'—'}</td>
            </tr>`).join('');
    if (info) info.textContent = `Page ${currentRecentPage} of ${total} (${recentData.length})`;
}

document.getElementById('recent-prev-page')?.addEventListener('click', () => {
    if (currentRecentPage > 1) { currentRecentPage--; renderRecentPage(); }
});
document.getElementById('recent-next-page')?.addEventListener('click', () => {
    if (currentRecentPage < Math.ceil(recentData.length / RECENT_PAGE_SIZE)) { currentRecentPage++; renderRecentPage(); }
});

// ================================================================
//  ALL COURSES
// ================================================================
async function loadAllCourses() {
    if (allCoursesData.length > 0) { renderCoursesPage(); return; }
    const tbody = document.getElementById('all-courses-body');
    if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">Loading…</td></tr>';
    try {
        const res  = await fetch('/api/courses.json');
        const data = await res.json();
        allCoursesData = (data.courses || []).sort((a,b) => parseInt(a.id||'9') - parseInt(b.id||'9'));
        renderCoursesPage();
    } catch(e) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:var(--red);">Error loading courses</td></tr>';
    }
}

function renderCoursesPage() {
    const tbody = document.getElementById('all-courses-body');
    const info  = document.getElementById('page-info');
    if (!tbody) return;
    const total = Math.ceil(allCoursesData.length / PAGE_SIZE);
    const start = (currentPage - 1) * PAGE_SIZE;
    const slice = allCoursesData.slice(start, start + PAGE_SIZE);
    tbody.innerHTML = slice.map(c => `
        <tr onclick="showCourseModal('${c.id}')">
            <td>${c.id}</td>
            <td><strong>${escHtml(c.name)}</strong></td>
            <td>${escHtml(c.university||'—')}</td>
            <td>${escHtml(c.domain||'—')}</td>
            <td>${escHtml(c.country||'—')}</td>
            <td>${c.has_qs_badge   ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td><span class="badge ${getBadgeClass(c.status)}">${c.status}</span></td>
        </tr>`).join('');
    if (info) info.textContent = `Page ${currentPage} of ${total} (${allCoursesData.length} courses)`;
}

document.getElementById('prev-page')?.addEventListener('click', () => {
    if (currentPage > 1) { currentPage--; renderCoursesPage(); }
});
document.getElementById('next-page')?.addEventListener('click', () => {
    if (currentPage < Math.ceil(allCoursesData.length / PAGE_SIZE)) { currentPage++; renderCoursesPage(); }
});

// ================================================================
//  MODAL
// ================================================================
async function showCourseModal(courseId, fallbackName, fallbackUni) {
    if (allCoursesData.length === 0) {
        try {
            const res  = await fetch('/api/courses.json');
            const data = await res.json();
            allCoursesData = data.courses || [];
        } catch(e) { return; }
    }
    let c = allCoursesData.find(x => String(x.id) === String(courseId));
    if (!c && fallbackName) c = allCoursesData.find(x => x.name === fallbackName && (x.university||'') === (fallbackUni||''));
    if (!c) { alert('Course not found.'); return; }

    document.getElementById('modal-course-title').textContent = c.name;

    const safe = v => v ? String(v) : 'Not Provided';
    const has_qs   = c.has_qs_badge;
    const has_nirf = c.has_nirf_badge;
    const has_free = c.has_free_box;
    const web_free = c.web_cost && c.web_cost.toLowerCase().includes('free');

    const rows = c.pdf_table || [
        { attribute:'Cost',       original: safe(c.cost),        verified: safe(c.web_cost),      status: c.cost_match     ? 'MATCH':'FALSE' },
        { attribute:'Duration',   original: safe(c.duration),    verified: safe(c.web_duration),  status: c.duration_match ? 'MATCH':'FALSE' },
        { attribute:'Mode',       original: safe(c.mode),        verified: safe(c.web_mode),      status: c.mode_match     ? 'MATCH':'FALSE' },
        { attribute:'Language',   original: safe(c.language),    verified: safe(c.web_language),  status: c.lang_match     ? 'MATCH':'FALSE' },
        { attribute:'Country',    original: safe(c.country),     verified: safe(c.country_verified||c.web_country||'Not Found'), status: c.country_match ? 'MATCH':'FALSE' },
        { attribute:'University', original: safe(c.university||c.uni), verified: safe(c.web_uni), status: c.uni_match      ? 'MATCH':'FALSE' },
        { attribute:'Skills',     original: safe(c.skills),      verified: safe(c.skills_verified), status: c.sk_match     ? 'MATCH':'FALSE' },
        { attribute:'QS Ranked',  original: has_qs  ? 'True (Badge)':'False', verified: safe(c.qs_detail),   status: (c.qs_ranked  ||!has_qs)  ? 'MATCH':'FALSE' },
        { attribute:'NIRF Ranked',original: has_nirf ? 'True (Badge)':'False', verified: safe(c.nirf_detail), status: (c.nirf_ranked||!has_nirf) ? 'MATCH':'FALSE' },
        { attribute:'Free Box',   original: has_free ? 'True':'False', verified: web_free ? 'Free':'Paid', status: (has_free===web_free) ? 'MATCH':'FALSE' }
    ];

    const tbody = document.getElementById('modal-table-body');
    tbody.innerHTML = rows.map(row => `
        <tr style="border-bottom:1px solid var(--border);">
            <td style="padding:10px 12px;color:var(--text-1);font-weight:600;font-size:0.85rem;">${row.attribute}</td>
            <td style="padding:10px 12px;color:var(--text-2);font-size:0.85rem;">${escHtml(row.original)}</td>
            <td style="padding:10px 12px;color:var(--text-2);font-size:0.85rem;">${escHtml(row.verified)}</td>
            <td style="padding:10px 12px;text-align:center;font-weight:700;font-size:0.8rem;letter-spacing:0.04em;color:${row.status==='MATCH'?'var(--green)':'var(--red)'};">${row.status}</td>
        </tr>`).join('');

    document.getElementById('course-modal').classList.add('open');
}

function initModal() {
    document.getElementById('close-modal')?.addEventListener('click', () =>
        document.getElementById('course-modal').classList.remove('open'));
    document.getElementById('delete-course-btn')?.addEventListener('click', () =>
        alert('Deleting from the online viewer is disabled. Please use the local dashboard.'));
    document.getElementById('course-modal')?.addEventListener('click', e => {
        if (e.target === document.getElementById('course-modal'))
            document.getElementById('course-modal').classList.remove('open');
    });
}

// ================================================================
//  MAIN DATA FETCH
// ================================================================
async function fetchData() {
    try {
        const res  = await fetch('/api/data.json');
        const data = await res.json();
        if (data.status !== 'success') return;

        globalData = data;
        updateCards(data.stats);
        updatePieChart(data.stats);
        updateBarChart();
        updateLineChart(data.country_counts);
        updateMapChart(data.country_counts);
        updateCountryLeaderboard(data.country_counts, 'country-list');

        const recent = data.recent?.length ? data.recent
            : (data.discrepancy_list || []).map((d,i) => ({
                id: String(i+1), name: d.name, university: d.university,
                status: 'Discrepancy', disc_reason: d.reason
            }));
        updateRecentVerifications(recent);

        if (currentFilter.type) applyFilter(currentFilter.type, currentFilter.value);

        // If author tab is active, refresh
        if (document.getElementById('tab-author')?.classList.contains('active')) {
            populateAuthorTab(data);
        }
    } catch(e) {
        console.error('Data fetch error:', e);
    }
}

// ================================================================
//  ANALYTICS TAB  —  Full Enriched Implementation
//  Uses BOTH globalData (/api/data.json) AND analyticsData (/api/analytics.json)
// ================================================================
let anCredentialChart = null;
let anPricingChart    = null;
let anDomainChart     = null;
let anStatusChart     = null;
let analyticsData     = null;
let geoTableData      = [];

const PALETTE = ['#6366f1','#818cf8','#f43f5e','#1dda9f','#f59e0b','#06b6d4','#ec4899','#8b5cf6'];
const STATUS_COLORS = { verified:'#1dda9f', discrepancy:'#f59e0b', error:'#f43f5e', unverified:'#6366f1' };

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
    if (el) { el.style.animation = 'slideDown 0.2s ease'; setTimeout(() => el.style.display='none', 180); }
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
    const cls = getBadgeClass(s||'');
    return `<span class="badge ${cls}">${escHtml(s||'—')}</span>`;
}

// ── KPI cards ────────────────────────────────────────────────────
function populateAnalyticsKPIs(d, globalStats, ccOverride) {
    const el = (id, v) => { const e = document.getElementById(id); if(e) e.textContent = v; };

    // Authoritative total — always from dashboard stats
    const tot = globalStats?.total || 0;

    // Indian courses: from country_counts passed in or globalData fallback
    const cc = ccOverride || globalData?.country_counts || {};
    const indiaCount = Object.entries(cc)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s,[,v]) => s+(Number(v)||0), 0);
    const intlCount = Math.max(0, tot - indiaCount);

    // Pricing
    const pricingCat   = d.pricing_category || {};
    const freeCount    = pricingCat['Free Courses'] || 0;
    const pricingTotal = Object.values(pricingCat).reduce((s,v)=>s+(Number(v)||0),0);

    // Country count — from pivot if available, else from country_counts
    const pivotKeys  = Object.keys(d.country_pivot||{}).filter(k => isValidCountry(k));
    const countryCnt = pivotKeys.length || Object.keys(cc).filter(k=>isValidCountry(k)).length;

    // Verification match rate
    const vs        = globalStats || {};
    const matchRate = vs.total ? ((vs.verified||0) / vs.total * 100).toFixed(1) : '—';

    el('an-total',          tot);
    el('an-indian',         indiaCount);
    el('an-intl',           intlCount);
    el('an-matchrate',      matchRate + (matchRate !== '—' ? '%' : ''));
    el('an-variants-sub',   `${Object.values(d.variant_category||{}).reduce((s,v)=>s+(Number(v)||0),0)} delivery variants`);
    el('an-indian-pct',     `${tot ? ((indiaCount/tot)*100).toFixed(1) : '—'}% of total catalog`);
    el('an-countries-count',`${countryCnt} countries represented`);
    el('an-verified-sub',   `${vs.verified||'—'} courses perfectly verified`);
    el('an-free',           pricingTotal);
    el('an-free-sub',       `${freeCount} fully free certifications`);
}


// ── Auto-insight cards ───────────────────────────────────────────
function populateInsightCards(d, globalData) {
    const container = document.getElementById('insight-cards-row');
    if (!container) return;

    const recent      = globalData?.recent || [];
    const stats       = globalData?.stats  || {};
    const countryPivot = d.country_pivot   || {};
    const domainPivot  = d.domain_pivot    || {};

    // Compute insights
    const tot     = stats.total    || 1;
    const matchPct = ((stats.verified||0)/tot*100).toFixed(1);
    const discPct  = ((stats.discrepancies||0)/tot*100).toFixed(1);

    const topCountry = Object.entries(countryPivot).filter(([k])=>isValidCountry(k))
        .sort((a,b)=>b[1]-a[1])[0];
    const topDomain  = Object.entries(domainPivot).filter(([k])=>k&&k!=='Total')
        .sort((a,b)=>(b[1].Total||0)-(a[1].Total||0))[0];

    // Most problematic country (from recent)
    const countryIssues = {};
    recent.forEach(r => {
        if (isValidCountry(r.country) && (r.status||'').toLowerCase() !== 'verified') {
            countryIssues[r.country] = (countryIssues[r.country]||0)+1;
        }
    });
    const topIssueCountry = Object.entries(countryIssues).sort((a,b)=>b[1]-a[1])[0];

    // Top university
    const uniCounts = {};
    recent.forEach(r => { if(r.university) uniCounts[r.university]=(uniCounts[r.university]||0)+1; });
    const topUni = Object.entries(uniCounts).sort((a,b)=>b[1]-a[1])[0];

    const insights = [
        { icon:'🏆', color:'var(--green)',  label:'Match Rate',      value:`${matchPct}%`, sub:'Courses perfectly verified' },
        { icon:'⚠️', color:'var(--accent)', label:'Discrepancy Rate',value:`${discPct}%`,  sub:'Need manual review' },
        { icon:'🌍', color:'var(--blue)',   label:'Top Country',     value: topCountry ? getFlag(topCountry[0])+' '+topCountry[0] : '—', sub: topCountry ? `${topCountry[1]} courses` : '' },
        { icon:'🔬', color:'var(--purple)', label:'Top Domain',      value: topDomain?.[0] || '—',  sub: topDomain ? `${topDomain[1].Total||0} courses` : '' },
        { icon:'🏛️', color:'var(--blue)',   label:'Top University',  value: topUni?.[0] || '—',     sub: topUni ? `${topUni[1]} courses` : '' },
        { icon:'🚨', color:'var(--red)',    label:'Most Issues',     value: topIssueCountry ? getFlag(topIssueCountry[0])+' '+topIssueCountry[0] : 'None', sub: topIssueCountry ? `${topIssueCountry[1]} flagged` : 'All clean!' },
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
    const entries = Object.entries(courseCategory||{}).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    if (anCredentialChart) anCredentialChart.destroy();
    anCredentialChart = new Chart(ctx, {
        type:'doughnut',
        data:{ labels:entries.map(e=>e[0]),
               datasets:[{ data:entries.map(e=>e[1]), backgroundColor:PALETTE, borderColor:'transparent', borderWidth:0, hoverOffset:10 }] },
        options:{ responsive:true, maintainAspectRatio:false, cutout:'70%',
                  plugins:{ legend:{display:false},
                            tooltip:{callbacks:{label:c=>`${c.label}: ${c.raw} programs`}} },
                  onClick:(e,els) => {
                      if (!els.length) return;
                      const label = entries[els[0].index][0];
                      openAnalyticsDrilldownByCategory(label);
                  }
        }
    });
    const legend = document.getElementById('an-credential-legend');
    if (legend) legend.innerHTML = entries.map(([label,val],i)=>`
        <div class="an-legend-item" onclick="openAnalyticsDrilldownByCategory('${label.replace(/'/g,"\\'")}')">
            <div class="an-legend-dot" style="background:${PALETTE[i%PALETTE.length]}"></div>
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
    const entries = Object.entries(pricingCategory||{}).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    if (anPricingChart) anPricingChart.destroy();
    anPricingChart = new Chart(ctx, {
        type:'bar',
        data:{ labels:entries.map(e=>e[0]),
               datasets:[{ label:'Courses', data:entries.map(e=>e[1]),
                   backgroundColor:'rgba(241,107,107,0.8)', hoverBackgroundColor:'#f16b6b',
                   borderRadius:8, borderSkipped:false }] },
        options:{ responsive:true, maintainAspectRatio:false,
            plugins:{ legend:{display:false} },
            scales:{ x:{grid:{display:false},ticks:{font:{size:12,weight:'600'},maxRotation:30}},
                     y:{beginAtZero:true,grid:{color:'rgba(255,255,255,0.04)'},ticks:{precision:0}} },
            animation:{duration:900,easing:'easeOutQuart'},
            onClick:(e,els) => { if (els.length) alert(`${entries[els[0].index][0]}: ${entries[els[0].index][1]} courses`); }
        }
    });
}

// ── Top countries hub list ────────────────────────────────────────
function populateAnTopCountries(countryPivot) {
    const el = document.getElementById('an-top-countries');
    if (!el) return;
    const entries = Object.entries(countryPivot||{}).filter(([k])=>isValidCountry(k))
        .sort((a,b)=>b[1]-a[1]).slice(0,5);
    const max = entries[0]?.[1]||1;
    el.innerHTML = entries.map(([name,cnt],i)=>`
        <div class="an-hub-row" onclick="geoRowDrilldown('${name.replace(/'/g,"\\'")}', ${cnt})" title="Click to see courses">
            <div class="an-hub-rank">${i+1}</div>
            <div class="an-hub-name">${getFlag(name)} ${escHtml(name)}</div>
            <div class="an-hub-bar-wrap"><div class="an-hub-bar" style="width:${Math.round(cnt/max*100)}%"></div></div>
            <div class="an-hub-count">${cnt}</div>
        </div>`).join('');
}

// ── Geography table ──────────────────────────────────────────────
function renderGeoTable(search='') {
    const tbody = document.getElementById('an-country-tbody');
    if (!tbody) return;
    const recent = globalData?.recent || [];
    const total  = geoTableData.reduce((s,[,v])=>s+v,0)||1;
    const max    = geoTableData[0]?.[1]||1;
    const rows   = search ? geoTableData.filter(([k])=>k.toLowerCase().includes(search)) : geoTableData;

    tbody.innerHTML = rows.length===0
        ? `<tr><td colspan="7" style="text-align:center;color:var(--text-3);padding:24px;">No results</td></tr>`
        : rows.map(([name,cnt],i) => {
            // Compute verified / issues from recent data
            const matching = recent.filter(r => (r.country||'').toLowerCase().includes(name.toLowerCase())
                                              || name.toLowerCase().includes((r.country||'').toLowerCase()));
            const verified = matching.filter(r=>(r.status||'').toLowerCase()==='verified').length;
            const issues   = matching.filter(r=>(r.status||'').toLowerCase()!=='verified' && r.status).length;
            return `<tr class="clickable-row" onclick="geoRowDrilldown('${name.replace(/'/g,"\\'")}', ${cnt})" title="Click to see courses">
                <td><span class="geo-rank">${(i+1).toString().padStart(2,'0')}</span></td>
                <td><span style="font-size:1.1rem;margin-right:8px;">${getFlag(name)}</span><strong>${escHtml(name)}</strong></td>
                <td style="text-align:center;"><span class="geo-volume-badge">${cnt}</span></td>
                <td style="text-align:center;"><span style="color:var(--green);font-weight:700;">${verified||'—'}</span></td>
                <td style="text-align:center;"><span style="color:var(--accent);font-weight:700;">${issues||'—'}</span></td>
                <td style="text-align:right;"><span class="geo-share">${((cnt/total)*100).toFixed(1)}%</span></td>
                <td><div class="geo-prog-wrap"><div class="geo-prog-bar" style="width:${Math.round(cnt/max*100)}%"></div></div></td>
            </tr>`;
        }).join('');
}

function geoRowDrilldown(countryName, cnt) {
    const recent = globalData?.recent || [];
    const matches = recent.filter(r =>
        (r.country||'').toLowerCase().includes(countryName.toLowerCase()) ||
        countryName.toLowerCase().includes((r.country||'').toLowerCase())
    );
    const rows = matches.length ? matches.map((r,i) => `<tr>
        <td style="color:var(--text-3);">${i+1}</td>
        <td style="font-weight:600;">${escHtml(r.name||r.course_name||'—')}</td>
        <td style="color:var(--text-2);">${escHtml(r.university||'—')}</td>
        <td>${escHtml(r.domain||'—')}</td>
        <td>${statusBadge(r.status)}</td>
    </tr>`).join('')
    : `<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet — run verification first</td></tr>`;

    openDrilldown('geo-drilldown','geo-drilldown-title','geo-drilldown-tbody',
        `${getFlag(countryName)} ${countryName} — ${cnt} Courses`, rows);
}

// ── Domain tab ───────────────────────────────────────────────────
function populateDomainTab(domainPivot) {
    const ctx     = document.getElementById('an-domain-chart');
    const recent  = globalData?.recent || [];
    const entries = Object.entries(domainPivot||{}).filter(([k])=>k&&k!=='Total')
        .sort((a,b)=>(b[1].Total||0)-(a[1].Total||0));

    if (ctx) {
        if (anDomainChart) anDomainChart.destroy();
        anDomainChart = new Chart(ctx, {
            type:'bar',
            data:{ labels:entries.map(([k])=>k),
                   datasets:[{ label:'Total Courses', data:entries.map(([,v])=>v.Total||0),
                       backgroundColor:'rgba(99,102,241,0.75)', hoverBackgroundColor:'#6366f1',
                       borderRadius:8, borderSkipped:false }] },
            options:{ responsive:true, maintainAspectRatio:false,
                plugins:{ legend:{display:false} },
                scales:{ x:{grid:{display:false},ticks:{font:{size:11,weight:'600'},maxRotation:30}},
                         y:{beginAtZero:true,grid:{color:'rgba(255,255,255,0.04)'},ticks:{precision:0}} },
                animation:{duration:900,easing:'easeOutQuart'},
                onClick:(e,els) => {
                    if (els.length) domainRowDrilldown(entries[els[0].index][0]);
                }
            }
        });
    }

    const tbody = document.getElementById('an-domain-tbody');
    if (tbody) tbody.innerHTML = entries.map(([name,v]) => {
        const total=v.Total||0, indian=v.Indian||0, intl=v.International||0;
        const ip = total ? Math.round(indian/total*100) : 50;
        // Compute from recent
        const domRecent  = recent.filter(r => (r.domain||'').toLowerCase().includes(name.toLowerCase()));
        const domVerif   = domRecent.filter(r=>(r.status||'').toLowerCase()==='verified').length;
        const domIssues  = domRecent.filter(r=>(r.status||'').toLowerCase()==='discrepancy').length;
        return `<tr class="clickable-row" onclick="domainRowDrilldown('${name.replace(/'/g,"\\'")}')">
            <td><div style="font-weight:800;color:var(--text-1);">${escHtml(name)}</div>
                <div style="font-size:0.68rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;">Click to explore</div></td>
            <td style="text-align:center;"><span class="dom-total">${total}</span></td>
            <td style="text-align:center;"><span class="dom-indian">${indian}</span></td>
            <td style="text-align:center;"><span class="dom-intl">${intl}</span></td>
            <td style="text-align:center;"><span style="color:var(--green);font-weight:700;">${domVerif||'—'}</span></td>
            <td style="text-align:center;"><span style="color:var(--accent);font-weight:700;">${domIssues||'—'}</span></td>
            <td><div class="dom-mix-bar"><div class="dom-mix-in" style="flex:${ip}"></div><div class="dom-mix-out" style="flex:${100-ip}"></div></div></td>
        </tr>`;
    }).join('');
}

function domainRowDrilldown(domainName) {
    const recent = globalData?.recent || [];
    const matches = recent.filter(r =>
        (r.domain||'').toLowerCase().includes(domainName.toLowerCase()));
    const rows = matches.length ? matches.map((r,i) => `<tr>
        <td style="color:var(--text-3);">${i+1}</td>
        <td style="font-weight:600;">${escHtml(r.name||r.course_name||'—')}</td>
        <td>${escHtml(r.university||'—')}</td>
        <td>${escHtml(r.country||'—')}</td>
        <td>${statusBadge(r.status)}</td>
        <td style="color:var(--text-3);font-size:0.78rem;">${escHtml(r.disc_reason||r.reason||'—')}</td>
    </tr>`).join('')
    : `<tr><td colspan="6" style="text-align:center;color:var(--text-3);padding:20px;">No course-level data yet — run verification first</td></tr>`;

    openDrilldown('dom-drilldown','dom-drilldown-title','dom-drilldown-tbody',
        `🔬 ${domainName} — Domain Deep-Dive`, rows);
}

// ── Category drill-down (credential doughnut click) ──────────────
function openAnalyticsDrilldownByCategory(catLabel) {
    const recent = globalData?.recent || [];
    const matches = recent.filter(r =>
        (r.category||r.level||r.type||'').toLowerCase().includes(catLabel.toLowerCase()) ||
        catLabel.toLowerCase().includes((r.category||r.level||r.type||'').toLowerCase())
    );
    alert(`Category "${catLabel}": ${matches.length} courses in live data.\nFilter via the All Courses tab for full details.`);
}

// ── Verification tab ─────────────────────────────────────────────
function populateVerificationTab(stats, recent) {
    // KPI row
    const kpiRow = document.getElementById('verif-kpi-row');
    if (kpiRow) {
        const tot  = stats.total||1;
        const verKpis = [
            { label:'Verified',     val: stats.verified||0,      pct: (stats.verified||0)/tot, color:'var(--green)' },
            { label:'Discrepancies',val: stats.discrepancies||0, pct: (stats.discrepancies||0)/tot, color:'var(--accent)' },
            { label:'Errors',       val: stats.errors||0,        pct: (stats.errors||0)/tot, color:'var(--red)' },
            { label:'Unverified',   val: stats.unverified||0,    pct: (stats.unverified||0)/tot, color:'var(--purple)' },
        ];
        kpiRow.innerHTML = verKpis.map(k => `
            <div class="verif-kpi-card" style="border-left:4px solid ${k.color};">
                <div style="font-size:1.8rem;font-weight:900;color:${k.color};">${k.val}</div>
                <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;color:var(--text-3);">${k.label}</div>
                <div style="margin-top:8px;height:4px;background:var(--bg-hover);border-radius:20px;overflow:hidden;">
                    <div style="height:4px;width:${(k.pct*100).toFixed(1)}%;background:${k.color};border-radius:20px;"></div>
                </div>
                <div style="font-size:0.72rem;color:var(--text-2);margin-top:4px;">${(k.pct*100).toFixed(1)}% of total</div>
            </div>`).join('');
    }

    // Status doughnut
    const ctx = document.getElementById('an-status-chart');
    if (ctx) {
        if (anStatusChart) anStatusChart.destroy();
        anStatusChart = new Chart(ctx, {
            type:'doughnut',
            data:{ labels:['Verified','Discrepancy','Error','Unverified'],
                   datasets:[{ data:[stats.verified||0, stats.discrepancies||0, stats.errors||0, stats.unverified||0],
                       backgroundColor:['#1dda9f','#f59e0b','#f43f5e','#6366f1'],
                       borderColor:'transparent', borderWidth:0, hoverOffset:10 }] },
            options:{ responsive:true, maintainAspectRatio:false, cutout:'68%',
                      plugins:{ legend:{display:false}, tooltip:{callbacks:{label:c=>`${c.label}: ${c.raw}`}} } }
        });
    }

    // Discrepancy reasons
    const reasons = {};
    recent.forEach(r => {
        if (r.disc_reason || r.reason) {
            const key = (r.disc_reason || r.reason || '').trim();
            if (key) reasons[key] = (reasons[key]||0)+1;
        }
    });
    const topReasons = Object.entries(reasons).sort((a,b)=>b[1]-a[1]).slice(0,8);
    const discEl = document.getElementById('an-disc-reasons');
    if (discEl) {
        discEl.innerHTML = topReasons.length ? topReasons.map(([reason,cnt]) => `
            <div class="disc-reason-row">
                <div class="disc-reason-text">${escHtml(reason)}</div>
                <div class="disc-reason-right">
                    <div class="disc-reason-bar-wrap">
                        <div class="disc-reason-bar" style="width:${Math.round(cnt/topReasons[0][1]*100)}%"></div>
                    </div>
                    <span class="disc-reason-count">${cnt}</span>
                </div>
            </div>`).join('')
        : `<div style="padding:32px;text-align:center;color:var(--text-3);">✅ No discrepancy reasons found — all clean!</div>`;
    }

    // Verification by country table
    const countrySt = {};
    recent.forEach(r => {
        const c = r.country || 'Unknown';
        if (!isValidCountry(c)) return;
        if (!countrySt[c]) countrySt[c] = {total:0,verified:0,discrepancy:0,error:0};
        countrySt[c].total++;
        const s = (r.status||'').toLowerCase();
        if (s==='verified') countrySt[c].verified++;
        else if (s==='discrepancy') countrySt[c].discrepancy++;
        else if (s==='error') countrySt[c].error++;
    });
    const vcTbody = document.getElementById('an-verif-country-tbody');
    if (vcTbody) {
        const vcEntries = Object.entries(countrySt).sort((a,b)=>b[1].total-a[1].total);
        vcTbody.innerHTML = vcEntries.length ? vcEntries.map(([country,st]) => {
            const rate = (st.verified/st.total*100).toFixed(0);
            const rateColor = rate>=80?'var(--green)':rate>=50?'var(--accent)':'var(--red)';
            return `<tr class="clickable-row" onclick="geoRowDrilldown('${country.replace(/'/g,"\\'")}', ${st.total})">
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
async function fetchAnalytics() {
    // Wait for dashboard data if not yet ready
    if (!globalData) {
        let waited = 0;
        await new Promise(resolve => {
            const poll = setInterval(() => {
                waited += 100;
                if (globalData || waited >= 6000) { clearInterval(poll); resolve(); }
            }, 100);
        });
    }

    // Always-available data from the dashboard
    const recent        = globalData?.recent         || [];
    const stats         = globalData?.stats          || {};
    const countryCounts = globalData?.country_counts || {};
    const domainCounts  = globalData?.domain_counts  || {};

    // Try supplementary analytics API (may be empty if no verification run)
    let d = { course_category:{}, pricing_category:{}, variant_category:{}, country_pivot:{}, domain_pivot:{} };
    try {
        const res  = await fetch('/api/analytics.json');
        const json = await res.json();
        if (json.status === 'success' && json.data) { d = analyticsData = json.data; }
    } catch(e) { console.warn('[Analytics] analytics.json not available, using dashboard data only'); }

    // Merge: prefer analytics data; fall back to globalData equivalents
    const effectiveCountryPivot = Object.keys(d.country_pivot||{}).length > 0
        ? d.country_pivot
        : Object.fromEntries(Object.entries(countryCounts).filter(([k])=>isValidCountry(k)));

    let effectiveDomainPivot = d.domain_pivot || {};
    if (Object.keys(effectiveDomainPivot).length === 0 && Object.keys(domainCounts).length > 0) {
        effectiveDomainPivot = {};
        Object.entries(domainCounts).forEach(([dom, total]) => {
            const dr  = recent.filter(r => (r.domain||'').toLowerCase().includes(dom.toLowerCase()));
            const ind = dr.filter(r => (r.country||'').toLowerCase().includes('india')).length || Math.round(total * 0.7);
            effectiveDomainPivot[dom] = { Total: total, Indian: ind, International: total - ind };
        });
    }

    const effectiveCourseCategory = Object.keys(d.course_category||{}).length > 0
        ? d.course_category : domainCounts;

    // Populate all sections
    populateAnalyticsKPIs(d, stats, countryCounts);
    populateInsightCards({ ...d, country_pivot: effectiveCountryPivot, domain_pivot: effectiveDomainPivot }, globalData);
    populateCredentialChart(effectiveCourseCategory);
    populatePricingChart(d.pricing_category);

    // India vs World - always from country_counts (truth)
    const realTotal  = stats.total || Object.values(countryCounts).reduce((s,v)=>s+v,0) || 1;
    const indiaTotal = Object.entries(countryCounts)
        .filter(([k]) => k.toLowerCase().includes('india'))
        .reduce((s,[,v]) => s+(Number(v)||0), 0);
    populateSplitVisual((indiaTotal / realTotal) * 100);

    populateAnTopCountries(effectiveCountryPivot);

    geoTableData = Object.entries(effectiveCountryPivot)
        .filter(([k])=>isValidCountry(k)).sort((a,b)=>b[1]-a[1]);
    renderGeoTable();

    populateDomainTab(effectiveDomainPivot);
    populateVerificationTab(stats, recent);

    console.log('[Analytics] OK - total:', realTotal, '| countries:', geoTableData.length, '| india:', indiaTotal);
}




// ================================================================
//  UPLOAD
// ================================================================
function initUpload() {
    const input = document.getElementById('pdf-upload-global');
    const label = document.getElementById('upload-label-global');
    if (!input) return;

    const isLocal = ['localhost','127.0.0.1'].includes(window.location.hostname);
    if (!isLocal && label) label.style.display = 'none';

    input.addEventListener('change', async () => {
        if (!input.files.length) return;
        if (!isLocal) { alert('Upload is only available on the local dashboard.'); input.value=''; return; }
        const orig = label.textContent;
        label.textContent = 'Uploading…';
        const fd = new FormData();
        for (const f of input.files) fd.append('files[]', f);
        try {
            const res    = await fetch('/api/upload', { method:'POST', body:fd });
            const result = await res.json();
            alert(result.status === 'success' ? `✓ ${result.message}` : `✗ ${result.message}`);
            if (result.status === 'success') { allCoursesData = []; fetchData(); }
        } catch(e) { alert('Upload failed.'); }
        finally { label.textContent = orig; input.value = ''; }
    });
}

// ================================================================
//  HELPERS
// ================================================================
function getBadgeClass(status) {
    switch ((status||'').toLowerCase()) {
        case 'verified':    return 'badge-verified';
        case 'error':       return 'badge-error';
        case 'discrepancy': return 'badge-discrepancy';
        default:            return 'badge-open';
    }
}

function escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ================================================================
//  INIT
// ================================================================
document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initCharts();
    initModal();
    initUpload();
    initAnalyticsSubTabs();

    // Chain: fetch dashboard data first, then analytics (analytics needs globalData)
    fetchData().then(() => fetchAnalytics());

    // Periodic refresh for dashboard data; analytics refreshes on tab click
    setInterval(fetchData, 8000);
});
