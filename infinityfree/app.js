/* ================================================================
   COURSE VERIFIER · app.js
   All-in-one frontend: MongoDB Atlas Data API + Client-side logic
   ================================================================ */

'use strict';

// ── Domain Ranges (fixed by course ID) ───────────────────────────
const DOMAIN_RANGES = [
    { label: 'Free',                   min: 1,    max: 25   },
    { label: 'Free to Audit',          min: 26,   max: 48   },
    { label: 'High Value Low Cost',    min: 49,   max: 100  },
    { label: 'Foundational',           min: 101,  max: 601  },
    { label: 'Network Infrastructure', min: 602,  max: 1585 },
    { label: 'System & Endpoint',      min: 1586, max: 1890 },
    { label: 'Cyber Forensics',        min: 1891, max: 2634 },
    { label: 'Data & Application',     min: 2635, max: 2965 },
    { label: 'Legal & Ethical',        min: 2966, max: 3727 },
];

function getDomainLabel(id) {
    const n = parseInt(id, 10);
    if (isNaN(n)) return 'Uncategorised';
    for (const r of DOMAIN_RANGES) {
        if (n >= r.min && n <= r.max) return r.label;
    }
    return 'Uncategorised';
}

// ── State ─────────────────────────────────────────────────────────
let allCourses = [];           // All documents from MongoDB (loaded once)
let domainChart = null;
let statusChart = null;

let vfPage = 1;                // Verification tab pagination
let cfPage = 1;                // All Courses tab pagination
const PAGE_SIZE = 100;

let vfFilter = { search: '', status: 'issues', country: 'all', domain: 'all' };
let cfFilter = { search: '', status: 'all', country: 'all', domain: 'all', qs: 'any' };

let modalCourse = null;        // Currently open course in modal

// ── API Base URL (Cloudflare Worker) ─────────────────────────────
// TODO: Replace this with your actual deployed Cloudflare Worker URL
// Example: 'https://course-verifier-api.YOUR-NAME.workers.dev'
const API_BASE_URL = 'https://course-verifier-api.YOUR-NAME.workers.dev';

// ── API Fetchers (Cloudflare Worker) ─────────────────────────────

/**
 * Fetch ALL courses from the Vercel API.
 * Returns full sorted array.
 */
async function fetchAllCourses() {
    setLoaderSub('Fetching courses from database…');
    const res = await fetch(`${API_BASE_URL}/api/get_courses`);
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`API error ${res.status}: ${err}`);
    }
    const data = await res.json();
    const docs = data.documents || [];
    setLoaderSub(`Loaded ${docs.length} courses…`);
    return docs;
}

/**
 * Write an updated course back to MongoDB via Vercel API.
 */
async function mongoUpdateCourse(courseId, update) {
    const res = await fetch(`${API_BASE_URL}/api/solve_course`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: courseId, update: update })
    });
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`API error ${res.status}: ${err}`);
    }
    return res.json();
}

// ── Loader helpers ────────────────────────────────────────────────

function setLoaderSub(text) {
    const el = document.getElementById('loader-sub');
    if (el) el.textContent = text;
}

function setConnStatus(state) {
    const dot   = document.getElementById('conn-dot');
    const label = document.getElementById('conn-label');
    if (!dot || !label) return;
    dot.className = 'status-dot ' + state;
    label.textContent = state === 'connected' ? 'Connected'
                      : state === 'error'     ? 'Error'
                      : 'Connecting';
}

// ── INIT ──────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    initTabs();

    // Fetch data from Vercel API
    try {
        setConnStatus('connecting');
        allCourses = await fetchAllCourses();
        setConnStatus('connected');

        document.getElementById('loading-screen').style.display = 'none';
        document.getElementById('main-page').style.display      = 'block';

        // Populate dropdowns
        populateFilters();

        // Render everything
        renderDashboard();
        renderVerificationTab();
        renderCoursesTab();

        // Wire up filter events
        initFilters();
        initModal();
        initKpiClickThrough();

    } catch (err) {
        setConnStatus('error');
        setLoaderSub('Connection failed: ' + err.message);
        console.error('[MongoFetch]', err);
    }
});

