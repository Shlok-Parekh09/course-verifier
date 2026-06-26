import re

filepath = r"d:\Users\Shlok Parekh\Downloads\Course-Verifier-3.0\infinityfree\app.js"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. State additions
state_add = """let modalCourse = null;        // Currently open course in modal

// ── Custom State ───────────────────────────────────────────────────
let sfPage = 1;
let sfFilter = { search: '' };
let sortState = {
    vf: { col: 'id', dir: 1 },
    cf: { col: 'id', dir: 1 },
    sf: { col: 'id', dir: 1 }
};

function getOriginalStatus(c) {
    if (c.pdf_table && c.pdf_table.some(r => r.status && r.status.toUpperCase() !== 'MATCH')) return 'Discrepancy';
    if (c.disc_reason && (c.disc_reason.includes('404') || c.disc_reason.toLowerCase().includes('website') || c.disc_reason.toLowerCase().includes('not found'))) return 'Error';
    if (c.disc_reason) return 'Discrepancy';
    return 'Verified';
}

function getOriginalCategory(c) {
    const s = getOriginalStatus(c);
    if (s === 'Error') return 'website_issue';
    if (s === 'Discrepancy') return 'mismatch';
    return 'verified';
}

function sortCourses(list, state) {
    return list.sort((a, b) => {
        let vA = a[state.col];
        let vB = b[state.col];
        
        if (state.col === 'domain') {
            vA = getDomainLabel(a.id);
            vB = getDomainLabel(b.id);
        } else if (state.col === 'name') {
            vA = (vA || '').toLowerCase();
            vB = (vB || '').toLowerCase();
        }
        
        if (typeof vA === 'string' && typeof vB === 'string') {
            return vA.localeCompare(vB) * state.dir;
        }
        if (vA < vB) return -1 * state.dir;
        if (vA > vB) return 1 * state.dir;
        return 0;
    });
}
"""
content = content.replace("let modalCourse = null;        // Currently open course in modal\n", state_add)


# 2. Add initSorting call in DOMContentLoaded
content = content.replace("initKpiClickThrough();", "initKpiClickThrough();\n        initSorting();")


# 3. Add initSorting function
init_sorting_func = """function initSorting() {
    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const tableId = th.closest('tbody') ? th.closest('tbody').id : th.closest('table').querySelector('tbody').id;
            const prefix = tableId.split('-')[0]; // vf, cf, sf
            const col = th.dataset.sort;
            if (sortState[prefix].col === col) {
                sortState[prefix].dir *= -1; // toggle
            } else {
                sortState[prefix].col = col;
                sortState[prefix].dir = 1;
            }
            // update UI arrows
            th.closest('tr').querySelectorAll('th.sortable').forEach(t => {
                t.textContent = t.textContent.replace(' ↑', ' ↕').replace(' ↓', ' ↕');
            });
            th.textContent = th.textContent.replace(' ↕', sortState[prefix].dir === 1 ? ' ↑' : ' ↓');
            
            if (prefix === 'vf') renderVerificationTab();
            if (prefix === 'cf') renderCoursesTab();
            if (prefix === 'sf') renderSolvedTab();
        });
    });
}
"""
content = content.replace("// ── POPULATE FILTER DROPDOWNS ─────────────────────────────────────", init_sorting_func + "\n// ── POPULATE FILTER DROPDOWNS ─────────────────────────────────────")


# 4. Filter binding for Solved Tab
filter_binds = """    document.getElementById('cf-next').addEventListener('click', () => { cfPage++; renderCoursesTab(); });

    // Solved Courses Tab
    document.getElementById('sf-search').addEventListener('input', e => {
        clearTimeout(cfTimer);
        cfTimer = setTimeout(() => { sfFilter.search = e.target.value.toLowerCase(); sfPage = 1; renderSolvedTab(); }, 220);
    });
    document.getElementById('sf-reset').addEventListener('click', () => {
        document.getElementById('sf-search').value = '';
        sfFilter = { search: '' };
        sfPage = 1;
        renderSolvedTab();
    });
    document.getElementById('sf-prev').addEventListener('click', () => { if (sfPage > 1) { sfPage--; renderSolvedTab(); } });
    document.getElementById('sf-next').addEventListener('click', () => { sfPage++; renderSolvedTab(); });
"""
content = content.replace("    document.getElementById('cf-next').addEventListener('click', () => { cfPage++; renderCoursesTab(); });\n", filter_binds)


