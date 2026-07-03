# Global Power Lines

Power transmission & distribution lines from OpenStreetMap, organized country-by-country as ready-to-use GeoJSON.

## Why this exists

Clean, free, country-level extracts of power line data — pull what you need into Mapbox, QGIS, or any mapping project without querying OSM yourself.

## Data source

All data is from **OpenStreetMap** via the Overpass API. Tags pulled:
- `power=line` — high-voltage transmission lines
- `power=minor_line` — distribution lines
- `power=cable` — underground/submarine cables (optional)

Each feature includes voltage, operator, cables, frequency, and name where tagged.

## Usage

### Fetch a country

```bash
python scripts/fetch_overpass.py --country US
```

Output lands in `geojson/<COUNTRY>/power_lines_<country>.geojson`.

### Fetch a custom area

```bash
python scripts/fetch_overpass.py --bbox "-125,24,-66,49"
```

### Available countries

| Country | Features | Size |
|---------|----------|------|
| NL | ~16k | ~7 MB |
| GB | ~224k | ~114 MB |

More added regularly. Run `python scripts/fetch_overpass.py --country XX` to generate any of 27+ supported countries.

## Using with Mapbox

```js
map.addSource('power-lines', {
  type: 'geojson',
  data: 'geojson/GB/power_lines_gb.geojson'
});

map.addLayer({
  id: 'power-lines',
  type: 'line',
  source: 'power-lines',
  paint: {
    'line-color': '#ff6b35',
    'line-width': 1,
    'line-opacity': 0.8
  }
});
```

For large datasets (100k+ features), upload to [Mapbox Tilesets](https://docs.mapbox.com/studio-manual/guides/upload-data/) instead of loading GeoJSON directly in the browser.

## License

Data is © OpenStreetMap contributors, licensed under the [Open Data Commons Open Database License](https://www.openstreetmap.org/copyright) (ODbL).

Scripts are MIT licensed.
