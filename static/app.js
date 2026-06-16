let statusChart;
let barChart;
let mapChart;
let lineChart;

let globalData = null;
let currentFilter = { type: null, value: null };
let countryDataList = [];

function initCharts() {
    Chart.defaults.color = '#6b7280';
    Chart.defaults.borderColor = '#e5e7eb';

    // 1. Line Chart (Country wise)
    const lineCtx = document.getElementById('countryLineChart').getContext('2d');
    lineChart = new Chart(lineCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Courses',
                data: [],
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.2)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });

    // 2. Status Pie Chart
    const pieCtx = document.getElementById('statusPieChart').getContext('2d');
    statusChart = new Chart(pieCtx, {
        type: 'doughnut',
        data: {
            labels: ['Verified', 'Discrepancies', 'Errors', 'Unverified'],
            datasets: [{
                data: [0, 0, 0, 0],
                backgroundColor: ['#10b981', '#f46a22', '#ef4444', '#4b5563'],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { position: 'bottom', labels: { usePointStyle: true, padding: 20 } }
            }
        }
    });

    // 3. Horizontal Bar Chart (Courses Count)
    const barCtx = document.getElementById('coursesBarChart').getContext('2d');
    barChart = new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Courses',
                data: [],
                backgroundColor: '#3b82f6',
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y', // Make it horizontal
            responsive: true,
            maintainAspectRatio: false,
            scales: { 
                x: { beginAtZero: true, ticks: { precision: 0 } },
                y: { ticks: { autoSkip: false } }
            },
            plugins: { legend: { display: false } },
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const idx = elements[0].index;
                    const label = barChart.data.labels[idx];
                    const toggleType = document.getElementById('bar-sort-toggle').value;
                    applyFilter(toggleType, label);
                }
            }
        }
    });

    // 4. Country Map Chart
    const mapCtx = document.getElementById('countryMapChart').getContext('2d');
    fetch('https://unpkg.com/world-atlas/countries-110m.json').then(r => r.json()).then(data => {
        let countries = ChartGeo.topojson.feature(data, data.objects.countries).features;
        // Filter out Antarctica to prevent the Mercator projection from zooming all the way out
        countries = countries.filter(d => d.properties.name !== 'Antarctica');
        mapChart = new Chart(mapCtx, {
            type: 'choropleth',
            data: {
                labels: countries.map(d => d.properties.name),
                datasets: [{
                    label: 'Courses',
                    data: countries.map(d => ({ feature: d, value: 0 })),
                    borderColor: '#9ca3af',
                    borderWidth: 0.5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                showOutline: false,
                showGraticule: false,
                layout: { padding: 0 },
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    projection: {
                        axis: 'x',
                        projection: 'equirectangular'
                    },
                    color: {
                        axis: 'x',
                        interpolate: 'oranges',
                        missing: '#f9fafb'
                    }
                }
            }
        });
    });

    // Toggle event listener
    document.getElementById('bar-sort-toggle').addEventListener('change', () => {
        updateBarChart();
    });

    document.getElementById('clear-filter').addEventListener('click', () => {
        applyFilter(null, null);
    });
}

function applyFilter(type, value) {
    currentFilter = { type, value };
    const badge = document.getElementById('active-filter-badge');
    if (value) {
        document.getElementById('filter-text').textContent = value;
        badge.classList.add('active');
    } else {
        badge.classList.remove('active');
    }
    
    // Re-render table
    if (globalData) {
        updateCourseDetailsTable(type, value);
    }
}

function updateCharts(data) {
    // Pie Chart
    statusChart.data.datasets[0].data = [
        data.stats.verified,
        data.stats.discrepancies,
        data.stats.errors,
        data.stats.unverified
    ];
    statusChart.update();

    // Store data globally to handle toggle
    globalData = data;
    updateBarChart();

    // Line Chart
    if (lineChart) {
        const sortedCountries = Object.entries(data.country_counts)
            .filter(x => x[0] !== 'Unknown' && x[0] !== 'Not Found / Mentioned on Website')
            .sort((a, b) => b[1] - a[1]);
            
        countryDataList = sortedCountries;
        
        lineChart.data.labels = sortedCountries.map(x => x[0]);
        lineChart.data.datasets[0].data = sortedCountries.map(x => x[1]);
        lineChart.update();
    }

    // Map Chart
    if (mapChart && mapChart.data.datasets[0].data.length > 0) {
        const dataset = mapChart.data.datasets[0].data;
        dataset.forEach(d => {
            const countryName = d.feature.properties.name;
            // Try to match exact or partial
            let val = 0;
            for (const [c, count] of Object.entries(data.country_counts)) {
                if (c.toLowerCase().includes(countryName.toLowerCase()) || countryName.toLowerCase().includes(c.toLowerCase())) {
                    val += count;
                }
            }
            d.value = val;
        });
        mapChart.update();
    }
}

