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
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
os.makedirs(OUTPUT_DIR, exist_ok=True)

EHV_THRESHOLD = 345000    # Extra High Voltage — 345 kV+ (covers US 345kV + EU 380kV)
HV_THRESHOLD = 230000     # High Voltage — 230 kV+

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
    
    # === EHV: ≥345 kV (strict, no missing voltage) ===
    print(f"\n=== Building EHV layer (≥345 kV, strict) ===")
    ehv, estats = build_layer(EHV_THRESHOLD, include_missing=False, countries=countries)
    ehv_path = os.path.join(OUTPUT_DIR, 'global_ehv.geojson')
    print(f"\nWriting EHV: {len(ehv['features'])} features → {ehv_path}")
    with open(ehv_path, 'w') as f:
        json.dump(ehv, f, separators=(',', ':'))
    ehv_size = os.path.getsize(ehv_path) / (1024*1024)
    print(f"  Size: {ehv_size:.1f} MB")
    
    # === HV: ≥230 kV (no missing, strict) ===
    print(f"\n=== Building HV layer (≥230 kV, strict) ===")
    hv, hvstats = build_layer(HV_THRESHOLD, include_missing=False, countries=countries)
    hv_path = os.path.join(OUTPUT_DIR, 'global_hv.geojson')
    print(f"\nWriting HV: {len(hv['features'])} features → {hv_path}")
    with open(hv_path, 'w') as f:
        json.dump(hv, f, separators=(',', ':'))
    hv_size = os.path.getsize(hv_path) / (1024*1024)
    print(f"  Size: {hv_size:.1f} MB")
    
    elapsed = time.time() - start
    print(f"\n✅ Done in {elapsed:.1f}s")
    print(f"   EHV: {len(ehv['features']):,} features, {ehv_size:.1f} MB")
    print(f"   HV:  {len(hv['features']):,} features, {hv_size:.1f} MB")
    print(f"\n   EHV by country:")
    for cc, c in sorted(estats['by_country'].items(), key=lambda x: -x[1]):
        if c > 0:
            print(f"     {cc}: {c:,}")

if __name__ == '__main__':
    main()
