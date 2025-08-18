// Dashboard JavaScript for real-time updates

const socket = io();

// Data storage
let instances = {};
let hashrateHistory = [];
const MAX_HISTORY_POINTS = 50;

// Chart instances
let hashrateChart;
let distributionChart;

// Initialize charts
function initCharts() {
    // Hashrate over time chart
    const hashrateCtx = document.getElementById('hashrate-chart').getContext('2d');
    hashrateChart = new Chart(hashrateCtx, {
        type: 'line',
        data: {
            datasets: [{
                label: 'Total Hashrate',
                data: [],
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        tooltipFormat: 'HH:mm:ss',
                        displayFormats: {
                            second: 'HH:mm:ss'
                        }
                    },
                    grid: {
                        color: 'rgba(156, 163, 175, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(156, 163, 175, 0.8)'
                    }
                },
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(156, 163, 175, 0.1)'
                    },
                    ticks: {
                        color: 'rgba(156, 163, 175, 0.8)',
                        callback: function(value) {
                            return formatHashrate(value);
                        }
                    }
                }
            }
        }
    });

    // Instance distribution chart
    const distributionCtx = document.getElementById('distribution-chart').getContext('2d');
    distributionChart = new Chart(distributionCtx, {
        type: 'doughnut',
        data: {
            labels: [],
            datasets: [{
                data: [],
                backgroundColor: [
                    'rgb(59, 130, 246)',
                    'rgb(16, 185, 129)',
                    'rgb(245, 158, 11)',
                    'rgb(239, 68, 68)',
                    'rgb(139, 92, 246)',
                    'rgb(236, 72, 153)'
                ]
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'rgba(156, 163, 175, 0.8)',
                        padding: 15
                    }
                }
            }
        }
    });
}

// Format hashrate for display
function formatHashrate(hashrate) {
    if (hashrate === 0) return '0 H/s';
    
    const units = ['H/s', 'KH/s', 'MH/s', 'GH/s', 'TH/s'];
    let unitIndex = 0;
    let value = hashrate;
    
    while (value >= 1000 && unitIndex < units.length - 1) {
        value /= 1000;
        unitIndex++;
    }
    
    return `${value.toFixed(2)} ${units[unitIndex]}`;
}

// Format large numbers
function formatNumber(num) {
    if (num < 1000) return num.toString();
    if (num < 1000000) return (num / 1000).toFixed(1) + 'K';
    if (num < 1000000000) return (num / 1000000).toFixed(1) + 'M';
    return (num / 1000000000).toFixed(1) + 'B';
}

// Format timestamp
function formatTimestamp(timestamp) {
    const now = Date.now();
    const diff = now - timestamp;
    
    if (diff < 5000) return 'Just now';
    if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    return `${Math.floor(diff / 3600000)}h ago`;
}

// Update statistics display
function updateStats(stats) {
    document.getElementById('active-instances').textContent = stats.total_instances;
    document.getElementById('total-hashrate').textContent = formatHashrate(stats.total_hashrate);
    document.getElementById('total-gpus').textContent = stats.total_gpus;
    document.getElementById('total-hashes').textContent = formatNumber(stats.total_hashes);
}

// Update instances table
function updateInstancesTable() {
    const tbody = document.getElementById('instances-table');
    const noInstances = document.getElementById('no-instances');
    
    const instancesList = Object.values(instances);
    
    if (instancesList.length === 0) {
        tbody.innerHTML = '';
        noInstances.style.display = 'block';
        return;
    }
    
    noInstances.style.display = 'none';
    
    // Sort by hashrate descending
    instancesList.sort((a, b) => b.recent_hashrate - a.recent_hashrate);
    
    tbody.innerHTML = instancesList.map(inst => `
        <tr class="border-b border-gray-700">
            <td class="py-3">
                <span class="font-mono text-sm">${inst.instance_id.substring(0, 16)}...</span>
            </td>
            <td class="py-3">
                <span class="font-semibold">${formatHashrate(inst.recent_hashrate)}</span>
            </td>
            <td class="py-3">${formatNumber(inst.total_hashes)}</td>
            <td class="py-3">
                ${inst.gpu_available ? 
                    `<span class="text-green-400">${inst.gpu_count} GPU${inst.gpu_count > 1 ? 's' : ''}</span>` : 
                    '<span class="text-gray-500">CPU Only</span>'}
            </td>
            <td class="py-3">
                <span class="status-indicator status-online"></span>
                <span class="text-green-400">Online</span>
            </td>
            <td class="py-3 text-gray-400">
                ${formatTimestamp(inst.last_seen * 1000)}
            </td>
        </tr>
    `).join('');
}

// Update hashrate chart
function updateHashrateChart(totalHashrate) {
    const now = Date.now();
    
    hashrateHistory.push({
        x: now,
        y: totalHashrate
    });
    
    // Keep only recent history
    if (hashrateHistory.length > MAX_HISTORY_POINTS) {
        hashrateHistory.shift();
    }
    
    hashrateChart.data.datasets[0].data = hashrateHistory;
    hashrateChart.update('none');
}

// Update distribution chart
function updateDistributionChart() {
    const instancesList = Object.values(instances);
    
    if (instancesList.length === 0) {
        distributionChart.data.labels = [];
        distributionChart.data.datasets[0].data = [];
    } else {
        // Get top 6 instances by hashrate
        const topInstances = instancesList
            .sort((a, b) => b.recent_hashrate - a.recent_hashrate)
            .slice(0, 6);
        
        distributionChart.data.labels = topInstances.map(inst => 
            inst.instance_id.substring(0, 8)
        );
        distributionChart.data.datasets[0].data = topInstances.map(inst => 
            inst.recent_hashrate
        );
    }
    
    distributionChart.update('none');
}

// Socket event handlers
socket.on('connect', () => {
    console.log('Connected to server');
});

socket.on('initial_data', (data) => {
    console.log('Received initial data:', data);
    
    // Update instances
    instances = {};
    data.instances.forEach(inst => {
        instances[inst.instance_id] = inst;
    });
    
    // Update displays
    updateStats(data.stats);
    updateInstancesTable();
    updateDistributionChart();
    updateHashrateChart(data.stats.total_hashrate);
});

socket.on('hashrate_update', (data) => {
    console.log('Hashrate update:', data);
    
    // Update instance
    instances[data.instance.instance_id] = data.instance;
    
    // Remove inactive instances (not seen in 30 seconds)
    const cutoff = Date.now() / 1000 - 30;
    Object.keys(instances).forEach(id => {
        if (instances[id].last_seen < cutoff) {
            delete instances[id];
        }
    });
    
    // Update displays
    updateStats(data.stats);
    updateInstancesTable();
    updateDistributionChart();
    updateHashrateChart(data.stats.total_hashrate);
});

socket.on('disconnect', () => {
    console.log('Disconnected from server');
});

// Periodic cleanup of inactive instances
setInterval(() => {
    const cutoff = Date.now() / 1000 - 30;
    let changed = false;
    
    Object.keys(instances).forEach(id => {
        if (instances[id].last_seen < cutoff) {
            delete instances[id];
            changed = true;
        }
    });
    
    if (changed) {
        updateInstancesTable();
        updateDistributionChart();
    }
}, 5000);

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
});