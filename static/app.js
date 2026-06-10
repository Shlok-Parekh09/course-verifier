let statusChart;

function initChart() {
    const ctx = document.getElementById('statusChart').getContext('2d');
    statusChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Verified', 'Discrepancies', 'Errors'],
            datasets: [{
                data: [0, 0, 0],
                backgroundColor: [
                    '#10b981', // green
                    '#f59e0b', // yellow/orange
                    '#ef4444'  // red
                ],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        usePointStyle: true,
                        padding: 20
                    }
                }
            }
        }
    });
}

function updateChart(stats) {
    statusChart.data.datasets[0].data = [
        stats.verified,
        stats.discrepancies,
        stats.errors
    ];
    statusChart.update();
}

function updateCards(stats) {
    document.getElementById('total-count').textContent = stats.total;
    document.getElementById('verified-count').textContent = stats.verified;
    document.getElementById('discrepancy-count').textContent = stats.discrepancies;
    document.getElementById('error-count').textContent = stats.errors;
    document.getElementById('missing-link-count').textContent = stats.missing_links;
}

function getBadgeClass(status) {
    switch (status.toLowerCase()) {
        case 'verified': return 'badge-verified';
        case 'error': return 'badge-error';
        case 'discrepancy': return 'badge-discrepancy';
        default: return 'badge-open';
    }
}

function updateRecentTable(recentList) {
    const tbody = document.querySelector('#recent-table tbody');
    tbody.innerHTML = '';
    
    recentList.forEach(course => {
        const tr = document.createElement('tr');
        
        const costMatch = course.cost_match ? 'Yes' : 'No';
        const durMatch = course.duration_match ? 'Yes' : 'No';
        
        tr.innerHTML = `
            <td>${course.index}</td>
            <td style="color: #f46a22; font-weight: 500;">${course.name.substring(0, 40)}${course.name.length > 40 ? '...' : ''}</td>
            <td>${course.university.substring(0, 30)}${course.university.length > 30 ? '...' : ''}</td>
            <td>${costMatch}</td>
            <td>${durMatch}</td>
            <td class="status-badge ${getBadgeClass(course.status)}">${course.status}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateDiscrepancyTable(discrepancyList) {
    const tbody = document.querySelector('#discrepancy-table tbody');
    tbody.innerHTML = '';
    
    discrepancyList.forEach(course => {
        const tr = document.createElement('tr');
        
        tr.innerHTML = `
            <td style="color: #ef4444; font-weight: 500;">${course.name.substring(0, 40)}${course.name.length > 40 ? '...' : ''}</td>
            <td>${course.university.substring(0, 30)}${course.university.length > 30 ? '...' : ''}</td>
            <td style="color: #4b5563;">${course.reason}</td>
        `;
        tbody.appendChild(tr);
    });
}

async function fetchData() {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        
        if (data.status === 'success') {
            updateCards(data.stats);
            updateChart(data.stats);
            updateRecentTable(data.recent);
            updateDiscrepancyTable(data.discrepancy_list);
        }
    } catch (error) {
        console.error('Error fetching live data:', error);
    }
}

// Initialize and start polling
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    fetchData(); // Initial fetch
    
    // Poll every 3 seconds for live updates
    setInterval(fetchData, 3000);
});
