# reports

週次レポート(Gemini API で生成)の保存先です。

- 毎週日曜 21:00 JST に `.github/workflows/weekly_report.yml` が実行されます。
- 生成されたレポートは `reports/<シーズン>/<年>-W<週番号>.md` に保存されます。
  例: `reports/2026-summer/2026-W40.md`
- このファイルは、`reports/` フォルダを最初から存在させるためのものです。削除しないでください。
