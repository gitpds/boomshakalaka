# Unified Multi-Channel Messaging for Reggie

> **Created:** 2026-02-03
> **Status:** Production

This document describes how Reggie maintains unified memory and context across all communication channels.

---

## Overview

Reggie can be reached through multiple channels, all sharing the same memory and conversation context:

| Channel | Status | How to Use |
|---------|--------|------------|
| **WebChat** | Active | http://localhost:3003/reggie/openclaw |
| **iMessage** | Active | Message from paired Apple device |
| **SMS** | Active | Text +1 612-255-9398 (must be on allowlist) |
| **Voice** | Active | Call +1 612-255-9398 (must be on allowlist) |
| **Slack** | Active | DM @Reggie in workspace (requires pairing approval) |
| **Email** | Active | Email reggie@paulstotts.com (full autonomy, all emails processed) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      MacBook (192.168.0.168)                      │
│                 Reggie's Brain - Fully Independent                │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  OpenClaw Gateway (:18789)                                  │  │
│  │  Session: agent:main:main (unified DM context)              │  │
│  │                                                              │  │
│  │  Memory Tiers:                                               │  │
│  │  ├─ Sessions (JSONL) - conversation transcripts             │  │
│  │  ├─ Workspace files - SOUL.md, CONTACTS.md, IDENTITY.md     │  │
│  │  └─ Memory DB - semantic search across all conversations    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                          ▲                                        │
│                          │                                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  reggie-voice Flask Server (:18790)                         │  │
│  │  - Handles Twilio voice webhooks directly                   │  │
│  │  - Calls OpenClaw CLI locally (no SSH overhead)             │  │
│  │  - Cloudflare Tunnel: reggie.pds.dev                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                          ▲                                        │
│                          │                                        │
│  Channel Inputs:                                                  │
│  ├─ iMessage (native plugin) ──────┐                             │
│  ├─ WebChat (native) ──────────────┤                             │
│  ├─ Slack (native plugin) ─────────┼──→ agent:main:main          │
│  ├─ Voice (local reggie-voice) ────┤    (shared context)         │
│  ├─ SMS (CLI via workstation) ─────┤                             │
│  └─ Email (local email_monitor) ───┘                             │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Key Change (2026-02-03):** Voice calls now route directly to MacBook via Cloudflare
Tunnel, eliminating the workstation from the voice call path. This reduces latency by
~100ms and allows Reggie to operate independently.

---

## Channel Details

### WebChat (Native)

- **URL:** http://localhost:3003/reggie/openclaw (proxied through dashboard)
- **Direct:** http://192.168.0.168:18789 (requires LAN/VPN)
- **Auth:** Gateway token (configured in openclaw.json)

### iMessage (Native Plugin)

- **Status:** Requires macOS with Messages app
- **Pairing:** Automatic via OpenClaw's imsg CLI
- **Policy:** `dmPolicy: pairing` - new contacts need approval

### Slack (Native Plugin)

- **App Name:** Reggie
- **Socket Mode:** Enabled (no webhook URL needed)
- **Tokens:**
  - Bot Token: `SLACK_BOT_TOKEN` (xoxb-...)
  - App Token: `SLACK_APP_TOKEN` (xapp-...)
- **Pairing:** New users receive a code, approve with:
  ```bash
  ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && openclaw pairing approve slack <CODE>"
  ```

### SMS (via Dashboard Webhook)

