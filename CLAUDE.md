# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install deps (target venv lives at ./venv per ecosystem.config.js)
pip install -r requirements.txt

# Run locally (requires .env with TELEGRAM_BOT_TOKEN)
python main.py

# Run under PM2 in production
pm2 start ecosystem.config.js
```

Environment variables (`.env`):
- `TELEGRAM_BOT_TOKEN` — required
- `LOG_LEVEL` — defaults to `INFO`
- `PERSISTENCE_PATH` — defaults to `bot_data`

There is no test suite, linter, or formatter configured.

## Architecture

A `python-telegram-bot` (v21+) async polling bot. `main.py` builds a single `Application` with `PicklePersistence` and delegates handler registration to per-feature modules in `handlers/`. Each module exposes a `register_*_handlers(application)` function that adds its `CommandHandler` / `MessageHandler` instances; `main.py` is the only place that knows about all of them.

### Persistence model
State lives in a single pickle file (`bot_data`, configurable via `PERSISTENCE_PATH`) flushed every 60 seconds. Three persistence scopes are used:
- `context.chat_data` — per-chat settings and feature toggles (janitor, channel filter, forward spam protection, filter patterns, whitelists, FSP cache).
- `context.bot_data` — global state: `start_time` and `tracked_chats` (built up by `track_chat` in `handlers/diagnostics.py`, which is registered in `main.py` as a catch-all `MessageHandler` at `group=999` so it runs after every other handler).
- `context.application.chat_data[chat_id]` — read directly by bot-owner admin commands in `diagnostics.py` to inspect other chats' settings.

Commands that mutate `chat_data` call `await context.application.update_persistence()` explicitly so changes survive even before the 60s tick. The `bot_data` file in the repo root is a checked-in snapshot of pickled state — be aware that committing it changes runtime behavior.

### Two distinct admin concepts
This is the most confusing thing in the codebase:
- **Chat admin** — `@admin_only` decorator in `handlers/conversation.py` calls `update.effective_chat.get_administrators()` to check Telegram-side admin status. Used for per-chat feature toggles (`/enable_janitor`, `/add_filter`, `/toggle_channel_filter`, etc.). Private chats are always treated as admin.
- **Bot owner** — hardcoded `ADMIN_USER_IDS = [352475318]` in `handlers/diagnostics.py`, checked via `is_admin()`. Used for cross-chat commands (`/stats`, `/admin_list_groups`, `/admin_leave_group`, `/admin_group_filters`). The `.env` also has an `ADMIN_USER_IDS` value but nothing currently reads it.

### Message handler ordering (PTB groups)
PTB runs handlers in numeric group order. The codebase relies on this:
- `group=0` (default) — command handlers and `handle_forward_spam` (forward MessageHandler in `conversation.py`).
- `group=1` — `filter_message` in `handlers/filters.py` (channel filter + regex filter for text/captions). Kept in its own group so it runs after commands.
- `group=999` — `track_chat_activity` in `main.py`, intentionally last so chat tracking sees every update regardless of earlier handlers' decisions.

### Filtering features (all per-chat, all in `chat_data`)
1. **Janitor / regex filtering** (`handlers/filters.py`) — gated by `janitorEnabled`; matches `filter_patterns` (list) against message text/caption with `re.IGNORECASE`. Deletes match and posts a self-destructing notice (30s via `job_queue.run_once(delete_message_job, ...)`).
2. **Channel filter** (`handlers/filters.py`) — gated by `channelFilterEnabled`; deletes messages where `sender_chat.type == "channel"` and the sender chat isn't the current chat. Skips `is_automatic_forward` (linked-channel posts) and entries in `channelWhitelist`. Channel-filter logic lives inside `filter_message` and runs *before* regex filtering, returning early on a match.
3. **Forward spam protection / FSP** (`handlers/conversation.py`) — gated by `forwardSpamProtectionEnabled`; `_make_forward_key()` produces a stable identity for a forwarded message (channel post → `chat:id:msg:id`; user forward → `user:id:date:ts:text:hash:media:fileid`). Keys are stored in `fsp_cache` with first-seen timestamps; a re-send within 24h is deleted. `_cleanup_fsp_cache()` prunes entries older than 24h on every check. Notices auto-delete after 6 seconds.

When touching `_make_forward_key`, note it supports both the new API (`forward_origin`) and the deprecated API (`forward_from` / `forward_from_chat`), and intentionally returns `None` for anonymous/hidden senders so we don't delete forwards we can't reliably identify.

### Logging
Single named logger `telegram_bot` configured in `utils/logger.py`. All handlers do `logging.getLogger("telegram_bot")` at module level — keep that name when adding new modules so output stays unified.
