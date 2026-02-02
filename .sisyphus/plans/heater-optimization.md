# Smart Heater Optimization System

## TL;DR

> **Quick Summary**: Build a reliable, intelligent heating control system that maintains 24-27°C room temperature while minimizing electricity usage. Starts with rule-based control + data collection, transitions to MPC (Model Predictive Control), then ML optimization after sufficient data.
> 
> **Deliverables**:
> - Docker-based Python control service with hysteresis logic
> - Data collection pipeline to InfluxDB
> - Comprehensive Grafana dashboard
> - Multi-channel alerting (Push + Discord)
> - RC thermal model for predictive control
> - XGBoost ML model (Phase 2)
> 
> **Estimated Effort**: Large (3-4 weeks for Phase 1, ongoing for Phase 2)
> **Parallel Execution**: YES - 3 waves
> **Critical Path**: Task 1 (HA API) → Task 3 (Data Collection) → Task 5 (Control Service) → Task 8 (Integration Testing)

---

## Context

### Original Request
User wants to optimize electricity bill by maintaining room temperature at 25-26°C (flexible to 24-27°C for savings). They have temperature/humidity sensors, outdoor weather API, heater toggle API, and electricity usage API via Home Assistant. Goal is to build an ML-optimized system that minimizes electricity usage while maintaining comfort.

### Interview Summary
**Key Discussions**:
- Heater: Daikin S25PTES-W heat pump (2.5kW class, mode+on/off control only)
- Single room scope
- Tiered electricity pricing (usage-based, not time-of-use)
- Billing cycle resets on 21st of each month
- Temperature flexibility: 24-27°C acceptable, hysteresis: ON@25°C, OFF@26°C
- Failure mode: Alert and wait for manual intervention
- Dashboard: Comprehensive with graphs, predictions, controls
- Resources: Docker, Cloudflare Workers, InfluxDB (existing), ML training capability

**Research Findings**:
- **Home Assistant control**: Use `climate.turn_on/off` via REST API with retry logic + WebSocket for monitoring
- **ML model**: XGBoost for 15-min prediction (not LSTM - need 6+ months data)
- **Thermal model**: 1R1C RC model, fit from 2 weeks data, refit weekly
- **Control strategy**: Rule-based → MPC → Offline RL (PPO) transition
- **Safety**: Min 3-5min cycle times critical for compressor protection

### Metis Review
**Identified Gaps** (addressed):
- Heat pump specs: Estimated 0.6-1.0kW based on 2.5kW class
- Minimum cycle times: Using standard 3-5 min
- Hysteresis band: User chose tight 1°C (25-26°C)
- Billing cycle: Resets on 21st
- Edge cases: Added sensor failure handling, API retry logic, manual override detection

---

## Work Objectives

### Core Objective
Build a reliable, intelligent heating control system that maintains 24-27°C room temperature while minimizing electricity costs by staying in lower tier pricing brackets.

### Concrete Deliverables
1. **heater-control** Docker container - Python service controlling heater via HA API
2. **data-collector** Docker container - Collects sensor data to InfluxDB
3. **Grafana dashboard** - Temperature, electricity, heater state, predictions
4. **Alerting system** - Push notifications + Discord webhook
5. **Thermal model** - 1R1C RC model fitted from collected data
6. **ML model** (Phase 2) - XGBoost for temperature prediction

### Definition of Done
- [ ] Room temperature stays within 24-27°C for 7 consecutive days
- [ ] No compressor short-cycling observed (min 3min between state changes)
- [ ] Alerts fire within 60 seconds of sensor failure
- [ ] Dashboard displays all required metrics
- [ ] System recovers automatically from container restarts
- [ ] Tier boundary tracking shows current monthly usage

### Must Have
- Hysteresis control (ON@25°C, OFF@26°C)
- Minimum 3-minute cycle enforcement
- Multi-channel alerting (push + Discord)
- Data persistence across restarts
- Manual override capability via dashboard
- Tier usage tracking and display

### Must NOT Have (Guardrails)
- ❌ Multi-room support
- ❌ Additional appliance control (water heater, etc.)
- ❌ Mobile application (use Grafana)
- ❌ Voice assistant integration
- ❌ Complex scheduling/modes (vacation, guest, etc.)
- ❌ Automatic ML retraining pipeline (manual in Phase 2)
- ❌ Temperature setpoint control (binary on/off only)
- ❌ Shorter than 3-minute cycles (compressor protection)

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: NO (new project)
- **User wants tests**: Both automated + manual
- **Framework**: pytest for Python services

### If TDD Enabled

Each TODO follows RED-GREEN-REFACTOR:

