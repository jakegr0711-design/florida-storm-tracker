# Florida Storm Tracker

A student science-communication project: every tropical cyclone that crossed Florida since 1851, a simple statistical hurricane track model tested against the National Hurricane Center, and an interactive map (`index.html`).

**Pages:**
- `index.html`: the live tracker. It shows active storms with NHC's forecast cone, track and watches/warnings, the 7-day outlook for new storms, and a personal risk report for any address (National Weather Service alerts and forecast, FEMA flood zone, USGS ground elevation, hurricane history within 50 miles). All data loads live from NOAA, FEMA and USGS in the visitor's browser and refreshes every 5 minutes (and when the visitor returns to the tab); the report notes any alerts that were issued or ended since the last check. `api/season.js` serves live season totals (from NHC best-track files) and the current El Nino/La Nina status (NOAA CPC), cached for an hour. The map uses Esri's keyless gray basemap, falling back to OpenStreetMap tiles if Esri fails.
- `history.html`: every storm that crossed Florida since 1851, plus the class forecast model you can test against real storms.

**View the site:** open `index.html` in a browser, or turn on GitHub Pages for this repository (Settings, Pages, Deploy from a branch, `main`, `/ (root)`). The hurricane chat assistant only works on the Claude-hosted version of the page; everything else works anywhere.

**This is a class project, not a forecast.** For real hurricane decisions use https://www.nhc.noaa.gov and your county emergency management.

## Method and findings

Built on NOAA/NHC HURDAT2 (file `hurdat2-1851-2025-092326.txt`, the "best track" database: 1,988 Atlantic storms, 55,524 six-hourly positions, 1851-2025). Everything here is reproducible: run `python build.py` in this folder (it writes images to `output/`).

## Files

| File | What it is |
|---|---|
| `index.html` | The interactive website: map, filters, model tester, and chat assistant |
| `predict_live.py`, `model_params.json`, `example_isaias/` | Run the model on a storm that is active right now (see below) |
| `hurdat2_compact.csv` | NOAA HURDAT2 data reduced to the columns the code uses |
| `map1_florida_tracks_1851_2025.png` | Every storm track that crossed Florida land, colored by strength while over Florida |
| `map2_where_florida_hurricanes_come_from.png` | Left: birthplace of the 105 storms that hit Florida at hurricane strength. Right: heat map of where those storms were during the 72 hours before reaching the state |
| `chart_florida_by_decade_and_month.png` | Florida crossings per decade and per month |
| `chart_model_vs_nhc_error.png` | Average position error of our model vs persistence, climatology, and the National Hurricane Center |
| `case_studies_irma_ian_milton_andrew.png` | Our model's 3-day forecast vs the real track for four famous Florida storms |
| `florida_storms_1851_2025.csv` | List of all 283 Florida-crossing storms with year, name, and strength at impact |
| `model_results.csv` | The error table behind the chart |
| `build.py` | All code (Python: pandas, scikit-learn, matplotlib, global-land-mask) |

## Key numbers (for the article)

- 283 tropical cyclones have crossed Florida since 1851; 105 of them were hurricanes while over the state and 34 were major (Category 3+).
- Florida hurricanes cluster in September (35) and October (34), then August (20). June, July and November together account for only 16.
- Where they come from: the 72-hour heat map shows the two main doors, the western Caribbean / Gulf (October storms like Wilma, Michael, Milton, Helene) and the Bahamas / open Atlantic (August-September Cape Verde storms like Andrew and Irma). Very few arrive from north of 30N or from east of 60W within 3 days.
- The 2020s already have 7 Florida hurricane crossings in 6 seasons: Sally 2020, Ian and Nicole 2022, Idalia 2023, Debby, Helene and Milton 2024.

## The model (what it is and is not)

Type: a "CLIPER-style" statistical model, the same family NHC uses as its skill baseline. Inputs at forecast time: latitude, longitude, wind speed, the storm's motion over the previous 6 and 12 hours, and day of year. Method: ridge regression on second-degree polynomial features, predicting the change in latitude and longitude at 12, 24, 48 and 72 hours. Trained on 22,944 forecast points from 1950-2014, tested on 5,237 points from 2015-2025 that the model never saw.

Average position error on the 2015-2025 test set (nautical miles):

| Lead time | Climatology only | Persistence | Our model | NHC CLIPER5 (2024) | NHC official (2024) |
|---|---|---|---|---|---|
| 12 h | 133 | 55 | 43 | 42 | 19 |
| 24 h | 254 | 134 | 107 | 88 | 28 |
| 48 h | 467 | 321 | 250 | 199 | 45 |
| 72 h | 646 | 531 | 384 | 281 | 67 |

