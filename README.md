# anime-tracker

## Trend outputs

`plot_trend.py` generates individual anime charts as before. It stores each anime's
genre data in its own CSV file under `data/<season>/genres/<genre>/<anime_id>.csv`.
The matching `trends/<season>/genres/<genre>/all_anime.png` shows each anime's MAL
score and member-count trends for that genre. The season-wide chart at
`trends/<season>/all_anime/all_anime.png` shows every anime in that season.

It also gathers those per-anime CSVs across seasons under
`data/genres/<genre>/<anime_id>.csv`, creates individual anime charts at
`trends/genres/<genre>/<anime_id>.png`, and creates a combined chart at
`trends/genres/<genre>/all_anime.png`. The daily tracker workflow generates and
commits these files automatically. Changes to season lists trigger collection, and
the new-season workflow collects and plots trends immediately after adding titles.
