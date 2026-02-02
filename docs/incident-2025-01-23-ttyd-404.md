# Incident Report: Top Terminal 404 Error

**Date:** January 23, 2025
**Resolved:** January 24, 2025
**Severity:** Service Degradation
**Affected Service:** Top terminal (port 7681)

## Summary

The top terminal in the dashboard returned a 404 error, making it completely unusable. The bottom terminal (port 7682) continued to work normally.

## Root Cause

The ttyd process for the top terminal was **manually started** with an extra `-I` flag pointing to a non-existent file:

```
ttyd -p 7681 -I /home/pds/boomshakalaka/ttyd/custom-index.html ...
```

The `-I` flag tells ttyd to use a custom index HTML file. When that file doesn't exist, ttyd returns 404 for all requests instead of serving the default interface.

**Key finding:** The startup scripts (`scripts/start_ttyd.sh`) were correct and did NOT contain this flag. Someone manually restarted the process with experimental flags, bypassing the proper startup mechanism.

## How It Was Detected

- Top terminal iframe showed 404 error
- Bottom terminal worked fine
- Process inspection revealed the discrepancy:
  ```bash
  ps aux | grep ttyd
  ```
  Showed the `-I` flag on port 7681 but not on port 7682

## Resolution

Restarted the ttyd service to reload using the correct startup script:

```bash
sudo systemctl restart ttyd
```

## Lessons Learned

### DO NOT manually start services with experimental flags in production

If you need to test custom ttyd configurations:

1. **Use a separate test port** - Don't override the production terminals
2. **Document what you're doing** - Leave a note or create a branch
3. **Use the systemd service** - Always restart via `systemctl` to ensure correct flags
4. **If you must test on production ports**, remember to restart the service when done

### Quick Diagnostic Commands

If a terminal returns 404, check the running process flags:

```bash
# See all ttyd processes and their flags
ps aux | grep ttyd

# Compare against the startup script
cat scripts/start_ttyd.sh

# Fix by restarting the service
sudo systemctl restart ttyd
```

## Prevention

The startup scripts are the source of truth. Any manual process restarts should use:

```bash
sudo systemctl restart ttyd
```

Never manually run ttyd with different flags unless you're explicitly testing on a non-production port.