- **Phone:** +1 612-255-9398 (Twilio)
- **Webhook:** POST /sms/webhook (workstation dashboard)
- **Allowlist:** Only approved numbers can message Reggie
- **Integration:** Calls OpenClaw CLI via SSH to MacBook
- **Session:** Uses dynamic UUID resolution (see [Session Routing](#session-routing) below)

SMS messages include channel context:
```
[SMS] [From: Paul] Hey Reggie, what's on my calendar?
```

### Email (MacBook-Native Polling Daemon)

**Architecture (2026-02-04):** Email is polled every 5 minutes from the MacBook,
processed through OpenClaw, with replies sent via Gmail API.

**FULL AUTONOMY MODE:** Reggie processes ALL incoming emails - no allowlist restrictions.
Basic safeguards prevent email loops (noreply addresses, automated bounces, etc.).

- **Email:** reggie@paulstotts.com
- **Polling Interval:** 5 minutes (via launchd)
- **Daemon:** MacBook `~/reggie-voice/email_monitor.py`
- **Service:** `com.reggie.email` (launchd)
- **Gmail API:** Accessed via SSH to workstation (service account auth)
- **Label:** Processed emails tagged with `Reggie-Processed`
- **Google Workspace:** Full access to Calendar, Drive, Sheets via automation scripts

Email processing flow:
1. Daemon checks for unread emails every 5 minutes
2. Skips automated/noreply emails to prevent loops
3. Reads full email content via workstation Gmail API
4. Formats with `[EMAIL] [From: {name}]` prefix
5. Sends to OpenClaw CLI locally on MacBook
6. Replies via Gmail API (as reggie@paulstotts.com)
7. Labels original email as `Reggie-Processed`

Email messages include channel context:
```
[EMAIL] [From: Paul]
Subject: Project Update

Hey Reggie, can you remind me what's on my schedule today?
```

**MacBook Services:**
```bash
# View email logs
ssh reggiembp 'tail -f ~/.reggie/email-monitor.log'

# Manually run once (for testing)
ssh reggiembp 'python3 ~/reggie-voice/email_monitor.py'

# Check service status
ssh reggiembp 'launchctl list | grep com.reggie.email'

# Restart service (will run immediately then every 5 min)
ssh reggiembp 'launchctl kickstart -k gui/$UID/com.reggie.email'
```

### Voice Calls (MacBook-Native via reggie-voice)

**Architecture Update (2026-02-03):** Voice calls now run directly on MacBook,
eliminating the workstation from the voice path for lower latency and independence.

- **Phone:** +1 612-255-9398 (same number as SMS)
- **Webhook:** POST https://reggie.pds.dev/voice/webhook
- **WebSocket:** wss://reggie.pds.dev/voice/stream
- **Server:** MacBook :18790 (reggie-voice Flask app)
- **Tunnel:** Cloudflare Tunnel (`reggie-voice` → `reggie.pds.dev`)
- **Allowlist:** Stored on MacBook at `~/.reggie/voice-allowlist.json`
- **STT:** Twilio built-in (via Google Speech)
- **TTS:** ElevenLabs (custom trained voice)
- **Integration:** Calls OpenClaw CLI **locally** (no SSH overhead!)

Voice calls work with Twilio ConversationRelay:
1. Caller dials +1 612-255-9398
2. Twilio calls `https://reggie.pds.dev/voice/webhook` (MacBook via Cloudflare)
3. reggie-voice returns TwiML with ConversationRelay config
4. ConversationRelay connects WebSocket to `wss://reggie.pds.dev/voice/stream`
5. Speech-to-text converts caller's speech to transcript
6. reggie-voice calls `openclaw agent` CLI **locally**
7. Response sent back for ElevenLabs text-to-speech

Voice messages include channel context:
```
[VOICE] [From: Paul] Hey Reggie, what's on my calendar?
```

**Latency:** ~1.0-2.0 seconds end-to-end (improved by eliminating SSH hop)

**MacBook Services:**
```bash
# Check voice server
ssh reggiembp 'curl -s http://localhost:18790/health'

# Check cloudflared tunnel
ssh reggiembp 'launchctl list | grep cloudflared'

# View voice logs
ssh reggiembp 'tail -f ~/.reggie/voice.log'

# Restart services
ssh reggiembp 'launchctl kickstart -k gui/$UID/com.reggie.voice'
ssh reggiembp 'launchctl kickstart -k gui/$UID/com.reggie.cloudflared'
```

---

## SMS/Voice Allowlist Management

### View Allowlist
```bash
curl http://localhost:3003/api/sms/allowlist | jq
```

### Add Number
```bash
curl -X POST http://localhost:3003/api/sms/allowlist \
  -H 'Content-Type: application/json' \
  -d '{"phone_number": "+15551234567", "name": "John"}'
```

### Remove Number
```bash
curl -X DELETE "http://localhost:3003/api/sms/allowlist/%2B15551234567"
```

### Send Outbound SMS
```bash
curl -X POST http://localhost:3003/api/sms/send \
  -H 'Content-Type: application/json' \
  -d '{"to": "+15551234567", "message": "Hello from Reggie!", "name": "John"}'
```

---

## Configuration Files

### Dashboard (.env) - Workstation
```bash
# Twilio SMS (voice is on MacBook now)
TWILIO_ACCOUNT_SID=ACd1d89c...
TWILIO_AUTH_TOKEN=c44fb4d3...
TWILIO_PHONE_NUMBER=+16122559398
```

### reggie-voice (.env) - MacBook ~/reggie-voice/
```bash
# Twilio credentials (for webhook validation)
TWILIO_ACCOUNT_SID=ACd1d89c...
TWILIO_AUTH_TOKEN=c44fb4d3...
TWILIO_PHONE_NUMBER=+16122559398

# ElevenLabs voice for TTS
ELEVENLABS_VOICE_ID=pNInz6obpgDQGcFmaJgB

# Cloudflare Tunnel domain
WEBHOOK_DOMAIN=reggie.pds.dev
```

### Voice Allowlist - MacBook ~/.reggie/voice-allowlist.json
```json
{
  "+15037547138": {"name": "Paul"}
}
```

### Email Skip Patterns (Loop Prevention)

Emails from these patterns are automatically skipped:
- `noreply@`, `no-reply@`, `donotreply@`, `mailer-daemon@`
- `notifications@`, `automated@`, `auto-reply@`
- Subject lines: `Auto:`, `Out of Office:`, `Delivery Status Notification`

### OpenClaw (MacBook ~/.openclaw/)

| File | Purpose |
|------|---------|
| `openclaw.json` | Gateway config, channel settings |
| `.env` | API keys (Anthropic, OpenAI, Slack tokens) |
| `workspace/SOUL.md` | Reggie's personality and guidelines |
| `workspace/CONTACTS.md` | Identity mapping across channels |
| `workspace/IDENTITY.md` | Reggie's self-description |
| `agents/main/sessions/` | Conversation history (JSONL) |

### Key openclaw.json Settings
```json
{
  "channels": {
    "slack": { "enabled": true },
    "imessage": { "enabled": true, "dmPolicy": "pairing" }
  },
  "gateway": {
    "port": 18789,
    "bind": "lan",
    "auth": { "mode": "token", "token": "..." }
  }
}
```

---

## Session Routing

### The Problem (Fixed 2026-02-06)

OpenClaw's CLI `--session-id main` does **not** resolve through alias mapping. It
creates a literal file `main.jsonl`, separate from the UUID-based session file
(e.g., `9acd4b8f-0ce9-4f9a-9763-073821d5d1a2.jsonl`) that native plugins (Slack,
iMessage, WebChat) use. This meant SMS and Voice messages landed in `main.jsonl`
while Slack read from the UUID file — breaking cross-channel recall.

### The Fix: Dynamic UUID Resolution

Instead of `--session-id main`, both the MacBook voice server (`openclaw_client.py`)
and the workstation dashboard (`server.py`) now dynamically look up the real system
session UUID:

```bash
openclaw sessions list --json
# Returns:
# {
#   "sessions": [{
#     "key": "agent:main:main",
#     "sessionId": "9acd4b8f-0ce9-4f9a-9763-073821d5d1a2",
#     "systemSent": true    <-- this is the one native plugins use
#   }]
# }
```

The `get_system_session_id()` function (MacBook) and `get_openclaw_session_id()`
function (workstation) resolve this UUID and cache it for 5 minutes:

1. Call `openclaw sessions list --json`
2. Find the session entry with `systemSent: true`
3. Use that `sessionId` (the real UUID) for `--session-id`
4. Cache for 5 minutes to avoid subprocess overhead
5. Fall back to `'main'` if resolution fails (graceful degradation)

### Session Flow by Channel

| Channel | Where It Runs | Session Resolution |
|---------|---------------|-------------------|
| **Slack** | MacBook (native plugin) | Uses UUID session natively |
| **iMessage** | MacBook (native plugin) | Uses UUID session natively |
| **WebChat** | MacBook (native plugin) | Uses UUID session natively |
| **Voice** | MacBook (reggie-voice) | `get_system_session_id()` resolves UUID |
| **SMS** | MacBook (reggie-voice) | `get_system_session_id()` resolves UUID |
| **SMS** (backup) | Workstation (dashboard) | `get_openclaw_session_id()` resolves UUID via SSH |
| **Email** | MacBook (email_monitor) | `get_system_session_id()` resolves UUID |

### Session Files on MacBook

```
~/.openclaw/agents/main/sessions/
├── 9acd4b8f-0ce9-4f9a-9763-073821d5d1a2.jsonl  # THE session (all channels)
└── main.jsonl.bak                                 # Stale file from before fix
```

**Important:** If `main.jsonl` reappears, something is still using `--session-id main`
instead of the resolved UUID. Investigate immediately.

### Verifying Session Routing

```bash
# Check which UUID is being resolved
ssh reggiembp 'cd ~/reggie-voice && source .venv/bin/activate && \
  python3 -c "from openclaw_client import get_system_session_id; print(get_system_session_id())"'

# Verify no stale main.jsonl exists
ssh reggiembp 'ls -la ~/.openclaw/agents/main/sessions/main.jsonl 2>/dev/null && echo "BAD: main.jsonl exists" || echo "OK: no stale session"'

# Cross-channel test: send SMS then ask Slack
# 1. Text Reggie: "Testing cross-channel, code word: pineapple"
# 2. In Slack: "What code word did I just text you?"
# 3. Should answer "pineapple" (proves shared session)
```

---

## Memory Persistence

All channels share the same OpenClaw session (`agent:main:main`), which means:

1. **Cross-channel recall**: "As we discussed over text..." works from any channel
2. **Unified identity**: CONTACTS.md maps phone/email/Slack to person
3. **Workspace files**: SOUL.md, TOOLS.md loaded into every conversation
4. **Automation memory**: Actions performed via automation scripts are logged

### Automation Memory (2026-02-04)

When Claude Code uses automation scripts (sheets.py, docs.py, gmail.py, etc.),
those actions are automatically logged to OpenClaw's memory so Reggie remembers
what he's done.

**How it works:**
- Each automation script imports from `memory.py`
- After significant actions (create, share, send), the script calls `log_action()`
- This sends a message to OpenClaw via SSH: `[AUTOMATION] Created spreadsheet "Budget 2026"`
- Reggie can later recall: "Have you created any spreadsheets?" → "Yes, I created Budget 2026"

**Supported actions:**
| Action | Script | Memory Log |
|--------|--------|------------|
| Create spreadsheet | sheets.py | `[AUTOMATION] Created Google Spreadsheet` |
| Share spreadsheet | sheets.py | `[AUTOMATION] Shared spreadsheet` |
| Create document | docs.py | `[AUTOMATION] Created Google Document` |
| Share document | docs.py | `[AUTOMATION] Shared document` |
| Send email | gmail.py | `[AUTOMATION] Sent email` |
| Create event | gcalendar.py | `[AUTOMATION] Created calendar event` |
| Update event | gcalendar.py | `[AUTOMATION] Updated calendar event` |
| Delete event | gcalendar.py | `[AUTOMATION] Deleted calendar event` |
| Upload file | drive.py | `[AUTOMATION] Uploaded file` |
| Share file | drive.py | `[AUTOMATION] Shared file` |
| Create folder | drive.py | `[AUTOMATION] Created folder` |

**Files:**
- `robotics/reggie/automation/memory.py` - Memory logging module
- Sessions stored on MacBook: `~/.openclaw/agents/main/sessions/*.jsonl`

### Testing Memory
```bash
# Via CLI (uses dynamic UUID resolution to hit the shared session)
ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && \
  SESSIONS=\$(openclaw sessions list --json) && \
  UUID=\$(echo \$SESSIONS | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(s[\"sessionId\"] for s in d[\"sessions\"] if s.get(\"systemSent\")))') && \
  openclaw agent --session-id \$UUID --message '[SMS] [From: Paul] Remember my favorite color is blue' --json"

# Later, from any channel
"What's my favorite color?"  # Should respond "blue"

# Test automation memory
cd /home/pds/robotics/reggie/automation
python3 sheets.py create --title "Test Sheet"  # Creates sheet + logs to memory

# Verify in session logs
ssh reggiembp 'grep -i "automation" ~/.openclaw/agents/main/sessions/*.jsonl | tail -5'
```

---

## Troubleshooting

### SMS/Voice Not Sharing Memory with Slack

This is almost always a session routing issue. Check:

1. **Verify UUID resolution works:**
   ```bash
   ssh reggiembp 'cd ~/reggie-voice && source .venv/bin/activate && \
     python3 -c "from openclaw_client import get_system_session_id; print(get_system_session_id())"'
   ```
   Should print a UUID like `9acd4b8f-...`, NOT `main`.

2. **Check for stale `main.jsonl`:**
   ```bash
   ssh reggiembp 'ls ~/.openclaw/agents/main/sessions/main.jsonl 2>/dev/null && echo "STALE SESSION EXISTS" || echo "OK"'
   ```
   If it exists, something is still using `--session-id main`. Back it up and investigate.

3. **Check voice server is using the patched code:**
   ```bash
   ssh reggiembp 'grep "get_system_session_id" ~/reggie-voice/openclaw_client.py && echo "PATCHED" || echo "NOT PATCHED"'
   ```

4. **Check dashboard is using the patched code:**
   ```bash
   grep "get_openclaw_session_id" /home/pds/boomshakalaka/dashboard/server.py && echo "PATCHED" || echo "NOT PATCHED"
   ```

### SMS Not Responding
1. Check allowlist: `curl http://localhost:3003/api/sms/allowlist | jq`
2. Check dashboard logs: `journalctl -u dashboard -f`
3. Test OpenClaw directly:
   ```bash
   ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && openclaw status"
   ```

### Voice Calls Not Connecting
1. Check voice server health: `ssh reggiembp 'curl -s http://localhost:18790/health'`
2. Check cloudflared tunnel: `ssh reggiembp 'launchctl list | grep cloudflared'`
3. Check allowlist on MacBook: `ssh reggiembp 'cat ~/.reggie/voice-allowlist.json'`
4. Test via Cloudflare: `curl -4 --resolve reggie.pds.dev:443:172.67.206.84 https://reggie.pds.dev/health`
5. Check voice logs: `ssh reggiembp 'tail -20 ~/.reggie/voice.log'`
6. Check cloudflared logs: `ssh reggiembp 'tail -20 ~/.cloudflared/cloudflared-error.log'`
7. Restart voice server: `ssh reggiembp 'launchctl kickstart -k gui/$UID/com.reggie.voice'`
8. Restart tunnel: `ssh reggiembp 'launchctl kickstart -k gui/$UID/com.reggie.cloudflared'`

### Voice TTS Issues
1. ElevenLabs is configured in Twilio ConversationRelay TwiML, not via API key
2. Check voice ID in reggie-voice/.env matches your ElevenLabs account
3. Check Twilio console for ConversationRelay errors

### Slack Not Responding
1. Check pairing status - user may need approval
2. Verify tokens in `~/.openclaw/.env` on MacBook
3. Check OpenClaw logs:
   ```bash
   ssh reggiembp "tail -100 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep slack"
   ```

### Email Not Being Processed
1. Check if sender matches skip pattern (noreply, automated, etc.)
2. Check email daemon status: `ssh reggiembp 'launchctl list | grep com.reggie.email'`
3. Check email logs: `ssh reggiembp 'tail -50 ~/.reggie/email-monitor.log'`
4. Test Gmail API connection: `cd /home/pds/robotics/reggie/automation && /home/pds/miniconda3/bin/python3 gmail.py inbox --limit 5`
5. Check if email already has `Reggie-Processed` label

### OpenClaw Gateway Down
```bash
# Check status
ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && openclaw gateway status"

# Restart
ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && openclaw gateway restart"
```

---

## Adding New Channels

### Native OpenClaw Channels
OpenClaw supports: WhatsApp, Telegram, Discord, Signal, Teams, Matrix, etc.

Enable in `~/.openclaw/openclaw.json`:
```json
{
  "channels": {
    "telegram": { "enabled": true }
  }
}
```

Then configure tokens in `~/.openclaw/.env` and restart gateway.

### Webhook-based Channels
For channels not natively supported, add a webhook route to `server.py` following the SMS pattern:
1. Receive inbound message
2. Call `send_to_openclaw(message, identifier, channel='channelname')`
3. Return response to the channel

---

## Related Documentation

- [OpenClaw Docs](https://docs.openclaw.ai/)
- [Twilio SMS Webhooks](https://www.twilio.com/docs/messaging/guides/webhook-request)
- [Twilio ConversationRelay](https://www.twilio.com/docs/voice/twiml/connect/conversationrelay)
- [ElevenLabs API](https://elevenlabs.io/docs/api-reference)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Slack Socket Mode](https://api.slack.com/apis/connections/socket)
