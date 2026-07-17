# JSON Table Editor — CMS Guide

> Content management system for the Roam Anguilla app.  
> **Editor:** `http://localhost:5050` · **Launch:** `python3 server.py`

---

## 1. Quick Start

```bash
cd /Users/kayboy/Documents/ROAMCMS
python3 server.py
# → Open http://localhost:5050
```

Or double-click **`JSON Table Editor.command`** / **`JSON Table Editor.app`** (Desktop or `/Applications`).

---

## 2. File Overview

| File | Purpose | Rows |
|---|---|---|
| `appcontent.json` | In-app content cards (featured, eat, activity) | ~3 |
| `events.json` | Weekly event schedule with place links | ~94 |
| `places.json` | Venue directory with Google Maps URLs | ~200+ |
| `webcontent.json` | Blog / web articles | ~2 |

---

## 3. Description Markup Schema

The `description` field in `appcontent.json` supports **4 tag types**. Tags are **validated live** against `places.json` and `events.json` with color coding.

### 3.1 Place Links

Link to a venue in `places.json`.

```html
<place>Sunset Lounge</place>
```

| Color | Meaning |
|---|---|
| 🟢 **Green bold** | Place exists in `places.json` — will render as a live `NavigationLink` in the app |
| 🔴 **Red strikethrough** | Place not found in `places.json` — app shows gray italic fallback |
| 🟠 **Orange** | Tag opened (`<place>`) but not yet closed — incomplete |

**Autocomplete:** Type `<place>` in the description editor → dropdown of all places from `places.json` → pick one → auto-closes `</place>`.

> **Deprecated:** `<link>/place/Name</link>` — migrated to `<place>Name</place>`.

### 3.2 Event Links

Link to an event in `events.json`. Format: `EventName+PlaceName+day`

```html
<event>SPROCKA @ VEYA RESTAURANT+Veya Restaurant+tuesday</event>
```

The Swift app splits on `+`:
- `parts[0]` = event name (fuzzy match)
- `parts[1]` = place name (fuzzy match)
- `parts[2]` = day of week

| Color | Meaning |
|---|---|
| 🟢 **Green bold** | Event found in `events.json` (name, place, and day all match) |
| 🔴 **Red strikethrough** | Event not found — app shows gray italic fallback |
| 🟠 **Orange** | Tag opened but not closed — incomplete |

**Autocomplete:** Type `<event>` → dropdown of events from `events.json` → pick → inserts `Name+Place+day</event>`.

**Note:** Event names can contain `&` (e.g. `CLAYTON CARTY & ACOUSTICS`) — the parser handles this correctly.

### 3.3 URL Links

```html
<a href='https://roamaxa.app/blog/volunteer-ant/'>Read more on our blog</a>
```

| Color | Meaning |
|---|---|
| 🔵 **Blue underline** | Clickable URL — renders as `Link` in the app |

Use single quotes `'...'` or double quotes `"..."` for the href.

### 3.4 Line Breaks

```html
<br>
```

Shown as `↵<br>` in the editor. Renders as `Spacer().frame(height: 10)` in the app.

---

## 4. Editor Features

### 4.1 Table Interface

| Feature | How |
|---|---|
| **Switch files** | Click file tabs at top |
| **Edit any cell** | Click cell → type (contenteditable) |
| **Description cells** | Click to open rich editor with live preview panel |
| **Add row** | `＋ Add Row` or `Ctrl+N` |
| **Duplicate row** | `⧉` button per row |
| **Delete rows** | Check rows → `🗑 Delete`, or `✕` per row |
| **Save** | `💾 Save` or `Ctrl+S` |
| **Export CSV** | `📥 CSV` |
| **Google Sheets paste** | Copy from Sheets → click a cell → `Ctrl+V` |

### 4.2 Place Dropdown (events.json)

The `place` column in `events.json` is a **linked dropdown** populated from `places.json`. Selecting a place **auto-fills** the `placeurl` field with the Google Maps URL.

