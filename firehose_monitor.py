#!/usr/bin/env python3
"""
Enhanced monitoring module for the hashrate monitor app.
Integrates firehose pipeline monitoring with the existing dashboard.
"""

import os
import time
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import deque
import threading
from flask import Blueprint, jsonify, render_template_string

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FirehoseMetrics:
    """Firehose-specific metrics"""
    bigtable_writes_per_second: float = 0
    bigtable_write_latency_ms: float = 0
    bigtable_error_rate: float = 0
    buffer_queue_depth: int = 0
    buffer_lag_seconds: float = 0
    worker_pool_size: int = 0
    worker_utilization: float = 0
    shard_distribution: Dict[str, int] = None
    batch_efficiency: float = 0
    retry_rate: float = 0


class FirehoseMonitor:
    """Monitor for Bigtable firehose pipeline integrated with hashrate monitoring"""
    
    def __init__(self, window_size: int = 300):
        self.window_size = window_size
        self.metrics_history = deque(maxlen=window_size)
        
        # Metrics storage
        self.current_metrics = FirehoseMetrics()
        self.alerts = deque(maxlen=100)
        
        # Performance counters
        self.counters = {
            'total_writes': 0,
            'failed_writes': 0,
            'total_retries': 0,
            'total_batches': 0,
            'messages_buffered': 0,
            'messages_processed': 0
        }
        
        # Alert thresholds
        self.thresholds = {
            'write_latency_ms': 100,
            'error_rate': 0.01,
            'buffer_lag_seconds': 10,
            'queue_depth': 50000,
            'worker_utilization': 0.9
        }
        
        # Start monitoring thread
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def update_bigtable_metrics(self, writes_per_sec: float, latency_ms: float, 
                                error_rate: float, shard_stats: Dict[str, int]):
        """Update Bigtable-specific metrics"""
        self.current_metrics.bigtable_writes_per_second = writes_per_sec
        self.current_metrics.bigtable_write_latency_ms = latency_ms
        self.current_metrics.bigtable_error_rate = error_rate
        self.current_metrics.shard_distribution = shard_stats or {}
        
        # Update counters
        self.counters['total_writes'] += int(writes_per_sec)
        
        # Check for alerts
        if latency_ms > self.thresholds['write_latency_ms']:
            self._add_alert('warning', f'High Bigtable latency: {latency_ms:.1f}ms')
        
        if error_rate > self.thresholds['error_rate']:
            self._add_alert('critical', f'High error rate: {error_rate:.2%}')
    
    def update_buffer_metrics(self, queue_depth: int, lag_seconds: float, 
                             messages_buffered: int):
        """Update buffer layer metrics"""
        self.current_metrics.buffer_queue_depth = queue_depth
        self.current_metrics.buffer_lag_seconds = lag_seconds
        self.counters['messages_buffered'] += messages_buffered
        
        # Check for alerts
        if queue_depth > self.thresholds['queue_depth']:
            self._add_alert('warning', f'Buffer queue backup: {queue_depth} messages')
        
        if lag_seconds > self.thresholds['buffer_lag_seconds']:
            self._add_alert('warning', f'High buffer lag: {lag_seconds:.1f}s')
    
    def update_worker_metrics(self, pool_size: int, utilization: float, 
                             batch_efficiency: float):
        """Update worker pool metrics"""
        self.current_metrics.worker_pool_size = pool_size
        self.current_metrics.worker_utilization = utilization
        self.current_metrics.batch_efficiency = batch_efficiency
        
        # Check for alerts
        if utilization > self.thresholds['worker_utilization']:
            self._add_alert('info', f'High worker utilization: {utilization:.1%}')
    
    def record_batch(self, batch_size: int, success: bool, retry_count: int = 0):
        """Record a batch write operation"""
        self.counters['total_batches'] += 1
        self.counters['messages_processed'] += batch_size
        
        if not success:
            self.counters['failed_writes'] += batch_size
        
        if retry_count > 0:
            self.counters['total_retries'] += retry_count
            self.current_metrics.retry_rate = (
                self.counters['total_retries'] / 
                max(1, self.counters['total_batches'])
            )
    
    def _add_alert(self, level: str, message: str):
        """Add an alert to the queue"""
        alert = {
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        }
        self.alerts.append(alert)
        logger.warning(f"Firehose Alert [{level}]: {message}")
    
    def _monitor_loop(self):
        """Background monitoring loop"""
        while self.running:
            try:
                # Calculate derived metrics
                if self.counters['total_batches'] > 0:
                    self.current_metrics.batch_efficiency = (
                        self.counters['messages_processed'] / 
                        (self.counters['total_batches'] * 5000)  # Assuming 5000 batch size
                    )
                
                # Store snapshot
                snapshot = {
                    'timestamp': time.time(),
                    'metrics': asdict(self.current_metrics),
                    'counters': self.counters.copy()
                }
                self.metrics_history.append(snapshot)
                
                # Sleep
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
    
    def get_metrics(self) -> Dict:
        """Get current metrics as dictionary"""
        return {
            'firehose': asdict(self.current_metrics),
            'counters': self.counters,
            'alerts': list(self.alerts)[-10:],  # Last 10 alerts
            'history': self._get_history_summary()
        }
    
    def _get_history_summary(self) -> Dict:
        """Get summary of historical metrics"""
        if not self.metrics_history:
            return {}
        
        # Calculate averages over window
        total_writes = sum(h['counters']['total_writes'] for h in self.metrics_history)
        time_span = self.metrics_history[-1]['timestamp'] - self.metrics_history[0]['timestamp']
        
        if time_span > 0:
            avg_writes_per_sec = total_writes / time_span
        else:
            avg_writes_per_sec = 0
        
        return {
            'avg_writes_per_second': avg_writes_per_sec,
            'total_messages_processed': self.counters['messages_processed'],
            'success_rate': 1 - (self.counters['failed_writes'] / 
                                max(1, self.counters['messages_processed'])),
            'time_span_seconds': time_span
        }
    
    def stop(self):
        """Stop the monitor"""
        self.running = False
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)


