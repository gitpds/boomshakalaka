# Local Voice Status

> **Last Updated:** 2026-02-05
> **Status:** Fix Applied, Needs Testing

## Current State

The TTS audio byte-swap fix has been applied to the reggie-voice server on the MacBook. The service is running but the fix has **not been verified** (user is remote).

## Problem Summary

TTS audio from ElevenLabs was received by the browser (448,000 bytes) but sounded silent. Test tones worked fine, proving browser audio output was functional.

**Root Cause (identified by OpenAI o3):**
- ElevenLabs sends 16-bit PCM in **big-endian** byte order (hi-byte, lo-byte)
- Both Python (`np.frombuffer(..., dtype=np.int16)`) and browser (`new Int16Array(...)`) assume **little-endian**
- Every sample's bytes were reversed: intended 0x7FFF became 0xFF7F = -129
- The loudest peaks sat at ±129...±153 instead of ±32,767
- Result: audio was essentially silence (-46 dB)

## Fix Applied

**File:** MacBook `~/reggie-voice/server.py`

Changed TTS chunk processing in both `browser_websocket` and `robot_websocket` handlers:

```python
# Before (wrong - assumed little-endian):
chunk_pcm = np.frombuffer(chunk, dtype=np.int16)
ws.send(chunk)

# After (correct - swaps big-endian to little-endian):
pcm_be = np.frombuffer(chunk, dtype='>i2')  # Read as big-endian
pcm_le = pcm_be.byteswap()                   # Swap to little-endian
ws.send(pcm_le.tobytes())
```

## Verification Steps (When Back On-Site)

1. **Check server logs:**
   ```bash
   ssh reggiembp "tail -f ~/.reggie/logs/reggie-voice-error.log"
   ```
   - `max amp` values should be in range **20,000-32,000** (not ~153)

2. **Browser test:**
   - Open http://localhost:3003/reggie/voice
   - Click "Start Voice"
   - Speak to Reggie
   - **Should hear TTS response at normal volume**

3. **Browser console should show:**
   - `max amplitude: ~30000` (approximately)

4. **Optional - save and inspect audio:**
   - Save a received chunk to disk
   - Open in Audacity as RAW 16-kHz mono little-endian
   - Waveform should look normal, not flat

## Service Management

```bash
# Check service status
ssh reggiembp "launchctl list | grep reggie.voice"

# Restart service
ssh reggiembp "launchctl kickstart -k gui/\$UID/com.reggie.voice"

# Check health
ssh reggiembp "curl -s http://localhost:18790/health | python3 -m json.tool"

# View logs
ssh reggiembp "tail -50 ~/.reggie/logs/reggie-voice-error.log"
```

## If Fix Doesn't Work

1. **Check if ElevenLabs changed format:** They might switch to little-endian in the future, which would require removing the swap
2. **Verify the fix is in place:**
   ```bash
   ssh reggiembp "grep -A3 'big-endian' ~/reggie-voice/server.py"
   ```
3. **Check browser-side processing:** The browser code in `reggie_voice.html` also processes audio - ensure it's not double-swapping

## Architecture Reference

```
Browser (localhost:3003/reggie/voice)
    ↓ WebSocket (audio from mic)
Dashboard (workstation:3003)
    ↓ WebSocket proxy
MacBook reggie-voice (192.168.0.168:18790)
    ↓ STT (Whisper) → OpenClaw → TTS (ElevenLabs)
    ↓ PCM audio (big-endian from ElevenLabs)
    ↓ BYTE SWAP (>i2 → little-endian) ← FIX APPLIED HERE
    ↓ WebSocket
Browser AudioWorklet
    ↓ Int16Array (expects little-endian)
Speaker output
```

## Related Files

| Location | File | Purpose |
|----------|------|---------|
| MacBook | `~/reggie-voice/server.py` | Voice server (fix applied here) |
| MacBook | `~/reggie-voice/tts.py` | ElevenLabs TTS pipeline |
| Workstation | `dashboard/templates/reggie_voice.html` | Browser voice UI |
| Workstation | `dashboard/server.py` | WebSocket proxy to MacBook |

## History

- **2026-02-05:** Byte-swap fix applied to server.py, service restarted, awaiting on-site verification
- **2026-02-04:** Previous alignment-only fix (odd byte buffering) didn't solve the issue
- **2026-02-03:** Voice bridge initially deployed, TTS audio silent
