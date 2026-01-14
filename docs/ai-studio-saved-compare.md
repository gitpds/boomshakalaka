# AI Studio - Saved Generations & Compare Features

Documentation for the saved generations management and comparison features added to AI Studio.

## Overview

These features allow users to:
1. **Save** images and videos to the gallery
2. **Delete** saved generations from the gallery
3. **Select multiple images** for comparison
4. **Compare images side-by-side** with parameter diff highlighting
5. **View saved videos** with play icon overlay and proper playback

---

## 1. Video Support in Gallery

### How Videos Are Detected

Videos are automatically detected by checking the `output_path` field in the database:

```python
is_video = gen.output_path and (
    gen.output_path.endswith('.mp4') or
    gen.output_path.endswith('.webm') or
    gen.output_path.endswith('.gif')
)
```

### Visual Indicators

Location: `dashboard/templates/ai_saved.html`

Videos in the gallery display:
- **"VIDEO" badge** - Top-right corner, accent-colored
- **Play button overlay** - Circular play icon centered on thumbnail
- **Video element** - Uses `<video>` tag instead of `<img>` for thumbnail

### CSS Styles

```css
.history-image.video-item::after {
    /* Circular background */
    width: 60px; height: 60px;
    background: rgba(0, 0, 0, 0.7);
    border-radius: 50%;
}

.history-image.video-item::before {
    /* Play triangle */
    border: 12px solid transparent;
    border-left: 20px solid white;
}

.video-badge {
    background: var(--accent);
    padding: 4px 8px;
    font-size: 0.7rem;
}
```

### Video Playback

Clicking a video in the gallery:
1. Redirects to `/ai/generate?load={id}&type=video`
2. Generate page detects `type=video` parameter
3. Calls `displayVideo()` instead of `displayImage()`
4. Video plays with controls, autoplay, loop, and muted

---

## 2. Delete Functionality

### API Endpoint

**`DELETE /api/ai/generation/<gen_id>`**

Location: `dashboard/server.py:2063`

Deletes a saved generation from the database.

**Parameters:**
- `gen_id` (path): The generation ID to delete
- `delete_files` (query, optional): Set to `true` to also delete the image files from disk

**Response:**
```json
{
  "deleted": true,
  "id": "generation_id_here"
}
```

**Example:**
```bash
# Delete from database only (keeps image files)
curl -X DELETE http://localhost:3003/api/ai/generation/abc123

# Delete from database AND delete image files
curl -X DELETE "http://localhost:3003/api/ai/generation/abc123?delete_files=true"
```

### Frontend Implementation

Location: `dashboard/templates/ai_saved.html`

Each saved generation card now has a "Delete" button that:
1. Shows a confirmation dialog
2. Calls the DELETE endpoint via fetch
3. Animates the card out (fade + scale) on success
4. Removes the card from the DOM

```javascript
async function deleteGeneration(event, id) {
    event.stopPropagation();
    if (!confirm('Are you sure you want to delete this generation?')) return;

    const response = await fetch(`/api/ai/generation/${id}`, { method: 'DELETE' });
    const data = await response.json();

    if (data.deleted) {
        // Animate and remove card
        const item = document.querySelector(`.history-item[data-id="${id}"]`);
        item.style.opacity = '0';
        item.style.transform = 'scale(0.9)';
        setTimeout(() => item.remove(), 300);
    }
}
```

---

## 3. Compare Selection Feature

### How It Works

1. Each saved generation card has a **checkbox** in the top-left corner
2. Selecting images highlights them with an accent border
3. A **floating action bar** appears at the bottom when 1+ items are selected
4. Clicking "Compare Selected" saves the selection to localStorage and navigates to `/ai/compare`

### Data Flow

```
User selects images → selectedItems Set tracks IDs
                   → Cards get .selected class
                   → Floating bar shows count

User clicks "Compare Selected" → Build compareList array with all params
                               → Save to localStorage('compareList')
                               → Navigate to /ai/compare

Compare page loads → Reads localStorage('compareList')
                  → Renders grid with images
                  → Shows parameter differences
```

### Selection Data Structure

When navigating to compare, the following data is stored per image:

```javascript
{
    id: "generation_id",
    image_url: "/api/ai/image/generation_id",
    seed: "12345",
    steps: 25,
    cfg_scale: 7.0,
    sampler: "euler",
    model: "model_name.safetensors",
    width: 1024,
    height: 1024
}
```

### Key Functions

| Function | Purpose |
|----------|---------|
| `toggleSelection(event, id)` | Add/remove item from selection set |
| `updateFloatingBar()` | Show/hide floating bar based on selection count |
| `clearSelection()` | Deselect all items |
| `compareSelected()` | Build data, save to localStorage, navigate to compare |