# 5. renderVerificationTab sorting and Mode column
rvt_orig = """    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('vf-tbody');
    tbody.innerHTML = '';
    
    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No courses match the current filters</td></tr>`;
        return;
    }

    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);
        
        let statBadge = '';"""
        
rvt_new = """    filtered = sortCourses(filtered, sortState.vf);
    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('vf-tbody');
    tbody.innerHTML = '';
    
    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No courses match the current filters</td></tr>`;
        return;
    }

    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);
        
        let statBadge = '';"""
content = content.replace(rvt_orig, rvt_new)

rvt_tr = """        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td>${statBadge}</td>
            <td class="td-issue">${escHtml(c.disc_reason || '—')}</td>
        `;"""
rvt_tr_new = """        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td>${escHtml(c.mode || '—')}</td>
            <td>${statBadge}</td>
            <td class="td-issue">${escHtml(c.disc_reason || '—')}</td>
        `;"""
content = content.replace(rvt_tr, rvt_tr_new)


# 6. renderCoursesTab sorting and Mode column
rct_orig = """    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('cf-tbody');
    tbody.innerHTML = '';

    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No courses match the current filters</td></tr>`;
        return;
    }

    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);"""
        
rct_new = """    filtered = sortCourses(filtered, sortState.cf);
    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('cf-tbody');
    tbody.innerHTML = '';

    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No courses match the current filters</td></tr>`;
        return;
    }

    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);"""
content = content.replace(rct_orig, rct_new)

rct_tr = """        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td>${qsBadge}</td>
            <td>${statBadge}</td>
        `;"""
        
rct_tr_new = """        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td>${escHtml(c.mode || '—')}</td>
            <td>${qsBadge}</td>
            <td>${statBadge}</td>
        `;"""
content = content.replace(rct_tr, rct_tr_new)


# 7. Add renderSolvedTab function
render_solved_func = """function renderSolvedTab() {
    let filtered = allCourses.filter(c => c.solved_attrs && c.solved_attrs.length > 0);
    
    if (sfFilter.search) {
        const q = sfFilter.search;
        filtered = filtered.filter(c => 
            (c.name || '').toLowerCase().includes(q) ||
            (c.university || '').toLowerCase().includes(q) ||
            (c.country || '').toLowerCase().includes(q)
        );
    }
    
    const total = filtered.length;
    const totalPages = Math.ceil(total / PAGE_SIZE) || 1;
    if (sfPage > totalPages) sfPage = totalPages;
    
    document.getElementById('sf-pag-info').textContent = `Page ${sfPage} of ${totalPages} (${total} total)`;
    document.getElementById('sf-prev').disabled = sfPage === 1;
    document.getElementById('sf-next').disabled = sfPage === totalPages;
    
    filtered = sortCourses(filtered, sortState.sf);
    
    const start = (sfPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;
    const pageData = filtered.slice(start, end);
    const tbody = document.getElementById('sf-tbody');
    tbody.innerHTML = '';
    
    if (pageData.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No solved courses yet!</td></tr>`;
        return;
    }
    
    pageData.forEach(c => {
        const domLabel = getDomainLabel(c.id);
        const tr = document.createElement('tr');
        tr.onclick = () => openModal(c.id);
        
        let statBadge = '';
        if (c.status === 'Verified') statBadge = `<span class="badge-status status-ver">Verified</span>`;
        else if (c.status === 'Discrepancy') statBadge = `<span class="badge-status status-disc">Discrepancy</span>`;
        else if (c.status === 'Error') statBadge = `<span class="badge-status status-err">Error</span>`;
        else statBadge = `<span class="badge-status">${c.status || '—'}</span>`;
        
        tr.innerHTML = `
            <td style="color:var(--text-dim); font-size:0.8rem;">${c.id}</td>
            <td class="td-name">${escHtml(c.name)}</td>
            <td>${escHtml(c.university)}</td>
            <td>${escHtml(c.country || '—')}</td>
            <td><span class="badge-domain">${domLabel}</span></td>
            <td>${escHtml(c.mode || '—')}</td>
            <td>${statBadge}</td>
        `;
        tbody.appendChild(tr);
    });
}
"""
content = content.replace("function renderCoursesTab() {", render_solved_func + "\nfunction renderCoursesTab() {")
content = content.replace("        renderCoursesTab();", "        renderCoursesTab();\n        renderSolvedTab();")

