#!/usr/bin/env python3
"""
Fetch power transmission & distribution lines from OpenStreetMap via Overpass API.

Usage:
    python fetch_overpass.py --country US
    python fetch_overpass.py --bbox "-125,24,-66,49"  # US bounding box
    python fetch_overpass.py --country GB --types line,minor_line

Outputs GeoJSON to ../geojson/<country>/
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]

# Country bounding boxes (min_lon, min_lat, max_lon, max_lat)
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
}

POWER_TYPES = {
    "line": "power=line",
    "minor_line": "power=minor_line",
    "cable": "power=cable",
}


def build_query(bbox, power_types):
    """Build Overpass QL query for power lines in a bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    bbox_str = f"{min_lat},{min_lon},{max_lat},{max_lon}"

    queries = []
    for pt in power_types:
        tag = POWER_TYPES[pt]
        key, val = tag.split("=")
        queries.append(f"""
    way["{key}"="{val}"]({bbox_str});
""")

    query = f"""[out:json][timeout:900];
"""
    query += "(\n"
    for q in queries:
        query += q
    query += ");\nout geom;"
    return query


def fetch_overpass(query):
    """Try multiple Overpass endpoints."""
    import urllib.parse
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
        if el.get("type") != "way":
            continue

        geometry_type = el.get("geometry", [])
        if not geometry_type:
            continue

        coords = [[node["lon"], node["lat"]] for node in geometry_type]

        if len(coords) < 2:
            continue

        tags = el.get("tags", {})

        feature = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "id": el.get("id"),
                "power_type": tags.get("power", ""),
                "voltage": tags.get("voltage", ""),
                "frequency": tags.get("frequency", ""),
                "cables": tags.get("cables", ""),
                "operator": tags.get("operator", ""),
                "name": tags.get("name", ""),
                "ref": tags.get("ref", ""),
                "layer": tags.get("layer", ""),
                "source": tags.get("source", "OpenStreetMap"),
            },
        }
        features.append(feature)

    return {"type": "FeatureCollection", "features": features}


def main():
    parser = argparse.ArgumentParser(description="Fetch power lines from OSM Overpass API")
    parser.add_argument("--country", help="Country code (e.g., US, GB, DE)")
    parser.add_argument("--bbox", help="Bounding box: min_lon,min_lat,max_lon,max_lat")
    parser.add_argument(
        "--types",
        default="line,minor_line",
        help="Comma-separated power types: line,minor_line,cable",
    )
    parser.add_argument("--output-dir", default=None, help="Output directory")

    args = parser.parse_args()

    if args.country:
        country = args.country.upper()
        if country not in COUNTRY_BBOXES:
            print(f"Unknown country: {country}", file=sys.stderr)
            print(f"Available: {', '.join(sorted(COUNTRY_BBOXES.keys()))}", file=sys.stderr)
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

    power_types = [t.strip() for t in args.types.split(",")]

    output_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geojson", country
    )
    os.makedirs(output_dir, exist_ok=True)

    print(f"Fetching power {', '.join(power_types)} for {country}...", file=sys.stderr)
    query = build_query(bbox, power_types)
    overpass_data = fetch_overpass(query)

    geojson = overpass_to_geojson(overpass_data)

    out_file = os.path.join(output_dir, f"power_lines_{country.lower()}.geojson")
    with open(out_file, "w") as f:
        json.dump(geojson, f)

    feature_count = len(geojson["features"])
    file_size_mb = os.path.getsize(out_file) / (1024 * 1024)

    print(f"\n✓ {feature_count} features → {out_file}", file=sys.stderr)
    print(f"  Size: {file_size_mb:.1f} MB", file=sys.stderr)

    # Also write summary
    summary = {
        "country": country,
        "types": power_types,
        "feature_count": feature_count,
        "file_size_mb": round(file_size_mb, 1),
        "source": "OpenStreetMap (Overpass API)",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    summary_file = os.path.join(output_dir, "summary.json")
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"  Summary → {summary_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
