# AI Studio - Complete Documentation

A local, privacy-first image and video generation application built into the Boomshakalaka dashboard. All processing happens 100% locally - nothing is sent to external servers.

**URL:** `http://localhost:3003/ai/`
**Backend:** ComfyUI at `127.0.0.1:8188`

---

## Table of Contents

1. [Generation Modes](#generation-modes)
2. [Model & LoRA Management](#model--lora-management)
3. [Saved Generations & Gallery](#saved-generations--gallery)
4. [Comparison Features](#comparison-features)
5. [Session History](#session-history)
6. [ComfyUI Integration](#comfyui-integration)
7. [API Reference](#api-reference)
8. [UI Features](#ui-features)
9. [Configuration & Paths](#configuration--paths)

---

## Generation Modes

### Text-to-Image (txt2img)

**Route:** `/ai/generate`
**API:** `POST /api/ai/generate`

Generates images from text prompts using checkpoint models (SDXL, Flux, SD3, etc.).

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | string | required | Text description of desired image |
| `negative_prompt` | string | "" | What to avoid in the image |
| `model` | string | required | Checkpoint model filename |
| `width` | int | 1024 | Image width (512-1536) |
| `height` | int | 1024 | Image height (512-1536) |
| `seed` | int | -1 | Random seed (-1 = random) |
| `steps` | int | 25 | Sampling steps (10-50) |
| `cfg_scale` | float | 7.0 | Guidance scale (1-15) |
| `sampler` | string | "euler" | Sampling method |
| `loras` | array | [] | LoRA configurations |
| `batch_size` | int | 1 | Images per batch (1-20) |

**Samplers:** euler, euler_ancestral, dpmpp_2m, dpmpp_2m_sde, dpmpp_3m_sde, ddim

**LoRA Format:**
```json
{
  "filename": "style_lora.safetensors",
  "strength": 0.8
}
```
- Strength range: 0.0-2.0 (>1.0 amplifies effect)
- Multiple LoRAs chain sequentially

---

### Image-to-Image (img2img)

**Tab:** "Image to Image" in `/ai/generate`
**API:** `POST /api/ai/generate` with `input_image` parameter

Transforms existing images using text prompts.

**Additional Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_image` | string | required | Uploaded image filename |
| `denoise` | float | 0.75 | Transformation strength (0-1) |

**Image Upload:**
- Endpoint: `POST /api/ai/upload`
- Formats: PNG, JPG, WebP
- Drag-and-drop from output area supported

---

### Image-to-Video (img2vid)

**Tab:** "Image to Video" in `/ai/generate`
**API:** `POST /api/ai/generate-video`

Animates static images into videos.

**Supported Video Models:**

| Model | Filename | VRAM | Notes |
|-------|----------|------|-------|
| LTX-Video 13B | `ltxv-13b-0.9.8-distilled-fp8.safetensors` | ~14GB | Recommended, general purpose |
| LTX-Video 2B | `ltx-video-2b-v0.9.safetensors` | ~8GB | Faster, lower VRAM |
| Wan 2.2 TI2V | `TI2V/Wan2_2-TI2V-5B_fp8_e4m3fn_scaled_KJ.safetensors` | ~10GB | Has motion_strength param |
| HunyuanVideo 1.5 | `hunyuanvideo1.5_720p_i2v_cfg_distilled_fp16.safetensors` | ~16GB | High quality |

**Video Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_image` | string | required | Image to animate |
| `video_model` | string | required | Video model filename |
| `width` | int | 768 | Video width (512-960) |
| `height` | int | 768 | Video height (512-960) |
| `frames` | int | 49 | Frame count (25≈1s, 49≈2s, 81≈3s, 121≈5s) |
| `fps` | int | 24 | Frames per second (8, 16, 24, 30) |
| `motion_strength` | float | 0.7 | Wan model only (0-1) |

**VRAM Estimation:**
```
vram = base * (1 + (res_mult - 1) * 0.3) * (1 + (frame_mult - 1) * 0.2)
```
Warning shown if estimated >22GB.

---

## Model & LoRA Management

**Page:** `/ai/models`

### Model Discovery

Models auto-detected by scanning directories for `.safetensors`, `.ckpt`, `.pt` files.

**Type Detection:**
- "flux" in name → Flux
- "xl" in name OR >6GB → SDXL
- "sd3" in name → SD3
- <5GB → SD 1.5

**Locations:**
- Checkpoints: `models/checkpoints/`
- LoRAs: `models/loras/`
- Symlink: `models/ → ComfyUI/models/`

### Model Tips

**API:** `GET /api/ai/model-tips/{filename}`

Returns model-specific recommendations:
- Best CFG range
- Best step count
- Recommended dimensions
- Recommended sampler
- Example prompts
- Trigger words (for LoRAs)

### Model Download

**API:** `POST /api/ai/models/download`

**Supported Sources:**
1. **HuggingFace** - `/blob/main/` or `/resolve/main/` URLs
2. **CivitAI** - Model URLs with `modelVersionId`
3. **Direct URLs** - Any `.safetensors` or `.ckpt` file

**Progress Tracking:** `GET /api/ai/models/download/{download_id}`

### Model/LoRA Deletion

**APIs:**
- `POST /api/ai/models/delete` with `{ "filename": "..." }`
- `POST /api/ai/loras/delete` with `{ "filename": "..." }`

---

## Saved Generations & Gallery

**Page:** `/ai/saved`
**Database:** `data/databases/generations.db` (SQLite)

### Database Schema

```sql
CREATE TABLE generations (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    prompt TEXT NOT NULL,
    negative_prompt TEXT DEFAULT '',
    model TEXT NOT NULL,
    seed INTEGER,
    steps INTEGER DEFAULT 25,
    cfg_scale REAL DEFAULT 7.0,
    sampler TEXT DEFAULT 'euler',
    scheduler TEXT DEFAULT 'normal',
    width INTEGER DEFAULT 1024,
    height INTEGER DEFAULT 1024,
    workflow_json TEXT,
    tags TEXT DEFAULT '',
    rating INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    parent_id TEXT,
    output_path TEXT,
    thumbnail_path TEXT
);
```

### Save to Gallery

**API:** `POST /api/ai/save`

```json
{
  "id": "generation_id",
  "params": {
    "prompt": "...",
    "model": "...",
    "seed": 12345,
    // ... all generation params
  }
}
```

**Key Feature:** Opt-in saving - generations are NOT auto-saved, preserving privacy.

### Gallery Features

- **Filtering:** Search by prompt, filter by model, filter favorites
- **Load:** Click to reload parameters into generate form
- **Delete:** Remove from database (optionally delete files)
- **Selection:** Checkbox multi-select for comparison
- **Video Support:** Videos display with "VIDEO" badge and play icon overlay

### Video Support in Gallery

The gallery automatically detects and displays videos differently from images:

**Detection:** Videos identified by `output_path` extension (`.mp4`, `.webm`, `.gif`)

**Visual Indicators:**
- "VIDEO" badge in top-right corner
- Play button overlay on thumbnail
- Video element with `preload="metadata"` for thumbnail extraction

**Playback:** Clicking a video redirects to generate page with `?load={id}&type=video`

### Save API (Images & Videos)

**API:** `POST /api/ai/save`

```json
{
  "id": "generation_id",
  "params": {
    "prompt": "...",
    "model": "...",
    "seed": 12345
  },
  "is_video": false
}
```

**Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `id` | string | required | Generation ID |
| `params` | object | required | Generation parameters |
| `is_video` | boolean | false | Set to true for video saves |

**Video Save Behavior:**
- When `is_video: true`, searches ComfyUI output directory for video file
- Stores full path in `output_path` column for later retrieval
- Video served via `/api/ai/video/{id}` endpoint

---

## Comparison Features

**Page:** `/ai/compare`

### Selection Workflow

1. On `/ai/saved`, check boxes on images to select
2. Floating action bar appears showing count
3. Click "Compare Selected"
4. Data saved to `localStorage('compareList')`
5. Redirected to `/ai/compare`

### Grid Layouts

| Option | Rows | Columns | Total Slots |
|--------|------|---------|-------------|
| 1x2 | 1 | 2 | 2 |
| 2x2 | 2 | 2 | 4 |
| 2x3 | 2 | 3 | 6 |

### Parameter Diff Panel

Displays when 2+ images loaded, highlighting differences in:
- Seed, CFG Scale, Steps, Sampler, Model, Width, Height

### Slot Controls

- **Use Settings:** Load parameters into generate form
- **Remove:** Remove from comparison

---

## Batch Generation

Generate multiple images in a single operation using the batch controls on the generate page.

### Controls

| Control | Range | Description |
|---------|-------|-------------|
| Batch Size | 1-20 | Images generated per ComfyUI batch |
| Number of Batches | 1-20 | Sequential batches to run |

**Maximum:** 20 × 20 = 400 images per batch operation

### How It Works

1. **Batch Size** controls ComfyUI's `EmptyLatentImage.batch_size` parameter
   - Higher values use more VRAM but generate faster
   - All images in a batch share the same seed base

2. **Number of Batches** runs sequential API calls
   - Each batch gets a new random seed for variety
   - Session history updates after each batch completes

### VRAM Considerations

- Batch size increases VRAM usage proportionally
- For high-resolution (1024×1024+), keep batch_size ≤ 8 to avoid OOM
- Warning shown if generating > 400 images

### API Response Format

When `batch_size > 1`, the API returns an images array:

```json
{
  "images": [
    { "id": "abc123_0", "url": "/api/ai/image/abc123_0" },
    { "id": "abc123_1", "url": "/api/ai/image/abc123_1" }
  ],
  "seed": 12345678,
  "batch_size": 4,
  "params": { ... }
}
```

---

## Session History

**Storage:** Browser `sessionStorage('aiStudioHistory')`
**Persistence:** Within tab session only

After each generation:
1. Thumbnail added to "Session History" section
2. Click to reload into output area
3. Drag to img2img/img2vid upload areas
4. "Clear" button to wipe history

---

## ComfyUI Integration

### Status Check

**API:** `GET /api/ai/comfy-status`

```json
{
  "running": true,
  "message": "Running - VRAM: 2.3/24.0 GB",
  "url": "http://127.0.0.1:8188",
  "vram_used": 2.3,
  "vram_total": 24.0
}
```

### Workflow Execution

1. Build workflow JSON (txt2img, img2img, or video)
2. POST to `http://127.0.0.1:8188/prompt`
3. Poll `/history/{prompt_id}` until complete
   - **Images:** 5 minute timeout
   - **Videos:** 30 minute timeout (high-res video takes longer)
4. Copy output to `data/generations/`

### Debug Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/ai/debug/outputs` | List recent ComfyUI output files |
| `POST /api/ai/debug/workflow` | Preview workflow without executing |
| `GET /api/ai/debug/comfyui` | ComfyUI system info |

---

## API Reference

### Generation

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/ai/generate` | txt2img / img2img |
| POST | `/api/ai/generate-video` | img2vid |

### Images & Videos

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/ai/image/{id}` | Serve generated image |
| GET | `/api/ai/image/{id}/thumb` | Serve thumbnail |
| GET | `/api/ai/video/{id}` | Serve generated video |
| POST | `/api/ai/upload` | Upload for img2img/vid |
| GET | `/api/ai/upload/{filename}` | Serve uploaded image |

### Saved Generations

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/ai/save` | Save to gallery |
| GET | `/api/ai/generation/{id}` | Get generation details |
| DELETE | `/api/ai/generation/{id}` | Delete generation |

### Models & LoRAs

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/ai/models` | List checkpoints |
| GET | `/api/ai/loras` | List LoRAs |
| GET | `/api/ai/model-tips/{filename}` | Get model tips |
| POST | `/api/ai/models/delete` | Delete checkpoint |
| POST | `/api/ai/loras/delete` | Delete LoRA |
| POST | `/api/ai/models/download` | Start download |
| GET | `/api/ai/models/download/{id}` | Download progress |

### System

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/ai/comfy-status` | ComfyUI status |

---

## UI Features

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Generate |
| R | Random seed |
| +/- | Adjust CFG |
| [/] | Adjust steps |

### Generate Page Layout

```
┌─────────────────────────────────────────────────────────┐
│ Output Area                    │ Control Panel          │
│ ┌─────────────────────────┐   │ [txt2img][img2img][vid]│
│ │                         │   │ Prompt: [............] │
│ │     Generated Image     │   │ Negative: [...........] │
│ │                         │   │ Model: [dropdown ▼]    │
│ │                         │   │ LoRAs: [+ Add LoRA]    │
│ └─────────────────────────┘   │ Size: [1024] x [1024]  │
│ [Save to Gallery] [Download]  │ Seed: [12345] [±][Rand]│
│                               │ Steps: [25] [±5]       │
│ Session History:              │ CFG: [7.0] [±]         │
│ [thumb][thumb][thumb]...      │ Sampler: [euler ▼]     │
│                               │ [Generate] [Regenerate]│
│                               │                        │
│                               │ ┌──Batch Generation──┐ │
│                               │ │ Batch Size:  [==]20│ │
│                               │ │ # Batches:   [==]20│ │
│                               │ │ Total: 400 images  │ │
│                               │ │ [Generate Batch]   │ │
│                               │ └────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Saved Page Layout

```
┌─────────────────────────────────────────────────────────┐
│ [Search...] [Model ▼] [Favorites ▼]                     │
├─────────────────────────────────────────────────────────┤
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐            │
│ │☑ IMG   │ │☐ VIDEO │ │☑ IMG   │ │☐ IMG   │            │
│ │        │ │  [▶]   │ │        │ │        │            │
│ │ prompt │ │ prompt │ │ prompt │ │ prompt │            │
│ │[Load][X]│ │[Load][X]│ │[Load][X]│ │[Load][X]│            │
│ └────────┘ └────────┘ └────────┘ └────────┘            │
├─────────────────────────────────────────────────────────┤
│         [ 2 selected ] [Clear] [Compare Selected]       │
└─────────────────────────────────────────────────────────┘
```

**Note:** Videos show a "VIDEO" badge and play button overlay. Clicking loads them into the generate page video player.

---

## Configuration & Paths

| Path | Purpose |
|------|---------|
| `models/checkpoints/` | Checkpoint models |
| `models/loras/` | LoRA files |
| `data/generations/` | Generated images |
| `data/databases/generations.db` | SQLite database |
| `data/uploads/` | Uploaded images |
| `/home/pds/image_gen/ComfyUI` | ComfyUI installation |

**ComfyUI Connection:**
- Host: `127.0.0.1` (localhost only)
- Port: `8188`

---

## Privacy

- **100% Local:** All processing on local GPU
- **No Telemetry:** No analytics or tracking
- **Opt-in Saving:** Generations not auto-saved
- **Offline Capable:** Works without internet (after models downloaded)
