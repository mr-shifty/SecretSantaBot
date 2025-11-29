# Logging Implementation Summary

## Overview
Comprehensive logging infrastructure has been successfully integrated throughout the Secret Santa Bot application. All core modules now use structured, centralized logging with file rotation and dual output (console + file).

## Logging Architecture

### Core Components

#### 1. **bot/logger.py** (Logger Configuration)
- **setup_logging(name, log_file, level)**: Initializes centralized logging with:
  - Console handler (stdout) for development/debugging
  - Rotating file handler (10MB, 5 backups) for production audit trails
  - Unified format with timestamps and line numbers
  - UTF-8 encoding
  - Automatic `logs/` directory creation

- **get_logger(name)**: Factory function returning module-specific loggers
  - Pattern: `logging.getLogger("secret_santa.{module_name}")`
  - Example: `get_logger("route1")` → `"secret_santa.route1"`

### Integrated Modules

#### 2. **bot/main.py** (Bot Entry Point)
**Logging Coverage:**
- Application startup banner
- Database initialization events
- Handler registration completion
- Scheduler startup/shutdown
- Telegram bot polling start
- Error handling with stack traces
- Graceful shutdown logging

**Example Logs:**
```
[2024-01-15 14:23:01] INFO: ========== Secret Santa Bot Starting ==========
[2024-01-15 14:23:01] INFO: Initializing database...
[2024-01-15 14:23:02] INFO: Database initialized successfully
[2024-01-15 14:23:02] INFO: Registering handlers...
[2024-01-15 14:23:02] INFO: Starting scheduler...
[2024-01-15 14:23:02] INFO: Starting polling...
```

#### 3. **bot/utils.py** (Database Utilities)
**Logging Coverage:**
- User creation/update events with telegram_id
- Route1/Route2 entry persistence with email logging
- Duplicate entry detection attempts

**Key Events:**
```
INFO: User 123456 created: @username
INFO: User 123456 updated
INFO: Saved route1 entry for user 123456 (email: user@example.com)
WARNING: User 123456 already has active route1 entry
```

#### 4. **bot/handlers/route1.py** (Detailed Registration FSM)
**Logging Coverage:**
- Duplicate registration attempts
- Valid/invalid email submissions
- Empty address rejection
- FSM state transitions (email → address → delivery → wishlist)
- Successful registration completion
- Registration cancellation

**Key Events:**
```
INFO: User 123456 started route1 registration
WARNING: User 123456 provided invalid email: invalid@email
INFO: User 123456 submitted route1 entry with email: user@example.com
INFO: User 123456 cancelled route1 registration
```

#### 5. **bot/handlers/route2.py** (Simplified Registration)
**Logging Coverage:**
- Duplicate route2 registration attempts
- Email validation failures
- Successful entry persistence
- Registration cancellation

**Key Events:**
```
INFO: User 123456 started route2 registration
WARNING: User 123456 provided invalid email for route2: invalid@email
INFO: User 123456 submitting route2 entry with email: user@example.com
```

#### 6. **bot/handlers/admin.py** (Admin Commands)
**Logging Coverage:**
- Admin authorization failures (non-admin access attempts)
- Draw command execution (route1, route2)
- Draw success/failure with pair counts
- Notification command execution
- CSV export operations with entry counts

**Key Events:**
```
WARNING: Non-admin user 654321 attempted /draw_route1
INFO: Admin 123456 triggered draw_route1
INFO: Route 1 draw completed successfully: 10 pairs created
INFO: Exporting 15 route1 entries for admin 123456
```

#### 7. **bot/randomizer.py** (Distribution Algorithm)
**Logging Coverage:**
- Draw operation start with route_type
- Active participant count
- Old assignment deletion before re-draw
- Final assignment creation count
- Algorithm failures (insufficient participants, pairing issues)

**Key Events:**
```
INFO: Starting draw for route_type=1
INFO: Found 12 active entries for route_type=1
INFO: Deleted 10 old assignments for route_type=1
INFO: Draw completed successfully: 12 assignments created
ERROR: Draw failed for route_type=1: Not enough participants (need 2, got 1)
```

#### 8. **bot/scheduler.py** (Background Tasks)
**Logging Coverage:**
- Scheduled task execution start
- 7-day unpaid assignment discovery
- Re-draw triggering on failures
- Scheduler startup/shutdown events

**Key Events:**
```
INFO: Starting scheduled task check_and_cancel_unpaid
INFO: Found 2 unpaid assignments older than 7 days
INFO: Triggering re-draw for route_type=1
INFO: Scheduler started successfully
INFO: Scheduler shut down successfully
```

#### 9. **admin_panel/main.py** (FastAPI Admin Panel)
**Logging Coverage:**
- API endpoint requests (method, path, parameters)
- User/entry retrieval counts
- Draw API calls with success/failure status
- CSV export data volumes
- Startup initialization events