**Task Structure:**
1. **RED**: Write failing test first
   - Test file: `tests/test_*.py`
   - Test command: `pytest tests/ -v`
   - Expected: FAIL (test exists, implementation doesn't)
2. **GREEN**: Implement minimum code to pass
   - Command: `pytest tests/ -v`
   - Expected: PASS
3. **REFACTOR**: Clean up while keeping green
   - Command: `pytest tests/ -v`
   - Expected: PASS (still)

**Test Setup Task (if infrastructure doesn't exist):**
- [ ] 0. Setup Test Infrastructure
  - Install: `pip install pytest pytest-asyncio pytest-mock`
  - Config: Create `pytest.ini`
  - Verify: `pytest --version` → shows version
  - Example: Create `tests/test_example.py`
  - Verify: `pytest tests/` → 1 test passes

### Automated Verification

Each TODO includes EXECUTABLE verification procedures that agents can run directly:

**By Deliverable Type:**

| Type | Verification Tool | Automated Procedure |
|------|------------------|---------------------|
| **API/Backend** | curl / httpie via Bash | Agent sends request, parses response, validates JSON fields |
| **Docker services** | docker compose + curl | Agent starts services, runs health checks, validates output |
| **InfluxDB writes** | influx CLI via Bash | Agent queries InfluxDB, validates data points exist |
| **Grafana dashboard** | curl API + Playwright | Agent checks dashboard JSON, screenshots panels |
| **Alerting** | curl Discord webhook | Agent triggers test alert, verifies delivery |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately):
├── Task 1: Home Assistant API Integration Module
├── Task 2: Project Setup + Docker Configuration
└── Task 7: Alerting System (Push + Discord)

Wave 2 (After Wave 1):
├── Task 3: Data Collection Service (depends: 1, 2)
├── Task 4: Grafana Dashboard Setup (depends: 2)
└── Task 6: Electricity Tier Tracker (depends: 1, 2)

Wave 3 (After Wave 2):
├── Task 5: Control Service with Hysteresis (depends: 1, 3)
└── Task 8: Integration Testing + Validation (depends: 3, 4, 5, 6, 7)

Wave 4 (After Wave 3 - Data Collection Period):
└── Task 9: Thermal Model (1R1C) Fitting (depends: 3)

Wave 5 (After 4+ weeks of data - Phase 2):
├── Task 10: MPC Controller (depends: 9)
└── Task 11: XGBoost ML Model Training (depends: 3, 10)

Critical Path: Task 1 → Task 3 → Task 5 → Task 8 → Task 9 → Task 10
Parallel Speedup: ~45% faster than sequential
```

### Dependency Matrix

| Task | Depends On | Blocks | Can Parallelize With |
|------|------------|--------|---------------------|
| 1 | None | 3, 5, 6 | 2, 7 |
| 2 | None | 3, 4, 6 | 1, 7 |
| 3 | 1, 2 | 5, 8, 9, 11 | 4, 6 |
| 4 | 2 | 8 | 3, 6 |
| 5 | 1, 3 | 8 | 6 |
| 6 | 1, 2 | 8 | 3, 4 |
| 7 | None | 8 | 1, 2 |
| 8 | 3, 4, 5, 6, 7 | 9 | None (integration) |
| 9 | 3 (+ 2 weeks data) | 10 | None |
| 10 | 9 | 11 | None |
| 11 | 3, 10 | None | None |

### Agent Dispatch Summary

| Wave | Tasks | Recommended Agents |
|------|-------|-------------------|
| 1 | 1, 2, 7 | delegate_task(category="unspecified-high", load_skills=[], run_in_background=true) × 3 |
| 2 | 3, 4, 6 | dispatch parallel after Wave 1 completes |
| 3 | 5, 8 | 5 after 3 completes; 8 after all complete |
| 4 | 9 | After 2+ weeks of data collection |
| 5 | 10, 11 | After thermal model validated |

---

## TODOs

### Phase 1: Core Infrastructure (Weeks 1-2)

- [x] 1. Home Assistant API Integration Module

  **What to do**:
  - Create Python module for HA REST API communication
  - Implement `climate.turn_on`, `climate.turn_off`, `climate.set_hvac_mode` wrappers
  - Add sensor reading functions (temperature, humidity, heater state, weather)
  - Implement retry logic with exponential backoff (3 retries, 1s/2s/4s)
  - Add WebSocket subscription for real-time state monitoring
  - Handle authentication via long-lived access token
  - Implement state verification after commands (verify heater actually changed)

  **Must NOT do**:
  - Temperature setpoint control (not supported by this unit)
  - Direct manipulation of HA config files
  - Caching that could mask actual state

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Core infrastructure module with reliability requirements
  - **Skills**: `[]`
    - No special skills needed - standard Python development
  - **Skills Evaluated but Omitted**:
    - `playwright`: Not needed - no browser automation for API work

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 7)
  - **Blocks**: Tasks 3, 5, 6
  - **Blocked By**: None (can start immediately)

  **References**:

  **External References** (libraries and frameworks):
  - Home Assistant REST API docs: https://developers.home-assistant.io/docs/api/rest/
  - Home Assistant WebSocket API: https://developers.home-assistant.io/docs/api/websocket/
  - `aiohttp` library for async HTTP: https://docs.aiohttp.org/
  - `websockets` library: https://websockets.readthedocs.io/

  **WHY Each Reference Matters**:
  - REST API docs show exact endpoints and authentication headers needed
  - WebSocket API enables real-time state monitoring without polling
  - aiohttp provides async HTTP client suitable for long-running service
  - websockets library handles HA's WebSocket protocol

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] Test file created: `tests/test_ha_client.py`
  - [ ] Test covers: successful turn_on command returns True
  - [ ] Test covers: failed command after 3 retries raises HaApiError
  - [ ] Test covers: state verification detects mismatch
  - [ ] `pytest tests/test_ha_client.py -v` → PASS (4+ tests)

  **Automated Verification:**
  ```bash
  # Agent runs from project directory:
  
  # 1. Test connection to HA
  curl -s -X GET "http://192.168.1.110:8123/api/" \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    | jq '.message'
  # Assert: Returns "API running."
  
  # 2. Test reading temperature sensor
  curl -s -X GET "http://192.168.1.110:8123/api/states/sensor.temperature" \
    -H "Authorization: Bearer $HA_TOKEN" \
    | jq '.state'
  # Assert: Returns numeric value (e.g., "24.5")
  
  # 3. Test reading climate entity
  curl -s -X GET "http://192.168.1.110:8123/api/states/climate.heater" \
    -H "Authorization: Bearer $HA_TOKEN" \
    | jq '.state'
  # Assert: Returns one of "heat", "cool", "off"
  ```

  **Evidence to Capture:**
  - [ ] curl output showing successful API responses
  - [ ] pytest output showing all tests pass
  - [ ] Module exports: `HaClient`, `HaApiError`, sensor reading functions

  **Commit**: YES
  - Message: `feat(ha-client): add Home Assistant API integration module with retry logic`
  - Files: `src/ha_client.py`, `tests/test_ha_client.py`
  - Pre-commit: `pytest tests/test_ha_client.py`

---

- [x] 2. Project Setup + Docker Configuration

  **What to do**:
  - Create project directory structure
  - Set up Python project with `pyproject.toml`
  - Create Dockerfile for control service
  - Create `docker-compose.yml` with services: control, data-collector
  - Configure environment variables (HA URL, token, InfluxDB connection)
  - Set up health check endpoints for each service
  - Create `.env.example` with required variables
  - Add pytest configuration

  **Must NOT do**:
  - Include secrets in docker-compose.yml (use .env)
  - Hardcode HA endpoint or credentials
  - Add unnecessary services (keep minimal)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Standard project scaffolding, well-defined structure
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 7)
  - **Blocks**: Tasks 3, 4, 6
  - **Blocked By**: None (can start immediately)

  **References**:

  **External References**:
  - Docker Python best practices: https://docs.docker.com/language/python/
  - InfluxDB Python client: https://github.com/influxdata/influxdb-client-python

  **WHY Each Reference Matters**:
  - Docker docs show multi-stage builds and security best practices
  - InfluxDB client shows connection patterns for time-series writes

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] `pytest --version` returns version number
  - [ ] `pytest tests/test_example.py` → PASS (1 test)

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Verify project structure
  ls -la src/ tests/ docker-compose.yml Dockerfile pyproject.toml
  # Assert: All files exist
  
  # 2. Verify Docker build
  docker compose build --no-cache
  # Assert: Exit code 0, no errors
  
  # 3. Verify containers start
  docker compose up -d
  sleep 5
  docker compose ps --format json | jq '.[].State'
  # Assert: All states are "running"
  
  # 4. Verify health endpoint
  curl -s http://localhost:8080/health | jq '.status'
  # Assert: Returns "healthy"
  
  # Cleanup
  docker compose down
  ```

  **Evidence to Capture:**
  - [ ] docker compose ps output showing healthy containers
  - [ ] Health endpoint response

  **Commit**: YES
  - Message: `chore(setup): initialize project structure with Docker and pytest`
  - Files: `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `pytest.ini`
  - Pre-commit: `docker compose build`

---

- [ ] 3. Data Collection Service

  **What to do**:
  - Create data collector service that polls HA sensors
  - Write to InfluxDB: temperature, humidity, heater_state, weather_forecast, electricity_usage
  - Implement polling intervals: temperature/humidity every 60s, weather every 5min, electricity daily
  - Add data validation (reject impossible values: temp < -40 or > 60)
  - Log all data points with timestamps
  - Handle InfluxDB connection failures gracefully (buffer in memory, retry)
  - Store heater state changes as events (not just periodic polls)

  **Must NOT do**:
  - Poll more frequently than 60s for temperature (unnecessary load)
  - Drop data on temporary InfluxDB failure (must buffer)
  - Store raw weather forecast (store relevant fields only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Critical data pipeline, reliability requirements
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 4, 6)
  - **Blocks**: Tasks 5, 8, 9, 11
  - **Blocked By**: Tasks 1, 2

  **References**:

  **External References**:
  - InfluxDB Python client write API: https://influxdb-client-python.readthedocs.io/en/stable/api.html#writeapi
  - InfluxDB line protocol: https://docs.influxdata.com/influxdb/v2/reference/syntax/line-protocol/

  **WHY Each Reference Matters**:
  - Write API docs show batch writing patterns for efficiency
  - Line protocol reference ensures correct data formatting

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] Test file: `tests/test_data_collector.py`
  - [ ] Test covers: valid temperature writes to InfluxDB
  - [ ] Test covers: invalid temperature (-50°C) is rejected
  - [ ] Test covers: InfluxDB failure triggers buffering
  - [ ] `pytest tests/test_data_collector.py -v` → PASS

  **Automated Verification:**
  ```bash
  # Agent runs after service runs for 5 minutes:
  
  # 1. Query InfluxDB for recent temperature data
  influx query 'from(bucket:"heater") |> range(start: -5m) |> filter(fn: (r) => r._measurement == "temperature")' \
    --host http://YOUR_INFLUXDB_HOST:8086 \
    --token $INFLUX_TOKEN \
    --org $INFLUX_ORG
  # Assert: Returns 3+ data points (5min ÷ 60s = 5 expected)
  
  # 2. Verify heater state recorded
  influx query 'from(bucket:"heater") |> range(start: -5m) |> filter(fn: (r) => r._measurement == "heater_state")'
  # Assert: Returns at least 1 data point
  
  # 3. Check container logs for errors
  docker compose logs data-collector --tail 50 | grep -i "error"
  # Assert: No critical errors
  ```

  **Evidence to Capture:**
  - [ ] InfluxDB query output showing temperature data points
  - [ ] Docker logs showing successful writes

  **Commit**: YES
  - Message: `feat(data-collector): add sensor data collection to InfluxDB`
  - Files: `src/data_collector.py`, `tests/test_data_collector.py`
  - Pre-commit: `pytest tests/test_data_collector.py`

---

- [ ] 4. Grafana Dashboard Setup

  **What to do**:
  - Create Grafana dashboard JSON with panels:
    - Current temperature (gauge)
    - Temperature history (time series, 24h and 7d views)
    - Heater state indicator (on/off)
    - Current electricity tier and monthly usage
    - Outdoor temperature + forecast
    - Control buttons (manual on/off override)
  - Configure InfluxDB as data source
  - Set up dashboard auto-refresh (30s)
  - Add temperature threshold lines (24°C, 27°C) on time series
  - Export dashboard JSON for version control

  **Must NOT do**:
  - Create mobile-specific views (use responsive Grafana)
  - Add complex alerting rules in Grafana (use separate alerting service)
  - Include admin panels (separate concern)

  **Recommended Agent Profile**:
  - **Category**: `visual-engineering`
    - Reason: Dashboard design, visualization layout
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - `frontend-ui-ux`: Grafana uses declarative JSON, not custom CSS/components

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 6)
  - **Blocks**: Task 8
  - **Blocked By**: Task 2

  **References**:

  **External References**:
  - Grafana dashboard JSON model: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/view-dashboard-json-model/
  - InfluxDB Flux queries in Grafana: https://grafana.com/docs/grafana/latest/datasources/influxdb/

  **WHY Each Reference Matters**:
  - JSON model reference enables version-controlled dashboard definitions
  - Flux query docs show how to build efficient time-series queries

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Import dashboard via API
  curl -X POST "http://localhost:3000/api/dashboards/db" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $GRAFANA_TOKEN" \
    -d @grafana/dashboard.json
  # Assert: Returns {"status": "success"}
  
  # 2. Verify dashboard loads
  curl -s "http://localhost:3000/api/dashboards/uid/heater-optimization" \
    -H "Authorization: Bearer $GRAFANA_TOKEN" \
    | jq '.dashboard.title'
  # Assert: Returns "Heater Optimization"
  
  # 3. Screenshot via Playwright (if available)
  # Navigate to http://localhost:3000/d/heater-optimization
  # Screenshot to .sisyphus/evidence/dashboard.png
  ```

  **Evidence to Capture:**
  - [ ] Dashboard JSON file in version control
  - [ ] Screenshot of dashboard with sample data

  **Commit**: YES
  - Message: `feat(dashboard): add Grafana dashboard for heater monitoring`
  - Files: `grafana/dashboard.json`, `docker-compose.yml` (add Grafana service)
  - Pre-commit: `docker compose up -d grafana && sleep 10`

---

- [ ] 5. Control Service with Hysteresis Logic

  **What to do**:
  - Create control service implementing state machine:
    ```
    IDLE          → monitoring, heater off
    HEATING       → heater on, waiting for target
    COOLDOWN      → heater off, minimum cycle timer (3min)
    MANUAL_OVERRIDE → user took control, waiting timeout (30min)
    FAILURE       → something broken, alerting
    ```
  - Implement hysteresis: ON at 25°C, OFF at 26°C
  - Enforce minimum 3-minute off-cycle (compressor protection)
  - Verify heater state after command (retry if mismatch)
  - Log all decisions with reasoning
  - Expose state via health endpoint
  - Handle sensor data staleness (alert if no data for 5min)

  **Must NOT do**:
  - Cycle faster than 3 minutes
  - Ignore state verification failures
  - Make decisions with stale data (>5min old)
  - Override manual control immediately

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Critical control logic, reliability requirements
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after Task 3)
  - **Blocks**: Task 8
  - **Blocked By**: Tasks 1, 3

  **References**:

  **External References**:
  - Python state machine libraries: https://github.com/pytransitions/transitions
  - Hysteresis control theory: https://en.wikipedia.org/wiki/Hysteresis#Control_systems

  **WHY Each Reference Matters**:
  - Transitions library provides clean state machine implementation
  - Hysteresis theory explains deadband control for preventing oscillation

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] Test file: `tests/test_controller.py`
  - [ ] Test: heater turns ON when temp drops below 25°C
  - [ ] Test: heater turns OFF when temp reaches 26°C
  - [ ] Test: minimum 3min cycle enforced (state stays COOLDOWN)
  - [ ] Test: stale data (>5min) triggers FAILURE state
  - [ ] Test: manual override respected for 30min
  - [ ] `pytest tests/test_controller.py -v` → PASS (5+ tests)

  **Automated Verification:**
  ```bash
  # Agent runs after controller is running:
  
  # 1. Check current state via health endpoint
  curl -s http://localhost:8080/health | jq '.state'
  # Assert: Returns one of "IDLE", "HEATING", "COOLDOWN", "MANUAL_OVERRIDE"
  
  # 2. Check control loop is running
  docker compose logs control --tail 20 | grep "Control decision"
  # Assert: Shows recent decision logs
  
  # 3. Verify minimum cycle time (run for 10min, check logs)
  docker compose logs control --since 10m | grep -c "state change"
  # Assert: ≤ 3 state changes in 10 minutes (no short-cycling)
  ```

  **Evidence to Capture:**
  - [ ] pytest output showing all tests pass
  - [ ] Container logs showing control decisions
  - [ ] Health endpoint showing state machine status

  **Commit**: YES
  - Message: `feat(controller): add hysteresis control with state machine`
  - Files: `src/controller.py`, `tests/test_controller.py`
  - Pre-commit: `pytest tests/test_controller.py`

