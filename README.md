# Matchday Edge

Live football and NBA scores, in-play stats, player box scores, model-rated bets, an acca builder and a £1 → £1K challenge tracker.

- `site/` is the web app. The browser polls the public ESPN feed every 10 seconds for live scores and stats.
- `engine/build.py` pulls fixtures, form, odds and stats and runs the prediction model. GitHub Actions runs it every 20 minutes and redeploys the site.
- `engine/challenge.json` holds the £1 → £1K challenge ladder.

18+. Predictions are estimates, not guarantees. BeGambleAware.org