function updateBarChart() {
    if (!globalData) return;
    const type = document.getElementById('bar-sort-toggle').value;
    const dataSource = type === 'domain' ? globalData.domain_counts : globalData.country_counts;
    
    // Sort and limit
    let entries = Object.entries(dataSource).sort((a, b) => b[1] - a[1]);
    
    if (type === 'country') {
        entries = entries.slice(0, 10);
    }
    
    const labels = entries.map(e => e[0]);
    const values = entries.map(e => e[1]);

    barChart.data.labels = labels;
    barChart.data.datasets[0].data = values;
    barChart.update();
}

function updateCards(stats) {
    document.getElementById('total-count').textContent = stats.total;
    document.getElementById('verified-count').textContent = stats.verified;
    document.getElementById('discrepancy-count').textContent = stats.discrepancies;
    document.getElementById('error-count').textContent = stats.errors + stats.unverified;
}

function getBadgeClass(status) {
    switch (status.toLowerCase()) {
        case 'verified': return 'badge-verified';
        case 'error': return 'badge-error';
        case 'discrepancy': return 'badge-discrepancy';
        default: return 'badge-open';
    }
}

function updateCourseDetailsTable(type, value) {
    const panel = document.getElementById('course-details-panel');
    const tbody = document.getElementById('course-details-body');
    const badge = document.getElementById('active-filter-badge');
    
    if (!type || !value || !globalData || !globalData.recent) {
        panel.style.display = 'none';
        badge.textContent = '';
        return;
    }

    panel.style.display = 'block';
    badge.textContent = `Filtered by ${type}: ${value}`;

    // Filter courses
    const filtered = globalData.recent.filter(c => {
        if (type === 'domain') return c.domain === value;
        if (type === 'country') return c.country === value;
        return true;
    });

    tbody.innerHTML = '';
    
    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">No courses found</td></tr>';
        return;
    }

    filtered.forEach(c => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${c.name}</strong></td>
            <td>${c.university}</td>
            <td><span class="badge badge-open">${c.domain}</span></td>
            <td>${c.country}</td>
            <td>${c.cost}</td>
            <td>${c.duration}</td>
            <td>${c.has_qs_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function fetchData() {
    try {
        const response = await fetch('/api/data.json');
        const data = await response.json();
        
        if (data.status === 'success') {
            updateCards(data.stats);
            updateCharts(data);
            
            // Show only discrepancies in the Verification tab as requested
            if (data.recent && data.recent.length > 0) {
                updateRecentVerifications(data.recent);
            } else if (data.discrepancy_list && data.discrepancy_list.length > 0) {
                const mapped = data.discrepancy_list.map((d, idx) => ({
                    id: (idx + 1).toString(),
                    name: d.name,
                    university: d.university,
                    status: 'Discrepancy',
                    disc_reason: d.reason,
                    pdf_page: null
                }));
                updateRecentVerifications(mapped);
            } else {
                updateRecentVerifications([]);
            }
            
            applyFilter(currentFilter.type, currentFilter.value); 
        }
    } catch (error) {
        console.error('Error fetching live data:', error);
    }
}

let recentVerificationsData = [];
let currentRecentPage = 1;
const RECENT_PAGE_SIZE = 30;
let lastRecentDataHash = '';

function updateRecentVerifications(recent) {
    if (!recent) return;
    
    const hash = JSON.stringify(recent);
    if (hash === lastRecentDataHash) return;
    lastRecentDataHash = hash;
    
    // Sort numerically by ID
    recentVerificationsData = [...recent].sort((a, b) => {
        return parseInt(a.id || '999999') - parseInt(b.id || '999999');
    });
    
    const totalPages = Math.ceil(recentVerificationsData.length / RECENT_PAGE_SIZE) || 1;
    if (currentRecentPage > totalPages) {
        currentRecentPage = totalPages;
    }
    renderRecentVerificationsPage();
}

function renderRecentVerificationsPage() {
    const tbody = document.getElementById('recent-verifications-body');
    const pageInfo = document.getElementById('recent-page-info');
    if (!tbody) return;
    tbody.innerHTML = '';
    
    if (recentVerificationsData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;">No verifications yet. Upload PDFs to verify.</td></tr>';
        if (pageInfo) pageInfo.textContent = 'Page 1 of 1 (0 verifications)';
        return;
    }
    
    const start = (currentRecentPage - 1) * RECENT_PAGE_SIZE;
    const end = start + RECENT_PAGE_SIZE;
    const paginated = recentVerificationsData.slice(start, end);
    
    paginated.forEach(c => {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.onclick = () => showCourseModal(c.id, c.name, c.university);
        tr.innerHTML = `
            <td><strong>${c.name}</strong></td>
            <td>${c.university}</td>
            <td><span class="badge ${getBadgeClass(c.status)}">${c.status}</span></td>
            <td>${c.disc_reason || '-'}</td>
            <td>${c.pdf_page ? c.pdf_page : '-'}</td>
        `;
        tbody.appendChild(tr);
    });
    
    const totalPages = Math.ceil(recentVerificationsData.length / RECENT_PAGE_SIZE) || 1;
    if (pageInfo) {
        pageInfo.textContent = `Page ${currentRecentPage} of ${totalPages} (${recentVerificationsData.length} verifications)`;
    }
}

document.getElementById('recent-prev-page')?.addEventListener('click', () => {
    if (currentRecentPage > 1) {
        currentRecentPage--;
        renderRecentVerificationsPage();
    }
});

document.getElementById('recent-next-page')?.addEventListener('click', () => {
    const totalPages = Math.ceil(recentVerificationsData.length / RECENT_PAGE_SIZE) || 1;
    if (currentRecentPage < totalPages) {
        currentRecentPage++;
        renderRecentVerificationsPage();
    }
});

// ---------------- TAB LOGIC ----------------

    // ---------------- INIT ----------------
    
    // Hide upload button if not on localhost
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
        const uploadBtn = document.getElementById('upload-label-global');
        if (uploadBtn) uploadBtn.style.display = 'none';
    }

function initTabs() {
    const links = document.querySelectorAll('#nav-tabs a');
    const contents = document.querySelectorAll('.tab-content');
    
    links.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Remove active from all
            links.forEach(l => l.parentElement.classList.remove('active'));
            contents.forEach(c => c.classList.remove('active'));
            
            // Add active to current
            link.parentElement.classList.add('active');
            const targetId = link.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
            
            if (targetId === 'tab-dashboard') {
                document.getElementById('header-text').style.visibility = 'visible';
            } else {
                document.getElementById('header-text').style.visibility = 'hidden';
            }
            
            if (targetId === 'tab-courses') {
                loadAllCourses();
            }
        });
    });
}

