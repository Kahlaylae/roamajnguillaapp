#!/usr/bin/env python3
"""
JSON Table Editor - Flask Server
View, edit, add, and delete rows in your JSON files through a web interface.
"""

import json
import os
import re
import subprocess
from flask import Flask, render_template, request, jsonify, send_from_directory

app = Flask(__name__)

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# Anguilla district names (ordered by specificity for matching)
ANGUILLA_DISTRICTS = [
    "West End", "Sandy Ground", "Island Harbour", "South Hill",
    "The Valley", "Blowing Point", "East End", "George Hill",
    "North Hill", "North Side", "Sandy Hill", "Stoney Ground",
    "The Quarter", "The Farrington", "Shoal Bay",
]


def normalize_location(raw):
    """Clean a raw Google Maps address into 'Area, Anguilla' format.

    Examples:
        'Sandy Ground 2640, Anguilla'     → 'Sandy Ground, Anguilla'
        '5WW4+4MG, Sandy Ground 2640, AI' → 'Sandy Ground, Anguilla'
        'Rte 1 SHOAL BAY WEST, 1254 Rupert Carty Drive, WEST END 2640, Anguilla'
                                          → 'West End, Anguilla'
    """
    if not raw or not isinstance(raw, str):
        return raw

    # Already clean? (matches 'Area, Anguilla' exactly)
    already_clean = re.match(r'^[A-Za-z ]+, Anguilla$', raw.strip())
    if already_clean:
        return raw.strip()

    raw_upper = raw.upper()
    for district in ANGUILLA_DISTRICTS:
        if district.upper() in raw_upper:
            return f"{district}, Anguilla"

    # Fallback: strip known noise patterns
    cleaned = raw
    cleaned = re.sub(r'\b\d{4,6}\b', '', cleaned)                     # Postal codes
    cleaned = re.sub(r'\b[0-9A-Z]{4}\+[0-9A-Z]{2,3}\b', '', cleaned) # Plus codes
    cleaned = re.sub(r'\bRte\s+\d+\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d+\s+\w+\s+\w+\s+(Drive|Road|Street|Lane)', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r',\s*,', ',', cleaned)
    cleaned = cleaned.strip(' ,')

    parts = [p.strip() for p in cleaned.split(',') if p.strip()]
    if len(parts) >= 2:
        area = parts[-2]
        return f"{area}, Anguilla"
    elif parts:
        return f"{parts[0]}, Anguilla"
    return raw  # Can't normalize — return as-is


def get_json_files():
    """Return list of .json files in the data directory."""
    files = []
    for f in sorted(os.listdir(DATA_DIR)):
        if f.endswith('.json') and os.path.isfile(os.path.join(DATA_DIR, f)):
            files.append(f)
    return files


def load_json(filename):
    """Safely load a JSON file."""
    filepath = os.path.join(DATA_DIR, filename)
    if not os.path.exists(filepath):
        return None, "File not found"
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data, None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {str(e)}"
    except Exception as e:
        return None, str(e)


def save_json(filename, data):
    """Save data to a JSON file with pretty formatting."""
    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True, None
    except Exception as e:
        return False, str(e)


@app.route('/')
def index():
    """Serve the main editor page."""
    files = get_json_files()
    with open(os.path.join(DATA_DIR, 'index.html'), 'r', encoding='utf-8') as f:
        html = f.read()
    # Inject file list for the template (simple replace)
    response = app.make_response(html)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/api/files')
def api_files():
    """Return list of JSON files."""
    return jsonify(get_json_files())


@app.route('/api/data/<filename>')
def api_get_data(filename):
    """Get data from a specific JSON file."""
    data, error = load_json(filename)
    if error:
        return jsonify({'error': error}), 404
    return jsonify(data)


@app.route('/api/data/<filename>', methods=['POST'])
def api_save_data(filename):
    """Save data to a specific JSON file."""
    new_data = request.get_json()
    if new_data is None:
        return jsonify({'error': 'Invalid JSON body'}), 400
    if not isinstance(new_data, list):
        return jsonify({'error': 'Data must be a JSON array'}), 400

    # Auto-normalize locations, tags, and strip id when saving places.json
    if filename == 'places.json':
        for row in new_data:
            if isinstance(row, dict):
                # Strip id — RoamIOS generates its own SHA256(title+location)
                row.pop('id', None)
                if 'location' in row:
                    row['location'] = normalize_location(row['location'])
            # Normalize tags: trim, lowercase, deduplicate within row
            if isinstance(row, dict) and 'tags' in row:
                raw = row.get('tags', '')
                if isinstance(raw, str) and raw.strip():
                    seen = set()
                    cleaned = []
                    for t in raw.split(','):
                        t = t.strip().lower()
                        if t and t not in seen:
                            seen.add(t)
                            cleaned.append(t)
                    row['tags'] = ', '.join(cleaned)

    # Event duplicate detection
    warnings = []
    if filename == 'events.json':
        from collections import Counter
        keys = []
        for row in new_data:
            if isinstance(row, dict):
                name = (row.get('name') or '').strip().lower()
                day = (row.get('eventday') or '').strip().lower()
                place = (row.get('place') or '').strip().lower()
                keys.append((name, day, place))
        dupes = [(k, c) for k, c in Counter(keys).items() if c > 1]
        if dupes:
            dup_names = [f'"{d[0][0].title()}" on {d[0][1].title()} ({d[1]}x)' for d in dupes[:5]]
            warnings.append(f'⚠️ {len(dupes)} duplicate event(s) detected: {"; ".join(dup_names)}')

    success, error = save_json(filename, new_data)
    result = {'status': 'ok', 'count': len(new_data)}
    if warnings:
        result['warnings'] = warnings
    if not success:
        return jsonify({'error': error}), 500
    return jsonify(result)


