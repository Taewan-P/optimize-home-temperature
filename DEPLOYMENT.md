# Deployment Guide

This guide walks you through deploying the heater optimization system to production.

## Prerequisites

- Docker and Docker Compose installed
- Access to your Home Assistant instance
- Home Assistant Long-Lived Access Token (create in Profile → Security)

## Step 1: Configure Environment Variables

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your actual credentials:

### Required Configuration

```bash
# Home Assistant Configuration
HA_URL=http://192.168.1.110:8123          # Your Home Assistant URL
HA_TOKEN=eyJhbGc...your_actual_token      # Your long-lived access token

# InfluxDB Configuration
INFLUX_TOKEN=your_random_secure_token     # Generate a secure token
INFLUX_ORG=home                           # Your organization name
INFLUX_BUCKET=heater                      # Keep as 'heater'
INFLUX_ADMIN_USER=admin                   # Admin username
INFLUX_ADMIN_PASSWORD=your_secure_pass    # Strong password

# Grafana Configuration
GRAFANA_ADMIN_PASSWORD=your_grafana_pass  # Strong password for Grafana

# Discord Webhook (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...  # Leave empty to disable
```

### Entity IDs Configuration

Update these to match your Home Assistant entity IDs:

```bash
# Home Assistant Entity IDs
HA_TEMP_SENSOR_ID=sensor.temperature           # Your temperature sensor
HA_HUMIDITY_SENSOR_ID=sensor.humidity          # Your humidity sensor
HA_HEATER_CLIMATE_ID=climate.heater            # Your heater climate entity
HA_WEATHER_ENTITY_ID=weather.home              # Your weather integration
HA_ELECTRICITY_SENSOR_ID=sensor.electricity_usage  # Your electricity sensor
```

To find your entity IDs:
1. Open Home Assistant → Developer Tools → States
2. Search for your sensors/climate entities
3. Copy the entity ID (e.g., `sensor.living_room_temperature`)

### Control Parameters (Optional)

Adjust these if needed:

```bash
# Temperature setpoints
HEATER_ON_TEMP=25.0    # Turn heater ON when temp drops below this
HEATER_OFF_TEMP=26.0   # Turn heater OFF when temp rises above this

# Safety parameters
MIN_CYCLE_TIME_SECONDS=180           # Minimum 3 minutes between state changes
SENSOR_STALE_TIMEOUT_SECONDS=300     # Alert if sensor data is >5 minutes old

# Polling intervals
TEMP_POLL_INTERVAL_SECONDS=60        # Check temperature every 60 seconds
WEATHER_POLL_INTERVAL_SECONDS=300    # Check weather every 5 minutes
ELECTRICITY_POLL_INTERVAL_SECONDS=86400  # Check electricity daily
```

## Step 2: Generate Secure Tokens

For InfluxDB token, generate a random secure string:

```bash
# On macOS/Linux
openssl rand -base64 32
```

Use the output as your `INFLUX_TOKEN`.

## Step 3: Verify Configuration

Before starting, verify your Home Assistant connection:

```bash
# Activate virtual environment
source .venv/bin/activate

# Test HA connection (create a simple test script)
python -c "
import os
from dotenv import load_dotenv
from src.ha_client import HomeAssistantClient

load_dotenv()
client = HomeAssistantClient(os.getenv('HA_URL'), os.getenv('HA_TOKEN'))
print('Testing connection...')
temp = client.get_sensor_state(os.getenv('HA_TEMP_SENSOR_ID'))
print(f'✓ Temperature: {temp}°C')
heater = client.get_climate_state(os.getenv('HA_HEATER_CLIMATE_ID'))
print(f'✓ Heater state: {heater}')
print('Connection successful!')
"
```

## Step 4: Start Services

Build and start all services:

```bash
# Build Docker images
docker compose build

# Start services in detached mode
docker compose up -d

# View logs
docker compose logs -f
```

Services will start on these ports:
- **InfluxDB**: http://localhost:8086
- **Grafana**: http://localhost:3000
- **Control Service**: http://localhost:8080 (internal only)
- **Data Collector**: No exposed port (internal only)

## Step 5: Verify Services

### Check Service Status

```bash
# View running containers
docker compose ps

# Check control service logs
docker compose logs control-service

# Check data collector logs
docker compose logs data-collector
```

All services should show status `Up`.

### Check Control Service Health

```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-02T14:30:00Z",
  "controller_state": "IDLE",
  "last_temp": 25.5
}
```

### Verify Data Collection

1. Open InfluxDB: http://localhost:8086
   - Login: `admin` / `INFLUX_ADMIN_PASSWORD` (from .env)
   - Navigate to: Data Explorer → `heater` bucket
   - Query: `from(bucket: "heater") |> range(start: -1h)`
   - Verify measurements: `temperature`, `humidity`, `heater_state`, `weather`

2. Open Grafana: http://localhost:3000
   - Login: `admin` / `GRAFANA_ADMIN_PASSWORD` (from .env)
   - Navigate to: Dashboards → "Heater Optimization"
   - Verify panels show data (may take 1-2 minutes for first datapoints)

## Step 6: Monitor Initial Operation

### First 24 Hours

Monitor the system closely during the first day:

1. **Check logs every few hours**:
   ```bash
   docker compose logs --tail=100 control-service
   ```

