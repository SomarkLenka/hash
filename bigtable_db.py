import os
import json
from datetime import datetime, timedelta
from google.cloud import bigtable
from google.cloud.bigtable import column_family
from google.cloud.bigtable import row_filters
import logging

logger = logging.getLogger(__name__)

class BigtableDB:
    def __init__(self):
        project_id = os.environ.get('BIGTABLE_PROJECT_ID')
        instance_id = os.environ.get('BIGTABLE_INSTANCE_ID')
        table_id = os.environ.get('BIGTABLE_TABLE_ID', 'hashrate-monitor')
        
        if not project_id or not instance_id:
            raise ValueError("BIGTABLE_PROJECT_ID and BIGTABLE_INSTANCE_ID must be set")
        
        self.client = bigtable.Client(project=project_id, admin=True)
        self.instance = self.client.instance(instance_id)
        self.table = self.instance.table(table_id)
        
        # Create table and column families if they don't exist
        self._setup_table()
    
    def _setup_table(self):
        """Create table and column families if they don't exist"""
        try:
            # Check if table exists
            existing_tables = self.instance.list_tables()
            table_exists = any(t.table_id == self.table.table_id for t in existing_tables)
            
            if not table_exists:
                logger.info(f"Creating Bigtable table: {self.table.table_id}")
                max_versions_rule = column_family.MaxVersionsGCRule(1)
                column_families = {
                    'instance': max_versions_rule,
                    'metrics': max_versions_rule,
                    'gpu': max_versions_rule
                }
                self.table.create(column_families=column_families)
                logger.info("Bigtable table created successfully")
        except Exception as e:
            logger.error(f"Error setting up Bigtable: {e}")
    
    def save_hashrate(self, data):
        """Save hashrate data to Bigtable"""
        try:
            # Create row key: instance_id#timestamp
            timestamp = data.get('timestamp', datetime.utcnow().isoformat())
            row_key = f"{data['instance_id']}#{timestamp}"
            
            row = self.table.direct_row(row_key)
            
            # Instance data
            row.set_cell('instance', 'id', data['instance_id'])
            row.set_cell('instance', 'timestamp', timestamp)
            row.set_cell('instance', 'gpu_count', str(data['gpu_count']))
            row.set_cell('instance', 'gpu_available', str(data['gpu_available']))
            
            # Metrics data
            row.set_cell('metrics', 'total_hashes', str(data['total_hashes']))
            row.set_cell('metrics', 'overall_hashrate', str(data['overall_hashrate']))
            row.set_cell('metrics', 'recent_hashrate', str(data['recent_hashrate']))
            
            # Optional GPU data
            if 'hashrate' in data:
                row.set_cell('gpu', 'hashrate', str(data['hashrate']))
            if 'temperature' in data:
                row.set_cell('gpu', 'temperature', str(data['temperature']))
            if 'gpu_name' in data:
                row.set_cell('gpu', 'name', data['gpu_name'])
            if 'power' in data:
                row.set_cell('gpu', 'power', str(data['power']))
            if 'efficiency' in data:
                row.set_cell('gpu', 'efficiency', str(data['efficiency']))
            
            row.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving to Bigtable: {e}")
            return False
    
    def get_instances(self):
        """Get all unique instances with their latest data"""
        try:
            instances = {}
            
            # Read all rows
            rows = self.table.read_rows()
            
            for row in rows:
                # Parse row key
                instance_id = row.row_key.decode('utf-8').split('#')[0]
                
                # Get cell data
                cells = row.cells
                
                if instance_id not in instances:
                    instance_data = {
                        'instance_id': instance_id,
                        'last_seen': None,
                        'hashrate': 0,
                        'temperature': 0,
                        'gpu_name': 'Unknown',
                        'power': 0,
                        'efficiency': 0,
                        'gpu_count': 0,
                        'gpu_available': 0,
                        'total_hashes': 0
                    }
                    
                    # Get latest values from cells
                    if 'instance' in cells:
                        if 'timestamp' in cells['instance']:
                            instance_data['last_seen'] = cells['instance']['timestamp'][0].value.decode('utf-8')
                        if 'gpu_count' in cells['instance']:
                            instance_data['gpu_count'] = int(cells['instance']['gpu_count'][0].value.decode('utf-8'))
                        if 'gpu_available' in cells['instance']:
                            instance_data['gpu_available'] = int(cells['instance']['gpu_available'][0].value.decode('utf-8'))
                    
                    if 'metrics' in cells:
                        if 'overall_hashrate' in cells['metrics']:
                            instance_data['hashrate'] = float(cells['metrics']['overall_hashrate'][0].value.decode('utf-8'))
                        if 'total_hashes' in cells['metrics']:
                            instance_data['total_hashes'] = int(cells['metrics']['total_hashes'][0].value.decode('utf-8'))
                    
                    if 'gpu' in cells:
                        if 'temperature' in cells['gpu']:
                            instance_data['temperature'] = float(cells['gpu']['temperature'][0].value.decode('utf-8'))
                        if 'name' in cells['gpu']:
                            instance_data['gpu_name'] = cells['gpu']['name'][0].value.decode('utf-8')
                        if 'power' in cells['gpu']:
                            instance_data['power'] = float(cells['gpu']['power'][0].value.decode('utf-8'))
                        if 'efficiency' in cells['gpu']:
                            instance_data['efficiency'] = float(cells['gpu']['efficiency'][0].value.decode('utf-8'))
                    
                    instances[instance_id] = instance_data
            
            return list(instances.values())
        except Exception as e:
            logger.error(f"Error getting instances from Bigtable: {e}")
            return []
    
    def get_instance_history(self, instance_id, hours=24):
        """Get history for a specific instance"""
        try:
            history = []
            
            # Create row prefix for the instance
            row_prefix = f"{instance_id}#"
            
            # Calculate time filter
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            
            # Read rows with prefix
            rows = self.table.read_rows(row_prefix=row_prefix.encode('utf-8'))
            
            for row in rows:
                # Parse timestamp from row key
                timestamp_str = row.row_key.decode('utf-8').split('#')[1]
                timestamp = datetime.fromisoformat(timestamp_str)
                
                # Skip old entries
                if timestamp < cutoff_time:
                    continue
                
                cells = row.cells
                data_point = {
                    'timestamp': timestamp_str,
                    'hashrate': 0,
                    'temperature': 0,
                    'power': 0
                }
                
                if 'metrics' in cells and 'overall_hashrate' in cells['metrics']:
                    data_point['hashrate'] = float(cells['metrics']['overall_hashrate'][0].value.decode('utf-8'))
                
                if 'gpu' in cells:
                    if 'temperature' in cells['gpu']:
                        data_point['temperature'] = float(cells['gpu']['temperature'][0].value.decode('utf-8'))
                    if 'power' in cells['gpu']:
                        data_point['power'] = float(cells['gpu']['power'][0].value.decode('utf-8'))
                
                history.append(data_point)
            
            # Sort by timestamp
            history.sort(key=lambda x: x['timestamp'])
            
            return history
        except Exception as e:
            logger.error(f"Error getting history from Bigtable: {e}")
            return []
    
    def cleanup_old_records(self, days=7):
        """Delete records older than specified days"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(days=days)
            deleted_count = 0
            
            rows = self.table.read_rows()
            
            for row in rows:
                # Parse timestamp from row key
                try:
                    timestamp_str = row.row_key.decode('utf-8').split('#')[1]
                    timestamp = datetime.fromisoformat(timestamp_str)
                    
                    if timestamp < cutoff_time:
                        row.delete()
                        row.commit()
                        deleted_count += 1
                except Exception as e:
                    logger.error(f"Error parsing row {row.row_key}: {e}")
                    continue
            
            logger.info(f"Deleted {deleted_count} old records from Bigtable")
            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up Bigtable: {e}")
            return 0