Linked columns show a 🔗 icon in the header.

### 4.3 Description Preview Panel

When editing a description cell in `appcontent.json`, a **preview panel** appears below the table showing the parsed markup with live color-coded validation.

### 4.4 Google Sheets Paste

Copy tab-separated data from Google Sheets and paste (`Ctrl+V`) into the table. The parser:
1. Detects if the first row is a header (matches column names)
2. Maps columns by name or position
3. Auto-expands rows if needed
4. Matches dropdown values for linked columns (e.g. place names)
5. Preserves number/boolean types

### 4.5 Keyboard Shortcuts

| Key | Action |
|---|---|
| `Ctrl+S` / `Cmd+S` | Save |
| `Ctrl+N` / `Cmd+N` | Add row |
| `Esc` | Exit description editor |

---

## 5. Event List Bulk Import

To bulk-import events from a text list:

```
Saturday
- PLACE_NAME | ACT_NAME | START_TIME - END_TIME
- PLACE_NAME | SUB_LOCATION | ACT_NAME | START_TIME - END_TIME
```

**Rules:**
- Day headers: `Saturday`, `Sunday`, `Monday`, etc.
- Pipe `|` separates place, act, and time
- Times: `7:30 PM - 9:30 PM`, `11:00 PM - UNTIL`
- `UNTIL` → 26.0 (2 AM next day)
- `SUNSET` → 19.0 (7 PM)
- Overnight: `11:00 PM - 4:00 AM` → end+24h if start ≥ 18

**Paste the list to Copilot** — it parses, matches places against `places.json`, auto-fills `placeurl`, and writes to `events.json`.

---

## 6. JSON Schemas

### 6.1 appcontent.json

```json
{
  "title": "Title of the content card",
  "subheadline": "Short subtitle (optional)",
  "description": "Rich text with <place>, <event>, <a>, <br> markup",
  "date": "2026-07-15",
  "url": "",
  "image": "https://...",
  "tag": "Festival",
  "tab": "featured"
}
```

| Field | Type | Notes |
|---|---|---|
| `title` | string | Card heading |
| `subheadline` | string | Secondary text |
| `description` | string | **Markup-enabled** (place, event, URL, br tags) |
| `date` | string | Display date |
| `url` | string | External link (optional) |
| `image` | string | Hero image URL |
| `tag` | string | Category badge |
| `tab` | string | `featured`, `eat`, `activity` |

### 6.2 events.json

```json
{
  "name": "DJ SUGAR @ SUNSET LOUNGE AT FOUR SEASONS",
  "eventday": "friday",
  "eventstart": 17.0,
  "eventend": 19.0,
  "eventdesc": "",
  "place": "Sunset Lounge",
  "placeurl": "https://www.google.com/maps/place/..."
}
```

| Field | Type | Notes |
|---|---|---|
| `name` | string | `ACT_NAME @ PLACE_NAME` |
| `eventday` | string | `sunday`–`saturday` |
| `eventstart` | float | Decimal hours (17.0 = 5:00 PM) |
| `eventend` | float | Decimal hours (26.0 = 2 AM next day) |
| `eventdesc` | string | Internal description |
| `place` | string | **Linked to `places.json` via dropdown** |
| `placeurl` | string | **Auto-filled from `places.json` `googleurl`** |

### 6.3 places.json

```json
{
  "googleurl": "https://www.google.com/maps/place/...",
  "title": "Sunset Lounge",
  "label": "Food",
  "type": "Restaurant",
  "tags": "",
  "website": "",
  "phone": "+1 264-...",
  "location": "West End, Anguilla",
  "latitude": 18.17,
  "longitude": -63.15,
  "open": 17,
  "closes": 23,
  "closedon": "",
  "image": "https://..."
}
```

### 6.4 content.json (Blog / Web Articles)

> **Note:** `webcontent.json` was consolidated into `content.json` on 2026-07-17.
> This single file now feeds the RoamWeb homepage, blog, AND the iOS web content carousel.

