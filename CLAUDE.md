# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hybrid Telegram Bot that collects and backs up messages from Telegram using **dual API architecture**: Pyrogram Client API (for message collection) + python-telegram-bot (for user interaction). Supports media file storage, AI-powered error analysis, and flexible cloud storage backends (S3/SFTP).

**Language:** Python 3.x with async/await
**Primary File:** `hybrid_main.py` (3250+ lines, all-in-one architecture)
**Version:** 2.3.0

## Essential Commands

### Running the bot
```bash
python hybrid_main.py
```

### Installing dependencies
```bash
pip install -r requirements.txt
```

### Testing storage connection
Use bot commands:
- `/teststorage` - Test S3/SFTP connection
- `/backup` - Manual backup test
- `/history` - List files on storage

### Logs and debugging
- Daily log files: `bot_YYYY-MM-DD.log`
- Use `/debug` command in bot to see current configuration
- Use `/optstats` for optimization system stats (if enabled)

## Architecture Overview

### Dual API System (Critical Concept)

The bot runs TWO Telegram clients simultaneously in a single process:

1. **Pyrogram Client API** (`client_app` - lines 1220-1226)
   - Uses user account (not bot account)
   - Collects messages from: "Saved Messages", private chats, groups, channels
   - Two async loops:
     - Quick check (0.5s interval): "Saved Messages" only
     - Periodic check (5s interval): Configured dialogs
   - Stores to daily JSON: `saved_messages_YYYY-MM-DD.json`

2. **python-telegram-bot API** (`application` - line 1665)
   - Uses BOT_TOKEN
   - Handles user commands (40+ commands)
   - Displays UI with inline/reply keyboards
   - Manages settings and user interactions

**Why dual API?** Pyrogram's Client API can read user messages from any chat; Bot API provides rich interaction features.

### Storage Architecture

**StorageManager** (lines 443-479) - Universal abstraction that routes to:
- **SFTP Backend** (`StorageBoxManager`, lines 215-308): Legacy Hetzner Storage Box via Paramiko
- **S3 Backend** (`ObjectStorageManager`, lines 310-440): S3-compatible storage (Hetzner Object Storage, AWS S3)

Selection based on `STORAGE_TYPE` env variable (`sftp` or `s3`).

**MediaManager** (lines 481-701)
- Organized structure: `media/photos/`, `media/videos/`, `media/documents/`, etc.
- Auto-downloads media when messages arrive
- Uploads to remote storage backend
- Stores metadata alongside files

### Key Components

**AIAssistant** (lines 743-875)
- Providers: OpenAI (gpt-4o-mini) or Anthropic (claude-3-5-sonnet)
- Analyzes errors from logs and provides: cause, solution, fixed code, warnings
- Maintains error history (max 10)

**ErrorMonitor** (lines 877-962)
- Logs all errors with traceback and context
- Rate-limits admin notifications (5-minute cooldown per error type)
- Auto-calls AI assistant for analysis

**APScheduler Tasks** (setup at line 1196)
- 23:59 daily: Upload JSON to storage
- 23:58 daily: Upload logs to storage
- 01:00 daily: Cleanup old logs and local files

**Optional Optimization Modules** (graceful imports at lines 95-100)
- `self_optimizer.py`: Performance profiling and auto-optimization
- `performance_monitor.py`: CPU/RAM tracking, caching, rate limiting
- `ai_code_improver.py`: Code analysis and refactoring suggestions
- These modules are OPTIONAL - bot runs normally without them

## Configuration

### Environment Variables (.env file)

**Required:**
```env
API_ID=your_api_id              # From https://my.telegram.org
API_HASH=your_api_hash          # From https://my.telegram.org
BOT_TOKEN=your_bot_token        # From @BotFather
```

**Storage (choose one):**
```env
# Option 1: S3 (recommended)
STORAGE_TYPE=s3
S3_ENDPOINT_URL=https://fsn1.your-objectstorage.com
S3_ACCESS_KEY=your_key
S3_SECRET_KEY=your_secret
S3_BUCKET_NAME=telegram-bot-backup
S3_REGION=fsn1

# Option 2: SFTP (legacy)
STORAGE_TYPE=sftp
STORAGE_BOX_HOST=your_host.your-storagebox.de
STORAGE_BOX_USERNAME=your_username
STORAGE_BOX_PASSWORD=your_password
STORAGE_BOX_PATH=/backup/telegram_bot/
```

**Optional AI:**
```env
OPENAI_API_KEY=sk-your-key
ANTHROPIC_API_KEY=sk-ant-your-key
AI_PROVIDER=openai  # or "anthropic"
```

### Access Control

Bot uses UUID-based access (line 211). Only allowed user can execute commands. UUID generated via `uuid.uuid5(uuid.NAMESPACE_OID, str(user_id))`. Use `/myuuid` command to get your UUID.

## Code Structure & Patterns

### Message Collection Flow

1. **Quick check loop** (lines 1244-1305): Every 0.5s, fetch latest "Saved Messages" via `client_app.get_chat_history("me")`
2. **Dialog check loop** (lines 1309-1410): Every 5s, iterate configured dialogs and fetch recent messages
3. **Message processing** (lines 1051-1066): Extract metadata, download media if present, save to JSON
4. **Raw update handler** (lines 1434+): Catches all Telegram updates for monitoring/logging