**Key Events:**
```
INFO: API request: GET /stats
INFO: API request: GET /users (skip=0, limit=100)
DEBUG: Returned 25 users
INFO: API request: POST /draw/1
INFO: Draw route1 successful: 10 assignments created
INFO: API request: GET /export/route1
DEBUG: Exporting 20 route1 entries
INFO: FastAPI admin panel starting up
INFO: Database initialized
```

## Log Levels Used

| Level | Purpose | Examples |
|-------|---------|----------|
| **INFO** | Normal operations | User registration, draw completion, API requests |
| **DEBUG** | Detailed operational info | Valid email accepted, returned counts, DB operations |
| **WARNING** | Potential issues | Invalid email, duplicate registration, auth failures |
| **ERROR** | Operation failures | Algorithm failure, missing participants, DB errors |

## Log Output

### Console Output
- Real-time visibility during development
- Timestamp + log level + message format
- All levels output to stdout

### File Output (`logs/app.log`)
- **Rotation Policy**: 10MB per file, 5 backup files (50MB total)
- **Format**: `[timestamp] [level] [filename:line] message`
- **Encoding**: UTF-8
- **Automatic Cleanup**: Old files archived as `app.log.1`, `app.log.2`, etc.

## Example Log File Structure

```
logs/
├── app.log          # Current active log (up to 10MB)
├── app.log.1        # Previous rotation
├── app.log.2        # Previous rotation
├── app.log.3        # Previous rotation
├── app.log.4        # Previous rotation
└── app.log.5        # Previous rotation (oldest)
```

## Usage Examples

### Starting Application with Logging
```bash
cd /home/parallels/projects/SecretSantaBot
python -m bot.main
```

### Monitoring Logs in Real-Time
```bash
# Console output (already visible)
# OR watch file logs:
tail -f logs/app.log

# Filter specific module:
tail -f logs/app.log | grep "route1"

# View error logs only:
tail -f logs/app.log | grep "ERROR\|WARNING"
```

### Docker Logging
```bash
# View container logs with app logs:
docker-compose logs -f bot

# Include admin panel logs:
docker-compose logs -f
```

## Testing Logging

### Manual Test Walkthrough
1. **Start bot**: `python -m bot.main`
2. **Start admin panel**: `uvicorn admin_panel.main:app --reload`
3. **In another terminal**: `tail -f logs/app.log`
4. **Trigger activities**:
   - User registration: `/route1` or `/route2` commands
   - Admin draw: `/draw_route1` or `/draw_route2`
   - API requests: `curl http://localhost:8000/stats`
5. **Observe log output** in both console and `logs/app.log`

## Logging Best Practices Implemented

✅ **Structured Logging**: All logs include contextual information (user_id, route_type, etc.)
✅ **File Rotation**: Automatic rotation prevents unbounded disk usage
✅ **Module-Specific Loggers**: Each module has dedicated namespace for filtering
✅ **Appropriate Levels**: INFO for operations, WARNING for anomalies, ERROR for failures
✅ **Performance**: File I/O buffered with rotation handler
✅ **Debugging**: File logs include line numbers for quick code location

## Files Modified

| File | Changes |
|------|---------|
| `bot/logger.py` | ✨ NEW - Logging configuration and factory |
| `bot/main.py` | Added startup/shutdown logging, DB init logs, polling logs |
| `bot/utils.py` | Added logs for user/entry operations |
| `bot/handlers/route1.py` | Added logs for FSM transitions and validation |
| `bot/handlers/route2.py` | Added logs for registration flow |
| `bot/handlers/admin.py` | Added logs for admin commands with auth checks |
| `bot/randomizer.py` | Added comprehensive draw operation logs |
| `bot/scheduler.py` | Added task execution and deadline logs |
| `admin_panel/main.py` | Added API endpoint and startup logs |

## Next Steps

1. **Monitor Logs**: Regularly check `logs/app.log` for patterns
2. **Alert Setup** (Optional): Configure log monitoring/alerting for production
3. **Log Analysis**: Review logs periodically for:
   - Invalid input patterns
   - Algorithm failures
   - User behavior anomalies
4. **Performance Tuning**: Monitor disk I/O from log rotations

## Troubleshooting

### Logs Not Appearing
1. Check `logs/` directory exists and is writable
2. Verify `BOT_TOKEN` is set (required for bot startup)
3. Check file permissions: `ls -la logs/app.log`
4. Review console for startup errors

### High Disk Usage
1. Check log file sizes: `du -sh logs/`
2. Adjust rotation size in `bot/logger.py` if needed
3. Review for excessive DEBUG logging in production

### Missing Logs
- Ensure module imports: `from bot.logger import get_logger`
- Verify logger initialization: `logger = get_logger("module_name")`
- Check that logging calls use the correct logger instance