2. **Verify temperature control**:
   - Temperature should oscillate between 25-26°C (with configured hysteresis)
   - Heater should respect minimum 3-minute cycle time
   - No rapid on/off cycling should occur

3. **Check for errors**:
   ```bash
   docker compose logs | grep -i error
   docker compose logs | grep -i warning
   ```

4. **Monitor Grafana dashboard**:
   - Temperature trends should be smooth
   - Heater state changes should be visible
   - No gaps in data collection

### Expected Behavior

**Normal operation:**
- Temperature readings every 60 seconds
- Heater turns ON when temp < 25.0°C
- Heater turns OFF when temp > 26.0°C
- Minimum 3 minutes between state changes
- Weather data updates every 5 minutes

**Alert scenarios:**
- Sensor data >5 minutes old → FAILURE state, Discord alert
- Heater state verification fails → Alert sent
- Manual override detected → Controller pauses, timeout after 30 minutes

## Step 7: Data Collection Phase

**Duration needed**: 2-4 weeks minimum

During this phase:
- ✅ Let the system run continuously
- ✅ Monitor for any errors or anomalies
- ✅ Verify data is being collected in InfluxDB
- ❌ Do NOT manually override heater frequently (affects model training)
- ❌ Do NOT change temperature setpoints (maintains consistent data)

After 2 weeks, you can proceed with:
- **Task 9**: Thermal Model (1R1C) fitting
- **Task 10**: MPC Controller implementation

After 4 weeks, you can proceed with:
- **Task 11**: XGBoost ML model training

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs <service-name>

# Common issues:
# 1. Port already in use
sudo lsof -i :8086  # Check InfluxDB port
sudo lsof -i :3000  # Check Grafana port

# 2. Environment variables not loaded
docker compose config  # Verify env vars are interpolated
```

### No Data in InfluxDB

1. **Check data collector logs**:
   ```bash
   docker compose logs data-collector
   ```

2. **Verify HA connection**:
   ```bash
   docker compose exec data-collector python -c "
   import os
   from src.ha_client import HomeAssistantClient
   client = HomeAssistantClient(os.getenv('HA_URL'), os.getenv('HA_TOKEN'))
   print(client.get_sensor_state(os.getenv('HA_TEMP_SENSOR_ID')))
   "
   ```

3. **Check InfluxDB connection**:
   - Verify `INFLUX_URL`, `INFLUX_TOKEN`, `INFLUX_ORG`, `INFLUX_BUCKET` in `.env`
   - Ensure InfluxDB container is running: `docker compose ps influxdb`

### Control Service Not Working

1. **Check controller state**:
   ```bash
   curl http://localhost:8080/health
   ```

2. **Verify HA climate entity**:
   - Entity ID is correct in `.env`
   - Climate entity supports `set_hvac_mode` service
   - Climate entity has `heat` mode available

3. **Check for state verification failures**:
   ```bash
   docker compose logs control-service | grep "verification"
   ```

### Grafana Dashboard Shows No Data

1. **Verify data source**:
   - Grafana → Configuration → Data Sources
   - Check "InfluxDB" connection is green
   - Test query in Data Explorer

2. **Check time range**:
   - Dashboard may default to last 24 hours
   - If system just started, zoom to last 1 hour

3. **Verify bucket name**:
   - Dashboard queries use `heater` bucket
   - Ensure `INFLUX_BUCKET=heater` in `.env`

## Stopping Services

```bash
# Stop services (containers remain)
docker compose stop

# Stop and remove containers
docker compose down

# Stop and remove containers + volumes (DELETES ALL DATA)
docker compose down -v
```

## Updating the System

```bash
# Pull latest code
git pull

# Rebuild images
docker compose build

# Restart services
docker compose down
docker compose up -d
```

## Backup Data

To backup InfluxDB data:

```bash
# Create backup directory
mkdir -p backups

# Backup InfluxDB data
docker compose exec influxdb influx backup /backup
docker cp $(docker compose ps -q influxdb):/backup ./backups/influxdb-$(date +%Y%m%d)
```

## Next Steps

Once you have 2+ weeks of data collected:

1. **Analyze collected data**:
   ```bash
   # Export data from InfluxDB
   # Run thermal model fitting (Task 9)
   ```

2. **Resume implementation**:
   - Return to `.sisyphus/plans/heater-optimization.md`
   - Task 9: Thermal Model (1R1C) Fitting
   - Task 10: MPC Controller
   - Task 11: XGBoost ML Model

3. **Document findings**:
   - Add learnings to `.sisyphus/notepads/heater-optimization/`
   - Update boulder.json when unblocked

## Support

For issues or questions:
1. Check logs: `docker compose logs -f`
2. Review test suite: `pytest tests/ -v`
3. Check integration tests: `pytest tests/integration/ -v`

---

**Deployment Checklist:**
- [ ] `.env` file configured with actual credentials
- [ ] Home Assistant connection tested
- [ ] Docker services started successfully
- [ ] Health endpoint returns `healthy`
- [ ] Data appearing in InfluxDB
- [ ] Grafana dashboard showing data
- [ ] No errors in logs
- [ ] System monitoring plan in place
- [ ] Data collection phase started
- [ ] Calendar reminder set for 2 weeks (Task 9) and 4 weeks (Task 11)