NHC figures are from the NHC 2024 Forecast Verification Report, Table 2 (Atlantic basin). Our model matches NHC's own statistical baseline at 12 h and is within about 35 percent of it at 3 days, which is what a weekend of coding gets you. The National Hurricane Center's real forecast is 2 to 6 times more accurate because it uses physics-based and AI models that simulate the steering winds around the storm. Our model never sees the atmosphere; it only sees where the storm has been.

Case studies show the failure mode clearly. For Andrew (1992), a storm that was in the training data, the model still predicted a recurve out to sea while the real storm turned west into Miami, an 810 n mi miss at 72 h. Statistics cannot see the high-pressure ridge that steered Andrew west.

## Caveats to state in the article

- Records before about 1900 undercount storms (no satellites, no aircraft, few ships). Before 1966 some storms over open water were missed entirely. Decade comparisons should be read with that in mind.
- "Crossed Florida" is detected by interpolating the 6-hourly track hourly and testing whether it passes over Florida land on a 1 km land mask. The Keys are small enough that the mask sometimes misses a Keys landfall, so Irma (2017) is recorded here at its mainland strength (Cat 3) rather than its Cudjoe Key landfall strength (Cat 4). Official NHC counts, which use landfall records directly, are slightly higher than ours.
- Strength uses the Saffir-Simpson wind thresholds (64, 83, 96, 113, 137 kt) on HURDAT2 one-minute sustained winds, taking the stronger of the two 6-hourly fixes on either side of the crossing. A storm weakening right at the coast can therefore show one category high (Idalia 2023 shows Cat 4; NHC's landfall intensity was Cat 3). Sally 2020 made landfall in Alabama but its track then crossed the Florida Panhandle, so it is counted.
- This model must not be used to forecast a live storm. Use the National Hurricane Center.

## Sources

- NOAA/NHC HURDAT2 Atlantic best track database: https://www.nhc.noaa.gov/data/hurdat/
- NHC Forecast Verification Report 2024: https://nhc.noaa.gov/verification/pdfs/Verification_2024.pdf
- global-land-mask (1 km land/ocean mask): https://pypi.org/project/global-land-mask/

## Running the model on a storm that is active right now

`predict_live.py` downloads NHC's public best-track file for each active Atlantic storm, runs our model from the latest 6-hourly position, and prints it next to NHC's official forecast for the same moment. It also saves a map.

```
pip install numpy matplotlib global-land-mask
python predict_live.py              # every active Atlantic storm
python predict_live.py al092026     # one storm (NHC id: basin + number + year)
```

Offline test with saved NHC files (Hurricane Isaias, Oct 8 2026 18Z):

```
python predict_live.py --bdeck example_isaias/bal092026.dat --adeck example_isaias/aal092026.dat
```

Result for Isaias, forecast from Oct 8 18Z (latitude N / longitude W):

| Lead | Our model | NHC official | Gap (n mi) |
|---|---|---|---|
| 12 h | 25.4 / 88.3 | 25.7 / 88.4 | 16 |
| 24 h | 27.1 / 86.8 | 28.2 / 87.4 | 76 |
| 48 h | 30.6 / 83.7 | 33.2 / 87.8 | 260 |
| 72 h | 33.7 / 79.3 | 37.0 / 85.0 | 344 |

Our model sends Isaias toward Florida's Big Bend because that is what storms in that spot have usually done. NHC sends it north into Alabama because its models can see the steering pattern this week. After the storm, compare both columns with the final best track: that comparison is the strongest piece of evidence for the article.

Do not publish our model's track for a live storm as a forecast. Show it only next to NHC's official forecast, clearly labeled, or after the storm as a scorecard.

## Chat assistant on the live site

`api/chat.js` is a Vercel serverless function. The page sends visitor questions to `/api/chat`; the function adds the Anthropic API key, the safety rules, the latest NHC advisory and outlook (fetched on the server, cached 10 minutes) and the visitor's risk report, then asks Claude and returns only the answer text. The key never reaches the browser.

To turn it on: in Vercel, open the project's Settings, Environment Variables, add `ANTHROPIC_API_KEY` (Production), save, then redeploy the latest deployment. The chat box stays hidden until the key exists.

Safeguards: requests are accepted only from this site, each visitor is limited to 20 messages an hour (best effort, per server instance), answers are capped at 700 tokens, and only the last 10 messages are sent. Set a monthly spending limit in the Anthropic Console as the real backstop. Optional settings: `ANTHROPIC_MODEL` (default `claude-haiku-5-5`) and `ALLOWED_ORIGINS` (comma-separated, for a custom domain).