### Storage Operations

When modifying storage code:
- Both backends must implement: `upload_file()`, `download_file()`, `list_files()`, `connect()`, `close()`
- S3 uses boto3, detects content-type automatically
- SFTP uses paramiko, creates folders recursively before upload
- All storage operations should be wrapped in try-except with error logging

### Adding New Bot Commands

Pattern (see lines 1465-1715):
```python
async def my_command(update: Update, context: ContextType) -> None:
    if update.message is None:
        return

    user_id = update.message.from_user.id
    if not check_access(user_id):
        await update.message.reply_text("⛔ Доступ заборонено")
        return

    # Command logic here
    await update.message.reply_text("Response")

# Register in main():
application.add_handler(CommandHandler("mycommand", my_command))
```

**Important:** Always check `update.message` for None and validate access.

### Media Handling

When adding new media types, update `MediaManager` (lines 481-701):
1. Add folder constant (e.g., `MEDIA_FOLDER / "newtype"`)
2. Create `_save_newtype()` async method following existing patterns
3. Update main message handler to detect and process new media type
4. Ensure metadata saved alongside file

### Type Hints & Code Quality

- Use `-> None` return type for all async handler functions
- Check `update.message` and `update.callback_query.message` for None before accessing
- Use `isinstance()` checks for `MaybeInaccessibleMessage` types
- Prefix unused parameters with `_` (e.g., `_context: ContextType`)
- Type alias for context: `ContextType = CallbackContext[Any, Any, Any, Any]`

## Common Development Scenarios

### Adding a new storage backend

1. Create new manager class implementing standard interface (see `StorageBoxManager` or `ObjectStorageManager` as template)
2. Update `StorageManager.__init__()` to handle new `STORAGE_TYPE` value
3. Add new env variables to `.env.example`
4. Update `README.md` and `MIGRATION_*.md` docs

### Modifying collection intervals

Bot settings stored in-memory (lines 100-118). To persist:
1. Save to JSON file after each settings change
2. Load from JSON file on startup
3. Update `/settings` command to show current values

### Extending AI capabilities

`AIAssistant` class (lines 743-875) handles all AI operations:
- `analyze_error()`: Returns structured dict with cause, solution, fixed_code, warnings
- `suggest_fix()`: Returns code block with improvements
- Add new methods following async patterns with try-except wrappers

### Testing storage operations

Use built-in bot commands:
- `/teststorage` - Tests connection without uploading
- `/backup` - Forces immediate backup (test upload)
- `/history` - Lists remote files (test listing)

### Debugging message collection

Enable detailed logging:
1. Check `bot_YYYY-MM-DD.log` for Pyrogram events (DEBUG level)
2. Use `/clientstatus` command to see Client API status
3. Use `/debug` command to see current settings
4. Add print statements in message loops (lines 1244-1410) for real-time feedback

## Important Constraints

### Do NOT:
- Modify the dual API architecture - both clients are required
- Remove access control checks from command handlers
- Block the asyncio event loop with synchronous operations
- Store secrets in code (always use .env)
- Delete the scheduler tasks without understanding backup implications

### Always:
- Test storage operations before modifying upload/download logic
- Check for None before accessing message attributes
- Use async/await for all Pyrogram and Bot API operations
- Maintain backward compatibility with existing JSON format
- Update CHANGELOG.md when making functional changes

## Execution Flow

```
1. Load .env → Initialize clients (Pyrogram + Bot API)
2. Setup scheduler → Start scheduled tasks (backup, cleanup)
3. Start Pyrogram Client → Begin message collection loops
4. Start Bot API → Listen for commands
5. Run until interrupted → Handle SIGINT/SIGTERM gracefully
6. Cleanup → Stop scheduler, close clients, cancel tasks
```

## File Locations & Naming

- Daily message files: `saved_messages_YYYY-MM-DD.json` (auto-deleted after upload)
- Log files: `bot_YYYY-MM-DD.log` (kept for 30 days)
- Session file: `telegram_client.session` (Pyrogram authentication)
- Media files: `media/{photos|videos|documents|audio|voice|stickers|animations}/`

## Performance Considerations

- Quick check (0.5s): Only "Saved Messages" to avoid rate limits
- Dialog check (5s): Configurable interval and limits
- Media downloads: Async, don't block message processing
- Storage uploads: Scheduled (nightly) to avoid interrupting collection
- Optional optimization modules: Add performance tracking without impacting core bot

## Documentation

Key files to update when making changes:
- `CHANGELOG.md` - Version history and changes
- `README.md` - User-facing documentation
- `WHATS_NEW*.md` - Feature announcements
- Migration guides (`MIGRATION_*.md`) - When changing storage/config

## Dependencies

Core:
- `pyrogram` + `TgCrypto` - Client API
- `python-telegram-bot` - Bot API
- `paramiko` - SFTP operations
- `boto3` - S3 operations
- `apscheduler` - Task scheduling

Optional:
- `openai` - OpenAI integration
- `anthropic` - Claude integration
- `psutil` - System monitoring

All versions in `requirements.txt` are tested and stable.
