#!/usr/bin/env python3
"""
Fetch power infrastructure data from OpenStreetMap via Overpass API.

Supports: power lines, minor lines, cables, substations, plants, generators.

Usage:
    python fetch_overpass.py --country US
    python fetch_overpass.py --country GB --layers line,substation,plant
    python fetch_overpass.py --bbox "-125,24,-66,49" --layers all
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

COUNTRY_BBOXES = {
    "US": (-125.0, 24.0, -66.0, 49.0),
    "GB": (-8.0, 49.5, 2.0, 61.0),
    "DE": (5.8, 47.2, 15.0, 55.1),
    "FR": (-5.5, 41.0, 10.0, 51.5),
    "ES": (-9.5, 36.0, 3.5, 43.8),
    "IT": (6.6, 35.5, 18.8, 47.1),
    "PL": (14.1, 49.0, 24.2, 54.8),
    "NL": (3.3, 50.7, 7.2, 53.6),
    "SE": (11.0, 55.3, 24.2, 69.1),
    "NO": (4.5, 57.9, 31.3, 71.3),
    "FI": (20.6, 59.8, 31.6, 70.1),
    "BR": (-74.0, -33.8, -34.8, 5.4),
    "CN": (73.5, 18.0, 135.1, 53.6),
    "IN": (68.1, 6.5, 97.4, 35.7),
    "AU": (113.3, -43.6, 153.6, -10.7),
    "JP": (129.4, 31.0, 145.8, 45.6),
    "KR": (124.6, 33.2, 131.9, 38.6),
    "RU": (19.6, 41.1, 180.0, 77.7),
    "CA": (-141.0, 41.7, -52.6, 73.0),
    "MX": (-117.1, 14.5, -86.7, 32.7),
    "AR": (-73.5, -55.1, -53.6, -21.8),
    "ZA": (16.5, -34.8, 32.9, -22.1),
    "EG": (24.7, 22.0, 36.9, 31.7),
    "TR": (25.6, 35.8, 45.0, 42.1),
    "ID": (95.0, -11.0, 141.0, 6.1),
    "TH": (97.3, 5.6, 105.6, 20.5),
    "VN": (102.1, 8.2, 109.5, 23.4),
    "PT": (-9.6, 36.9, -6.1, 42.2),
    "GR": (20.0, 34.8, 27.0, 41.8),
    "AT": (9.5, 46.4, 17.2, 49.1),
    "CH": (5.9, 45.8, 10.5, 47.8),
    "BE": (2.5, 49.5, 6.5, 51.5),
    "DK": (8.0, 54.5, 13.0, 57.8),
    "IE": (-10.7, 51.4, -5.3, 55.4),
    "CZ": (12.1, 48.5, 18.9, 51.1),
    "HU": (16.0, 45.7, 22.9, 48.6),
    "RO": (20.3, 43.6, 29.7, 48.3),
    "BG": (22.3, 41.2, 28.6, 44.2),
    "HR": (13.4, 42.1, 19.5, 46.6),
    "RS": (18.8, 42.2, 23.0, 46.2),
    "UA": (22.1, 44.2, 40.2, 52.4),
    "NZ": (166.4, -47.3, 178.6, -34.3),
    "CL": (-75.7, -56.5, -66.3, -17.5),
    "CO": (-79.0, -4.2, -66.8, 12.6),
    "PE": (-81.3, -18.3, -68.6, 0.1),
    "NG": (2.6, 4.2, 14.7, 13.9),
    "KE": (33.9, -5.0, 41.9, 4.7),
    "MA": (-13.2, 21.3, -1.0, 35.9),
    "PH": (117.0, 5.0, 127.0, 19.0),
    "PK": (60.8, 23.7, 77.8, 37.1),
    "BD": (88.0, 20.5, 92.7, 26.7),
    "MY": (99.6, 0.9, 119.3, 7.4),
    "SG": (103.6, 1.2, 104.0, 1.5),
}

# Layer definitions: (layer_name, tag_key, tag_value, geometry_types)
# geometry_types: 'way' for lines/areas, 'node' for points, 'both' for all
LAYERS = {
    "line": {
        "query": 'way["power"="line"]',
        "geom": "way",
        "filename": "power_lines",
        "desc": "High-voltage transmission lines",
    },
    "minor_line": {
        "query": 'way["power"="minor_line"]',
        "geom": "way",
        "filename": "power_minor_lines",
        "desc": "Distribution lines",
    },
    "cable": {
        "query": 'way["power"="cable"]',
        "geom": "way",
        "filename": "power_cables",
        "desc": "Underground/submarine cables",
    },
    "substation": {
        "query": '(node["power"="substation"]; way["power"="substation"];)',
        "geom": "both",
        "filename": "power_substations",
        "desc": "Substations (points + polygons)",
    },
    "plant": {
        "query": '(node["power"="plant"]; way["power"="plant"]; relation["power"="plant"];)',
        "geom": "both",
        "filename": "power_plants",
        "desc": "Power plants (points + polygons)",
    },
    "generator": {
        "query": '(node["power"="generator"]; way["power"="generator"];)',
        "geom": "both",
        "filename": "power_generators",
        "desc": "Individual generators (solar, wind, etc.)",
    },
    "tower": {
        "query": 'node["power"="tower"]',
        "geom": "node",
        "filename": "power_towers",
        "desc": "Transmission towers/poles",
    },
}


def build_query(bbox, layer_names):
    """Build Overpass QL query for given layers in a bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    query = f"[out:json][timeout:900];\n(\n"
    for name in layer_names:
        layer = LAYERS[name]
        raw = layer["query"]

        # Handle compound queries (parenthesized unions)
        if raw.startswith("("):
            # e.g. (node["power"="substation"]; way["power"="substation"];)
            # Add bbox to each element inside
            inner = raw.strip()[1:-1].strip()  # remove outer parens
            for stmt in inner.split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                # stmt looks like: node["power"="substation"] or way["power"="plant"]
                query += f"  {stmt}({bbox_str});\n"
        else:
            # Simple: way["power"="line"]
            query += f"  {raw}({bbox_str});\n"

    query += ");\nout geom;"
    return query