// ---------------- UPLOAD LOGIC ----------------

function initUpload() {
    const input = document.getElementById('pdf-upload-global');
    const label = document.getElementById('upload-label-global');
    
    if (!input) return;
    
    input.addEventListener('change', async () => {
        if (input.files.length === 0) return;
        
        if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
            alert('Upload feature is only available on the local dashboard. Please run "python dashboard.py" on your machine to upload PDFs.');
            input.value = '';
            return;
        }
        
        const originalText = label.textContent;
        label.textContent = 'Processing...';
        
        const formData = new FormData();
        for (let i = 0; i < input.files.length; i++) {
            formData.append('files[]', input.files[i]);
        }
        
        try {
            const res = await fetch('/api/upload', {
                method: 'POST',
                body: formData
            });
            const result = await res.json();
            
            if (result.status === 'success') {
                alert(`Success: ${result.message}`);
                
                // Reset cache to force reload of courses tab data
                allCoursesData = [];
                if (document.getElementById('tab-courses').classList.contains('active')) {
                    loadAllCourses();
                }
                fetchData(); // instantly refresh dashboard
            } else {
                alert(`Error: ${result.message}`);
        }
    } catch (e) {
        if (!e.message.includes('fetch')) {
            alert(`Error uploading files: ${e.message}`);
        } else {
            alert('Upload feature is only available on the local version of the dashboard. Please use localhost:5000 to upload PDFs.');
        }
    } finally {
        label.textContent = originalText;
        input.value = ''; // reset
    }
    });
}

// ---------------- COURSES LOGIC ----------------
let allCoursesData = [];
let currentPage = 1;
const PAGE_SIZE = 100;

