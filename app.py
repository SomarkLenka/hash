#!/usr/bin/env python3
"""
Hashrate Monitoring Server
Receives and displays hashrate data from distributed hash generators
"""

import os
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import threading
import logging

from flask import Flask, request, jsonify, render_template, g
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import humanize

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Database configuration
DATABASE = os.environ.get('DATABASE_PATH', 'hashrate.db')
CLEANUP_INTERVAL = 3600  # Clean old records every hour
RETENTION_DAYS = 7  # Keep data for 7 days


@dataclass
class HashrateData:
    """Data structure for hashrate information"""
    instance_id: str
    total_hashes: int
    overall_hashrate: float
    recent_hashrate: float
    timestamp: str
    gpu_count: int
    gpu_available: bool
    ip_address: str = ""
    last_seen: float = 0


class HashrateStore:
    """In-memory store for active instances"""
    
    def __init__(self):
        self.instances: Dict[str, HashrateData] = {}
        self.lock = threading.Lock()
    
    def update(self, data: HashrateData):
        """Update instance data"""
        with self.lock:
            data.last_seen = time.time()
            self.instances[data.instance_id] = data
    
    def get_all(self) -> List[HashrateData]:
        """Get all active instances"""
        with self.lock:
            # Filter out instances not seen in last 30 seconds
            cutoff = time.time() - 30
            active = [
                inst for inst in self.instances.values()
                if inst.last_seen > cutoff
            ]
            return active
    
    def get_stats(self) -> dict:
        """Get aggregate statistics"""
        instances = self.get_all()
        
        if not instances:
            return {
                'total_instances': 0,
                'total_hashrate': 0,
                'total_hashes': 0,
                'total_gpus': 0,
                'avg_hashrate': 0
            }
        
        total_hashrate = sum(inst.recent_hashrate for inst in instances)
        total_hashes = sum(inst.total_hashes for inst in instances)
        total_gpus = sum(inst.gpu_count for inst in instances if inst.gpu_available)
        
        return {
            'total_instances': len(instances),
            'total_hashrate': total_hashrate,
            'total_hashes': total_hashes,
            'total_gpus': total_gpus,
            'avg_hashrate': total_hashrate / len(instances) if instances else 0
        }


# Global hashrate store
hashrate_store = HashrateStore()


