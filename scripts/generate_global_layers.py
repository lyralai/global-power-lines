#!/usr/bin/env python3
"""
Generate global Backbone (≥380 kV) and Transmission (≥220 kV) GeoJSON layers
from per-country power line files.

- Parses compound voltage values (e.g. "380000;220000") → takes max
- Includes features with missing/empty voltage in backbone (likely transmission)
- Simplifies geometries by rounding coords to 4 decimal places (~11m)
- Strips properties to essentials (voltage, name, operator, country)
"""

import json
import os
import sys
import time

GEOJSON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'geojson')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'docs', 'data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

BACKBONE_THRESHOLD = 380000   # 380 kV
TRANSMISSION_THRESHOLD = 220000  # 220 kV

def parse_max_voltage(v):
    """Parse voltage string, return max value in volts."""
    if not v or str(v).strip() == '':
        return None
    parts = str(v).split(';')
    vals = []
    for p in parts:
        p = p.strip()
        try:
            val = int(float(p))
            if val > 0:
                vals.append(val)
        except (ValueError, TypeError):
            pass
    return max(vals) if vals else None

def simplify_coords(coords, precision=3):
    """Round coordinate precision to reduce file size.
    3 decimal places ≈ ~111m at equator — plenty for world-zoom view."""
    if isinstance(coords[0], (int, float)):
        # Single coordinate pair [lng, lat]
        return [round(c, precision) for c in coords]
    elif isinstance(coords[0], list):
        # Nested array (LineString, MultiLineString, etc.)
        return [simplify_coords(c, precision) for c in coords]
    return coords

def process_country(cc, country_dir):
    """Process a country's power_lines file, yield (feature, max_voltage) tuples."""
    filepath = os.path.join(country_dir, f'power_lines_{cc.lower()}.geojson')
    if not os.path.exists(filepath):
        # Try uppercase
        filepath = os.path.join(country_dir, f'power_lines_{cc}.geojson')
    if not os.path.exists(filepath):
        return
    
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠ {cc}: failed to read: {e}", file=sys.stderr)
        return
    
    for feat in data.get('features', []):
        props = feat.get('properties', {})
        v_raw = props.get('voltage', '')
        v_max = parse_max_voltage(v_raw)
        yield feat, v_max, props

def build_layer(threshold_volt, include_missing, countries):
    """Build a global GeoJSON layer with features above threshold."""
    features = []
    stats = {'total': 0, 'included': 0, 'by_country': {}}
    
    for cc in countries:
        country_dir = os.path.join(GEOJSON_DIR, cc)
        if not os.path.isdir(country_dir):
            continue
        
        count = 0
        for feat, v_max, props in process_country(cc, country_dir):
            stats['total'] += 1
            
            include = False
            if v_max is None and include_missing:
                include = True
            elif v_max is not None and v_max >= threshold_volt:
                include = True
            
            if not include:
                continue
            
            # Simplify geometry
            geom = feat.get('geometry', {})
            if 'coordinates' in geom:
                geom = dict(geom)
                geom['coordinates'] = simplify_coords(geom['coordinates'])
            
            # Minimal properties
            new_props = {
                'voltage': props.get('voltage', ''),
                'v_max': v_max if v_max else 0,
                'name': props.get('name', ''),
                'country': cc,
            }
            # Keep operator if present and short
            op = props.get('operator', '')
            if op and len(str(op)) < 50:
                new_props['operator'] = str(op)
            
            new_feat = {
                'type': 'Feature',
                'geometry': geom,
                'properties': new_props,
            }
            features.append(new_feat)
            count += 1
            stats['included'] += 1
        
        stats['by_country'][cc] = count
        if count > 0:
            print(f"  {cc}: {count} features")
    
    geojson = {
        'type': 'FeatureCollection',
        'features': features,
        'metadata': {
            'threshold_volt': threshold_volt,
            'include_missing_voltage': include_missing,
            'feature_count': len(features),
        }
    }
    return geojson, stats

def main():
    start = time.time()
    
    # Get all country codes
    countries = sorted([
        d for d in os.listdir(GEOJSON_DIR)
        if os.path.isdir(os.path.join(GEOJSON_DIR, d)) and len(d) == 2
    ])
    print(f"Found {len(countries)} countries: {', '.join(countries)}")
    
    # === BACKBONE: ≥380 kV only (strict, no missing voltage) ===
    print(f"\n=== Building Backbone layer (≥380 kV, strict) ===")
    backbone, bstats = build_layer(BACKBONE_THRESHOLD, include_missing=False, countries=countries)
    backbone_path = os.path.join(OUTPUT_DIR, 'global_backbone.geojson')
    print(f"\nWriting backbone: {len(backbone['features'])} features → {backbone_path}")
    with open(backbone_path, 'w') as f:
        json.dump(backbone, f, separators=(',', ':'))
    backbone_size = os.path.getsize(backbone_path) / (1024*1024)
    print(f"  Size: {backbone_size:.1f} MB")
    
    # === TRANSMISSION: ≥220 kV (no missing, strict) ===
    print(f"\n=== Building Transmission layer (≥220 kV, strict) ===")
    transmission, tstats = build_layer(TRANSMISSION_THRESHOLD, include_missing=False, countries=countries)
    transmission_path = os.path.join(OUTPUT_DIR, 'global_transmission.geojson')
    print(f"\nWriting transmission: {len(transmission['features'])} features → {transmission_path}")
    with open(transmission_path, 'w') as f:
        json.dump(transmission, f, separators=(',', ':'))
    trans_size = os.path.getsize(transmission_path) / (1024*1024)
    print(f"  Size: {trans_size:.1f} MB")
    
    elapsed = time.time() - start
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   Backbone: {len(backbone['features']):,} features, {backbone_size:.1f} MB")
    print(f"   Transmission: {len(transmission['features']):,} features, {trans_size:.1f} MB")
    print(f"\n   Backbone by country:")
    for cc, c in sorted(bstats['by_country'].items(), key=lambda x: -x[1]):
        if c > 0:
            print(f"     {cc}: {c:,}")

if __name__ == '__main__':
    main()