# ── Places metadata (unique labels & tags) ─────────────────────────
@app.route('/api/places-meta')
def api_places_meta():
    """Return all unique labels and tags from places.json."""
    data, _ = load_json('places.json')
    labels_set = set()
    tags_set = set()

    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                lbl = (row.get('label') or '').strip()
                if lbl:
                    labels_set.add(lbl)
                raw_tags = row.get('tags', '')
                if isinstance(raw_tags, str) and raw_tags.strip():
                    for t in raw_tags.split(','):
                        t = t.strip().lower()
                        if t:
                            tags_set.add(t)

    return jsonify({
        'labels': sorted(labels_set),
        'tags': sorted(tags_set),
    })


# ── Image file listing ────────────────────────────────────────────
IMAGES_DIR = os.path.join(DATA_DIR, 'images')
IMAGE_EXTENSIONS = {'.png', '.webp', '.jpg', '.jpeg'}
ALL_IMAGE_EXTS = {'.png','.webp','.jpg','.jpeg','.gif','.bmp','.tiff','.tif','.heic','.HEIC'}


@app.route('/api/images')
def api_images():
    """Return list of image files in /images/ directory."""
    images = []
    if os.path.isdir(IMAGES_DIR):
        for f in sorted(os.listdir(IMAGES_DIR)):
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS and os.path.isfile(os.path.join(IMAGES_DIR, f)):
                images.append(f)
    return jsonify(images)


@app.route('/api/images/all')
def api_images_all():
    """Scan ALL images across the CMS — ROAMCMS/images/ + RoamWeb/blog/*/images/.
    Returns list of dicts with metadata plus summary stats."""
    results = []
    scan_dirs = [(IMAGES_DIR, 'images/')]
    # Blog article images
    if os.path.isdir(BLOG_DIR):
        for slug in os.listdir(BLOG_DIR):
            blog_img_dir = os.path.join(BLOG_DIR, slug, 'images')
            if os.path.isdir(blog_img_dir):
                scan_dirs.append((blog_img_dir, f'blog/{slug}/images/'))

    for scan_dir, prefix in scan_dirs:
        if not os.path.isdir(scan_dir):
            continue
        for f in sorted(os.listdir(scan_dir)):
            ext = os.path.splitext(f)[1].lower()
            if ext not in ALL_IMAGE_EXTS:
                continue
            fullpath = os.path.join(scan_dir, f)
            if not os.path.isfile(fullpath):
                continue
            size = os.path.getsize(fullpath)
            info = {
                'filename': f,
                'relpath': prefix + f,
                'fullpath': fullpath,
                'size': size,
                'size_kb': round(size / 1024, 1),
                'width': 0,
                'height': 0,
                'format': ext.lstrip('.'),
                'broken': False,
            }
            try:
                if HAS_PILLOW:
                    with Image.open(fullpath) as img:
                        info['width'], info['height'] = img.size
                        info['format'] = (img.format or ext.lstrip('.')).lower()
            except Exception:
                info['broken'] = True
            results.append(info)

    results.sort(key=lambda x: x['filename'].lower())
    total = len(results)
    total_size = sum(r['size'] for r in results)
    formats = {}
    for r in results:
        fmt = r['format']
        formats[fmt] = formats.get(fmt, 0) + 1
    broken = sum(1 for r in results if r['broken'])

    return jsonify({
        'images': results,
        'stats': {
            'total': total,
            'total_size_kb': round(total_size / 1024, 1),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'formats': formats,
            'broken': broken,
        }
    })


