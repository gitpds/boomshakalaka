# Garbage Time Betting Strategy

ROI-optimized betting on NBA/NFL halftime blowouts.

## Strategy Overview

When a team has a large halftime lead, "garbage time" regression occurs:
- Winning team rests starters
- Losing team plays aggressively
- Trailing team often covers the spread in the second half

## Optimal Betting Ranges

Based on analysis of 2,885 historical NBA games:

| Range | Win Rate | Edge | EV per $100 | Action |
|-------|----------|------|-------------|--------|
| 12-14pt | ~50% | -2% | -$4.55 | **SKIP** |
| 14-15pt | 60% | +7.6% | +$14.55 | BET |
| **15-17pt** | **61.4%** | **+9.1%** | **+$17.31** | **OPTIMAL** |
| 17-20pt | 57-61% | +5-9% | +$9-17 | BET |
| 20+pt | Variable | Check | Verify | CAUTION |

**Key insight**: Maximize ROI by focusing on 15-17pt leads, not volume.

## Dashboard

Access at: `/sports/betting/analysis`

Features:
- **Bell distribution chart** - Edge % by point bucket
- **ROI bucket table** - EV per $100 at each range
- **Running profit tracker** - Hypothetical P&L for optimal range
- **Recent games** - Individual game results with running totals

## Slack Alerts

Real-time notifications sent to `#boomshakalaka-alerts` **ONLY for OPTIMAL range** (15-17pt leads).

- Alerts only trigger for 15-17pt leads (61.4% win rate, +9.1% edge)
- No emails - Slack only
- Duplicate alerts prevented via `alert_sent` tracking in database

## Files

| File | Description |
|------|-------------|
| `dashboard/server.py` | Backend analysis functions |
| `dashboard/templates/sports_betting_analysis.html` | Analysis dashboard |
| `skills/slack_notification/` | Slack notification skill |
| `~/money_printing/polymarket/sports_betting/live_monitor.py` | Data collection (records blowouts to DB) |
| `~/money_printing/polymarket/sports_betting/alert_blowouts.py` | Slack alerts (OPTIMAL only) |
| `~/money_printing/polymarket/sports_betting/garbage_time.db` | Game database |

## Configuration

**Thresholds** (in `live_monitor.py`):
- NBA: 15+ point lead at halftime (records to DB)
- NFL: 17+ point lead at halftime

**Alert Range** (in `alert_blowouts.py`):
- OPTIMAL_MIN: 15
- OPTIMAL_MAX: 17
- Only 15-16pt leads trigger Slack alerts

## Cron Schedule

The monitor runs during game hours:
- **NBA Weekday**: Every 10 min, 6-11 PM (Mon-Fri)
- **NBA Weekend**: Every 10 min, 12-11 PM (Sat-Sun)
- **NFL Sunday**: Every 10 min, 12-10 PM
- **NFL Mon/Thu**: Every 10 min, 7-11 PM

## Changelog

**January 2026**
- Removed email notifications (Slack only)
- Raised NBA threshold from 14pt to 15pt
- Filtered Slack alerts to OPTIMAL range only (15-17pt)
- Added duplicate alert prevention via `alert_sent` tracking
