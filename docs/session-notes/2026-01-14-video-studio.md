# Session Notes: Video Studio & Parameter Controls

**Date:** 2026-01-14
**Branch:** dev
**PR:** https://github.com/gitpds/boomshakalaka/pull/3

---

## What Was Built

### Video Studio (`/ai/video`)
A dedicated interface for video generation with ComfyUI, featuring:

1. **Multi-Segment Video Creation**
   - Timeline view showing all segments
   - Duration display per segment and total
   - Segment preview, deletion, and management

2. **Continue From Last Frame**
   - Extracts final frame from generated video
   - Uses it as input for next segment
   - Auto-suggests incremented seed for consistency
   - Help modal explaining the workflow

3. **Video Stitching**
   - FFmpeg-powered segment concatenation
   - "Stitch All" button in timeline panel
   - Downloads combined video

4. **Model-Specific Parameters**
   - **LTX-Video**: Sampler selection (euler, dpmpp_2m, etc.), strength, max/base shift
   - **Wan 2.x**: Motion strength, shift (1-10), scheduler (unipc/euler/ddim)
   - **Hunyuan**: Embedded CFG scale

5. **Video Quality (CRF) Control**
   - Slider from 10 (best) to 35 (smallest file)
   - Dynamic hint showing quality level
   - Default: 19 (high quality)

6. **Model Tips Panel**
   - Collapsible panel with optimal settings per model
   - Example prompts with "Use Example" button
   - Recommended negative prompts (LTX only)
   - Smart negative prompt handling (disabled for Wan/Hunyuan)

---

## Files Created

| File | Purpose |
|------|---------|
| `dashboard/templates/ai_video.html` | Video Studio UI (~1900 lines) |
| `dashboard/video_model_params.py` | Model parameter definitions |
| `dashboard/video_utils.py` | FFmpeg utilities for frame extraction/stitching |
| `docs/ai-studio.md` | AI Studio documentation |
| `docs/ai-studio-saved-compare.md` | Save/compare feature docs |

---

## Files Modified

| File | Changes |
|------|---------|
| `dashboard/server.py` | Video API endpoints, workflow builders, VIDEO_MODEL_TIPS |
| `dashboard/templates/base.html` | Added Video Studio nav link |
| `dashboard/templates/ai_generate.html` | Model tips panel improvements |
| `dashboard/templates/ai_saved.html` | Gallery/save fixes |
| `dashboard/templates/ai_compare.html` | Minor updates |

---

## Key Code Locations

### Server Routes
- `/ai/video` - Video Studio page (line ~1757)
- `/api/ai/generate-video` - Video generation API (line ~2270)
- `/api/ai/video/extract-frame` - Extract last frame (line ~2470)
- `/api/ai/video/stitch` - Stitch segments (line ~2500)

### Workflow Builders
- `build_video_workflow()` - Dispatcher (line ~3437)
- `build_ltx_video_workflow()` - LTX builder (line ~3545)
- `build_wan_video_workflow()` - Wan builder (line ~3200)
- `build_hunyuan_video_workflow()` - Hunyuan builder (line ~3350)

### Model Parameters
- `VIDEO_MODEL_PARAMS` in `video_model_params.py` - Parameter definitions
- `VIDEO_MODEL_TIPS` in `server.py` (line ~1244) - Tips content

---

## Parameter Reference

### LTX-Video
| Parameter | Range | Default | Notes |
|-----------|-------|---------|-------|
| Sampler | euler, dpmpp_2m, etc. | euler | euler is fastest |
| Strength | 0.5-1.0 | 0.8 | Higher = more faithful to input |
| Max Shift | 1.0-4.0 | 2.05 | Noise schedule (advanced) |
| Base Shift | 0.5-2.0 | 0.95 | Noise schedule (advanced) |
| CRF | 10-35 | 19 | Video quality |

### Wan 2.x
| Parameter | Range | Default | Notes |
|-----------|-------|---------|-------|
| Motion Strength | 0.0-1.0 | 0.7 | Key parameter for movement |
| Shift | 1.0-10.0 | 5.0 | Higher = more dramatic motion |
| Scheduler | unipc, euler, ddim | unipc | unipc fastest, euler most stable |
| CRF | 10-35 | 19 | Video quality |

### HunyuanVideo
| Parameter | Range | Default | Notes |
|-----------|-------|---------|-------|
| Embedded CFG | 1.0-15.0 | 6.0 | Quality vs creativity balance |
| CRF | 10-35 | 19 | Video quality |

---

## Import Fix Note

The `video_model_params.py` import has a fallback for running from dashboard directory:

```python
try:
    from dashboard.video_model_params import VIDEO_MODEL_PARAMS, ...
    VIDEO_PARAMS_AVAILABLE = True
except ImportError:
    try:
        from video_model_params import VIDEO_MODEL_PARAMS, ...
        VIDEO_PARAMS_AVAILABLE = True
    except ImportError:
        VIDEO_PARAMS_AVAILABLE = False
```

---

## Testing Checklist

- [ ] Video Studio loads at `/ai/video`
- [ ] Model selector shows available video models with types
- [ ] Model tips panel expands/collapses
- [ ] "Use Example Prompt" fills prompt field
- [ ] Negative prompt disabled for Wan/Hunyuan models
- [ ] CRF slider updates hint text
- [ ] LTX shows sampler dropdown
- [ ] Wan shows shift slider and scheduler dropdown
- [ ] Video generates successfully
- [ ] "Continue From Last Frame" extracts frame and sets up next generation
- [ ] Continuation guide modal opens and closes
- [ ] "Stitch All" combines segments into single video

---

## Next Steps / Future Ideas

1. **First-Last-Frame to Video** - Wan 2.x supports FLF2V mode
2. **Batch processing** - Generate multiple variations
3. **Preset system** - Save/load parameter configurations
4. **Progress indicator** - Real-time generation progress
5. **Audio support** - Add audio to stitched videos
