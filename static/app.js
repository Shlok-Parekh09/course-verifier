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
                        borderColor: 'rgba(255,255,255,0.07)',
                        borderWidth: 0.5
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    showOutline: false, showGraticule: false,
                    layout: { padding: 0 },
                    plugins: { legend: { display: false },
                        tooltip: { callbacks: {
                            label: ctx => `${ctx.label}: ${ctx.raw.value || 0} courses`
                        }}
                    },
                    scales: {
                        projection: { axis: 'x', projection: 'equirectangular' },
                        color: { axis: 'x', interpolate: 'oranges', missing: 'rgba(255,255,255,0.04)' }
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

function updateLineChart(countryCounts) {
    if (!lineChart) return;
    const sorted = Object.entries(countryCounts || {})
        .filter(([k]) => k && k !== 'Unknown' && k !== 'Not Found / Mentioned on Website')
        .sort((a,b) => b[1]-a[1])
        .slice(0, 20);
    countryDataList = sorted;
    lineChart.data.labels               = sorted.map(x => x[0]);
    lineChart.data.datasets[0].data     = sorted.map(x => x[1]);
    lineChart.update();
}

function updateMapChart(countryCounts) {
    if (!mapChart || !mapChart.data?.datasets?.[0]?.data?.length) return;
    mapChart.data.datasets[0].data.forEach(d => {
        const name = d.feature.properties.name;
        let val = 0;
        for (const [c, cnt] of Object.entries(countryCounts || {})) {
            if (c.toLowerCase().includes(name.toLowerCase()) || name.toLowerCase().includes(c.toLowerCase())) {
                val += cnt;
            }
        }
        d.value = val;
    });
    mapChart.update();
}

function updateCountryLeaderboard(countryCounts, containerId = 'country-list') {
    const el = document.getElementById(containerId);
    if (!el) return;
    const entries = Object.entries(countryCounts || {})
        .filter(([k]) => k && k !== 'Unknown' && k !== 'Not Found / Mentioned on Website')
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
//  ANALYTICS TAB  —  Premium Implementation
// ================================================================
let anCredentialChart = null;
let anPricingChart    = null;
let anDomainChart     = null;
let analyticsData     = null;
let geoTableData      = [];

const PALETTE = ['#6366f1','#818cf8','#f43f5e','#1dda9f','#f59e0b','#06b6d4','#ec4899','#8b5cf6'];

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

function populateAnalyticsKPIs(d, globalStats) {
    const el = (id, v) => { const e = document.getElementById(id); if(e) e.textContent = v; };
    const catEntries    = Object.entries(d.course_category || {});
    const totalPrograms = catEntries.reduce((s,[,v]) => s + (Number(v)||0), 0);
    const indianPrograms = catEntries
        .filter(([k]) => k.toLowerCase().includes('indian'))
        .reduce((s,[,v]) => s + (Number(v)||0), 0);
    const intlPrograms  = totalPrograms - indianPrograms;
    const pricingCat    = d.pricing_category || {};
    const freeCount     = pricingCat['Free Courses'] || 0;
    const totalFree     = Object.values(pricingCat).reduce((s,v) => s+(Number(v)||0), 0);
    const tot = totalPrograms || globalStats?.total || 0;
    const ind = indianPrograms;
    el('an-total',       tot);
    el('an-indian',      ind);
    el('an-intl',        intlPrograms);
    el('an-free',        totalFree);
    el('an-variants-sub', `${Object.values(d.variant_category||{}).reduce((s,v)=>s+(Number(v)||0),0)} delivery variants`);
    el('an-indian-pct',  `${tot ? ((ind/tot)*100).toFixed(1) : '—'}% of total catalog`);
    el('an-free-sub',    `${freeCount} fully free certifications`);
}

function populateCredentialChart(courseCategory) {
    const ctx = document.getElementById('an-credential-chart');
    if (!ctx) return;
    const entries = Object.entries(courseCategory || {}).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    if (anCredentialChart) anCredentialChart.destroy();
    anCredentialChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: entries.map(e=>e[0]),
            datasets: [{ data: entries.map(e=>e[1]), backgroundColor: PALETTE,
                borderColor:'transparent', borderWidth:0, hoverOffset:10 }]
        },
        options: {
            responsive:true, maintainAspectRatio:false, cutout:'70%',
            plugins: { legend:{display:false}, tooltip:{callbacks:{label:ctx=>` ${ctx.label}: ${ctx.raw} programs`}} }
        }
    });
    const legend = document.getElementById('an-credential-legend');
    if (legend) legend.innerHTML = entries.map(([label,val],i)=>`
        <div class="an-legend-item">
            <div class="an-legend-dot" style="background:${PALETTE[i%PALETTE.length]}"></div>
            <div>
                <div class="an-legend-name">${escHtml(label)}</div>
                <div class="an-legend-val">${val} Courses</div>
            </div>
        </div>`).join('');
}