// ── THEME ─────────────────────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem('cv_theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeIcon(saved);

    document.getElementById('theme-btn').addEventListener('click', () => {
        const cur = document.documentElement.getAttribute('data-theme');
        const next = cur === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('cv_theme', next);
        updateThemeIcon(next);
        // Re-render charts with new colours
        renderDashboard();
    });
}

function updateThemeIcon(theme) {
    const el = document.getElementById('theme-icon');
    if (el) el.textContent = theme === 'dark' ? '☀' : '🌙';
}

// ── TABS ──────────────────────────────────────────────────────────

function initTabs() {
    document.getElementById('nav-tabs').addEventListener('click', e => {
        const link = e.target.closest('.nav-tab');
        if (!link) return;
        e.preventDefault();
        const target = link.dataset.tab;
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
        link.classList.add('active');
        document.getElementById(target).classList.add('active');
    });
}

// ── POPULATE FILTER DROPDOWNS ─────────────────────────────────────

function populateFilters() {
    const countries = [...new Set(allCourses.map(c => c.country).filter(Boolean))].sort();
    const domains   = DOMAIN_RANGES.map(r => r.label);

    ['vf-country', 'cf-country'].forEach(id => {
        const sel = document.getElementById(id);
        countries.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c; opt.textContent = c;
            sel.appendChild(opt);
        });
    });

    ['vf-domain', 'cf-domain'].forEach(id => {
        const sel = document.getElementById(id);
        domains.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            sel.appendChild(opt);
        });
    });
}

// ── FILTER EVENTS ─────────────────────────────────────────────────