@app.route('/api/images/process', methods=['POST'])
def api_images_process():
    """Process images: resize to ≤500px, convert to .jpg, delete originals.
    Uses Pillow with macOS sips fallback for HEIC/broken files."""
    data = request.get_json() or {}
    filenames = data.get('filenames')  # optional whitelist; None = all

    # Collect all images
    all_resp = api_images_all()
    all_images = all_resp.json['images']
    if filenames:
        all_images = [i for i in all_images if i['filename'] in filenames]

    if not all_images:
        return jsonify({'error': 'No images found'}), 400

    results = []
    for info in all_images:
        fullpath = info['fullpath']
        base = os.path.splitext(fullpath)[0]
        jpg_path = base + '.jpg'
        status = 'skipped'
        note = ''

        # Already a ≤500px .jpg? Skip
        if (info['format'] in ('jpg', 'jpeg') and info['width'] > 0
                and info['width'] <= 500 and info['height'] <= 500
                and fullpath.lower().endswith('.jpg')):
            status = 'already_ok'
            note = 'Already ≤500px .jpg'
        else:
            try:
                img = None
                opened_with = 'Pillow'
                try:
                    if HAS_PILLOW:
                        img = Image.open(fullpath)
                        img.load()
                except Exception:
                    # macOS fallback: sips handles HEIC, malformed headers, etc.
                    opened_with = 'sips'
                    tmp_png = fullpath + '.tmp_convert.png'
                    subprocess.run(
                        ['sips', '-s', 'format', 'png', fullpath, '--out', tmp_png],
                        check=True, capture_output=True, timeout=30)
                    if os.path.exists(tmp_png) and HAS_PILLOW:
                        img = Image.open(tmp_png)
                        img.load()

                if img is None:
                    raise Exception('Could not open image with any method')

                w, h = img.size
                largest = max(w, h)
                if largest > 500 or opened_with == 'sips':
                    ratio = 500 / largest if largest > 500 else 1.0
                    new_size = (int(w * ratio), int(h * ratio))
                    img = img.resize(new_size, Image.LANCZOS)
                    status = 'resized'
                else:
                    status = 'converted'

                # Ensure RGB (handle RGBA, P, LA modes)
                if img.mode in ('RGBA', 'P', 'LA'):
                    rgb = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    rgb.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = rgb
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                img.save(jpg_path, 'JPEG', quality=85, optimize=True)
                note = f'{opened_with}: {w}×{h} → {img.size[0]}×{img.size[1]}'

                # Delete original if extension changed
                if os.path.abspath(fullpath) != os.path.abspath(jpg_path):
                    os.remove(fullpath)

                # Clean up temp files
                for tmp in [fullpath + '.tmp_convert.png']:
                    if os.path.exists(tmp):
                        os.remove(tmp)

            except Exception as exc:
                status = 'failed'
                note = str(exc)[:120]

        results.append({
            'filename': info['filename'],
            'relpath': info['relpath'],
            'status': status,
            'note': note,
        })

    ok = sum(1 for r in results if r['status'] in ('resized', 'converted', 'already_ok'))
    failed = sum(1 for r in results if r['status'] == 'failed')
    skipped = sum(1 for r in results if r['status'] == 'skipped')

    return jsonify({
        'results': results,
        'summary': {'ok': ok, 'failed': failed, 'skipped': skipped, 'total': len(results)}
    })


# ── Image auto-match persistence ──────────────────────────────────
MATCHES_FILE = os.path.join(DATA_DIR, 'image-matches.json')


