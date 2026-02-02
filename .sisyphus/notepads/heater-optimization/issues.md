# Issues & Gotchas - Heater Optimization

This file tracks problems encountered and their solutions.

---

## Task 1: HA Client Module (2026-02-02)

### Minor Issues Resolved
- **Unused imports**: Initial test file had `asyncio`, `PropertyMock` imports not used - removed
- **Import sorting**: Ruff flagged unsorted imports - auto-fixed with `ruff --fix`
- **LSP not available**: basedpyright not installed - used ruff for static analysis instead

### Notes for Future Tasks
- `turn_on()` expects state to become "heat", `turn_off()` expects "off"
- `_verify_state()` uses polling (0.5s interval, 5s timeout by default)
- WebSocket subscription uses `asyncio.create_task()` for message processing

## Task 7: Alerting System (2026-02-02)

### Issues Resolved
- **Test method name typo**: Initial test used `alerting._send_push` instead of `alerting._send_ha_push` - fixed
- **Memo-style comments**: Removed "Update last alert time", "Check deduplication" comments - code is self-documenting
- **Color comments**: Removed inline comments for hex color values - values are self-explanatory

### Integration Notes
- **aiohttp dependency**: Already in pyproject.toml, no new deps needed
- **Async/await pattern**: Consistent with HaClient module
- **Environment variables**: Discord webhook URL should come from .env (not implemented in module, caller's responsibility)
- **HA token**: Reuses same token as HaClient

### Future Considerations
- **Alert persistence**: Current implementation keeps log in memory only - consider InfluxDB storage for long-term history
- **Alert acknowledgment**: Mechanism exists but not integrated with UI/API endpoints yet
- **Rate limiting**: No rate limiting on alert sending - could add per-channel limits if needed
- **Custom data validation**: No schema validation for custom_data dict - could add pydantic validation


## Task 3: Data Collector Service (2026-02-02)

### Issues Resolved
- **datetime.utcnow() deprecation**: Python 3.12+ deprecates `datetime.utcnow()` - use `datetime.now(UTC)` instead
- **Unused test imports**: Initial test file imported `deque`, `MagicMock`, `patch` but didn't use them - removed
- **LSP not available**: basedpyright not installed - used ruff for linting and py_compile for syntax check

### Integration Notes
- **HaClient dependency**: DataCollector requires HaClient instance for sensor reading
- **Environment variables**: Uses same INFLUX_* and HA_*_ID vars defined in .env.example
- **Async context manager**: Use `async with DataCollector(...)` for proper InfluxDB connection lifecycle

### Future Considerations
- **WebSocket subscription for heater state**: Current implementation polls; could use HaClient.subscribe_state_changes() for instant events
- **Weather forecast storage**: Currently stores only current weather; could expand to store forecast array
- **Electricity usage granularity**: Daily polling may miss peak usage times - consider sub-daily polling
- **Buffer persistence**: Memory-only buffer lost on crash - could add disk-based backup for critical data

## Task 6: Electricity Tier Tracker (2026-02-02)

### Issues Encountered

#### 1. Python Environment SSL Issues
- **Problem**: System Python 3.9.6 missing SSL module, pip install failed
- **Solution**: Used Python 3.14 from Homebrew with existing venv
- **Lesson**: Always check venv exists before creating new one

#### 2. InfluxDB Client Import Mismatch
- **Problem**: Initially used `influxdb_client_3` (v3 client) instead of `influxdb_client` (v2 client)
- **Solution**: Changed to `InfluxDBClientAsync` from `influxdb_client.client.influxdb_client_async`
- **Lesson**: Check existing codebase patterns (data_collector.py) for consistency

#### 3. Days Remaining Calculation Off-by-One
- **Problem**: `(cycle_end - now).days` doesn't include current day
- **Solution**: Use `.date()` for date-only comparison: `(cycle_end.date() - now.date()).days`
- **Lesson**: datetime arithmetic with `.days` gives full days between timestamps, not inclusive count

#### 4. LSP Server Not Installed
- **Problem**: basedpyright-langserver not available in environment
- **Impact**: Could not run lsp_diagnostics for type checking
- **Workaround**: Tests passed, manual code review sufficient for this task
- **Future**: Install basedpyright in venv for type checking

### Gotchas

- **Billing cycle edge cases**: Month/year boundaries require careful date arithmetic
- **Mock datetime**: Must use `side_effect` to preserve datetime constructor while mocking `now()`
- **Tier boundaries**: Inclusive vs exclusive boundaries matter (120 kWh is Tier 2, not Tier 1)
- **Delayed data**: Real-world electricity APIs have 9-hour delay, must query historical data

