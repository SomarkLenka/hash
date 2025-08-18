# Hashrate Monitor

A real-time web dashboard for monitoring distributed SHA256 hash generators. Features WebSocket-based live updates, historical data tracking, and beautiful visualizations.

## Features

- **Real-time Dashboard**: Live updates via WebSocket connections
- **Instance Tracking**: Monitor multiple hash generator instances
- **Historical Data**: SQLite storage with 7-day retention
- **Statistics**: Total hashrate, GPU count, active instances
- **Visualizations**: Interactive charts for hashrate trends and instance distribution
- **REST API**: Full API for programmatic access
- **Auto-cleanup**: Automatic removal of inactive instances and old data

## API Endpoints

### POST /api/hashrate
Receive hashrate data from generator instances.

```json
{
  "instance_id": "hostname_timestamp_abc123",
  "total_hashes": 1000000,
  "overall_hashrate": 50000.5,
  "recent_hashrate": 52000.3,
  "timestamp": "2024-01-20T10:30:00Z",
  "gpu_count": 4,
  "gpu_available": true
}
```

### GET /api/instances
Get all active instances (last 30 seconds).

### GET /api/stats
Get aggregate statistics.

### GET /api/history/{instance_id}
Get historical data for a specific instance.

### GET /api/summary
Get 24-hour summary statistics.

## Deployment to Railway

### 1. Prerequisites
- Railway account (https://railway.app)
- GitHub repository with this code

### 2. Deploy via GitHub

1. Push this folder to a GitHub repository:
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/hashrate-monitor.git
git push -u origin main
```

2. In Railway Dashboard:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will auto-detect the configuration

3. Environment Variables (optional):
   - `SECRET_KEY`: Set a secure secret key for production
   - `DATABASE_PATH`: Path for SQLite database (default: hashrate.db)

4. Railway will automatically:
   - Detect Python via requirements.txt
   - Use the Procfile for start command
   - Assign a public URL like `hashrate-monitor.up.railway.app`

### 3. Deploy via Railway CLI

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login to Railway
railway login

# Initialize new project
railway init

# Deploy
railway up

# Get deployment URL
railway domain
```

## Local Development

### Using Docker

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Access dashboard
open http://localhost:5000
```

### Without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python app.py

# Or with gunicorn
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 app:app
```

## Configure Hash Generators

Update your hash generators to point to your deployed monitor:

1. Get your Railway URL (e.g., `https://your-app.up.railway.app`)

2. Update hash generator config:
```json
{
  "monitoring": {
    "endpoint": "https://your-app.up.railway.app/api/hashrate"
  }
}
```

Or use environment variable:
```bash
MONITORING_ENDPOINT=https://your-app.up.railway.app/api/hashrate
```

## Dashboard Features

### Real-time Metrics
- Active instance count
- Combined hashrate across all instances
- Total GPU count
- Total hashes generated

### Visualizations
- **Hashrate Chart**: Line chart showing total hashrate over time
- **Distribution Chart**: Doughnut chart showing hashrate distribution by instance
- **Instance Table**: Live-updating table with all instance details

### Auto-refresh
- WebSocket connections for instant updates
- Automatic removal of inactive instances
- No manual refresh needed

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│ Hash Generator  │────▶│   Monitor    │────▶│  Dashboard  │
│   Instance 1    │     │   Server     │     │  (Browser)  │
└─────────────────┘     │              │     └─────────────┘
                        │  - Flask      │            ▲
┌─────────────────┐     │  - SocketIO  │            │
│ Hash Generator  │────▶│  - SQLite    │────────────┘
│   Instance 2    │     │              │    WebSocket
└─────────────────┘     └──────────────┘
```

## Performance

- Handles 1000+ requests/second
- WebSocket support for 100+ concurrent dashboard viewers
- SQLite database with automatic cleanup
- Lightweight: ~50MB Docker image

## Security Notes

- Set `SECRET_KEY` environment variable in production
- Use HTTPS in production (Railway provides this automatically)
- Consider adding authentication for sensitive deployments
- Database is local SQLite (consider PostgreSQL for larger deployments)

## Monitoring the Monitor

Railway provides built-in metrics:
- Request count and latency
- Memory and CPU usage
- Error rates
- Custom health endpoint at `/health`

## Troubleshooting

### No instances showing
- Check generator configuration points to correct URL
- Verify network connectivity
- Check Railway logs: `railway logs`

### Database errors
- Ensure write permissions for DATABASE_PATH
- Check disk space
- Database auto-creates on first run

### WebSocket issues
- Ensure browser supports WebSockets
- Check for proxy/firewall blocking
- Railway handles WebSocket routing automatically

## License

MIT# hash