def load_matches():
    """Load confirmed image matches from disk."""
    if os.path.exists(MATCHES_FILE):
        try:
            with open(MATCHES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_matches(matches):
    """Persist confirmed image matches to disk."""
    try:
        with open(MATCHES_FILE, 'w', encoding='utf-8') as f:
            json.dump(matches, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


@app.route('/api/image-matches', methods=['GET'])
def api_get_matches():
    """Get all confirmed image matches."""
    return jsonify(load_matches())


@app.route('/api/image-matches', methods=['POST'])
def api_save_matches():
    """Save confirmed image matches (merge with existing)."""
    new_matches = request.get_json()
    if not isinstance(new_matches, dict):
        return jsonify({'error': 'Expected a dict of title→filename'}), 400
    existing = load_matches()
    existing.update(new_matches)
    if save_matches(existing):
        return jsonify({'status': 'ok', 'count': len(existing)})
    return jsonify({'error': 'Failed to save matches'}), 500


@app.route('/api/auto-match-images', methods=['POST'])
def api_auto_match():
    """Given a list of place titles, return suggested image matches.

    Matching rules (in priority order):
    1. Existing confirmed match (from image-matches.json)
    2. First ~7 alphanumeric chars of title match first ~7 of filename
    """
    body = request.get_json()
    titles = body.get('titles', []) if body else []
    if not isinstance(titles, list):
        return jsonify({'error': 'Expected {"titles": [...]}'}), 400

    # Get all image files
    images = []
    if os.path.isdir(IMAGES_DIR):
        for f in sorted(os.listdir(IMAGES_DIR)):
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                images.append(f)

    confirmed = load_matches()
    matches = {}

    for title in titles:
        if not title or not isinstance(title, str):
            continue

        # Rule 1: confirmed match
        if title in confirmed:
            matches[title] = confirmed[title]
            continue

        # Rule 2: first ~7 alphanumeric chars
        prefix = ''.join(c.lower() for c in title if c.isalnum())[:7]
        if len(prefix) < 3:
            continue

        for img in images:
            img_prefix = ''.join(c.lower() for c in os.path.splitext(img)[0] if c.isalnum())[:7]
            if len(img_prefix) >= 3 and prefix == img_prefix:
                matches[title] = img
                break

    return jsonify({'matches': matches, 'total_titles': len(titles), 'total_matches': len(matches)})


@app.route('/images/<path:filename>')
def serve_image(filename):
    """Serve image files from the /images/ directory."""
    return send_from_directory(IMAGES_DIR, filename)


# ═══════════════════════════════════════════════════════════════════
#  BLOG CONTENT WRITER — article editor & publisher
# ═══════════════════════════════════════════════════════════════════

BLOG_DIR = os.path.join(os.path.dirname(DATA_DIR), 'RoamWeb', 'blog')
SITEMAP_PATH = os.path.join(os.path.dirname(DATA_DIR), 'RoamWeb', 'sitemap.xml')
ROAMWEB_DIR = os.path.join(os.path.dirname(DATA_DIR), 'RoamWeb')

# Serve blog images for the editor preview
@app.route('/blog-images/<path:filepath>')
def serve_blog_image(filepath):
    """Serve image files from the RoamWeb/blog/ directory for preview."""
    return send_from_directory(BLOG_DIR, filepath)

from datetime import datetime
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def resize_image(filepath, max_dim=500):
    """Resize an image so its largest dimension ≤ max_dim. Overwrites original."""
    if not HAS_PILLOW:
        return False
    try:
        img = Image.open(filepath)
        w, h = img.size
        largest = max(w, h)
        if largest <= max_dim:
            return False  # no resize needed
        ratio = max_dim / largest
        new_size = (int(w * ratio), int(h * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        img.save(filepath, quality=85, optimize=True)
        return True
    except Exception:
        return False


def resize_blog_images(slug):
    """Resize all images in a blog article folder to ≤500px."""
    blog_path = os.path.join(BLOG_DIR, slug)
    resized = 0
    for root, dirs, files in os.walk(blog_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.webp'):
                if resize_image(os.path.join(root, f)):
                    resized += 1
    return resized


def slugify(text):
    """Create a URL-safe slug from text."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug or 'untitled'


def find_hero_image(slug):
    """Find the hero image for a blog article. Checks hero.jpg, hero.jpeg, hero.webp, hero.png."""
    blog_path = os.path.join(BLOG_DIR, slug)
    for ext in ('.jpg', '.jpeg', '.webp', '.png'):
        hero_path = os.path.join(blog_path, f'hero{ext}')
        if os.path.exists(hero_path):
            return f'hero{ext}'
        # Also check images/ subfolder
        hero_path2 = os.path.join(blog_path, 'images', f'hero{ext}')
        if os.path.exists(hero_path2):
            return f'images/hero{ext}'
    return 'images/hero.jpg'  # default


def has_hero_image(slug):
    """Check if a blog article has a hero image."""
    blog_path = os.path.join(BLOG_DIR, slug)
    for ext in ('.jpg', '.jpeg', '.webp', '.png'):
        if os.path.exists(os.path.join(blog_path, f'hero{ext}')):
            return True
        if os.path.exists(os.path.join(blog_path, 'images', f'hero{ext}')):
            return True
    return False


def generate_blog_html(slug, headline, subheadline, tag, body_html, date_str):
    """Generate the full blog article HTML page."""
    escaped_headline = headline.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    escaped_sub = (subheadline or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    hero_img = find_hero_image(slug)
    hero_filename = hero_img  # keep images/ prefix — hero lives in images/ folder
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_headline} — Roam Anguilla</title>
  <meta name="description" content="{escaped_sub}">
  <meta property="og:title" content="{escaped_headline}">
  <meta property="og:description" content="{escaped_sub}">
  <meta property="og:image" content="https://roamaxa.app/blog/{slug}/{hero_img}">
  <meta property="og:url" content="https://roamaxa.app/blog/{slug}/">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="https://roamaxa.app/blog/{slug}/">
  <link rel="icon" type="image/webp" href="/titlelogo.webp" sizes="25x25">
  <link rel="stylesheet" href="/style.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3098807263908139" crossorigin="anonymous"></script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": "{escaped_headline}",
    "description": "{escaped_sub}",
    "image": "https://roamaxa.app/blog/{slug}/{hero_img}",
    "datePublished": "{date_str}",
    "author": {{ "@type": "Organization", "name": "Roam Anguilla" }}
  }}
  </script>
</head>
<body>
  <header class="blog-header">
    <div class="blog-header-inner">
      <div class="logo">
        <a href="/" style="text-decoration:none;display:flex;align-items:center;gap:0.6rem;">
          <img src="/assets/titlelogo.webp" alt="" style="height:38px;width:auto;" />
          <h1>Roam <span>Anguilla</span></h1>
        </a>
      </div>
      <nav class="header-nav" aria-label="Main navigation">
        <a href="/blog" class="nav-link active">Blog</a>
        <a href="/events.html" class="nav-link">Events</a>
        <a href="/places.html" class="nav-link">Places</a>
        <a href="/about.html" class="nav-link">About</a>
      </nav>
      <a href="/download.html" class="get-app-link">
        <i class="fas fa-mobile-alt"></i> Get the App
      </a>
    </div>
  </header>
  <article>
    <header class="article-header">
      <h1 class="article-title">{escaped_headline}</h1>
      <div class="article-meta">Published on {date_str} by Roam Anguilla Team | <span class="tag">{tag}</span></div>
    </header>
    <img src="{hero_filename}" alt="{escaped_headline}" class="hero-image" loading="lazy">
    <div class="article-content">
{body_html}
    </div>
  </article>
  <div class="comments-section">
    <h3>Join the Conversation</h3>
    <div id="disqus_thread"></div>
    <script>
      var disqus_config = function () {{
        this.page.url = 'https://roamaxa.app/blog/{slug}/';
        this.page.identifier = 'roam-anguilla-{slug}';
        this.page.title = '{escaped_headline}';
      }};
      (function() {{
        var d = document, s = d.createElement('script');
        s.src = 'https://roamanguilla.disqus.com/embed.js';
        s.setAttribute('data-timestamp', +new Date());
        (d.head || d.body).appendChild(s);
      }})();
    </script>
    <noscript>Please enable JavaScript to view the <a href="https://disqus.com/?ref_noscript">comments powered by Disqus.</a></noscript>
  </div>
  <script id="dsq-count-scr" src="//roamanguilla.disqus.com/count.js" async></script>
</body>
</html>'''


def update_content_json(slug, headline, subheadline, description, date_str, tag, image_path):
    """Add/update an article entry in ROAMCMS content.json (relative paths)."""
    content_path = os.path.join(DATA_DIR, 'content.json')
    entry = {
        'title': headline,
        'subheadline': subheadline or '',
        'description': description or '',
        'date': date_str,
        'tag': tag,
        'url': f'/blog/{slug}/',
        'image': image_path or f'/blog/{slug}/hero.png'
    }
    data, _ = load_json('content.json')
    if not isinstance(data, list):
        data = []
    # Remove empty subheadline/description for cleaner JSON
    if not entry['subheadline']:
        del entry['subheadline']
    if not entry['description']:
        del entry['description']
    # Update existing or append
    found = False
    for i, row in enumerate(data):
        if row.get('url') == entry['url']:
            data[i] = entry
            found = True
            break
    if not found:
        data.insert(0, entry)  # newest first
    save_json('content.json', data)
    # Also update RoamWeb's local copy if it exists
    roamweb_content = os.path.join(ROAMWEB_DIR, 'jsonassets', 'content.json')
    if os.path.exists(os.path.dirname(roamweb_content)):
        try:
            with open(roamweb_content, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass


def update_webcontent_json(slug, headline, subheadline, description, date_str, tag, image_path):
    """Add/update an article entry in ROAMCMS webcontent.json (absolute URLs for iOS)."""
    entry = {
        'title': headline,
        'subheadline': subheadline or '',
        'description': description or '',
        'date': date_str,
        'tag': tag,
        'url': f'https://roamaxa.app/blog/{slug}/',
        'image': image_path or f'https://roamaxa.app/blog/{slug}/hero.png'
    }
    if not entry['subheadline']:
        del entry['subheadline']
    if not entry['description']:
        del entry['description']
    data, _ = load_json('webcontent.json')
    if not isinstance(data, list):
        data = []
    found = False
    for i, row in enumerate(data):
        if row.get('url') == entry['url']:
            data[i] = entry
            found = True
            break
    if not found:
        data.insert(0, entry)
    save_json('webcontent.json', data)


def regenerate_sitemap():
    """Regenerate sitemap.xml with all blog articles + static pages."""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    urlset = ET.Element('urlset', xmlns=NS)

    # Static pages
    static_pages = [
        ('https://roamaxa.app/', 'weekly', '0.8'),
        ('https://roamaxa.app/blog/', 'weekly', '0.8'),
    ]
    today = datetime.now().strftime('%Y-%m-%d')
    for loc, freq, pri in static_pages:
        url = ET.SubElement(urlset, 'url')
        ET.SubElement(url, 'loc').text = loc
        ET.SubElement(url, 'changefreq').text = freq
        ET.SubElement(url, 'priority').text = pri

    # Blog articles — use file modification time for <lastmod>
    if os.path.isdir(BLOG_DIR):
        for folder in sorted(os.listdir(BLOG_DIR)):
            blog_path = os.path.join(BLOG_DIR, folder)
            index_path = os.path.join(blog_path, 'index.html')
            if os.path.isdir(blog_path) and os.path.exists(index_path):
                url = ET.SubElement(urlset, 'url')
                ET.SubElement(url, 'loc').text = f'https://roamaxa.app/blog/{folder}/'
                # Use file modification time for lastmod
                mtime = os.path.getmtime(index_path)
                lastmod_date = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
                ET.SubElement(url, 'lastmod').text = lastmod_date
                ET.SubElement(url, 'changefreq').text = 'monthly'
                ET.SubElement(url, 'priority').text = '0.7'

    # Pretty-print
    xml_str = ET.tostring(urlset, encoding='unicode')
    xml_str = minidom.parseString(xml_str).toprettyxml(indent='  ', encoding='UTF-8').decode('utf-8')
    # Remove the XML declaration double-encoding
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str.split('?>', 1)[-1].strip() + '\n'

    with open(SITEMAP_PATH, 'w', encoding='utf-8') as f:
        f.write(xml_str)


def _place_card_html(place_name):
    """Generate HTML for a <place> tag reference. Looks up places.json for Google Maps link."""
    places_data, _ = load_json('places.json')
    place_info = None
    if isinstance(places_data, list):
        for p in places_data:
            if p.get('title', '').lower() == place_name.lower():
                place_info = p
                break
    if place_info and place_info.get('googleurl'):
        gurl = place_info['googleurl']
        loc = place_info.get('location', '')
        return (
            f'<div class="place-card" style="background:#f0f7ff;border:1px solid #1E6F9F;border-radius:10px;padding:14px 18px;margin:1.2em 0;display:flex;align-items:center;gap:12px">'
            f'<span style="font-size:1.5rem">📍</span>'
            f'<div style="flex:1"><strong style="color:#1a2c3e">{place_name}</strong>'
            f'<br><span style="font-size:0.85rem;color:#666">{loc}</span></div>'
            f'<a href="{gurl}" target="_blank" rel="noopener" '
            f'style="background:#1E6F9F;color:white;padding:8px 16px;border-radius:8px;text-decoration:none;font-size:0.85rem;font-weight:600;white-space:nowrap">🗺 View on Map</a>'
            f'</div>'
        )
    else:
        return (
            f'<div class="place-card" style="background:#fff8f0;border:1px dashed #ccc;border-radius:10px;padding:14px 18px;margin:1.2em 0">'
            f'<em style="color:#999">📍 {place_name}</em>'
            f'</div>'
        )


def parse_body_to_html(body_text):
    """Convert editor body text to HTML.
    
    Syntax:
      # Heading         → <h1>Heading</h1>
      ## Heading        → <h2>Heading</h2>
      <box>content</box> → <div class="cta-box">content</div>
      <place>Name</place> → styled place card with Google Maps link
      [img:file.jpg]    → marks next line as caption, creates image block
      blank line        → <br> separator between paragraphs
      regular text      → wrapped in <p> tags
      raw HTML          → passed through as-is
    """
    lines = body_text.split('\n')
    html_parts = []
    para_lines = []
    pending_image = None
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # CTA Box: <box> ... </box> (multi-line block)
        if stripped.startswith('<box>'):
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            box_lines = []
            rest = stripped[5:].strip()  # content after <box> on opening line
            if rest:
                box_lines.append(rest)
            i += 1
            while i < len(lines):
                line = lines[i]
                s = line.strip()
                if s == '</box>':
                    break
                if '</box>' in s:
                    before = line[:line.find('</box>')].strip()
                    if before:
                        box_lines.append(before)
                    break
                box_lines.append(line)
                i += 1
            box_content = '\n'.join(box_lines)
            # Convert <place> tags within box content
            box_content = re.sub(
                r'<place>(.+?)</place>',
                lambda m: _place_card_html(m.group(1).strip()),
                box_content
            )
            html_parts.append(f'<div class="cta-box">{box_content}</div>')
            i += 1
            continue
        
        # Place tag: <place>Name</place> — styled place card with Google Maps link
        place_match = re.match(r'^<place>(.+?)</place>$', stripped)
        if place_match:
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            html_parts.append(_place_card_html(place_match.group(1).strip()))
            i += 1
            continue
        
        # Image marker: [img:filename.jpg]
        img_match = re.match(r'^\[img:(.+?)\]$', stripped)
        if img_match:
            # Flush pending paragraph
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            
            filename = img_match.group(1).strip()
            # Next line is caption (if it exists and isn't empty/syntax)
            caption = ''
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and not next_line.startswith('##') and not next_line.startswith('#') and not next_line.startswith('[img:') and not next_line.startswith('<box>') and not next_line.startswith('<place>'):
                    caption = next_line
                    i += 1  # consume caption line
            
            caption_attr = caption.replace('"', '&quot;')
            img_html = f'<div class="article-image"><img src="images/{filename}" alt="{caption_attr}" loading="lazy">'
            if caption:
                img_html += f'<span class="image-caption">{caption}</span>'
            img_html += '</div>'
            html_parts.append(img_html)
            i += 1
            continue
        
        # H1 heading — entire rest of line after # becomes the heading
        if stripped.startswith('#') and not stripped.startswith('##'):
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            html_parts.append(f'<h1>{stripped[1:]}</h1>')
            i += 1
            continue
        
        # H2 heading — entire rest of line after ## becomes the heading
        if stripped.startswith('##'):
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            html_parts.append(f'<h2>{stripped[2:]}</h2>')
            i += 1
            continue
        
        # Raw HTML (pass through if it looks like HTML)
        if re.match(r'^\s*<(\w+)[^>]*>', stripped):
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            html_parts.append(line)
            i += 1
            continue
        
        # Blank line → flush paragraph as <br> separator
        if not stripped:
            if para_lines:
                html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
                para_lines = []
            i += 1
            continue
        
        # Regular text
        para_lines.append(line)
        i += 1
    
    # Flush remaining paragraph
    if para_lines:
        html_parts.append('<p>' + ' '.join(para_lines) + '</p>')
    
    return '\n'.join(html_parts)


# ── Blog API Endpoints ─────────────────────────────────────────────

@app.route('/api/blog/articles')
def api_blog_list():
    """List existing blog articles with metadata."""
    articles = []
    if os.path.isdir(BLOG_DIR):
        for folder in sorted(os.listdir(BLOG_DIR)):
            blog_path = os.path.join(BLOG_DIR, folder)
            index_path = os.path.join(blog_path, 'index.html')
            if os.path.isdir(blog_path) and os.path.exists(index_path):
                # Get metadata from content.json
                data, _ = load_json('content.json')
                meta = {}
                if isinstance(data, list):
                    for row in data:
                        if row.get('url', '').endswith(f'/{folder}/'):
                            meta = row
                            break
                articles.append({
                    'slug': folder,
                    'title': meta.get('title', folder),
                    'date': meta.get('date', ''),
                    'tag': meta.get('tag', ''),
                    'has_hero': has_hero_image(folder),
                    'hero': find_hero_image(folder),
                })
    return jsonify(articles)


@app.route('/api/blog/article/<slug>')
def api_blog_get(slug):
    """Get an article's body and metadata for editing."""
    index_path = os.path.join(BLOG_DIR, slug, 'index.html')
    if not os.path.exists(index_path):
        return jsonify({'error': 'Article not found'}), 404
    
    # Read the HTML and extract body content
    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # Extract body from article content div (handles both .article-content and .article-body)
    body_match = re.search(r'<div class="article-(?:content|body)">\s*(.*?)\s*</div>\s*(?:</article>|</div>)', html, re.DOTALL)
    if not body_match:
        # Fallback: extract everything inside <article> tags
        body_match = re.search(r'<article>\s*(.*?)\s*</article>', html, re.DOTALL)
    body_html = body_match.group(1).strip() if body_match else ''
    
    # Get metadata from content.json
    data, _ = load_json('content.json')
    meta = {}
    if isinstance(data, list):
        for row in data:
            if row.get('url', '').endswith(f'/{slug}/'):
                meta = row
                break
    
    return jsonify({
        'slug': slug,
        'title': meta.get('title', ''),
        'subheadline': meta.get('subheadline', ''),
        'tag': meta.get('tag', ''),
        'date': meta.get('date', ''),
        'body_html': body_html,
    })


@app.route('/api/blog/create', methods=['POST'])
def api_blog_create():
    """Create a new blog article — generates HTML page, updates metadata, sitemap."""
    body = request.get_json()
    if not body:
        return jsonify({'error': 'No data provided'}), 400
    
    headline = (body.get('headline') or body.get('title') or '').strip()
    subheadline = (body.get('subheadline') or '').strip()
    tag = (body.get('tag') or 'Travel Tips').strip()
    slug = (body.get('slug') or slugify(headline)).strip()
    body_text = (body.get('body') or '').strip()
    hero_image = body.get('hero_image', 'hero.png')
    
    if not headline:
        return jsonify({'error': 'Headline is required'}), 400
    if not slug:
        return jsonify({'error': 'Slug is required'}), 400
    
    date_str = datetime.now().strftime('%B %d, %Y')
    description = subheadline or ' '.join(body_text.split()[:30]) if body_text else ''
    
    # Convert body text to HTML
    body_html = parse_body_to_html(body_text) if body_text else ''
    
    # Create blog directory
    blog_path = os.path.join(BLOG_DIR, slug)
    images_path = os.path.join(blog_path, 'images')
    os.makedirs(images_path, exist_ok=True)
    
    # Generate the HTML page
    full_html = generate_blog_html(slug, headline, subheadline, tag, body_html, date_str)
    index_path = os.path.join(blog_path, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    # Batch resize all images in the article folder to ≤500px
    resized_count = resize_blog_images(slug)
    
    # Update metadata files
    image_rel = f'/blog/{slug}/{hero_image}' if hero_image else f'/blog/{slug}/hero.png'
    update_content_json(slug, headline, subheadline, description, date_str, tag, image_rel)
    update_webcontent_json(slug, headline, subheadline, description, date_str, tag, image_rel)
    
    # Regenerate sitemap
    try:
        regenerate_sitemap()
    except Exception:
        pass
    
    return jsonify({
        'status': 'ok',
        'slug': slug,
        'url': f'/blog/{slug}/',
        'full_url': f'https://roamaxa.app/blog/{slug}/',
        'images_resized': resized_count,
    })


@app.route('/api/blog/update/<slug>', methods=['POST'])
def api_blog_update(slug):
    """Update an existing blog article."""
    blog_path = os.path.join(BLOG_DIR, slug)
    index_path = os.path.join(blog_path, 'index.html')
    if not os.path.exists(index_path):
        return jsonify({'error': 'Article not found'}), 404
    
    body = request.get_json()
    if not body:
        return jsonify({'error': 'No data provided'}), 400
    
    headline = (body.get('headline') or body.get('title') or '').strip()
    subheadline = (body.get('subheadline') or '').strip()
    tag = (body.get('tag') or 'Travel Tips').strip()
    body_text = (body.get('body') or '').strip()
    hero_image = body.get('hero_image', 'hero.png')
    date_str = body.get('date') or datetime.now().strftime('%B %d, %Y')
    
    if not headline:
        return jsonify({'error': 'Headline is required'}), 400
    
    description = subheadline or ' '.join(body_text.split()[:30]) if body_text else ''
    
    # Convert body text to HTML
    body_html = parse_body_to_html(body_text) if body_text else ''
    
    # Regenerate the HTML page
    full_html = generate_blog_html(slug, headline, subheadline, tag, body_html, date_str)
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(full_html)
    
    # Batch resize all images in the article folder to ≤500px
    resized_count = resize_blog_images(slug)
    
    # Update metadata files
    image_rel = f'/blog/{slug}/{hero_image}' if hero_image else f'/blog/{slug}/hero.jpg'
    update_content_json(slug, headline, subheadline, description, date_str, tag, image_rel)
    update_webcontent_json(slug, headline, subheadline, description, date_str, tag, image_rel)
    
    # Regenerate sitemap
    try:
        regenerate_sitemap()
    except Exception:
        pass
    
    return jsonify({
        'status': 'ok',
        'slug': slug,
        'url': f'/blog/{slug}/',
        'full_url': f'https://roamaxa.app/blog/{slug}/',
        'images_resized': resized_count,
    })


@app.route('/api/blog/images/<slug>')
def api_blog_images_list(slug):
    """List all images in a blog article's folder."""
    blog_path = os.path.join(BLOG_DIR, slug)
    images = []
    if os.path.isdir(blog_path):
        for root, dirs, files in os.walk(blog_path):
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
                    rel = os.path.relpath(os.path.join(root, f), blog_path)
                    images.append(rel)
    return jsonify(images)


@app.route('/api/blog/upload-image/<slug>', methods=['POST'])
def api_blog_upload_image(slug):
    """Upload an image to a blog article. Auto-resizes to 500px max dimension."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400
    
    # Validate extension
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        return jsonify({'error': 'Invalid file type. Use jpg, png, webp, or gif.'}), 400
    
    # Ensure blog directory exists
    blog_path = os.path.join(BLOG_DIR, slug)
    images_path = os.path.join(blog_path, 'images')
    os.makedirs(images_path, exist_ok=True)
    
    # Sanitize filename
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', file.filename)
    save_path = os.path.join(images_path, safe_name)
    file.save(save_path)
    
    # Auto-resize
    resized = resize_image(save_path)
    
    return jsonify({
        'status': 'ok',
        'filename': safe_name,
        'path': f'images/{safe_name}',
        'resized': resized,
    })


if __name__ == '__main__':
    print("\n📊 JSON Table Editor")
    print("=" * 40)
    print(f"Data directory: {DATA_DIR}")
    print(f"JSON files found: {', '.join(get_json_files())}")
    print("\nOpen http://localhost:5050 in your browser\n")
    app.run(host='127.0.0.1', port=5050, debug=False)