---

- [ ] 6. Electricity Tier Tracker

  **What to do**:
  - Create tier tracking module that:
    - Queries electricity usage from HA/GraphQL API
    - Tracks cumulative kWh since billing cycle start (21st)
    - Calculates current tier and cost
    - Predicts tier boundary crossing based on current usage rate
    - Stores daily usage to InfluxDB
  - Handle delayed data (previous day available at ~9am)
  - Calculate estimated heater contribution to usage
  - Expose current tier via API endpoint

  **Must NOT do**:
  - Assume real-time electricity data (it's delayed 9hrs)
  - Make control decisions based on electricity alone (temperature takes priority)
  - Store raw GraphQL responses (extract needed fields only)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-low`
    - Reason: Straightforward data aggregation, no complex logic
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 3, 4)
  - **Blocks**: Task 8
  - **Blocked By**: Tasks 1, 2

  **References**:

  **External References**:
  - GraphQL Python client: https://gql.readthedocs.io/
  - Japanese electricity tier pricing example (reference for logic)

  **WHY Each Reference Matters**:
  - GQL library handles GraphQL queries to provider API
  - Tier logic reference ensures correct bracket calculations

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] Test file: `tests/test_tier_tracker.py`
  - [ ] Test: correctly identifies tier 1 (0-120kWh)
  - [ ] Test: correctly identifies tier 2 (120-300kWh)
  - [ ] Test: handles billing cycle rollover (21st reset)
  - [ ] `pytest tests/test_tier_tracker.py -v` → PASS

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Query current tier via API
  curl -s http://localhost:8080/api/tier | jq '.'
  # Assert: Returns {"tier": N, "usage_kwh": X, "days_remaining": Y}
  
  # 2. Verify tier data in InfluxDB
  influx query 'from(bucket:"heater") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "electricity")'
  # Assert: Returns data points
  ```

  **Evidence to Capture:**
  - [ ] Tier API response
  - [ ] InfluxDB electricity data points

  **Commit**: YES
  - Message: `feat(tier-tracker): add electricity tier tracking and prediction`
  - Files: `src/tier_tracker.py`, `tests/test_tier_tracker.py`
  - Pre-commit: `pytest tests/test_tier_tracker.py`

---

- [x] 7. Alerting System (Push + Discord)

  **What to do**:
  - Create alerting module with multi-channel support:
    - Home Assistant push notifications (companion app)
    - Discord webhook backup
  - Alert types:
    - CRITICAL: Temperature outside 24-27°C hard limits
    - CRITICAL: Sensor failure (no data for 5min)
    - CRITICAL: HA API unreachable after retries
    - WARNING: Approaching tier boundary (predicted within 3 days)
    - INFO: System state changes (for debugging)
  - Implement alert deduplication (same alert once per 30min)
  - Add alert acknowledgment mechanism
  - Log all alerts with timestamps

  **Must NOT do**:
  - Spam alerts (enforce 30min dedup)
  - Send INFO alerts to Discord (push only)
  - Block on alert delivery failure

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward integration, well-defined APIs
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2)
  - **Blocks**: Task 8
  - **Blocked By**: None (can start immediately)

  **References**:

  **External References**:
  - HA notification service: https://www.home-assistant.io/integrations/notify/
  - Discord webhook API: https://discord.com/developers/docs/resources/webhook

  **WHY Each Reference Matters**:
  - HA notify docs show how to trigger push notifications
  - Discord webhook docs show payload format for messages

  **Acceptance Criteria**:

  **Tests (TDD):**
  - [ ] Test file: `tests/test_alerting.py`
  - [ ] Test: critical alert sends to both channels
  - [ ] Test: duplicate alert within 30min is suppressed
  - [ ] Test: Discord failure doesn't block push notification
  - [ ] `pytest tests/test_alerting.py -v` → PASS

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Trigger test alert via API
  curl -X POST http://localhost:8080/api/alert/test \
    -H "Content-Type: application/json" \
    -d '{"type": "test", "message": "Automated test alert"}'
  # Assert: Returns {"status": "sent", "channels": ["push", "discord"]}
  
  # 2. Verify Discord webhook received message
  # (Check Discord channel or use webhook.site for testing)
  
  # 3. Verify deduplication
  curl -X POST http://localhost:8080/api/alert/test -d '{"type": "test", "message": "Same alert"}'
  curl -X POST http://localhost:8080/api/alert/test -d '{"type": "test", "message": "Same alert"}'
  # Assert: Second call returns {"status": "deduplicated"}
  ```

  **Evidence to Capture:**
  - [ ] Discord message screenshot or webhook.site capture
  - [ ] Push notification screenshot (from phone)

  **Commit**: YES
  - Message: `feat(alerting): add multi-channel alerting with deduplication`
  - Files: `src/alerting.py`, `tests/test_alerting.py`
  - Pre-commit: `pytest tests/test_alerting.py`

---

- [ ] 8. Integration Testing + Validation

  **What to do**:
  - Create end-to-end integration tests:
    - Full control loop with mock HA API
    - Data flow: sensor → InfluxDB → Grafana
    - Alert triggering and delivery
    - Container orchestration (start/stop/restart)
  - Run system for 24hrs in test mode
  - Verify temperature stays within bounds
  - Verify no short-cycling occurs
  - Document any issues found

  **Must NOT do**:
  - Test against production HA without safeguards
  - Skip container restart testing
  - Ignore intermittent failures

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Requires thorough testing across multiple components
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - `playwright`: Only if Grafana UI testing needed

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 3 (after all Wave 2 tasks)
  - **Blocks**: Task 9 (ML phase)
  - **Blocked By**: Tasks 3, 4, 5, 6, 7

  **References**:

  **External References**:
  - pytest-docker for container testing: https://github.com/avast/pytest-docker
  - Integration testing best practices

  **WHY Each Reference Matters**:
  - pytest-docker enables automated container lifecycle testing
  - Best practices ensure comprehensive coverage

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # Agent runs full integration test suite:
  
  # 1. Run integration tests
  pytest tests/integration/ -v --tb=short
  # Assert: All tests pass
  
  # 2. Run 24hr stability test (or shorter for CI)
  docker compose up -d
  sleep 86400  # or 3600 for 1hr smoke test
  
  # 3. Verify temperature stayed in bounds
  influx query 'from(bucket:"heater") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "temperature") |> filter(fn: (r) => r._value < 24 or r._value > 27) |> count()'
  # Assert: Count is 0 (no out-of-bounds readings)
  
  # 4. Verify no short-cycling
  docker compose logs control --since 24h | grep "state change" | head -100
  # Assert: No two state changes within 3 minutes
  
  # 5. Verify containers recovered from restart
  docker compose restart control
  sleep 30
  curl -s http://localhost:8080/health | jq '.status'
  # Assert: Returns "healthy"
  ```

  **Evidence to Capture:**
  - [ ] Integration test results
  - [ ] 24hr temperature graph screenshot
  - [ ] State change log analysis

  **Commit**: YES
  - Message: `test(integration): add end-to-end integration tests`
  - Files: `tests/integration/`, test reports
  - Pre-commit: `pytest tests/integration/ -v`