# Flask Blueprint for API endpoints
firehose_bp = Blueprint('firehose', __name__)

# Global monitor instance
firehose_monitor = None


def init_firehose_monitor():
    """Initialize the firehose monitor"""
    global firehose_monitor
    if firehose_monitor is None:
        firehose_monitor = FirehoseMonitor()
        logger.info("Firehose monitor initialized")
    return firehose_monitor


@firehose_bp.route('/api/firehose/metrics')
def get_firehose_metrics():
    """Get firehose pipeline metrics"""
    if firehose_monitor:
        return jsonify(firehose_monitor.get_metrics())
    return jsonify({'error': 'Monitor not initialized'}), 500


@firehose_bp.route('/api/firehose/update', methods=['POST'])
def update_firehose_metrics():
    """Update firehose metrics from workers"""
    try:
        data = request.json
        
        if 'bigtable' in data:
            firehose_monitor.update_bigtable_metrics(
                writes_per_sec=data['bigtable'].get('writes_per_second', 0),
                latency_ms=data['bigtable'].get('latency_ms', 0),
                error_rate=data['bigtable'].get('error_rate', 0),
                shard_stats=data['bigtable'].get('shard_stats', {})
            )
        
        if 'buffer' in data:
            firehose_monitor.update_buffer_metrics(
                queue_depth=data['buffer'].get('queue_depth', 0),
                lag_seconds=data['buffer'].get('lag_seconds', 0),
                messages_buffered=data['buffer'].get('messages_buffered', 0)
            )
        
        if 'workers' in data:
            firehose_monitor.update_worker_metrics(
                pool_size=data['workers'].get('pool_size', 0),
                utilization=data['workers'].get('utilization', 0),
                batch_efficiency=data['workers'].get('batch_efficiency', 0)
            )
        
        if 'batch' in data:
            firehose_monitor.record_batch(
                batch_size=data['batch'].get('size', 0),
                success=data['batch'].get('success', True),
                retry_count=data['batch'].get('retries', 0)
            )
        
        return jsonify({'status': 'success'})
        
    except Exception as e:
        logger.error(f"Error updating firehose metrics: {e}")
        return jsonify({'error': str(e)}), 500


@firehose_bp.route('/api/firehose/alerts')
def get_firehose_alerts():
    """Get active firehose alerts"""
    if firehose_monitor:
        return jsonify(list(firehose_monitor.alerts))
    return jsonify([])