async function loadAllCourses() {
    if (allCoursesData.length > 0) {
        renderCoursesPage();
        return; 
    }
    
    const tbody = document.getElementById('all-courses-body');
    if (tbody) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;">Loading all courses, please wait...</td></tr>';
    }
    
    try {
        const res = await fetch('/api/courses.json');
        const data = await res.json();
        allCoursesData = data.courses || [];
        allCoursesData.sort((a, b) => parseInt(a.id || '999999') - parseInt(b.id || '999999'));
        renderCoursesPage();
    } catch (e) {
        console.error(e);
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;color:red;">Error loading courses</td></tr>';
        }
    }
}

function renderCoursesPage() {
    const tbody = document.getElementById('all-courses-body');
    const pageInfo = document.getElementById('page-info');
    if (!tbody) return;
    
    tbody.innerHTML = '';
    
    const start = (currentPage - 1) * PAGE_SIZE;
    const end = start + PAGE_SIZE;
    const paginated = allCoursesData.slice(start, end);
    
    paginated.forEach(c => {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.onclick = () => showCourseModal(c.id);
        tr.innerHTML = `
            <td>${c.id}</td>
            <td><strong>${c.name}</strong></td>
            <td>${c.university}</td>
            <td>${c.domain}</td>
            <td>${c.country}</td>
            <td>${c.has_qs_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td>${c.has_nirf_badge ? '<span class="badge badge-verified">Yes</span>' : '<span class="badge badge-error">No</span>'}</td>
            <td><span class="badge ${getBadgeClass(c.status)}">${c.status}</span></td>
        `;
        tbody.appendChild(tr);
    });
    
    const totalPages = Math.ceil(allCoursesData.length / PAGE_SIZE);
    pageInfo.textContent = `Page ${currentPage} of ${totalPages} (${allCoursesData.length} courses)`;
}

document.getElementById('prev-page')?.addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        renderCoursesPage();
    }
});

document.getElementById('next-page')?.addEventListener('click', () => {
    const totalPages = Math.ceil(allCoursesData.length / PAGE_SIZE);
    if (currentPage < totalPages) {
        currentPage++;
        renderCoursesPage();
    }
});

// ---------------- INITIALIZATION ----------------
// ---------------- MODAL LOGIC ----------------

