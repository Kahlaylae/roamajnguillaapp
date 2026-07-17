#!/usr/bin/env python3
"""
JSON Table Editor - Flask Server
View, edit, add, and delete rows in your JSON files through a web interface.
"""

import json
import os
import re
from flask import Flask, render_template, request, jsonify

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
    return render_template('index.html', files=files)


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

    # Auto-normalize locations when saving places.json
    if filename == 'places.json':
        for row in new_data:
            if isinstance(row, dict) and 'location' in row:
                original = row['location']
                row['location'] = normalize_location(original)

    success, error = save_json(filename, new_data)
    if not success:
        return jsonify({'error': error}), 500
    return jsonify({'status': 'ok', 'count': len(new_data)})


if __name__ == '__main__':
    print("\n📊 JSON Table Editor")
    print("=" * 40)
    print(f"Data directory: {DATA_DIR}")
    print(f"JSON files found: {', '.join(get_json_files())}")
    print("\nOpen http://localhost:5050 in your browser\n")
    app.run(host='127.0.0.1', port=5050, debug=False)