def get_db():
    """Get database connection"""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    """Close database connection"""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def init_db():
    """Initialize database tables"""
    with app.app_context():
        db = get_db()
        db.execute('''
            CREATE TABLE IF NOT EXISTS hashrate_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id TEXT NOT NULL,
                total_hashes INTEGER,
                overall_hashrate REAL,
                recent_hashrate REAL,
                gpu_count INTEGER,
                gpu_available BOOLEAN,
                ip_address TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster queries
        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_instance_timestamp 
            ON hashrate_history(instance_id, timestamp DESC)
        ''')
        
        db.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON hashrate_history(created_at)
        ''')
        
        db.commit()
        logger.info("Database initialized")


def cleanup_old_records():
    """Remove records older than retention period"""
    with app.app_context():
        try:
            db = get_db()
            cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
            
            result = db.execute(
                'DELETE FROM hashrate_history WHERE created_at < ?',
                (cutoff,)
            )
            db.commit()
            
            if result.rowcount > 0:
                logger.info(f"Cleaned up {result.rowcount} old records")
        except Exception as e:
            logger.error(f"Error cleaning up old records: {e}")


def periodic_cleanup():
    """Periodically clean up old records"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cleanup_old_records()


@app.route('/')
def index():
    """Dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/hashrate', methods=['POST'])
def receive_hashrate():
    """Receive hashrate data from generator instances"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ['instance_id', 'total_hashes', 'overall_hashrate', 
                         'recent_hashrate', 'timestamp', 'gpu_count', 'gpu_available']
        
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        # Get client IP
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        # Create HashrateData object
        hashrate_data = HashrateData(
            instance_id=data['instance_id'],
            total_hashes=data['total_hashes'],
            overall_hashrate=data['overall_hashrate'],
            recent_hashrate=data['recent_hashrate'],
            timestamp=data['timestamp'],
            gpu_count=data['gpu_count'],
            gpu_available=data['gpu_available'],
            ip_address=ip_address
        )
        
        # Update in-memory store
        hashrate_store.update(hashrate_data)
        
        # Store in database
        db = get_db()
        db.execute('''
            INSERT INTO hashrate_history 
            (instance_id, total_hashes, overall_hashrate, recent_hashrate, 
             gpu_count, gpu_available, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            hashrate_data.instance_id,
            hashrate_data.total_hashes,
            hashrate_data.overall_hashrate,
            hashrate_data.recent_hashrate,
            hashrate_data.gpu_count,
            hashrate_data.gpu_available,
            hashrate_data.ip_address,
            hashrate_data.timestamp
        ))
        db.commit()
        
        # Emit update to connected clients
        socketio.emit('hashrate_update', {
            'instance': asdict(hashrate_data),
            'stats': hashrate_store.get_stats()
        })
        
        logger.info(f"Received hashrate from {hashrate_data.instance_id}: {hashrate_data.recent_hashrate:.2f} H/s")
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        logger.error(f"Error processing hashrate data: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/instances')
def get_instances():
    """Get all active instances"""
    instances = hashrate_store.get_all()
    return jsonify([asdict(inst) for inst in instances])


@app.route('/api/stats')
def get_stats():
    """Get aggregate statistics"""
    return jsonify(hashrate_store.get_stats())


@app.route('/api/history/<instance_id>')
def get_instance_history(instance_id):
    """Get historical data for a specific instance"""
    try:
        hours = int(request.args.get('hours', 24))
        
        db = get_db()
        cutoff = datetime.now() - timedelta(hours=hours)
        
        cursor = db.execute('''
            SELECT timestamp, recent_hashrate, total_hashes, gpu_count
            FROM hashrate_history
            WHERE instance_id = ? AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 1000
        ''', (instance_id, cutoff))
        
        history = []
        for row in cursor:
            history.append({
                'timestamp': row['timestamp'],
                'hashrate': row['recent_hashrate'],
                'total_hashes': row['total_hashes'],
                'gpu_count': row['gpu_count']
            })
        
        return jsonify(history)
        
    except Exception as e:
        logger.error(f"Error fetching history: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/summary')
def get_summary():
    """Get summary statistics for all instances"""
    try:
        db = get_db()
        
        # Get 24-hour statistics
        cutoff = datetime.now() - timedelta(hours=24)
        
        cursor = db.execute('''
            SELECT 
                COUNT(DISTINCT instance_id) as unique_instances,
                SUM(total_hashes) as total_hashes_24h,
                AVG(recent_hashrate) as avg_hashrate_24h,
                MAX(recent_hashrate) as peak_hashrate_24h
            FROM hashrate_history
            WHERE timestamp > ?
        ''', (cutoff,))
        
        row = cursor.fetchone()
        
        # Get current active instances
        active_instances = hashrate_store.get_all()
        stats = hashrate_store.get_stats()
        
        summary = {
            'current': {
                'active_instances': len(active_instances),
                'total_hashrate': stats['total_hashrate'],
                'total_gpus': stats['total_gpus'],
                'avg_hashrate': stats['avg_hashrate']
            },
            'last_24h': {
                'unique_instances': row['unique_instances'] or 0,
                'total_hashes': row['total_hashes_24h'] or 0,
                'avg_hashrate': row['avg_hashrate_24h'] or 0,
                'peak_hashrate': row['peak_hashrate_24h'] or 0
            }
        }
        
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health_check():
    """Health check endpoint for Railway"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info(f"Client connected: {request.sid}")
    
    # Send initial data
    emit('initial_data', {
        'instances': [asdict(inst) for inst in hashrate_store.get_all()],
        'stats': hashrate_store.get_stats()
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection"""
    logger.info(f"Client disconnected: {request.sid}")


if __name__ == '__main__':
    # Initialize database
    init_db()
    
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
    cleanup_thread.start()
    
    # Get port from environment (Railway sets this)
    port = int(os.environ.get('PORT', 5000))
    
    # Run the app
    socketio.run(app, host='0.0.0.0', port=port, debug=False)