---

### Phase 2: Predictive Control (Week 4+, after data collection)

- [ ] 9. Thermal Model (1R1C) Fitting

  **What to do**:
  - Implement 1R1C thermal model:
    ```python
    dT_indoor/dt = (1/RC) * (T_outdoor - T_indoor) + (P_heater / C) * heater_state
    ```
  - Fit model parameters (R, C, P) from collected data using scipy.optimize
  - Validate model accuracy (MAE < 0.5°C for 15min predictions)
  - Create prediction function for temperature 15min-2hr ahead
  - Implement weekly refitting schedule
  - Store model parameters in InfluxDB for tracking

  **Must NOT do**:
  - Fit with less than 2 weeks of data
  - Use model without validation
  - Assume static parameters (weather/season changes)

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: Mathematical modeling, optimization, requires analytical thinking
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after 2+ weeks data collection)
  - **Blocks**: Tasks 10, 11
  - **Blocked By**: Task 3 (needs collected data)

  **References**:

  **External References**:
  - darkgreybox library (RC models): https://github.com/czagoni/darkgreybox
  - scipy.optimize.minimize: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize.html
  - Bacher & Madsen 2011 paper (RC model theory)

  **WHY Each Reference Matters**:
  - darkgreybox shows reference implementation of building thermal models
  - scipy.optimize provides parameter fitting via nonlinear least squares
  - Academic paper provides theoretical foundation

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Fit model on historical data
  python -c "from src.thermal_model import fit_model; params = fit_model(); print(params)"
  # Assert: Returns {"R": float, "C": float, "P": float}
  
  # 2. Validate prediction accuracy
  python -c "from src.thermal_model import validate_model; mae = validate_model(); print(f'MAE: {mae}')"
  # Assert: MAE < 0.5°C
  
  # 3. Test prediction function
  python -c "from src.thermal_model import predict; t = predict(current_temp=25, outdoor_temp=10, heater_on=True, horizon_min=15); print(t)"
  # Assert: Returns reasonable temperature (20-30°C range)
  ```

  **Evidence to Capture:**
  - [ ] Model parameters (R, C, P values)
  - [ ] Validation MAE metric
  - [ ] Prediction vs actual comparison plot

  **Commit**: YES
  - Message: `feat(thermal-model): add 1R1C thermal model with parameter fitting`
  - Files: `src/thermal_model.py`, `tests/test_thermal_model.py`
  - Pre-commit: `pytest tests/test_thermal_model.py`

---

- [ ] 10. MPC (Model Predictive Control) Controller

  **What to do**:
  - Implement MPC using thermal model:
    - Predict temperature 2hrs ahead for different control sequences
    - Optimize for minimum energy while staying in 24-27°C
    - Apply first action, recompute every 15min
  - Integrate with existing state machine (replace simple hysteresis)
  - Add fallback to hysteresis if model unavailable
  - Log predictions vs actual for model improvement

  **Must NOT do**:
  - Remove safety constraints (min cycle time, hard limits)
  - Make MPC mandatory (must fallback gracefully)
  - Optimize beyond 2hr horizon (diminishing returns)

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: Control theory, optimization, complex logic
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 5 (after thermal model)
  - **Blocks**: Task 11
  - **Blocked By**: Task 9

  **References**:

  **External References**:
  - MPC theory for HVAC: https://en.wikipedia.org/wiki/Model_predictive_control
  - scipy.optimize for trajectory optimization

  **WHY Each Reference Matters**:
  - MPC theory explains receding horizon control
  - scipy provides optimization tools for control sequence selection

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Test MPC decision
  python -c "from src.mpc_controller import get_action; action = get_action(current_temp=25.5, outdoor_temp=5); print(action)"
  # Assert: Returns "on" or "off"
  
  # 2. Verify MPC respects safety constraints
  python -c "from src.mpc_controller import get_action; action = get_action(current_temp=24, outdoor_temp=5, last_state_change_seconds=60); print(action)"
  # Assert: Returns current state (cooldown enforced)
  
  # 3. Run A/B comparison (MPC vs hysteresis) on historical data
  python scripts/compare_controllers.py --days 7
  # Assert: MPC energy usage ≤ hysteresis energy usage
  ```

  **Evidence to Capture:**
  - [ ] MPC decision logs
  - [ ] Energy comparison: MPC vs hysteresis
  - [ ] Prediction accuracy over time

  **Commit**: YES
  - Message: `feat(mpc): add Model Predictive Control for optimized heating`
  - Files: `src/mpc_controller.py`, `tests/test_mpc_controller.py`
  - Pre-commit: `pytest tests/test_mpc_controller.py`

