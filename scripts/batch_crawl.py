#!/usr/bin/env python3
"""
Batch crawl power infrastructure data for all supported countries.
Handles staggering, retries, and logs results.

Usage:
    python batch_crawl.py --layers line,minor_line,substation,plant
    python batch_crawl.py --countries US,GB,DE --layers all
"""

import subprocess
import sys
import time
import os
import json

ALL_COUNTRIES = [
    # Europe (already done lines for some — will skip if summary exists)
    "GB", "DE", "FR", "ES", "IT", "PL", "NL", "SE", "NO", "FI",
    "PT", "GR", "AT", "CH", "BE", "DK", "IE", "CZ", "HU", "RO",
    "BG", "HR", "RS", "UA",
    # Americas
    "CA", "MX", "BR", "AR", "CL", "CO", "PE",
    # Asia-Pacific
    "JP", "KR", "AU", "NZ", "CN", "IN", "ID", "TH", "VN",
    "MY", "PH", "PK", "BD", "SG",
    # Africa/Middle East
    "ZA", "EG", "TR", "NG", "KE", "MA",
    # Skip US/RU for now (need bbox splitting)
]

SKIP_COUNTRIES_LINES = {"GB", "DE", "ES", "IT", "PL", "NL", "SE", "NO", "FI"}  # already have lines

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_overpass.py")
GEOJSON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "geojson")
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "crawl_log.json")


def check_existing(country, layers):
    """Check if all layers already exist for this country."""
    country_dir = os.path.join(GEOJSON_DIR, country)
    if not os.path.isdir(country_dir):
        return False
    for layer in layers:
        # Map layer names to filenames
        layer_files = {
            "line": "power_lines",
            "minor_line": "power_minor_lines",
            "cable": "power_cables",
            "substation": "power_substations",
            "plant": "power_plants",
            "generator": "power_generators",
            "tower": "power_towers",
        }
        fname = f"{layer_files.get(layer, layer)}_{country.lower()}.geojson"
        if not os.path.exists(os.path.join(country_dir, fname)):
            return False
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--countries", default=None, help="Comma-separated country codes (default: all)")
    parser.add_argument("--layers", default="line,minor_line,substation,plant",
                        help="Comma-separated layers or 'all'")
    parser.add_argument("--delay", type=int, default=30, help="Seconds between countries")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip countries where all layers already exist")
    args = parser.parse_args()

    layers = args.layers.split(",")
    countries = args.countries.split(",") if args.countries else ALL_COUNTRIES

    results = []

    for i, country in enumerate(countries):
        country = country.strip().upper()

        # Skip if already has all layers
        if args.skip_existing and check_existing(country, layers):
            print(f"[{i+1}/{len(countries)}] {country}: SKIP (all layers exist)")
            results.append({"country": country, "status": "skipped"})
            continue

        # For countries that already have lines, only fetch missing layers
        country_layers = list(layers)
        if country in SKIP_COUNTRIES_LINES and "line" in country_layers and "minor_line" in country_layers:
            country_layers = [l for l in country_layers if l not in ("line", "minor_line")]

        layers_str = ",".join(country_layers)
        print(f"[{i+1}/{len(countries)}] {country}: fetching {layers_str}...")

        result = subprocess.run(
            [sys.executable, SCRIPT, "--country", country, "--layers", layers_str],
            capture_output=True, text=True, timeout=1800
        )

        status = "ok" if result.returncode == 0 else "failed"
        stderr_lines = result.stderr.strip().split("\n")[-3:] if result.stderr else []

        print(f"  → {status}")
        if stderr_lines:
            for l in stderr_lines:
                print(f"  {l}")

        results.append({
            "country": country,
            "status": status,
            "layers": country_layers,
        })

        # Save log incrementally
        with open(LOG_FILE, "w") as f:
            json.dump({"results": results, "layers": layers}, f, indent=2)

        if i < len(countries) - 1:
            time.sleep(args.delay)

    # Final summary
    ok = sum(1 for r in results if r["status"] == "ok")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] == "skipped")

    print(f"\n{'='*50}")
    print(f"Done: {ok} ok, {failed} failed, {skipped} skipped")
    if failed:
        print("Failed countries:")
        for r in results:
            if r["status"] == "failed":
                print(f"  - {r['country']}")


if __name__ == "__main__":
    main()