function initFilters() {
    let vfTimer, cfTimer;

    // Verification tab
    document.getElementById('vf-search').addEventListener('input', e => {
        clearTimeout(vfTimer);
        vfTimer = setTimeout(() => { vfFilter.search = e.target.value.toLowerCase(); vfPage = 1; renderVerificationTab(); }, 220);
    });
    document.getElementById('vf-status').addEventListener('change', e => { vfFilter.status = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-country').addEventListener('change', e => { vfFilter.country = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-domain').addEventListener('change', e => { vfFilter.domain = e.target.value; vfPage = 1; renderVerificationTab(); });
    document.getElementById('vf-reset').addEventListener('click', () => {
        vfFilter = { search: '', status: 'issues', country: 'all', domain: 'all' };
        document.getElementById('vf-search').value = '';
        document.getElementById('vf-status').value  = 'issues';
        document.getElementById('vf-country').value = 'all';
        document.getElementById('vf-domain').value  = 'all';
        vfPage = 1;
        renderVerificationTab();
    });

    // All Courses tab
    document.getElementById('cf-search').addEventListener('input', e => {
        clearTimeout(cfTimer);
        cfTimer = setTimeout(() => { cfFilter.search = e.target.value.toLowerCase(); cfPage = 1; renderCoursesTab(); }, 220);
    });
    document.getElementById('cf-status').addEventListener('change', e => { cfFilter.status = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-country').addEventListener('change', e => { cfFilter.country = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-domain').addEventListener('change', e => { cfFilter.domain = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-qs').addEventListener('change', e => { cfFilter.qs = e.target.value; cfPage = 1; renderCoursesTab(); });
    document.getElementById('cf-reset').addEventListener('click', () => {
        cfFilter = { search: '', status: 'all', country: 'all', domain: 'all', qs: 'any' };
        document.getElementById('cf-search').value  = '';
        document.getElementById('cf-status').value  = 'all';
        document.getElementById('cf-country').value = 'all';
        document.getElementById('cf-domain').value  = 'all';
        document.getElementById('cf-qs').value      = 'any';
        cfPage = 1;
        renderCoursesTab();
    });

    // Pagination
    document.getElementById('vf-prev').addEventListener('click', () => { if (vfPage > 1) { vfPage--; renderVerificationTab(); } });
    document.getElementById('vf-next').addEventListener('click', () => { vfPage++; renderVerificationTab(); });
    document.getElementById('cf-prev').addEventListener('click', () => { if (cfPage > 1) { cfPage--; renderCoursesTab(); } });
    document.getElementById('cf-next').addEventListener('click', () => { cfPage++; renderCoursesTab(); });
}

// ── KPI click-through to Verification tab ────────────────────────
function initKpiClickThrough() {
    document.getElementById('kpi-disc-card').addEventListener('click', () => {
        vfFilter.status = 'Discrepancy'; vfPage = 1;
        document.getElementById('vf-status').value = 'Discrepancy';
        document.querySelector('.nav-tab[data-tab="tab-verification"]').click();
    });
    document.getElementById('kpi-err-card').addEventListener('click', () => {
        vfFilter.status = 'Error'; vfPage = 1;
        document.getElementById('vf-status').value = 'Error';
        document.querySelector('.nav-tab[data-tab="tab-verification"]').click();
    });

    // KPI strip cards
    document.getElementById('vf-strip').addEventListener('click', e => {
        const card = e.target.closest('.kpi-strip-card');
        if (!card) return;
        document.querySelectorAll('.kpi-strip-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        const status = card.dataset.vfStatus;
        vfFilter.status = status; vfPage = 1;
        document.getElementById('vf-status').value = status;
        renderVerificationTab();
    });
}

// ── DASHBOARD ─────────────────────────────────────────────────────

function renderDashboard() {
    const total = allCourses.length;
    const verified = allCourses.filter(c => c.status === 'Verified').length;
    const disc     = allCourses.filter(c => c.status === 'Discrepancy').length;
    const err      = allCourses.filter(c => c.status === 'Error').length;
    const pct      = total ? Math.round((verified / total) * 100) : 0;

    setText('kpi-total',       total.toLocaleString());
    setText('kpi-verified',    verified.toLocaleString());
    setText('kpi-verified-pct', `${pct}% of total`);
    setText('kpi-disc',        disc.toLocaleString());
    setText('kpi-err',         err.toLocaleString());

    renderDomainChart();
    renderStatusDonut(verified, disc, err);
    renderCountryList();
}

function renderDomainChart() {
    const counts = {};
    DOMAIN_RANGES.forEach(r => { counts[r.label] = 0; });
    allCourses.forEach(c => {
        const lbl = getDomainLabel(c.id);
        counts[lbl] = (counts[lbl] || 0) + 1;
    });

    const labels = Object.keys(counts);
    const data   = Object.values(counts);
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const textCol = isDark ? '#94a3b8' : '#64748b';
    const gridCol = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

    const ctx = document.getElementById('domainBarChart').getContext('2d');
    if (domainChart) domainChart.destroy();

    domainChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                data,
                backgroundColor: 'rgba(99,102,241,0.6)',
                borderColor:     'rgba(99,102,241,1)',
                borderWidth: 1,
                borderRadius: 6,
                hoverBackgroundColor: 'rgba(99,102,241,0.85)',
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${ctx.raw.toLocaleString()} courses` } } },
            scales: {
                x: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol } },
                y: { ticks: { color: textCol, font: { size: 11 } }, grid: { color: gridCol }, beginAtZero: true },
            },
        },
    });
}

function renderStatusDonut(verified, disc, err) {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const textCol = isDark ? '#94a3b8' : '#64748b';
    const ctx = document.getElementById('statusDonut').getContext('2d');
    if (statusChart) statusChart.destroy();

    statusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Verified', 'Discrepancy', 'Error'],
            datasets: [{
                data: [verified, disc, err],
                backgroundColor: ['rgba(34,197,94,0.75)', 'rgba(245,158,11,0.75)', 'rgba(239,68,68,0.75)'],
                borderColor:     ['#22c55e', '#f59e0b', '#ef4444'],
                borderWidth: 2,
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            cutout: '68%',
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.raw.toLocaleString()}` } } },
        },
    });

    // Custom legend
    const legend = document.getElementById('donut-legend');
    const total  = verified + disc + err;
    legend.innerHTML = [
        { label: 'Verified',     color: '#22c55e', val: verified },
        { label: 'Discrepancy',  color: '#f59e0b', val: disc     },
        { label: 'Error',        color: '#ef4444', val: err      },
    ].map(i => `
        <div class="donut-legend-item">
            <div class="donut-dot" style="background:${i.color}"></div>
            ${i.label} — ${i.val.toLocaleString()} (${total ? Math.round((i.val/total)*100) : 0}%)
        </div>
    `).join('');
}

