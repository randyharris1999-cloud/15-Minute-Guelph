# 15-Minute Guelph

How much of Guelph can you reach from your front door on foot, or by bus and on foot?

Search any Guelph address to get:

- **A 15-minute score** (0–100). It's based on walking time along the city's streets and trails to groceries, parks, schools, pharmacies, clinics, libraries, cafés, trails, playgrounds, gardens and restrooms, plus bus frequency and street trees.
- **Walk and bus + walk reach maps.** The bus maps use the full Guelph Transit timetable.
- **Next departures within a 5-minute walk.** These use live arrival predictions and show service alerts.
- **Live buses** on the map, updated every 15 seconds.
- **Live City layers:** amenities, AED defibrillators, road closures and sidewalk snow clearing.
- **A city-wide score map and a Census view** that links access to income, age, renting and commuting in each of Guelph's 201 census neighbourhoods.

## Publish it on GitHub Pages

1. On GitHub, create a new **public** repository named `fifteen-minute-guelph`.
2. Click **uploading an existing file**. Drag in everything from this folder, including the `data` and `scripts` folders and the `.nojekyll` file, then click **Commit changes**.
   - Windows hides files that start with a dot. If `.nojekyll` doesn't show up, it isn't critical: it only stops GitHub from processing the site with Jekyll.
3. Go to **Settings > Pages**. Under **Build and deployment**, set **Source** to *Deploy from a branch* and **Branch** to `main` / `(root)`, then save.
4. After a minute or two the site is live at
   **https://randyharris1999-cloud.github.io/fifteen-minute-guelph/**

Live buses work right away. `config.js` points at the Cloudflare Worker you already run for the Guelph Trip Planner (`guelph-trip-planner`), and that Worker already accepts requests from `randyharris1999-cloud.github.io`. Nothing needs to change on Cloudflare.

## Test on your own computer

Browsers block data loading from files opened by double-clicking, so serve the folder instead:

```
cd fifteen-minute-guelph
python -m http.server 8000
```

Open http://localhost:8000. Your Worker also allows `localhost:8000`, so live buses work here too.

## What's in the folder

| Path | What it is |
|---|---|
| `index.html` | The app (map, report card, reach maps, census view) |
| `config.js` | Live-data setting: the relay address |
| `gtfsrt.js` | Reads Guelph Transit's GTFS-realtime feed format in the browser |
| `leaflet.min.js` | Leaflet 1.9.4 map library |
| `data/` | Pre-built data: walking network, addresses and scores, buildings, water, street names, trees, places, transit schedule, census |
| `scripts/` | The Python build scripts and app source that produced `data/` and `index.html` |

## Where the data comes from

| Data | Source | Updates |
|---|---|---|
| Addresses, buildings, streets, trails, parks, trees, watercourses | City of Guelph Open Data | At build time |
| Schools, facilities, restrooms, community gardens, AEDs | City of Guelph map server | Live on every visit |
| Road closures and detours | City of Guelph map server | Live, every 5 min |
| Sidewalk snow clearing | City of Guelph winter plow tracking | Live, during winter operations |
| Bus schedule | Guelph Transit GTFS (fall 2026) | At build time |
| Bus positions, predictions, alerts | Guelph Transit GTFS-realtime, through the Cloudflare relay | Live, every 15 to 120 s |
| Grocery stores, pharmacies, clinics, cafés, playgrounds | © OpenStreetMap contributors (ODbL) | At build time |
| Population, income, age, renting, commuting | Statistics Canada, 2021 Census of Population, dissemination areas | At build time |

## Rebuilding the data

The `scripts/` folder holds the pipeline:

1. `build_graph.py` builds the walking network.
2. `build_data.py` snaps places, trees and transit to the network and scores every address.
3. `build_extra.py` prepares buildings, water and street names.
4. `build_census.py` joins the census data.
5. `build_html.py` assembles the page.

The file paths at the top of each script point to where they were first run, so edit them to match your folders. Rebuild when Guelph Transit publishes a new schedule (usually September and January) or when you want fresher OpenStreetMap shops.

## Notes

- Live times use the visitor's clock and assume Ontario time.
- The city-wide score map uses the last build. Each address's report card uses the live City layers.
- The City's road closures service was returning errors at build time. The app reports "not responding" and carries on.

An independent project built on City of Guelph open data. Not an official City of Guelph service. Created by Randy Harris.