---

## 4. Compare Page Grid Sizes

### Available Layouts

| Option | Rows | Columns | Total Slots |
|--------|------|---------|-------------|
| 1x2    | 1    | 2       | 2           |
| 2x2    | 2    | 2       | 4           |
| 2x3    | 2    | 3       | 6           |

### CSS Classes

Location: `dashboard/templates/ai_compare.html`

```css
.compare-grid.grid-1x2 { grid-template-columns: 1fr 1fr; }
.compare-grid.grid-2x2 { grid-template-columns: 1fr 1fr; }
.compare-grid.grid-2x3 { grid-template-columns: 1fr 1fr 1fr; }
```

### Grid Size Parsing

The format is `RxC` (Rows x Columns):

```javascript
const [rows, cols] = gridSize.split('x').map(Number);
const totalSlots = rows * cols;
```

---

## 5. Parameter Diff Panel

When 2+ images are loaded in the compare view, a "Parameter Differences" panel appears showing:

- Seed
- CFG Scale
- Steps
- Sampler
- Model
- Width
- Height

Values that **differ** between images are highlighted with the accent color.

---

## File Locations

| File | Purpose |
|------|---------|
| `dashboard/server.py:1970` | Save endpoint with `is_video` support |
| `dashboard/server.py:2063` | DELETE endpoint |
| `dashboard/server.py:2266` | Video serving endpoint (checks DB `output_path`) |
| `dashboard/templates/ai_saved.html` | Saved gallery with video detection & display |
| `dashboard/templates/ai_compare.html` | Compare grid view |
| `dashboard/templates/ai_generate.html:2314` | `handleLoadParameter()` with video support |

---

## Database Schema

Generations are stored in SQLite at `data/databases/generations.db`:

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

---

## UI Components

### Saved Page (`/ai/saved`)

```
┌─────────────────────────────────────────────────────────┐
│ [Search...] [Model Filter ▼] [All/Favorites ▼]          │
├─────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│ │☑         │ │☐  VIDEO  │ │☑         │ │☐         │    │
│ │  IMAGE   │ │   [▶]    │ │  IMAGE   │ │  IMAGE   │    │
│ │          │ │          │ │          │ │          │    │
│ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤    │
│ │ Prompt...│ │ Prompt...│ │ Prompt...│ │ Prompt...│    │
│ │ [model]  │ │ [model]  │ │ [model]  │ │ [model]  │    │
│ ├──────────┤ ├──────────┤ ├──────────┤ ├──────────┤    │
│ │[Load][Del]│ │[Load][Del]│ │[Load][Del]│ │[Load][Del]│    │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
├─────────────────────────────────────────────────────────┤
│        ┌─────────────────────────────────────┐          │
│        │ 2 selected [Clear] [Compare Selected]│          │
│        └─────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────┘
```

**Note:** Videos display with a "VIDEO" badge and play button [▶] overlay.

### Compare Page (`/ai/compare`)

```
┌─────────────────────────────────────────────────────────┐
│ Grid Size: [1x2] [2x2] [2x3]    ☑ Sync Zoom [Clear All] │
├─────────────────────────────────────────────────────────┤
│ ┌────────────────────┐  ┌────────────────────┐          │
│ │                    │  │                    │          │
│ │      IMAGE 1       │  │      IMAGE 2       │          │
│ │                    │  │                    │          │
│ ├────────────────────┤  ├────────────────────┤          │
│ │ Seed: 12345        │  │ Seed: 67890        │          │
│ │ CFG: 7             │  │ CFG: 7             │          │
│ │ Steps: 25          │  │ Steps: 30          │          │
│ ├────────────────────┤  ├────────────────────┤          │
│ │[Use Settings][Remove]│  │[Use Settings][Remove]│          │
│ └────────────────────┘  └────────────────────┘          │
├─────────────────────────────────────────────────────────┤
│ Parameter Differences                                    │
│ ─────────────────────────────────────────────────────── │
│ seed        │  12345  │  67890  │  (highlighted)        │
│ cfg_scale   │    7    │    7    │                       │
│ steps       │   25    │   30    │  (highlighted)        │
└─────────────────────────────────────────────────────────┘
```

---

## Future Enhancements

Potential improvements that could be added:

1. **Batch delete** - Delete multiple selected items at once
2. **Export collage** - Save comparison grid as single image
3. **Sync zoom/pan** - Synchronized zoom across all compare slots
4. **Drag-and-drop reorder** - Rearrange images in compare view
5. **Save comparison sets** - Bookmark specific comparisons for later
