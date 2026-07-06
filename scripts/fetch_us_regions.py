#!/usr/bin/env python3
"""
Fetch US power infrastructure by region. The US is too large for a single Overpass query,
so we split it into 12 regional bounding boxes, fetch each, then merge.
"""

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

# 12 US regions — each small enough for Overpass to handle
US_REGIONS = {
    "pacific_nw":   (-125.0, 45.0, -116.0, 49.0),    # WA, OR
    "pacific_s":    (-125.0, 32.0, -114.0, 45.0),     # CA, NV
    "mountain_w":   (-114.0, 36.0, -104.0, 49.0),     # ID, MT, WY, UT, CO
    "southwest":    (-114.0, 31.0, -103.0, 37.0),     # AZ, NM
    "plains_n":     (-104.0, 43.0, -94.0, 49.0),      # ND, SD, NE, MN
    "plains_s":     (-104.0, 33.0, -94.0, 40.0),      # KS, OK, TX panhandle
    "texas":        (-106.5, 25.8, -93.5, 36.5),      # TX
    "great_lakes":  (-94.0, 41.0, -80.0, 49.0),       # MN, WI, MI, IL, IN, OH
    "midwest_s":    (-95.0, 35.0, -82.0, 41.0),       # MO, IA, IL, IN, KY
    "northeast":    (-82.0, 40.0, -66.0, 47.5),       # NY, PA, NJ, CT, RI, MA, VT, NH, ME
    "mid_atlantic": (-82.0, 36.0, -75.0, 40.0),       # VA, WV, MD, DE, DC
    "southeast":    (-90.0, 30.0, -75.0, 36.0),       # NC, SC, GA, AL, TN, FL panhandle
    "florida":      (-88.0, 24.5, -80.0, 31.0),       # FL
    "louisiana_ms": (-94.0, 28.0, -88.0, 33.0),       # LA, MS
    "arkansas":     (-94.5, 33.0, -89.5, 37.0),       # AR
    "alaska":       (-170.0, 54.0, -130.0, 71.5),     # AK
    "hawaii":       (-160.5, 18.5, -154.5, 22.5),     # HI
}

LAYERS = {
    "line": ('way', 'power', 'line'),
    "minor_line": ('way', 'power', 'minor_line'),
    "substation": ('both', 'power', 'substation'),
    "plant": ('both', 'power', 'plant'),
}


def build_query(bbox, layer_name):
    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    _, key, val = LAYERS[layer_name]

    if layer_name in ("substation", "plant"):
        return f"""[out:json][timeout:600];
(
  node["{key}"="{val}"]({bbox_str});
  way["{key}"="{val}"]({bbox_str});
);
out geom;"""
    else:
        return f"""[out:json][timeout:600];
(
  way["{key}"="{val}"]({bbox_str});
);
out geom;"""


def fetch_overpass(query):
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    for url in OVERPASS_URLS:
        try:
            print(f"    {url.split('//')[1].split('/')[0]}...", file=sys.stderr)
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "global-power-lines/1.0",
            })
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"    failed: {e}", file=sys.stderr)
            time.sleep(5)
    return None


def to_geojson(overpass_data):
    features = []
    for el in overpass_data.get("elements", []):
        tags = el.get("tags", {})
        geom = None
        t = el.get("type")

        if t == "node" and "lon" in el:
            geom = {"type": "Point", "coordinates": [el["lon"], el["lat"]]}
        elif t == "way":
            nodes = el.get("geometry", [])
            if len(nodes) < 2:
                continue
            coords = [[n["lon"], n["lat"]] for n in nodes]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                geom = {"type": "Polygon", "coordinates": [coords]}
            else:
                geom = {"type": "LineString", "coordinates": coords}

        if not geom:
            continue

        features.append({
            "type": "Feature",
            "geometry": geom,
            "properties": {
                "id": el.get("id"),
                "power_type": tags.get("power", ""),
                "voltage": tags.get("voltage", ""),
                "operator": tags.get("operator", ""),
                "name": tags.get("name", ""),
                "cables": tags.get("cables", ""),
                "plant_source": tags.get("plant:source", tags.get("generator:source", "")),
                "substation_type": tags.get("substation", ""),
                "source": "OpenStreetMap",
            },
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--layers", default="line,minor_line,substation,plant")
    parser.add_argument("--regions", default=None, help="Comma-separated region names (default: all)")
    parser.add_argument("--merge-only", action="store_true", help="Skip fetch, just merge existing")
    args = parser.parse_args()

    layers = args.layers.split(",")
    regions = args.regions.split(",") if args.regions else list(US_REGIONS.keys())

    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geojson", "US")
    regions_dir = os.path.join(base_dir, "regions")
    os.makedirs(regions_dir, exist_ok=True)

    total_features = {}

    for layer_name in layers:
        layer_features = []
        layer_filename = {
            "line": "power_lines",
            "minor_line": "power_minor_lines",
            "substation": "power_substations",
            "plant": "power_plants",
        }.get(layer_name, f"power_{layer_name}")

        for region_name in regions:
            if region_name not in US_REGIONS:
                print(f"Unknown region: {region_name}", file=sys.stderr)
                continue

            # Check if region file already exists
            region_file = os.path.join(regions_dir, f"{layer_filename}_{region_name}.geojson")
            if os.path.exists(region_file):
                with open(region_file) as f:
                    existing = json.load(f)
                count = len(existing["features"])
                print(f"  {region_name}: cached ({count} features)", file=sys.stderr)
                layer_features.extend(existing["features"])
                continue

            bbox = US_REGIONS[region_name]
            print(f"  {region_name}: fetching {layer_name}...", file=sys.stderr)

            query = build_query(bbox, layer_name)
            data = fetch_overpass(query)

            if data is None:
                print(f"  {region_name}: FAILED", file=sys.stderr)
                continue

            geojson = to_geojson(data)
            count = len(geojson["features"])
            print(f"  {region_name}: {count} features", file=sys.stderr)

            with open(region_file, "w") as f:
                json.dump(geojson, f)

            layer_features.extend(geojson["features"])
            time.sleep(10)  # Be nice to Overpass

        # Merge all regions into one file
        merged = {"type": "FeatureCollection", "features": layer_features}
        merged_file = os.path.join(base_dir, f"{layer_filename}_us.geojson")
        with open(merged_file, "w") as f:
            json.dump(merged, f)

        size_mb = os.path.getsize(merged_file) / (1024 * 1024)
        print(f"\n✓ {layer_name}: {len(layer_features)} total features, {size_mb:.1f} MB → {merged_file}", file=sys.stderr)
        total_features[layer_name] = len(layer_features)

    # Summary
    summary = {
        "country": "US",
        "regions_fetched": regions,
        "layers": {k: {"feature_count": v} for k, v in total_features.items()},
        "total_features": sum(total_features.values()),
        "source": "OpenStreetMap (Overpass API)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(os.path.join(base_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"US total: {summary['total_features']} features across {len(total_features)} layers", file=sys.stderr)


if __name__ == "__main__":
    main()
