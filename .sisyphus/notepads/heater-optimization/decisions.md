# Architectural Decisions - Heater Optimization

This file tracks key architectural and design decisions made during implementation.

---

## Task 2: Project Setup + Docker Configuration (2026-02-02)

### Decision: Multi-stage Docker Build
**Rationale**: Reduces final image size by ~60% (builder stage discarded, only runtime deps in final image)
**Alternative considered**: Single-stage build (simpler but larger images)
**Impact**: Faster container startup, lower storage/bandwidth costs

### Decision: Python 3.10 as Base Version
**Rationale**: Stable, widely supported, good balance of features and compatibility
**Alternative considered**: 3.11+ (newer but less stable), 3.9 (older but more compatible)
**Impact**: Aligns with pyproject.toml requires-python = ">=3.10"

### Decision: Separate Control and Data-Collector Services
**Rationale**: Allows independent scaling, failure isolation, and different restart policies if needed
**Alternative considered**: Single monolithic service (simpler but less flexible)
**Impact**: Enables parallel data collection and control logic without blocking

### Decision: InfluxDB + Grafana in docker-compose
**Rationale**: Complete observability stack in one compose file, easier local development
**Alternative considered**: Assume external InfluxDB/Grafana (requires manual setup)
**Impact**: New developers can `docker compose up` and have full stack running

### Decision: Health Checks on All Services
**Rationale**: Docker Compose can detect failures and restart automatically
**Alternative considered**: No health checks (rely on container exit codes)
**Impact**: Automatic recovery from transient failures (network hiccups, temporary service unavailability)

### Decision: Named Volumes for Data Persistence
**Rationale**: Data survives container restarts, easier to backup/migrate
**Alternative considered**: Bind mounts (tighter coupling to host filesystem)
**Impact**: Production-ready persistence without host filesystem dependencies

### Decision: Environment Variables for All Configuration
**Rationale**: Follows 12-factor app principles, enables same image across dev/prod
**Alternative considered**: Config files (harder to manage in containers)
**Impact**: Secure secrets handling via .env, no hardcoded values in code/images

### Decision: .env.example Pattern
**Rationale**: Documents all required variables, prevents missing config errors
**Alternative considered**: Hardcoded defaults (less transparent)
**Impact**: Clear onboarding for new developers, prevents "why isn't this working?" issues


## Controller Architecture Decisions (2025-02-03)

### State Machine Implementation
**Decision**: Used plain Python Enum instead of `transitions` library
**Rationale**: 
- Simpler implementation for this use case
- No external dependency needed
- Manual state management provides full control and transparency
- Easier to test and debug

### Health Endpoint Design
**Decision**: Integrated health endpoint into control_service.py using aiohttp
**Rationale**:
- aiohttp already a project dependency
- Runs control loop as background task while serving HTTP
- Single process/container for simplicity
- Health endpoint provides real-time controller state

### Configuration Management
**Decision**: All thresholds and timeouts configurable via environment variables with sensible defaults
**Rationale**:
- Flexible deployment (dev/staging/prod different settings)
- Easy to tune without code changes
- Follows 12-factor app principles
- Defaults match requirements specification

### Error Handling Strategy
**Decision**: Enter FAILURE state on critical errors, send alerts, but keep service running
**Rationale**:
- Fail-safe behavior: don't silently continue with stale data
- Alerts notify operators of issues
- Service keeps running to potentially recover
- Health endpoint shows FAILURE state for monitoring

### Timestamp Handling
**Decision**: Handle both timezone-aware and naive datetimes in staleness check
**Rationale**:
- HA API may return timestamps in different formats
- Robust implementation prevents crashes on timezone issues
- Compares apples-to-apples (both naive or both aware)

### Retry Logic
**Decision**: 3 retries with 2-second delays, then FAILURE state
**Rationale**:
- Tolerates transient network issues
- 2-second delay allows HA to process command
- Max 3 attempts prevents infinite loops
- FAILURE state ensures operator awareness

