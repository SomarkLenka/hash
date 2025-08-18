#!/usr/bin/env python
import os
import sys
import subprocess

port = os.environ.get('PORT', '5000')
cmd = [
    'gunicorn',
    '--worker-class', 'eventlet',
    '-w', '1',
    '--bind', f'0.0.0.0:{port}',
    '--timeout', '120',  # Increase timeout to 120 seconds
    '--graceful-timeout', '30',
    'app:app'
]

subprocess.run(cmd)