# Enhanced dashboard template
FIREHOSE_DASHBOARD = """
<!DOCTYPE html>
<html>
<head>
    <title>Firehose Pipeline Dashboard</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            color: #fff;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .metric-card {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s;
        }
        .metric-card:hover {
            transform: translateY(-5px);
        }
        .metric-label {
            font-size: 0.9em;
            opacity: 0.8;
            margin-bottom: 5px;
        }
        .metric-value {
            font-size: 2.5em;
            font-weight: bold;
            background: linear-gradient(45deg, #00ff88, #00ffff);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .metric-unit {
            font-size: 0.7em;
            opacity: 0.7;
        }
        .chart-container {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            height: 400px;
        }
        .alerts-container {
            background: rgba(255,255,255,0.1);
            backdrop-filter: blur(10px);
            padding: 20px;
            border-radius: 10px;
            max-height: 300px;
            overflow-y: auto;
        }
        .alert-item {
            padding: 10px;
            margin: 10px 0;
            border-radius: 5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .alert-item.info {
            background: rgba(52, 152, 219, 0.3);
        }
        .alert-item.warning {
            background: rgba(241, 196, 15, 0.3);
        }
        .alert-item.critical {
            background: rgba(231, 76, 60, 0.3);
        }
        .status-indicator {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #00ff88;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Firehose Pipeline Dashboard</h1>
            <p>Real-time Bigtable Ingestion Monitoring</p>
            <div class="status-indicator"></div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Bigtable Writes</div>
                <div class="metric-value" id="writes-per-sec">-</div>
                <div class="metric-unit">writes/sec</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Write Latency</div>
                <div class="metric-value" id="latency">-</div>
                <div class="metric-unit">ms</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Buffer Queue</div>
                <div class="metric-value" id="queue-depth">-</div>
                <div class="metric-unit">messages</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Worker Pool</div>
                <div class="metric-value" id="workers">-</div>
                <div class="metric-unit">workers</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Error Rate</div>
                <div class="metric-value" id="error-rate">-</div>
                <div class="metric-unit">%</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Batch Efficiency</div>
                <div class="metric-value" id="efficiency">-</div>
                <div class="metric-unit">%</div>
            </div>
        </div>
        
        <div class="chart-container">
            <canvas id="throughput-chart"></canvas>
        </div>
        
        <div class="alerts-container">
            <h3>Active Alerts</h3>
            <div id="alerts-list"></div>
        </div>
    </div>
    
    <script>
        // Initialize chart
        const ctx = document.getElementById('throughput-chart').getContext('2d');
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Writes/sec',
                        data: [],
                        borderColor: '#00ff88',
                        backgroundColor: 'rgba(0, 255, 136, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Queue Depth (÷100)',
                        data: [],
                        borderColor: '#00ffff',
                        backgroundColor: 'rgba(0, 255, 255, 0.1)',
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        labels: { color: '#fff' }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    },
                    y: {
                        ticks: { color: '#fff' },
                        grid: { color: 'rgba(255,255,255,0.1)' }
                    }
                }
            }
        });
        
        // Update function
        async function updateDashboard() {
            try {
                const response = await fetch('/api/firehose/metrics');
                const data = await response.json();
                
                // Update metrics
                document.getElementById('writes-per-sec').textContent = 
                    data.firehose.bigtable_writes_per_second.toFixed(0);
                document.getElementById('latency').textContent = 
                    data.firehose.bigtable_write_latency_ms.toFixed(1);
                document.getElementById('queue-depth').textContent = 
                    data.firehose.buffer_queue_depth.toLocaleString();
                document.getElementById('workers').textContent = 
                    data.firehose.worker_pool_size;
                document.getElementById('error-rate').textContent = 
                    (data.firehose.bigtable_error_rate * 100).toFixed(2);
                document.getElementById('efficiency').textContent = 
                    (data.firehose.batch_efficiency * 100).toFixed(1);
                
                // Update chart
                const now = new Date().toLocaleTimeString();
                chart.data.labels.push(now);
                chart.data.datasets[0].data.push(data.firehose.bigtable_writes_per_second);
                chart.data.datasets[1].data.push(data.firehose.buffer_queue_depth / 100);
                
                // Keep last 30 points
                if (chart.data.labels.length > 30) {
                    chart.data.labels.shift();
                    chart.data.datasets.forEach(dataset => dataset.data.shift());
                }
                
                chart.update('none');
                
                // Update alerts
                const alertsList = document.getElementById('alerts-list');
                alertsList.innerHTML = '';
                data.alerts.forEach(alert => {
                    const div = document.createElement('div');
                    div.className = 'alert-item ' + alert.level;
                    div.innerHTML = `
                        <span>${alert.timestamp}</span>
                        <span>${alert.message}</span>
                    `;
                    alertsList.appendChild(div);
                });
                
            } catch (error) {
                console.error('Failed to update dashboard:', error);
            }
        }
        
        // Update every 2 seconds
        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""


@firehose_bp.route('/firehose')
def firehose_dashboard():
    """Serve the firehose dashboard"""
    return render_template_string(FIREHOSE_DASHBOARD)


# Integration function for main app
def integrate_firehose_monitoring(app):
    """Integrate firehose monitoring into the main Flask app"""
    # Initialize monitor
    init_firehose_monitor()
    
    # Register blueprint
    app.register_blueprint(firehose_bp)
    
    logger.info("Firehose monitoring integrated into hashrate monitor app")
    
    return firehose_monitor