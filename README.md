# anime-tracker

## Trend outputs

`plot_trend.py` generates individual anime charts as before. It stores each anime's
genre data in its own CSV file under `data/<season>/genres/<genre>/<anime_id>.csv`.
The matching `trends/<season>/genres/<genre>/all_anime.png` shows each anime's MAL
score, MAL member count, dアニメ favorites, and dアニメ ranking trends for that
genre. The season-wide chart at `trends/<season>/all_anime/all_anime.png` shows
the same metrics for every anime in that season. Ranking charts put better ranks
(lower numbers) higher on the axis.

For catalog use, the repository also keeps a full season summary CSV at
`data/<season>/all_anime/all_anime.csv` and a full cross-season CSV at
`data/all_anime.csv`. Each row corresponds to one anime entry in the same format
as the daily tracking data. `daily_tracker.py` refreshes these summaries after
each collection, and `start_new_season.py` creates them when a new season is added.

It also gathers those per-anime CSVs across seasons under
`data/genres/<genre>/<anime_id>.csv`, creates individual anime charts at
`trends/genres/<genre>/<anime_id>.png`, and creates a combined chart at
`trends/genres/<genre>/all_anime.png`. The daily tracker workflow generates and
commits these files automatically. Changes to season lists trigger collection, and
the new-season workflow collects and plots trends immediately after adding titles.