def fetch_overpass(query):
    """Try multiple Overpass endpoints."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")

    for url in OVERPASS_URLS:
        try:
            print(f"  Trying {url}...", file=sys.stderr)
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "global-power-lines/1.0 (https://github.com/lyralai/global-power-lines)",
                },
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                print(f"  Got {len(result.get('elements', []))} elements", file=sys.stderr)
                return result
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            print(f"  Failed: {e}", file=sys.stderr)
            time.sleep(5)
            continue

    raise RuntimeError("All Overpass endpoints failed")


def overpass_to_geojson(overpass_data):
    """Convert Overpass JSON to GeoJSON FeatureCollection."""
    features = []

    for el in overpass_data.get("elements", []):
        tags = el.get("tags", {})
        el_type = el.get("type")
        geometry = None

        # Node → Point
        if el_type == "node":
            if "lon" in el and "lat" in el:
                geometry = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        # Way → LineString or Polygon
        elif el_type == "way":
            geom_nodes = el.get("geometry", [])
            if len(geom_nodes) < 2:
                continue
            coords = [[n["lon"], n["lat"]] for n in geom_nodes]
            # Check if it's a closed way (polygon)
            if len(coords) >= 4 and coords[0] == coords[-1]:
                geometry = {"type": "Polygon", "coordinates": [coords]}
            else:
                geometry = {"type": "LineString", "coordinates": coords}
        # Relation → try to get members
        elif el_type == "relation":
            members = el.get("members", [])
            line_coords = []
            for m in members:
                if "geometry" in m:
                    line_coords.extend([[n["lon"], n["lat"]] for n in m["geometry"]])
            if len(line_coords) >= 2:
                geometry = {"type": "LineString", "coordinates": line_coords}

        if not geometry:
            continue

        feature = {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "id": el.get("id"),
                "osm_type": el_type,
                "power_type": tags.get("power", ""),
                "voltage": tags.get("voltage", ""),
                "frequency": tags.get("frequency", ""),
                "cables": tags.get("cables", ""),
                "wires": tags.get("wires", ""),
                "operator": tags.get("operator", ""),
                "name": tags.get("name", ""),
                "ref": tags.get("ref", ""),
                "plant_source": tags.get("plant:source", tags.get("generator:source", "")),
                "plant_output": tags.get("plant:output:electricity", ""),
                "substation_type": tags.get("substation", ""),
                "layer": tags.get("layer", ""),
                "source": tags.get("source", "OpenStreetMap"),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def fetch_layer(country, bbox, layer_name, output_dir):
    """Fetch a single layer for a country."""
    layer = LAYERS[layer_name]
    print(f"  Fetching {layer_name} ({layer['desc']})...", file=sys.stderr)

    query = build_query(bbox, [layer_name])
    try:
        overpass_data = fetch_overpass(query)
    except RuntimeError as e:
        print(f"  ✗ {layer_name} failed: {e}", file=sys.stderr)
        return None

    geojson = overpass_to_geojson(overpass_data)
    feature_count = len(geojson["features"])

    if feature_count == 0:
        print(f"  ⚠ {layer_name}: 0 features", file=sys.stderr)
        return None

    out_file = os.path.join(output_dir, f"{layer['filename']}_{country.lower()}.geojson")
    with open(out_file, "w") as f:
        json.dump(geojson, f)

    file_size_mb = os.path.getsize(out_file) / (1024 * 1024)
    print(f"  ✓ {layer_name}: {feature_count} features, {file_size_mb:.1f} MB", file=sys.stderr)

    return {
        "layer": layer_name,
        "feature_count": feature_count,
        "file_size_mb": round(file_size_mb, 1),
        "filename": os.path.basename(out_file),
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch power infrastructure from OSM")
    parser.add_argument("--country", help="Country code (e.g., US, GB, DE)")
    parser.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    parser.add_argument(
        "--layers",
        default="line,minor_line",
        help=f"Comma-separated layers: {','.join(LAYERS.keys())} or 'all'",
    )
    parser.add_argument("--output-dir", default=None)

    args = parser.parse_args()

    if args.country:
        country = args.country.upper()
        if country not in COUNTRY_BBOXES:
            available = ", ".join(sorted(COUNTRY_BBOXES.keys()))
            print(f"Unknown country: {country}. Available: {available}", file=sys.stderr)
            sys.exit(1)
        bbox = COUNTRY_BBOXES[country]
    elif args.bbox:
        parts = [float(x) for x in args.bbox.split(",")]
        if len(parts) != 4:
            print("BBox must be: min_lon,min_lat,max_lon,max_lat", file=sys.stderr)
            sys.exit(1)
        bbox = tuple(parts)
        country = "custom"
    else:
        print("Must specify --country or --bbox", file=sys.stderr)
        sys.exit(1)

    if args.layers == "all":
        layer_names = list(LAYERS.keys())
    else:
        layer_names = [l.strip() for l in args.layers.split(",")]
        for l in layer_names:
            if l not in LAYERS:
                print(f"Unknown layer: {l}. Available: {', '.join(LAYERS.keys())}", file=sys.stderr)
                sys.exit(1)

    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geojson", country
    )
    os.makedirs(output_dir, exist_ok=True)

    print(f"Country: {country}", file=sys.stderr)
    print(f"Layers: {', '.join(layer_names)}", file=sys.stderr)
    print(f"BBox: {bbox}", file=sys.stderr)
    print(file=sys.stderr)

    results = []
    for layer_name in layer_names:
        result = fetch_layer(country, bbox, layer_name, output_dir)
        if result:
            results.append(result)
        time.sleep(3)  # Be nice to Overpass between layers

    # Write summary
    summary = {
        "country": country,
        "bbox": list(bbox),
        "layers": results,
        "total_features": sum(r["feature_count"] for r in results),
        "total_size_mb": round(sum(r["file_size_mb"] for r in results), 1),
        "source": "OpenStreetMap (Overpass API)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    summary_file = os.path.join(output_dir, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Total: {summary['total_features']} features, {summary['total_size_mb']} MB", file=sys.stderr)
    print(f"Summary → {summary_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