# 8. Unsolve fix in solveAttr
solve_attr_orig = """    const newStatus = allSolved ? 'Verified' : c.status;
    const newCategory = allSolved ? 'verified' : c.issue_category;"""
    
solve_attr_new = """    const newStatus = allSolved ? 'Verified' : getOriginalStatus(c);
    const newCategory = allSolved ? 'verified' : getOriginalCategory(c);"""
content = content.replace(solve_attr_orig, solve_attr_new)

content = content.replace("        renderCoursesTab();\n        renderSolvedTab();\n        renderSolvedTab();", "        renderCoursesTab();\n        renderSolvedTab();")

# 9. Solve All / Unsolve All logic and button text
solve_all_orig = """async function solveAll() {
    if (!modalCourse) return;
    const c = modalCourse;
    const rows = c.pdf_table || [];
    const solved = rows.map(r => r.attribute?.toLowerCase()).filter(Boolean);

    const update = {
        solved_attrs: solved,
        status: 'Verified',
        issue_category: 'verified',
    };
    Object.assign(c, update);"""
    
solve_all_new = """async function solveAll() {
    if (!modalCourse) return;
    const c = modalCourse;
    const rows = c.pdf_table || [];
    
    const mismatchAttrs = rows
        .filter(r => r.status ? (r.status.toUpperCase() !== 'MATCH') : (r.original !== r.verified))
        .map(r => r.attribute?.toLowerCase()).filter(Boolean);
        
    const curSolved = c.solved_attrs || [];
    const allSolved = mismatchAttrs.every(a => curSolved.includes(a));
    
    let update;
    if (allSolved) {
        // Unsolve all! Restore original state
        update = {
            solved_attrs: [],
            status: getOriginalStatus(c),
            issue_category: getOriginalCategory(c),
        };
    } else {
        // Solve all
        update = {
            solved_attrs: mismatchAttrs,
            status: 'Verified',
            issue_category: 'verified',
        };
    }
    Object.assign(c, update);"""
content = content.replace(solve_all_orig, solve_all_new)

# 10. Hide solve all button correctly and update text
solve_all_btn_orig = """        const solveAllBtn = document.getElementById('modal-solve-all');
        solveAllBtn.style.display = (hasMismatch && c.status !== 'Verified') ? 'inline-flex' : 'none';
        solveAllBtn.textContent = allSolved ? '✓ All Resolved' : '✓ Mark All Resolved';"""
        
solve_all_btn_new = """        const solveAllBtn = document.getElementById('modal-solve-all');
        solveAllBtn.style.display = hasMismatch ? 'inline-flex' : 'none';
        if (allSolved) {
            solveAllBtn.textContent = '✗ Unsolve All';
            solveAllBtn.style.background = '#333';
            solveAllBtn.style.color = '#ccc';
        } else {
            solveAllBtn.textContent = '✓ Mark All Resolved';
            solveAllBtn.style.background = 'var(--primary)';
            solveAllBtn.style.color = 'var(--bg)';
        }"""
content = content.replace(solve_all_btn_orig, solve_all_btn_new)


with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated app.js successfully!")