---

- [ ] 11. XGBoost ML Model Training

  **What to do**:
  - Train XGBoost model for 15min temperature prediction
  - Features: outdoor_temp, indoor_temp, heater_state, time_of_day, day_of_week, heater_on_duration, temp_change_rate
  - Target: temperature 15min ahead
  - Implement training script with hyperparameter tuning
  - Evaluate against thermal model (should be comparable or better)
  - Set up manual retraining process (not automatic)
  - Store model artifacts and metrics

  **Must NOT do**:
  - Automatic retraining (manual process for Phase 2)
  - Replace MPC entirely (ML augments, doesn't replace)
  - Train with less than 4 weeks of data

  **Recommended Agent Profile**:
  - **Category**: `ultrabrain`
    - Reason: ML training, hyperparameter optimization, evaluation
  - **Skills**: `[]`
    - No special skills needed
  - **Skills Evaluated but Omitted**:
    - None relevant

  **Parallelization**:
  - **Can Run In Parallel**: Partial (with Task 10 after thermal model)
  - **Parallel Group**: Wave 5
  - **Blocks**: None (final task)
  - **Blocked By**: Tasks 3, 10

  **References**:

  **External References**:
  - XGBoost documentation: https://xgboost.readthedocs.io/
  - scikit-learn model evaluation: https://scikit-learn.org/stable/modules/model_evaluation.html

  **WHY Each Reference Matters**:
  - XGBoost docs show training API and hyperparameter options
  - sklearn evaluation provides metrics for model comparison

  **Acceptance Criteria**:

  **Automated Verification:**
  ```bash
  # Agent runs:
  
  # 1. Train model
  python scripts/train_xgboost.py --data-days 28
  # Assert: Creates models/xgboost_temp.json
  
  # 2. Evaluate model
  python scripts/evaluate_model.py --model xgboost
  # Assert: MAE < 0.5°C (comparable to thermal model)
  
  # 3. Test inference speed
  python -c "import time; from src.ml_predictor import predict; start=time.time(); [predict() for _ in range(100)]; print((time.time()-start)/100)"
  # Assert: < 10ms per prediction
  ```

  **Evidence to Capture:**
  - [ ] Model metrics (MAE, RMSE)
  - [ ] Feature importance plot
  - [ ] Comparison with thermal model

  **Commit**: YES
  - Message: `feat(ml): add XGBoost temperature prediction model`
  - Files: `src/ml_predictor.py`, `scripts/train_xgboost.py`, `models/`
  - Pre-commit: `pytest tests/test_ml_predictor.py`

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `feat(ha-client): add Home Assistant API integration module` | src/ha_client.py, tests/ | pytest |
| 2 | `chore(setup): initialize project structure with Docker` | pyproject.toml, Dockerfile, docker-compose.yml | docker compose build |
| 3 | `feat(data-collector): add sensor data collection to InfluxDB` | src/data_collector.py | pytest |
| 4 | `feat(dashboard): add Grafana dashboard for heater monitoring` | grafana/dashboard.json | curl API |
| 5 | `feat(controller): add hysteresis control with state machine` | src/controller.py | pytest |
| 6 | `feat(tier-tracker): add electricity tier tracking` | src/tier_tracker.py | pytest |
| 7 | `feat(alerting): add multi-channel alerting` | src/alerting.py | pytest |
| 8 | `test(integration): add end-to-end integration tests` | tests/integration/ | pytest |
| 9 | `feat(thermal-model): add 1R1C thermal model` | src/thermal_model.py | pytest |
| 10 | `feat(mpc): add Model Predictive Control` | src/mpc_controller.py | pytest |
| 11 | `feat(ml): add XGBoost temperature prediction` | src/ml_predictor.py | pytest |

---

## Success Criteria

### Verification Commands
```bash
# System health check
docker compose ps  # All containers running
curl http://localhost:8080/health  # Returns {"status": "healthy"}

# Data collection verification
influx query 'from(bucket:"heater") |> range(start: -1h) |> count()'
# Expected: Multiple data points per measurement

# Temperature compliance
influx query 'from(bucket:"heater") |> range(start: -7d) |> filter(fn: (r) => r._measurement == "temperature") |> filter(fn: (r) => r._value < 24 or r._value > 27) |> count()'
# Expected: 0 (no violations)

# Alert test
curl -X POST http://localhost:8080/api/alert/test
# Expected: {"status": "sent"}

# Control decisions
docker compose logs control --tail 10 | grep "decision"
# Expected: Recent control decisions logged
```

### Final Checklist
- [ ] All "Must Have" present:
  - [ ] Hysteresis control working
  - [ ] 3-minute cycle enforcement verified
  - [ ] Push + Discord alerts functional
  - [ ] Data persists across restarts
  - [ ] Manual override in dashboard works
  - [ ] Tier tracking displays correctly
- [ ] All "Must NOT Have" absent:
  - [ ] No multi-room code
  - [ ] No appliance code beyond heater
  - [ ] No mobile app
  - [ ] No voice integration
  - [ ] No complex scheduling
- [ ] All tests pass: `pytest tests/ -v`
- [ ] 7-day temperature compliance verified
- [ ] No short-cycling in logs