async function showCourseModal(courseId, fallbackName = null, fallbackUniversity = null) {
    if (allCoursesData.length === 0) {
        try {
            const res = await fetch('/api/courses.json');
            const data = await res.json();
            allCoursesData = data.courses || [];
        } catch (e) {
            console.error(e);
            return;
        }
    }

    let c = allCoursesData.find(x => String(x.id) === String(courseId));
    if (!c && fallbackName) {
        c = allCoursesData.find(x => x.name === fallbackName && x.university === fallbackUniversity);
    }

    if (!c) {
        alert("Course details not found.");
        return;
    }

    document.getElementById('modal-course-title').textContent = c.name;
    
    const deleteBtn = document.getElementById('delete-course-btn');
    if (deleteBtn) {
        deleteBtn.onclick = () => {
            alert("Deleting courses from the online viewer is disabled. Please delete from the local dashboard.");
        };
    }

    const tbody = document.getElementById('modal-table-body');
    tbody.innerHTML = '';
    
    let tableData = c.pdf_table;
    if (!tableData) {
        // Construct from c data dynamically if no pdf_table exists from session
        const safe_val = (v) => v ? String(v) : 'Not Provided';
        const has_qs = c.has_qs_badge;
        const has_nirf = c.has_nirf_badge;
        const has_free = c.has_free_box;
        
        const web_is_free = c.web_cost && c.web_cost.toLowerCase().includes('free');
        
        tableData = [
            { attribute: 'Cost', original: safe_val(c.cost), verified: safe_val(c.web_cost), status: c.cost_match ? 'MATCH' : 'FALSE' },
            { attribute: 'Duration', original: safe_val(c.duration), verified: safe_val(c.web_duration), status: c.duration_match ? 'MATCH' : 'FALSE' },
            { attribute: 'Mode', original: safe_val(c.mode), verified: safe_val(c.web_mode), status: c.mode_match ? 'MATCH' : 'FALSE' },
            { attribute: 'Language', original: safe_val(c.language), verified: safe_val(c.web_language), status: c.lang_match ? 'MATCH' : 'FALSE' },
            { attribute: 'Country', original: safe_val(c.country), verified: safe_val(c.country_verified || c.web_country || 'Not Found'), status: c.country_match ? 'MATCH' : 'FALSE' },
            { attribute: 'University', original: safe_val(c.university || c.uni), verified: safe_val(c.web_uni), status: c.uni_match ? 'MATCH' : 'FALSE' },
            { attribute: 'Skills', original: safe_val(c.skills), verified: safe_val(c.skills_verified), status: c.sk_match ? 'MATCH' : 'FALSE' },
            { attribute: 'QS Ranked', original: has_qs ? 'True (Badge Present)' : 'False', verified: safe_val(c.qs_detail), status: (c.qs_ranked || !has_qs) ? 'MATCH' : 'FALSE' },
            { attribute: 'NIRF Ranked', original: has_nirf ? 'True (Badge Present)' : 'False', verified: safe_val(c.nirf_detail), status: (c.nirf_ranked || !has_nirf) ? 'MATCH' : 'FALSE' },
            { attribute: 'Free Box', original: has_free ? 'True' : 'False', verified: web_is_free ? 'Free' : 'Paid', status: (has_free == web_is_free) ? 'MATCH' : 'FALSE' }
        ];
    }
    
    tableData.forEach(row => {
        const tr = document.createElement('tr');
        tr.style.borderBottom = '1px solid var(--border-color)';
        const statusColor = row.status === 'MATCH' ? 'var(--color-green)' : 'var(--color-red)';
        tr.innerHTML = `
            <td style="padding: 12px; color: var(--text-main);"><strong>${row.attribute}</strong></td>
            <td style="padding: 12px; color: var(--text-secondary);">${row.original}</td>
            <td style="padding: 12px; color: var(--text-secondary);">${row.verified}</td>
            <td style="padding: 12px; color: ${statusColor}; font-weight: bold; text-align: center;">${row.status}</td>
        `;
        tbody.appendChild(tr);
    });
    
    document.getElementById('course-modal').style.display = 'flex';
}

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    initTabs();
    initUpload();
    
    const closeBtn = document.getElementById('close-modal');
    if(closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('course-modal').style.display = 'none';
        });
    }
    
    const modal = document.getElementById('course-modal');
    if(modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) modal.style.display = 'none';
        });
    }
    
    const countryHeading = document.getElementById('country-wise-heading');
    if (countryHeading) {
        countryHeading.addEventListener('click', () => {
            const chartDiv = document.getElementById('country-chart-container');
            const listDiv = document.getElementById('country-list-container');
            
            if (listDiv.style.display === 'none') {
                chartDiv.style.display = 'none';
                listDiv.style.display = 'block';
                listDiv.innerHTML = countryDataList.map(x => `<strong>${x[0]}</strong> - ${x[1]}`).join('<br>');
            } else {
                chartDiv.style.display = 'block';
                listDiv.style.display = 'none';
            }
        });
    }
    
    setTimeout(fetchData, 500); 
    setInterval(fetchData, 5000); // 5 sec interval for live updates
    setTimeout(fetchAnalytics, 1000); // Fetch analytics once
});

async function fetchAnalytics() {
    try {
        const response = await fetch('/api/analytics.json');
        const res = await response.json();
        if (res.status === 'success') {
            const data = res.data;
            
            // Render Course Category Table
            const ccBody = document.querySelector('#course-category-table tbody');
            if (ccBody) {
                ccBody.innerHTML = Object.entries(data.course_category).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
            }
            
            // Render Variant Category Table
            const vcBody = document.querySelector('#variant-category-table tbody');
            if (vcBody) {
                vcBody.innerHTML = Object.entries(data.variant_category).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
            }
            
            // Render Pricing Category Table
            const pcBody = document.querySelector('#pricing-category-table tbody');
            if (pcBody) {
                pcBody.innerHTML = Object.entries(data.pricing_category).map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
            }
            
            // Render Domain Pivot Table
            const domBody = document.querySelector('#domain-pivot-table tbody');
            if (domBody) {
                domBody.innerHTML = Object.entries(data.domain_pivot).map(([k, v]) => `
                    <tr>
                        <td>${k}</td>
                        <td>${v.Total}</td>
                        <td>${v.Indian}</td>
                        <td>${v.International}</td>
                    </tr>
                `).join('');
            }
            
            // Render Country Pivot Table
            const ctryBody = document.querySelector('#country-pivot-table tbody');
            if (ctryBody) {
                ctryBody.innerHTML = Object.entries(data.country_pivot)
                    .sort((a, b) => b[1] - a[1])
                    .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
            }
        }
    } catch (e) {
        console.error('Failed to fetch analytics:', e);
    }
}
