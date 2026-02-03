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
| **Slack** | Active | DM @Reggie in workspace (requires pairing approval) |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      OpenClaw Gateway                             │
│                   (MacBook 192.168.0.168:18789)                  │
├──────────────────────────────────────────────────────────────────┤
│  Session: agent:main:main (unified DM context)                   │
│                                                                   │
│  Memory Tiers:                                                    │
│  ├─ Sessions (JSONL) - conversation transcripts                  │
│  ├─ Workspace files - SOUL.md, CONTACTS.md, IDENTITY.md          │
│  └─ Memory DB - semantic search across all conversations         │
│                                                                   │
│  Channels:                                                        │
│  ├─ iMessage (native plugin) ──────┐                             │
│  ├─ WebChat (native) ──────────────┼──→ agent:main:main          │
│  ├─ Slack (native plugin) ─────────┤    (shared context)         │
│  └─ SMS (CLI via dashboard) ───────┘                             │
└──────────────────────────────────────────────────────────────────┘
```

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
- **Webhook:** POST /sms/webhook
- **Allowlist:** Only approved numbers can message Reggie
- **Integration:** Calls OpenClaw CLI via SSH to MacBook

SMS messages include channel context:
```
[SMS] [From: Paul] Hey Reggie, what's on my calendar?
```

---

## SMS Allowlist Management

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

### Dashboard (.env)
```bash
# Twilio SMS
TWILIO_ACCOUNT_SID=ACd1d89c...
TWILIO_AUTH_TOKEN=c44fb4d3...
TWILIO_PHONE_NUMBER=+16122559398
```

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

## Memory Persistence

All channels share the same OpenClaw session (`agent:main:main`), which means:

1. **Cross-channel recall**: "As we discussed over text..." works from any channel
2. **Unified identity**: CONTACTS.md maps phone/email/Slack to person
3. **Workspace files**: SOUL.md, TOOLS.md loaded into every conversation

### Testing Memory
```bash
# Via CLI (simulates SMS)
ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && \
  openclaw agent --to +15037547138 --message 'Remember my favorite color is blue' --json"

# Later, from any channel
"What's my favorite color?"  # Should respond "blue"
```

---

## Troubleshooting

### SMS Not Responding
1. Check allowlist: `curl http://localhost:3003/api/sms/allowlist | jq`
2. Check dashboard logs: `journalctl -u dashboard -f`
3. Test OpenClaw directly:
   ```bash
   ssh reggiembp "source ~/.nvm/nvm.sh && nvm use node && openclaw status"
   ```

### Slack Not Responding
1. Check pairing status - user may need approval
2. Verify tokens in `~/.openclaw/.env` on MacBook
3. Check OpenClaw logs:
   ```bash
   ssh reggiembp "tail -100 /tmp/openclaw/openclaw-$(date +%Y-%m-%d).log | grep slack"
   ```

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
- [Slack Socket Mode](https://api.slack.com/apis/connections/socket)