function renderCountryList() {
    const counts = {};
    allCourses.forEach(c => {
        if (c.country) counts[c.country] = (counts[c.country] || 0) + 1;
    });

    const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15);
    const max = sorted[0]?.[1] || 1;

    document.getElementById('country-list').innerHTML = sorted.map(([name, count], i) => `
        <div class="country-row">
            <div class="country-rank">${i + 1}</div>
            <div class="country-name" title="${escHtml(name)}">${escHtml(name)}</div>
            <div class="country-bar-wrap">
                <div class="country-bar" style="width:${Math.round((count / max) * 100)}%"></div>
            </div>
            <div class="country-count">${count}</div>
        </div>
    `).join('');
}

// ── VERIFICATION TAB ──────────────────────────────────────────────

function applyVfFilter(courses) {
    const { search, status, country, domain } = vfFilter;
    return courses.filter(c => {
        if (status === 'issues') { if (c.status === 'Verified') return false; }
        else if (status !== 'all') { if (c.status !== status) return false; }
        if (country !== 'all' && c.country !== country) return false;
        if (domain  !== 'all' && getDomainLabel(c.id) !== domain) return false;
        if (search) {
            const hay = `${c.name} ${c.university} ${c.country} ${c.disc_reason}`.toLowerCase();
            if (!hay.includes(search)) return false;
        }
        return true;
    });
}

function renderVerificationTab() {
    const filtered = applyVfFilter(allCourses);
    const total    = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (vfPage > totalPages) vfPage = totalPages;
    const slice = filtered.slice((vfPage - 1) * PAGE_SIZE, vfPage * PAGE_SIZE);

    // KPI strip
    setText('vfs-total', total.toLocaleString());
    setText('vfs-disc',  allCourses.filter(c => c.status === 'Discrepancy').length.toLocaleString());
    setText('vfs-err',   allCourses.filter(c => c.status === 'Error').length.toLocaleString());
    setText('vfs-ver',   allCourses.filter(c => c.status === 'Verified').length.toLocaleString());

    // Table
    const tbody = document.getElementById('vf-tbody');
    if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No courses match the current filters.</td></tr>';
    } else {
        tbody.innerHTML = slice.map((c, i) => `
            <tr onclick="openModal(${c.id})" title="Click to view details">
                <td>${(vfPage - 1) * PAGE_SIZE + i + 1}</td>
                <td title="${escHtml(c.name)}" style="max-width:260px;">${escHtml(c.name)}</td>
                <td title="${escHtml(c.university)}">${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${getDomainLabel(c.id)}</span></td>
                <td>${badgeHtml(c.status)}</td>
                <td style="font-size:0.78rem; color:var(--text-muted); max-width:200px; overflow:hidden; text-overflow:ellipsis;" title="${escHtml(c.disc_reason || c.issue_sub_type || '')}">${escHtml(c.disc_reason || c.issue_sub_type || '—')}</td>
            </tr>
        `).join('');
    }

    // Pagination
    setText('vf-pag-info', `Page ${vfPage} of ${totalPages} (${total.toLocaleString()} courses)`);
    document.getElementById('vf-prev').disabled = vfPage <= 1;
    document.getElementById('vf-next').disabled = vfPage >= totalPages;
}

// ── ALL COURSES TAB ───────────────────────────────────────────────

function applyCfFilter(courses) {
    const { search, status, country, domain, qs } = cfFilter;
    return courses.filter(c => {
        if (status !== 'all' && c.status !== status) return false;
        if (country !== 'all' && c.country !== country) return false;
        if (domain  !== 'all' && getDomainLabel(c.id) !== domain) return false;
        if (qs === 'yes' && !c.has_qs_badge) return false;
        if (qs === 'no'  &&  c.has_qs_badge) return false;
        if (search) {
            const hay = `${c.name} ${c.university} ${c.country} ${c.skills || ''}`.toLowerCase();
            if (!hay.includes(search)) return false;
        }
        return true;
    });
}

