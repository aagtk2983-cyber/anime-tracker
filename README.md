# anime-tracker

## Trend outputs

`plot_trend.py` generates individual anime charts as before, and also gathers each
season's genre data into `data/<season>/genres/<genre>/all_anime.csv`. The matching
`trends/<season>/genres/<genre>/all_anime.png` shows each anime's MAL score and
member-count trends for that genre.

It also creates all-season genre data at `data/genres/<genre>/all_anime.csv`,
individual anime charts at `trends/genres/<genre>/<anime_id>.png`, and a combined
chart at `trends/genres/<genre>/all_anime.png`. The daily tracker workflow generates
and commits these files automatically.
