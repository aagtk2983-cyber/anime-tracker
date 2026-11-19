import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from anime_lists import _season_data_rows, populate_change_rates


class PopulateChangeRatesTests(unittest.TestCase):
    def test_rates_compare_to_previous_valid_observation(self):
        rows = [
            {
                "mal_score": "8.0",
                "mal_members": "1,000",
                "danime_favorites": "100",
                "danime_rank": "20",
                "danime_weekly_rank": "50",
            },
            {
                "mal_score": "8.4",
                "mal_members": "1,250",
                "danime_favorites": "",
                "danime_rank": "10",
                "danime_weekly_rank": "40",
            },
            {
                "mal_score": "8.4",
                "mal_members": "1,250",
                "danime_favorites": "200",
                "danime_rank": "10",
                "danime_weekly_rank": "40",
            },
        ]

        populate_change_rates(rows)

        self.assertEqual(rows[0]["mal_score_change_pct"], "")
        self.assertEqual(rows[1]["mal_score_change_pct"], "5.000000")
        self.assertEqual(rows[1]["mal_members_change_pct"], "25.000000")
        self.assertEqual(rows[1]["danime_rank_change_pct"], "-50.000000")
        self.assertEqual(rows[1]["danime_weekly_rank_change_pct"], "-20.000000")
        self.assertEqual(rows[1]["danime_favorites_change_pct"], "")
        self.assertEqual(rows[2]["danime_favorites_change_pct"], "100.000000")

    def test_zero_previous_value_has_no_percentage_rate(self):
        rows = [{"danime_rank": "0"}, {"danime_rank": "5"}, {"danime_rank": "10"}]

        populate_change_rates(rows)

        self.assertEqual(rows[1]["danime_rank_change_pct"], "")
        self.assertEqual(rows[2]["danime_rank_change_pct"], "100.000000")

    def test_aggregate_adds_rate_columns_and_weekly_rank(self):
        fields = [
            "anime_id", "season", "date", "time", "mal_score",
            "mal_members", "danime_favorites", "danime_rank",
            "danime_weekly_rank",
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            title_dir = os.path.join(temp_dir, "2026-fall", "all_anime")
            os.makedirs(title_dir)
            title_path = os.path.join(title_dir, "sample.csv")
            with open(title_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerow(dict(
                    anime_id="sample", season="2026-fall", date="2026-10-01",
                    time="01:00:00", mal_score="8.0", mal_members="1000",
                    danime_favorites="100", danime_rank="20",
                    danime_weekly_rank="40",
                ))
                writer.writerow(dict(
                    anime_id="sample", season="2026-fall", date="2026-10-02",
                    time="01:00:00", mal_score="8.4", mal_members="1250",
                    danime_favorites="150", danime_rank="10",
                    danime_weekly_rank="30",
                ))

            with patch("anime_lists.DATA_DIR", temp_dir):
                result = _season_data_rows("2026-fall")

        self.assertEqual(result[1]["danime_weekly_rank"], "30")
        self.assertEqual(result[1]["mal_score_change_pct"], "5.000000")
        self.assertEqual(result[1]["danime_weekly_rank_change_pct"], "-25.000000")


if __name__ == "__main__":
    unittest.main()