function renderCoursesTab() {
    const filtered   = applyCfFilter(allCourses);
    const total      = filtered.length;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    if (cfPage > totalPages) cfPage = totalPages;
    const slice = filtered.slice((cfPage - 1) * PAGE_SIZE, cfPage * PAGE_SIZE);

    const tbody = document.getElementById('cf-tbody');
    if (!slice.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No courses match the current filters.</td></tr>';
    } else {
        tbody.innerHTML = slice.map((c, i) => `
            <tr onclick="openModal(${c.id})" title="Click to view details">
                <td>${(cfPage - 1) * PAGE_SIZE + i + 1}</td>
                <td title="${escHtml(c.name)}">${escHtml(c.name)}</td>
                <td title="${escHtml(c.university)}">${escHtml(c.university || '—')}</td>
                <td>${escHtml(c.country || '—')}</td>
                <td><span style="font-size:0.78rem; color:var(--text-muted);">${getDomainLabel(c.id)}</span></td>
                <td>${c.has_qs_badge ? '<span class="badge" style="background:var(--blue-bg);color:var(--blue);border:1px solid rgba(59,130,246,0.25);">QS ✓</span>' : '—'}</td>
                <td>${badgeHtml(c.status)}</td>
            </tr>
        `).join('');
    }

    setText('cf-pag-info', `Page ${cfPage} of ${totalPages} (${total.toLocaleString()} courses)`);
    document.getElementById('cf-prev').disabled = cfPage <= 1;
    document.getElementById('cf-next').disabled = cfPage >= totalPages;
}

// ── MODAL ─────────────────────────────────────────────────────────

function initModal() {
    document.getElementById('modal-close').addEventListener('click', closeModal);
    document.getElementById('course-modal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
    document.getElementById('modal-solve-all').addEventListener('click', solveAll);
}

async function openModal(courseId) {
    const cBase = allCourses.find(x => x.id == courseId);
    if (!cBase) return;
    
    // Show loading state while fetching heavy details
    setText('modal-title', cBase.name || '—');
    setText('modal-sub', 'Fetching details from database...');
    document.getElementById('modal-meta').innerHTML = '';
    document.getElementById('modal-tbody').innerHTML = '<tr><td colspan="5" class="empty-state">Loading comparison data...</td></tr>';
    document.getElementById('course-modal').classList.add('open');

    // Fetch full course data (lazy load) from Vercel API
    try {
        const res = await fetch(`/api/get_course_details?id=${courseId}`);
        if (!res.ok) {
            const err = await res.text();
            throw new Error(`API error ${res.status}: ${err}`);
        }
        const data = await res.json();
        const c = data.document;
        if (!c) throw new Error('Course not found');
        modalCourse = c;

        setText('modal-sub',   `${c.university || '—'}  ·  ${c.country || '—'}  ·  Page ${c.pdf_page || '?'}`);

        // Badge
        const badge = document.getElementById('modal-badge');
        badge.className = 'badge badge-' + (c.status || '').toLowerCase();
        badge.textContent = c.status || '—';

        // Meta chips
        document.getElementById('modal-meta').innerHTML = [
            ['Cost',     c.cost],
            ['Duration', c.duration],
            ['Mode',     c.mode],
            ['Domain',   getDomainLabel(c.id)],
            ['QS',       c.has_qs_badge ? '✓ Ranked' : '—'],
            ['NIRF',     c.has_nirf_badge ? '✓ Ranked' : '—'],
        ].map(([k, v]) => `<div class="meta-chip"><strong>${k}:</strong> ${escHtml(String(v || '—'))}</div>`).join('');

        // Comparison table
        const rows     = c.pdf_table || [];
        const solved   = c.solved_attrs || [];
        const hasMismatch = rows.some(r => r.original !== r.verified);

        if (!rows.length) {
            document.getElementById('modal-tbody').innerHTML = '<tr><td colspan="5" class="empty-state">No comparison data available.</td></tr>';
        } else {
            document.getElementById('modal-tbody').innerHTML = rows.map(r => {
                const isSolved  = solved.includes(r.attribute?.toLowerCase());
                const isMismatch = r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified);
                const rowClass  = isSolved ? 'solved-row' : isMismatch ? 'mismatch-row' : '';
                const matchIcon = isMismatch
                    ? '<span class="match-icon match-no">✕</span>'
                    : '<span class="match-icon match-yes">✓</span>';
                const btn = isMismatch
                    ? `<button class="btn-solve ${isSolved ? 'solved' : ''}"
                           onclick="solveAttr(${c.id}, '${escJs(r.attribute)}', ${isSolved})"
                           title="${isSolved ? 'Undo resolve' : 'Mark as resolved'}">
                           ${isSolved ? '✓ Solved' : 'Solve'}
                       </button>`
                    : '<span style="color:var(--text-dim); font-size:0.78rem;">OK</span>';
                return `<tr class="${rowClass}">
                    <td>${escHtml(r.attribute || '—')}</td>
                    <td>${escHtml(r.original  || '—')}</td>
                    <td>${escHtml(r.verified  || '—')}</td>
                    <td>${matchIcon}</td>
                    <td>${btn}</td>
                </tr>`;
            }).join('');
        }

        // Hint + Solve All button
        const allSolved = rows.every(r => {
            const isMismatch = r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified);
            return !isMismatch || solved.includes(r.attribute?.toLowerCase());
        });
        document.getElementById('modal-hint').textContent = c.disc_reason || '';
        const solveAllBtn = document.getElementById('modal-solve-all');
        solveAllBtn.style.display = (hasMismatch && c.status !== 'Verified') ? 'inline-flex' : 'none';
        solveAllBtn.textContent   = allSolved ? '✓ All Resolved' : '✓ Mark All Resolved';

    } catch (err) {
        document.getElementById('modal-tbody').innerHTML = `<tr><td colspan="5" class="empty-state" style="color:var(--red)">Error loading details: ${err.message}</td></tr>`;
    }
}