```json
{
  "title": "Anguilla Summer Festival 2026 — The Complete Guide",
  "date": "July 17, 2026",
  "tag": "Festivals & Events",
  "description": "Your complete guide to Anguilla Summer Festival 2026. Full schedule, event breakdowns, pricing, and insider tips — from J'Ouvert and boat racing to the Caribbean Beach Party, pageants, Calypso, and more.",
  "url": "/blog/summer-festival-2026/",
  "image": "/blog/summer-festival-2026/hero.webp"
}
```

| Field | Type | Notes |
|---|---|---|
| `title` | string | Blog post title |
| `date` | string | Display date (e.g. "July 17, 2026") |
| `tag` | string | Category badge (e.g. "Festivals & Events", "Travel Tips") |
| `description` | string | Plain text excerpt — NO markup tags (unlike appcontent.json) |
| `url` | string | Relative path to blog post (e.g. `/blog/summer-festival-2026/`) |
| `image` | string | Relative path to hero image |

---

## 7. Time Conversion Reference

| Time | Decimal |
|---|---|
| 12:00 PM | 12.0 |
| 1:00 PM | 13.0 |
| 5:00 PM | 17.0 |
| 6:30 PM | 18.5 |
| 7:00 PM | 19.0 |
| 8:00 PM | 20.0 |
| 9:45 PM | 21.75 |
| 11:00 PM | 23.0 |
| 12:00 AM | 0.0 (or 24.0) |
| 1:00 AM | 1.0 (or 25.0) |
| 4:00 AM | 4.0 (or 28.0) |
| UNTIL | 26.0 (sentinel) |

**Rule:** If `end < start` and `start >= 18`, add 24 to end (overnight event).

---

## 8. Linked Columns Configuration

Defined in `templates/index.html`:

```js
const linkedColumns = {
  'events.json': {
    'place': {
      lookupFile: 'places.json',
      lookupKey: 'title',       // column in places.json
      autofill: {               // auto-fill these when place selected
        'placeurl': 'googleurl'
      }
    }
  }
};
```

To add more linked columns, extend this config object.

---

## 9. Adding a Missing Place

If a venue isn't in `places.json`:

1. Open `places.json` in the editor
2. Click `＋ Add Row`
3. Fill in `title`, `googleurl` (from Google Maps), and other fields
4. `💾 Save`
5. Switch back to `events.json` — the dropdown now includes the new place, selecting it auto-fills `placeurl`

---

## 10. Architecture

```
ROAMCMS/
├── server.py              # Flask API (read/write JSON files)
├── app_launcher.py        # macOS launcher (daemonizes server)
├── templates/
│   └── index.html         # Single-page editor UI
├── appcontent.json        # In-app content cards
├── content.json            # Blog / web articles (consolidated, was webcontent.json)
├── events.json            # Event schedule
├── places.json            # Venue directory
├── requirements.txt       # Python deps (flask)
├── JSON Table Editor.app  # macOS app bundle
└── JSON Table Editor.command  # Double-click launcher
```

**Frontend → Backend flow:**
```
Browser (index.html)
  → fetch('/api/data/events.json')     GET  — load
  → fetch('/api/data/events.json')     POST — save
  → fetch('/api/files')                GET  — list files
```

---

## 11. Troubleshooting

| Problem | Fix |
|---|---|
| Server won't start | `lsof -ti:5050 \| xargs kill` then retry |
| Port 5050 in use | Kill existing: `lsof -ti:5050 \| xargs kill` |
| Place dropdown empty | Make sure `places.json` has data with `title` fields |
| Event link shows red | Event doesn't exist in `events.json` — check name+place+day |
| Place link shows red | Place not in `places.json` — add it first |
| Changes not saving | Click `💾 Save` or `Ctrl+S` |
| App won't open | Use `.command` file instead; check `python3` and `flask` are installed |