function populatePricingChart(pricingCategory) {
    const ctx = document.getElementById('an-pricing-chart');
    if (!ctx) return;
    const entries = Object.entries(pricingCategory||{}).filter(([,v])=>v>0).sort((a,b)=>b[1]-a[1]);
    if (anPricingChart) anPricingChart.destroy();
    anPricingChart = new Chart(ctx, {
        type:'bar',
        data:{labels:entries.map(e=>e[0]),datasets:[{label:'Courses',data:entries.map(e=>e[1]),
            backgroundColor:'rgba(241,107,107,0.8)',hoverBackgroundColor:'#f16b6b',borderRadius:8,borderSkipped:false}]},
        options:{responsive:true,maintainAspectRatio:false,
            plugins:{legend:{display:false}},
            scales:{
                x:{grid:{display:false},ticks:{font:{size:12,weight:'600'},maxRotation:30}},
                y:{beginAtZero:true,grid:{color:'rgba(255,255,255,0.04)'},ticks:{precision:0}}
            },animation:{duration:900,easing:'easeOutQuart'}}
    });
}

function populateAnTopCountries(countryPivot) {
    const el = document.getElementById('an-top-countries');
    if (!el) return;
    const entries = Object.entries(countryPivot||{}).filter(([k])=>k&&k!=='Unknown')
        .sort((a,b)=>b[1]-a[1]).slice(0,6);
    const max = entries[0]?.[1]||1;
    el.innerHTML = entries.map(([name,cnt],i)=>`
        <div class="an-hub-row">
            <div class="an-hub-rank">${i+1}</div>
            <div class="an-hub-name">${getFlag(name)} ${escHtml(name)}</div>
            <div class="an-hub-bar-wrap"><div class="an-hub-bar" style="width:${Math.round(cnt/max*100)}%"></div></div>
            <div class="an-hub-count">${cnt}</div>
        </div>`).join('');
}

function renderGeoTable(search='') {
    const tbody = document.getElementById('an-country-tbody');
    if (!tbody) return;
    const total = geoTableData.reduce((s,[,v])=>s+v,0)||1;
    const max   = geoTableData[0]?.[1]||1;
    const rows  = search ? geoTableData.filter(([k])=>k.toLowerCase().includes(search)) : geoTableData;
    tbody.innerHTML = rows.length===0
        ? `<tr><td colspan="5" style="text-align:center;color:var(--text-3);padding:24px;">No results</td></tr>`
        : rows.map(([name,cnt],i)=>`
            <tr>
                <td><span class="geo-rank">${(i+1).toString().padStart(2,'0')}</span></td>
                <td><span style="font-size:1.1rem;margin-right:8px;">${getFlag(name)}</span><strong>${escHtml(name)}</strong></td>
                <td style="text-align:center;"><span class="geo-volume-badge">${cnt} Courses</span></td>
                <td style="text-align:right;"><span class="geo-share">${((cnt/total)*100).toFixed(2)}%</span></td>
                <td><div class="geo-prog-wrap"><div class="geo-prog-bar" style="width:${Math.round(cnt/max*100)}%"></div></div></td>
            </tr>`).join('');
}

function populateDomainTab(domainPivot) {
    const ctx = document.getElementById('an-domain-chart');
    const entries = Object.entries(domainPivot||{}).filter(([k])=>k&&k!=='Total')
        .sort((a,b)=>(b[1].Total||0)-(a[1].Total||0));
    if (ctx) {
        if (anDomainChart) anDomainChart.destroy();
        anDomainChart = new Chart(ctx, {
            type:'bar',
            data:{labels:entries.map(([k])=>k),datasets:[{label:'Total Courses',
                data:entries.map(([,v])=>v.Total||0),backgroundColor:'rgba(99,102,241,0.75)',
                hoverBackgroundColor:'#6366f1',borderRadius:8,borderSkipped:false}]},
            options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},
                scales:{x:{grid:{display:false},ticks:{font:{size:11,weight:'600'},maxRotation:30}},
                    y:{beginAtZero:true,grid:{color:'rgba(255,255,255,0.04)'},ticks:{precision:0}}},
                animation:{duration:900,easing:'easeOutQuart'}}
        });
    }
    const tbody = document.getElementById('an-domain-tbody');
    if (tbody) tbody.innerHTML = entries.map(([name,v])=>{
        const total=v.Total||0,indian=v.Indian||0,intl=v.International||0;
        const ip=total?Math.round(indian/total*100):50;
        return `<tr>
            <td><div style="font-weight:800;color:var(--text-1);">${escHtml(name)}</div>
                <div style="font-size:0.7rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.06em;margin-top:2px;">Specialization</div></td>
            <td style="text-align:center;"><span class="dom-total">${total}</span></td>
            <td style="text-align:center;"><span class="dom-indian">${indian}</span></td>
            <td style="text-align:center;"><span class="dom-intl">${intl}</span></td>
            <td><div class="dom-mix-bar"><div class="dom-mix-in" style="flex:${ip}"></div>
                <div class="dom-mix-out" style="flex:${100-ip}"></div></div></td>
        </tr>`;
    }).join('');
}

async function fetchAnalytics() {
    try {
        const res  = await fetch('/api/analytics.json');
        const json = await res.json();
        if (json.status !== 'success') return;
        const d = analyticsData = json.data;
        populateAnalyticsKPIs(d, globalData?.stats);
        populateCredentialChart(d.course_category);
        populatePricingChart(d.pricing_category);
        geoTableData = Object.entries(d.country_pivot||{})
            .filter(([k])=>k&&k!=='Unknown').sort((a,b)=>b[1]-a[1]);
        renderGeoTable();
        populateAnTopCountries(d.country_pivot);
        populateDomainTab(d.domain_pivot);
    } catch(e) { console.error('Analytics fetch error:', e); }
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

    setTimeout(fetchData,      500);
    setTimeout(fetchAnalytics, 1200);
    setInterval(fetchData, 6000);
});