function closeModal() {
    document.getElementById('course-modal').classList.remove('open');
    modalCourse = null;
}

// ── SOLVE ─────────────────────────────────────────────────────────

async function solveAttr(courseId, attr, isSolved) {
    const c = allCourses.find(x => x.id == courseId);
    if (!c) return;

    let solved = [...(c.solved_attrs || [])];
    const key  = attr.toLowerCase();

    if (isSolved) {
        // Undo: remove from solved list
        solved = solved.filter(s => s !== key);
    } else {
        // Solve: add to solved list
        if (!solved.includes(key)) solved.push(key);
    }

    // Determine new status: if all mismatched attrs are solved → Verified
    const rows = c.pdf_table || [];
    const mismatchAttrs = rows
        .filter(r => r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified))
        .map(r => r.attribute?.toLowerCase());
    const allSolved = mismatchAttrs.every(a => solved.includes(a));

    const newStatus   = allSolved ? 'Verified'    : c.status;
    const newCategory = allSolved ? 'verified'    : c.issue_category;

    const update = {
        solved_attrs:   solved,
        status:         newStatus,
        issue_category: newCategory,
    };

    // Optimistic local update
    Object.assign(c, update);

    try {
        await mongoUpdateCourse(courseId, update);
        // Re-open modal to reflect new state
        openModal(courseId);
        // Refresh tab counts
        renderVerificationTab();
        renderCoursesTab();
        // Refresh dashboard KPIs
        const verified = allCourses.filter(x => x.status === 'Verified').length;
        const disc     = allCourses.filter(x => x.status === 'Discrepancy').length;
        const err      = allCourses.filter(x => x.status === 'Error').length;
        const total    = allCourses.length;
        setText('kpi-verified', verified.toLocaleString());
        setText('kpi-verified-pct', `${Math.round((verified/total)*100)}% of total`);
        setText('kpi-disc', disc.toLocaleString());
        setText('kpi-err',  err.toLocaleString());
        renderStatusDonut(verified, disc, err);
    } catch (err) {
        // Revert optimistic update on failure
        Object.assign(c, { solved_attrs: c.solved_attrs, status: c.status });
        alert('Failed to save: ' + err.message);
    }
}

async function solveAll() {
    if (!modalCourse) return;
    const c    = modalCourse;
    const rows = c.pdf_table || [];
    const solved = rows.map(r => r.attribute?.toLowerCase()).filter(Boolean);

    const update = {
        solved_attrs:   solved,
        status:         'Verified',
        issue_category: 'verified',
    };
    Object.assign(c, update);

    try {
        await mongoUpdateCourse(c.id, update);
        openModal(c.id);
        renderVerificationTab();
        renderCoursesTab();
    } catch (err) {
        alert('Failed to save: ' + err.message);
    }
}

// ── HELPERS ───────────────────────────────────────────────────────

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function escHtml(str) {
    return String(str || '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escJs(str) {
    return String(str || '').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function badgeHtml(status) {
    const cls = {
        Verified:    'badge-verified',
        Discrepancy: 'badge-discrepancy',
        Error:       'badge-error',
    }[status] || 'badge-error';
    return `<span class="badge ${cls}">${escHtml(status || '—')}</span>`;
}
