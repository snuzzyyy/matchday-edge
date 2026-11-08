# Accabox (formerly Matchday Edge): handover

Everything a new Claude session (or developer) needs to keep building Matchday Edge without re-discovering anything.
Last updated: 1 Nov 2026, end of the second build session.

**Read §0 first: it is the first job.** Then skim §2 (how the owner works) and §11 (lessons learned the hard way).

---

## 0. FIRST JOB: NBA player bets in the acca builder (and swapping legs, more than 3 legs)

> **DONE (1 Nov 2026, third session).** What shipped, so you don't redo it:
> - Engine: `player_log` / `player_props` in `engine/build.py` (top 4 players per team by minutes, 22+ min, Out skipped, up to 3 lines per stat). ~100 `P:` markets per game; data.json ≈ 1.1 MB.
> - Client: `isProp`, `propLeg`, `legText`, `optsHTML` (dropdowns grouped "Match bets" + one group per player), `pinGame` (swap/remove/change-main keeps the game's other legs and stops re-optimising). Player bets are priced bookie-style with `livePrice` (no market price exists). Bundles use a beam search, up to 4 legs.
> - Player bets are kept out of Tips, Top picks, presets, the game page's "Best bets" and import matching (`marketIn`). Game page shows a table per player under "Player bets".
> - Also fixed: in-play "or choose one yourself" collapsed on every 10 s redraw (`S.addOpen`); acca → slip now uses exactly the legs on screen (`S._accaLegs` / `S._accaLiveLegs`); phone-tracked bet copies are matched to saved bets by legs (`localTracked`, `legSig`) and clear themselves after the game (`pruneTracked`).
> - Not done (v2): live player-bet chances in the in-play acca.
> - Later the same session: Ctrl+V / drag-drop screenshot import on PC (`importShot`, also reads "@ 2.10" / "@210" odds); Sky stat specials ("A, B & C 7+ shots between them" → one leg with `group: [{pid,name,side,gid,team}]`, summed by `legValue` and `engine/settle.py`; "(N so far)" ignored); same-player multi-leg cards titled "Name · N bets"; £1K stake box (`data-chalstake`: sets `C.bank`, wallet moves by the difference, lower = `C.taken`, higher = `C.added`).
> - Football player bets: `football_props` in `engine/build.py` (confirmed line-up or 3+ starts in the last 5 → ESPN athlete game log `/sports/soccer/athletes/{id}/gamelog`, 12 h cache; Premier League blends Fantasy PL xG and skips FPL-injured players). Markets: to score, shots, shots on target, times fouled, to be carded. `propText` shows "X to score" / "X to be carded".
> - Line-up screen: `pitchHTML` + `formationRows` with the owner's Gemini art (`img/pitch.webp`, `img/halloween/pitch.webp`, icons in `img/lineups/`; originals in `art/lineups/`).
> - Live redraws only pause while someone is actually typing (`S._typedAt`), not just because a box has focus (that froze bets on PC).
> - £1K is now up to 3 separate challenges (`CH_MAX`), each a ladder with one bet at a time that can be football or NBA: stored as `{v:4, ladders:[{id,start,rungs,rung,bank,attempts,started,history[],past[],taken,added,active:{sport,legs,label,match,dec,p,custom}}], closed:[past attempts of closed challenges]}`. `S.chalSel` = selected challenge id; `chalNow()` = selected; `saveChal(C)` saves one; `saveChalAll()` saves all. Old v2 (one per sport) and v3 (one ladder, several bets) are converted by `normChal`. `engine/settle.py` settles each challenge with the original `settle_ladder`.
> - Imported bets need odds to save to My Bets (otherwise they'd only exist on that device). `refreshMine()` re-reads bets/£1K/balance every minute.
> - Import always saves (signed in): unmatched text becomes `{manual:true,label}` legs the owner marks Landed/Lost (`data-mleg`); `betOutcome` and `engine/settle.py` `outcome()` never call a bet won while one is unmarked. Odds: typed > parsed > `impEst` (app prices) > ask. Player search is 1.5 days, widened to 5 (`S.impWide`) only when a name is missing.
> - Bet cards: `bc-money` row (stake/odds/returns), "chance it lands now" (`betChance`/`legChance`), per-leg % (`withPc`). £1K bets have their own section in My Bets.
> - Acca builder: `levelPreset(n)` ready-made double/treble/four-fold/same-game for the chosen RISK level (pre-match only, cached 30 s).
> - Themed ready-made accas per sport (`THEMES`, `buildPreset(kind, win, sport)`, `mixPick`/`MIX`), and a Multi tab in Bets (`viewMulti`, `multiPreset`, `multiTheme`, window `S.multiWin`). All ready-made accas load by id through `presetLegs()` (`lvl:` / `th:` / `mp:` / `mt:`). Game page: `popularHTML` (bet builders at 3 prices). The game page has tabs pinned under the Back bar (`.gtabs`, `data-gtab`, `S.gtab`, reset to Overview when a new game opens): Overview (win chance, in-play angles, 4 key stats, bet builders), Bets/Markets (best bets + all markets), Stats (stats, quarters, timeline, leaders, form), Line-ups/Players (pitch, box score, injuries). Each tab is two columns on wide screens (`cols()` in `drawerHTML`, `.g-cols.one` when only one side has content).
> - Commits from this sandbox are authored as Claude <noreply@anthropic.com> (a stop hook requires it).

The owner asked for this last and is waiting on it. Their words: *"include player points etc and be able to add more than 3 and be able to swap some out"*. Their screenshot was an NBA same-game acca (Celtics @ Magic) where the only same-game options were the total, the handicap and the winner, so the builder ran out of bets to add. Do this first, in this order.

### 0.1 Where the numbers come from (already checked)

- ESPN player game log (works, no key):
  `https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{athleteId}/gamelog`
  Add `?season=2026` for last season (current season value is `2027` = 2026-27).
  Response: `labels` = `["MIN","FG","FG%","3PT","3P%","FT","FT%","REB","AST","BLK","STL","PF","TO","PTS"]`,
  games under `seasonTypes[0].categories[*].events[*].stats` (array aligned with `labels`; `3PT` is `"made-attempted"`).
- Team roster (player ids and names): `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{teamId}/roster` → `athletes[]` (`id`, `displayName`).
- Injuries are already in each game's summary (`s.injuries`, used in `engine/build.py`). Skip players listed as `Out`.

### 0.2 Engine (engine/build.py, inside `nba()`)

For every NBA game that is `pre` and starts within ~36 hours:

1. Get both rosters (use the existing `get(url, cache_key, ttl)` helper with a ~6 h ttl, and `pmap` for parallel fetches).
2. For each player, fetch the game log for this season and last season (cache 6 h). Work out per-game PTS, REB, AST, 3PM (made part of `3PT`), PRA (= PTS + REB + AST) and MIN.
3. Keep players averaging 22+ minutes (use last season if they have fewer than 3 games this season). Drop players who are `Out`. Cap at about 8 players per game, so `data.json` stays small.
4. Model per stat:
   - mean `m = (n*cur + k*prev) / (n + k)` with `k = 6` (shrinks a hot first week toward last season);
   - spread `sd = max(empirical sd of the last ~20 games, 0.25*m + 2)` for PTS/REB/AST/PRA;
   - `P(X >= t) = 1 - Φ((t - 0.5 - m) / sd)` (normal with a continuity correction; `phi` already exists in build.py);
   - threes: Poisson with mean `m` (`p_over`/`poisson` helpers exist).
5. Lines (bookie style): PTS 10/15/20/25/30/35/40, REB 4/6/8/10/12, AST 3/4/6/8/10, 3PM 1/2/3/4/5, PRA 20/25/30/35/40/45/50. Keep lines with 0.12 ≤ p ≤ 0.92, and at most 3 lines per player per stat (the ones with p nearest 0.5–0.8).
6. Append to that game's `model.markets` (the same list the client already uses):
   ```python
   {"k": f"P:{pid}:{stat}:{t}", "label": f"{name} {t}+ {word}", "p": p, "fair": 1/p,
    "prop": {"pid": pid, "name": name, "side": "h" or "a", "team": team_short_name, "stat": stat, "target": t, "label": word}}
   ```
   `stat` must be one of `PTS`, `REB`, `AST`, `3PM`, `PRA`. `word` is `points`, `rebounds`, `assists`, `threes` or `pts+reb+ast`. `side` is `h`/`a`, matching `g.box` keys. These exact fields are what the client's player tracking (`legValue`) already reads for imported player bets, so tracking and settling then work with no extra code.
7. Test locally: `python3 engine/build.py --fast`, then check `site/data.json` has `P:` markets with sensible probabilities (e.g. a 30-ppg star should be about 70–80% for 25+). **Don't commit a broken data.json**: Actions rebuilds it anyway.

### 0.3 Client (site/index.html)

1. **`asLegs()`** (≈ line 1471): when `m.prop` exists, spread it into the leg (`pid, name, side, team, stat, target, label = word`). Then slip → saved bet → My Bets uses the player progress bars and auto-settling (`legValue`, `betOutcome`, `engine/settle.py` NBA prop path). Check `savebet` and the acca → slip path (`data-accaslip`) carry the fields.
2. **`SG_GROUP`** (≈ line 1496): return `"p:" + pid + ":" + stat` for `P:` keys, so one line per player per stat is allowed but different players and stats can combine.
3. **`withBundles()`** (≈ line 1498): with props there are far more groups. Keep combinations bounded:
   - limit to the ~8 groups with the best single p;
   - build bundles with a small beam search instead of all triples;
   - **allow up to 4 legs** (the owner asked for more than 3), and keep the "likeliest at every price level" binning.

   Rules already there: no team-to-score with that team's result (fake value). Add: no two props for the same player and stat.
4. **The "＋ Add the likeliest extra bet" button** (`addMoreSel`, ≈ line 1530): it suggests from groups not yet used and needs p ≥ 0.5. With props it will naturally keep offering bets, which gives "more than 3". Make sure it still excludes clashes.
5. **Swapping legs (requested).** Give each same-game extra row (`extraRow`) a dropdown like the main leg's (`data-accaalt`), e.g. `data-accaxswap="gid|oldKey"`, listing that game's free options. On change:
   - if the leg was a manual extra (in `S.accaX[gid]`), replace the key there;
   - if it was auto-picked (from a bundle), pin the game's main leg (`S.accaPick[gid] = mainKey`) and move all its current extras, with the swapped one, into `S.accaX[gid]`, so the pick stops being re-optimised.

   Do the same for in-play (`S.accaLivePick`, `S.accaLiveX`, `data-accalxswap`).
6. **Game page:** add `["Player bets", /^P:/]` to `MGROUPS.nba` (≈ line 1898), so the market tables show them pre-match.
7. **Tips page** (`gameTip`, `tiers`, `candidates`): either leave props out of "Most likely" (recommended at first, as they crowd the cards) or add a "Player bet" row. Exclude `P:` from `tiers()` until checked.
8. **In-play:** `liveMarkets()` does not produce `P:` markets, so props simply won't appear in the in-play acca. That's fine for v1. v2 could compute a live probability from the box score (`legValue`) and minutes left.
9. **Test at 400 px and 360 px** (see §9):
   - pick one NBA game, choose Bigger odds, and check the builder offers player bets;
   - add the acca to the slip, save it, and check My Bets shows player progress bars;
   - swap an auto-picked leg, and add a 4th and 5th leg.
   Then publish and tell the owner in plain words.

### 0.4 After that (owner's open asks)

- **Cash-out tracker:** the owner was given this rundown and asked to decide; **they haven't said yes yet, so ask first**. Each live acca in My Bets would get "Worth about £X now": stake × chance now × odds, minus about 10% bookie cut. The owner could type Sky's offer and get a "good or bad offer" read.
- **Football player bets in the builder:** anytime scorer, shots on target, fouls won, using per-player data. Not researched yet; ESPN soccer athlete endpoints are untested.
- **Real UK bookie prices / Sky Bet slip links:** needs a paid odds feed. The owner was told about The Odds API / Odds-API.io (about £20–60/month); Sky Bet itself has no public slip link.

---

## 1. What it is

**Accabox** (renamed from Matchday Edge on 2 Nov 2026; X handle @accabox was free then) is a UK sports-betting companion app for **football (14 leagues incl. League One/Two, Eredivisie, Portugal, MLS) and the NBA**, built for the owner (GitHub **snuzzyyy**, display name **Snuzzy**, friend code **690481**) and their friends.

It does:
- live scores and stats, a prediction model on every market, tips for every game
- an acca builder (pre-match and in-play, same-game bets picked automatically)
- bet tracking from typed text or a **screenshot**, live leg-by-leg progress, automatic settling (in the app and overnight on GitHub)
- a betting balance, a stats page, two £1 → £1K challenge ladders (football and NBA)
- Friends, following and Top players, profiles with badges, bet alerts
- an Android app, iPhone home-screen support, and a seasonal Halloween theme

**Live links**

| What | Where |
|---|---|
| Website / web app | https://snuzzyyy.github.io/matchday-edge/ |
| Download page (Android + iPhone steps) | https://snuzzyyy.github.io/matchday-edge/app.html |
| APK | https://github.com/snuzzyyy/matchday-edge/releases/download/app/MatchdayEdge.apk (also `site/MatchdayEdge.apk`) |
| Repo (public) | https://github.com/snuzzyyy/matchday-edge |
| Supabase | project `kbsdakacdiolzsiykeql` (West EU), https://supabase.com/dashboard/project/kbsdakacdiolzsiykeql |
| SQL editor (for the owner) | https://supabase.com/dashboard/project/kbsdakacdiolzsiykeql/sql/new |
| GitHub secrets page | https://github.com/snuzzyyy/matchday-edge/settings/secrets/actions |

---

## 2. How the owner likes to work (important)

- **Not technical.** Do everything yourself. Only ask them for steps that need their accounts (Supabase SQL, GitHub secrets/uploads), with exact links and click-by-click steps. Give SQL **on as few lines as possible** (a multi-line paste broke once on their phone).
- **Works from phone screenshots,** often several in a row, often sent *while you are still working*. Fix exactly what's shown, then check related screens. Images sent mid-turn are often **not saved as files**: ask them to resend in a new message, or upload to GitHub (`https://github.com/snuzzyyy/matchday-edge/upload/main/<folder>`). That worked well for the Halloween art.
- **Wants things automatic:** "choose for me", "settle itself", "don't make me pick". Prefer smart defaults with an override.
- **Cares about matching Sky Bet** (their bookie): odds, balance, bets. They notice when numbers don't match.
- **Short, plain answers.** Say what changed, how to see it, and what (if anything) they must do.
- **Design:** dark mode only, keep all artwork and icons, say "Friends" not "mates", UK fractional odds by default, UK times, £.
- **Devices:** an Android phone (app 1.4), a Windows PC with Brave, friends on iPhone. Test at 400 px and 360 px (and 1300 px for layout).
- **Don't run chatty background monitors.** The site updates itself.
- **Never paste secrets in chat** (Supabase secret key, keystore). They go straight into GitHub secrets.

**State of their account at handover:** they were told to set their balance to £8.00 (Profile → Balance → Edit) and change their £1K Elche bet's odds to 2.30 (£1K → tap the odds box). The £1K ladders briefly failed to load because of a bug (fixed, see §11). If they say anything is still missing, write a one-line Supabase `update challenges set data = ... where user_id = ...` for them; their ladder data shape is in §7.

---

## 3. Architecture

```
Phone / PC (site/index.html, one file)
  ├─ every 10 s: live scores, stats, box scores, play-by-play straight from ESPN (CORS *)
  ├─ data.json + logos.json from GitHub Pages (predictions, fixtures)
  ├─ Supabase (supabase-js 2.45.4 from jsDelivr): accounts, bets, ladders, friends, follows, wallets
  ├─ Tesseract.js 5.1.1 (jsDelivr, loaded only when reading a screenshot)
  └─ sw.js: only for bet-alert notifications (no caching)

GitHub Actions
  ├─ update.yml, every 20 min + every push to main:
  │    1. python3 engine/build.py   → site/data.json, logos.json
  │    2. python3 engine/settle.py  → settles finished bets and £1K steps in Supabase (secret SUPABASE_SERVICE_KEY)
  │    3. stamp mde-build meta → publish site/ to gh-pages
  └─ android.yml, on android/** changes: build signed APK → release "app"

Android app (android/): a WebView of the live site, plus the JS bridge window.MDEApp
```

No server of our own. ESPN is free, has no key and is about 1–3 minutes behind TV. Pre-match odds come from DraftKings (US) inside ESPN, converted to fractions. There are no real UK bookmaker prices yet.

---

## 4. Repo layout

| Path | What |
|---|---|
| `site/index.html` | **The whole app** (≈3,500 lines: HTML + CSS + JS). |
| `site/config.js` | Supabase URL + publishable key (public by design; RLS protects data). |
| `site/data.json`, `site/logos.json` | Built by the engine every 20 min. Don't edit by hand. |
| `site/sw.js` | Service worker for alerts only. |
| `site/app.html` | Download page (Android + iPhone steps; Halloween banner in season). |
| `site/img/` | Artwork (webp). `site/img/halloween/` = seasonal versions. `site/img/logos/nba-2.webp` = Celtics Lucky logo override. |
| `art/halloween-originals/` | The owner's original uploads (not deployed). |
| `engine/build.py` | Data engine + prediction model. |
| `engine/settle.py` | Overnight settler (bets, £1K ladders, wallet credits). |
| `supabase/*.sql` | schema, social, badges, wallet, follows. **All have been run on the live project.** |
| `android/` | WebView app (Java, no AndroidX), version 1.4 / versionCode 5. |
| `.github/workflows/update.yml`, `android.yml` | See §3. |

---

## 5. Features and where they live (index.html)

**Navigation:**
- 5 tabs (`NAV`): Live · Games (Fixtures/Tables/News) · Bets (Tips/Accas/My Bets/Stats) · £1K · Friends, plus `#account`, `#perks` and `#stats`.
- Routing is hash-based (`view()`); state is in the global `S`; everything renders through `render()`.
- `render()` only rewrites `#main` when its HTML changed (`MAIN._h`). To force a redraw, set `$("#main")._h = null`.

**Live and Games:**
- **Live:** live cards (`liveCard`), the clock label (`clockLabel`: "Q3 · 6:32 left", "HT"), and a strip for your bets in play.
- **Game page:** `drawerHTML`. Header with short names on phones, win-chance labels above a slim bar (`probBar`), in-play angles, market tables (`marketsTable`: Chance / Price, "Too short" / "Unlikely"), box score and timeline.
- **Tables:** live/kick-off tags (`teamGameTag`); favourite rows use the class `favrow` (NOT `fav`).

**Bets:**
- **Tips** (`viewBets`): "Every game" (`everyGameView`/`gameTip`: Most likely + Bigger price, chance words `chanceWord`, colours `tipColor`) or "Top picks" (`viewTopPicks`/`tiers`).
- **Accas:** pre-match (`viewAcca`) and in-play (`viewAccaLive`).
  - Levels (`RISK`) target the WHOLE acca's odds: Safest < 2.5, Balanced 2.5–4, Bigger 5+.
  - `jointPick` chooses legs together for the best chance in range.
  - `withBundles` adds same-game combinations of up to 3 bets (one per `SG_GROUP`, no team-to-score with its result). Switch: `sgOpt` / `mde:sgAuto`.
  - Manual extras live in `S.accaX` / `S.accaLiveX`, pins in `S.accaPick` / `S.accaLivePick`. The "＋ Add the likeliest extra bet" button and "or choose one yourself" are in `addMoreSel`.
- **My Bets** (`viewMyBets`):
  - live cards (`betCard`) for imported bets (`S.tracked`, localStorage), saved bets (Supabase `bets`) and running £1K bets (orange tag);
  - "To settle" for hand-typed bets, then Settled tiles (`betTile`) that open a breakdown (`betViewSheet`);
  - a balance strip with "if they all land" (`openReturns`).
- **Stats** (`viewStats`): profit chart (`profitChart`, hover `chartPoint`), tables by bet type, legs, odds, sport and month.

**Importing a bet** (`importSheet`, in `#implayer`, built once and refreshed with `impRefresh` so typing isn't interrupted):
- typed text goes through `parseBet`; screenshots through `readShot` (Tesseract on the phone) → `matchLegsIn`;
- bookie wording is mapped to our markets by `marketIn`; team stat bets by `teamStatIn` (`T:` keys);
- the draft is saved in `mde:impDraft`.

**Leg types (the shape is what tracking and settling read):**
- Player: `{sport, gid, side, pid, name, team, stat, target, label, half?}`. NBA stats: PTS REB AST 3PM PRA STL BLK. Football: shotsOnTarget totalShots totalGoals goalAssists foulsSuffered foulsCommitted cards. `half: 1|2` = football first/second-half bet, counted from the play-by-play (`halfStat`).
- Match market: `{sport, gid, k, label, match, kick}`, with `k` from the model markets (1, X2, O25, C8.5, Y3.5, ML1, SP1, …).
- Team stat: `k = "T:<cards|corners|sot|goals|shots|fouls>:<each|home|away>:<n>"`.
- Once settled: `fst: "hit"|"miss"` and `final` are saved into the leg, so breakdowns survive after the game leaves the feed.

**Tracking and settling:**
- `legInfo0`: one leg's state + HTML; `legInfo` wraps it so it's tappable and opens the game.
- `betCard`: the card around the legs.
- `betOutcome`: decides won/lost. It only calls a player bet lost from a box score fetched AFTER full time (`g._postDetail`); first-half legs are decided at half time.
- `autoSettle`: runs from `render` and a 20 s timer. `settleBet` updates conditionally (`.eq("result", prev)`) and re-reads the wallet first, so it can't double-pay alongside `engine/settle.py`.

**£1K challenge:**
- One ladder per sport, stored as `{v:2, football, nba}`. Helpers: `splitChal`, `chalNow(sport)`, `saveChal(C, sport)`. `saveChal` refuses unless `S.chalLoaded`.
- Real returns (`chalPath`), cash out / take money out (`cashSheet`), both-ladders summary (`chalSummary`).
- £1K stakes and winnings move the wallet.

**Balance** (`wallets` table): `walletAdjust(delta)` re-reads the wallet first. Saving a bet subtracts the stake; settling adds `credit()`. It's private unless `is_public`.

**Friends:**
- Feed tiles (`betTile`) with a live status; tap one to see the bet; Copy bet (`data-tail`).
- Top players (`topView`), People and search (`peopleSection`), following (`follows`).
- **Comments** (`supabase/chat.sql`: `comments` table; anyone who can see the bet can comment, delete own or on own bet): `loadComments`, `chatThread` in the bet sheet (`#chatForm`, `data-delcm`), 💬 count on feed items (`socialActs`), open sheet refreshes comments every 10 s. `S.chatReady` is false until the SQL is run, so comment UI hides itself.
- **Copied marks:** copying a bet inserts a `tail` reaction (allowed by chat.sql); shown as "📋 Copied by N" and names in the bet sheet.
- **Feed extras:** `friendsWeekHTML` (top earner, most wins, best odds, last 7 days), `liveFriendsHTML` (friends' bets in play, legs landed + chance).
- **Friends' board periods:** `leaderboard_since(days)` RPC (chat.sql), chips `data-bdays` 7/30/0; falls back to `leaderboard()` if the RPC is missing.
- **Bet categories (audited 2 Nov 2026):** level accas always land in their RISK range (Safest ≤2.5, Balanced 2.5–4, Bigger odds 5+). Game-page "Popular bets" use strict bands: Around evens 1.8–2.5, Around 2/1 2.75–3.75, Around 5/1 5–8, picking the one closest to the named price. Themed accas follow the level (`levelTheme`: tries 2–5 legs per theme, each priced near `target^(1/n)`, keeps the likeliest combo inside the level range, hides the theme if it can't get within ~12%; `mixPick` priced the same way). "Bigger punch" was removed; "Safe four" is now "<Level> four". Multi-sport themes are dropped unless they hold both sports (`multiTheme` → `multiTheme0`). Stats: manual legs count towards legs and type, `T:` keys are "Team stats", mixed-sport bets are "Multi-sport", odds bands are Under evens / Evens to 3/1 / Over 3/1 to 9/1 / Over 9/1.
- **Level minimum leg price:** `RISK[*].minLeg` (Safest none, Balanced 1.2, Bigger odds 1.4), relaxed to `target^(1/n)` for big accas, applied via `riskOpts()` in level/multi presets and the pre/in-play builders (`accaPreLegs`/`accaLiveLegs` wrap `withMinFallback`, which rebuilds without the minimum only if the level can't be hit). The "add the likeliest extra bet" suggestion respects it too.
- **£1K ladder:** one bar per bet (10), each labelled with what you'll have if it wins; amounts under £10 show pennies (`ladderLabel`, `fmtBank` → `money`).
- **Free bets** (`supabase/freebets.sql`: `bets.free_stake`, leaderboards count `stake - free_stake`): helpers `freeOf`, `cashStake`, `betPL`, `winReturns`; a win returns `stake × odds − free_stake`, the free part is never taken off the balance or counted as a loss. Marked via the slip (`#slipfree`), import (`#impfree`, auto-ticked when the text says "free bet"), add-by-hand (`#ab-free`) or later on any of your bets (`data-freebet` button on cards and the bet sheet, which also fixes returns and the balance). `insertBet()` retries without `free_stake` if the column is missing. settle.py subtracts it too. Tag: `FREE_TAG` (`.fb-tag`).
- **Acca leg swap:** every leg row in the builders shows the bet name (`pickBox`; the native select sits invisibly over the name, so tapping it still opens the full list) and a ↻ button (`data-reroll="pre|live|gid|key"` → `reroll()`): next best bet in that game at about the same price (within 1.8×), within the level's minimum, cycling through ones not tried yet (`S.rollSeen`). Other games are pinned first so only the tapped leg changes. The row plays a glow/spin animation (`S._rolled`, `.rolled`).
- **Import pairing:** in `parseBet`, a line that is just a match ("A v B") takes the bet lines directly below it (or above it, if none below) as its legs.
- **You vs friend:** `h2hHTML(uid)` in `mateSheet` (last 30 days).
- **Friend notifications:** `socialPoll()` every 60 s: reactions, comments and copies on your bets, friends' wins, friends' new bets (`apref` keys social, copy, fwin, fbet; fbet off by default). Seen keys in `mde:socSeen`; the first run never alerts.
- Profiles: `mateSheet`, and `profileShowcase` (stats, form, biggest win, badges, teams).

**Profile** (`viewAccount` + `profileView`): grouped setting cards with switches (`setrow`), balance, Theme (Halloween), Alerts, Privacy (share bets, leaderboards, search, public bets), favourite teams. **Plan & perks** page: `viewPerks`.

**Alerts** (`alertTick`, every 15 s):
- events: leg landed / one away / missed / bet settled;
- already-landed legs are not alerted on first sight (`mde:alerted`, `mde:alertKnown`);
- Android uses `MDEApp.notify`; browsers and iPhone home-screen apps use `sw.js`;
- live updates keep running in the background while alerts are on and a bet is live.
- **Kick-off of games in your bets:** `koGames` in `alertTick`, key `ko:<sport><gid>`, pref `betko`, skipped for followed games (they have their own) and for games already 20+ min old on first sight.
- **Timed alerts with the app closed (Android 1.7+):** `natSync` hands `MDEApp.schedule(key, atMs, title, body)` / `unschedule(key)` the 5-minute and kick-off alerts (bets + followed games); `AlarmReceiver.java` (AlarmManager, exact if allowed via USE_EXACT_ALARM, else inexact) posts them. Scheduled keys are marked seen so JS never repeats them; state in `mde:natSched`. Goals/legs/results with the app closed still need the push server.
- **5-minute heads-up:** `soonCheck` in `alertTick` sends one alert per saved/tracked/£1K bet when its first game is ≤6 min from kick-off (pref `soon`, key `<id>:soon`, sent even for just-saved bets).
- **Notifications panel** (`notifSheet`, `S.notifOpen`, opened by `data-notif` from the Live page button and Account → Notifications): master switch (`alertOpt`/`alertOpt2`), per-type choices (`mde:alertPrefs`, `apref(k)`: land, close, miss, result, ko, goal, red, ht, tight, ft) and the followed games.
- **Followed games:** bell on fixture rows and live cards (`bellBtn`, `data-gfollow`), "Notify me" on the game page. Stored on the device in `mde:gfollow`; `gameAlerts()` (called from `alertTick`) compares against `mde:gstate` and sends kick-off, goals (with scorer), red cards, half-time/quarter breaks, close NBA finishes and full-time. First sight never alerts. Follows drop 8 h after kick-off. `followActive()` keeps live updates running in the background too.

**Other:**
- **Account refresh:** `loadAccount()` runs on returning to the app (after 60 s) and every 5 minutes, so Pro, badges and overnight settles appear without a restart.
- **Halloween:** active 17 Oct–7 Nov (UK) unless switched off (`mde:spooky`). `art(name)` swaps image paths; static images use `data-hw`/`data-plain`; an inline script swaps the header/splash before load; `body.spooky` styles the header and badges.
- **Logos:** `LOGO_FIX` overrides ESPN logos (Celtics → Lucky).
- **Share:** phones use the native share sheet (`MDEApp.share` on Android 1.3+, `navigator.share` on iPhone/Android browsers). PCs use our own menu (`shareSheet`: WhatsApp, Messages, Email, Copy link).

---

## 6. Data engine and model (engine/build.py)

- **Sources:** ESPN scoreboards (yesterday to +5 days) for EPL, Championship, UCL, UEL, La Liga, Serie A, Bundesliga, Ligue 1, Scottish Premiership, and the NBA; summaries, standings, last-5 summaries.
- **Football:** Poisson on attack/defence strengths, blended 65% with the market for 1X2 and O/U 2.5. Corners use a normal approximation (variance 1.6 × mean); cards are Poisson.
- **NBA:** point-differential model blended 70% with the moneyline; normal approximations for spreads and totals.
- **In-play (client, `liveMarkets`):**
  - time left includes injury time (`fbLeft`: 2 + 5 minutes);
  - corners and cards blend the pre-match rate with the game's actual pace, plus a late-game boost;
  - in-play prices are shown bookie-style via `livePrice` (`LIVE_MARGIN = 0.85` of fair winnings).
- `--fast` skips logos. The cache is `engine/cache/` (gitignored; Actions caches it).

---

## 7. Supabase

- **Tables:**
  - `profiles`: display_name, avatar_url, fav_teams, plan, badges, friend_code, share_bets, show_on_leaderboard, discoverable, bets_public
  - `bets`: legs jsonb, odds_dec, stake, result, returns, settled_at, placed_at, label, match, sport, kickoff
  - `challenges`: user_id, data jsonb = `{v:2, football:{start,rungs,rung,bank,attempts,started,history[],active,past[],taken}, nba:{…}}`
  - `pro_waitlist`, `friendships`, `reactions`, `wallets` (amount, set_at, is_public), `follows` (follower, followee)
- **RPCs:** `leaderboard()`, `add_friend(code)`, `remove_friend`, `is_friend`, `shares_bets`, `people(ids)`, `search_people(q)`, `top_players(days)`, `bets_are_public(owner)`.
- **RLS:**
  - users can't change their own plan or badges;
  - friends can read each other's bets if `share_bets`; anyone signed in can read `bets_public` bets of discoverable users;
  - **so any "my bets" query must filter `.eq("user_id", uid)`** (see §11);
  - wallets are private unless `is_public`.
- **Give Pro / badges** (the owner runs this; friend code from the profile):
  `update profiles set plan = 'pro' where friend_code = 'ABC123';` (and `badges = array['dev']` for DEV). Reverse with `'free'`.
- **Settings:** confirm email OFF; Site URL / redirects `https://snuzzyyy.github.io/matchday-edge/**`.
- **Keys:** the publishable key is in config.js; the secret key is only in the GitHub secret `SUPABASE_SERVICE_KEY`. **Claude never sees it and must never ask for it in chat.**
- **SQL testing:** a local Postgres 16 exists in the sandbox. Start it as the postgres user in `/var/lib/postgresql/<dir>`, stub `auth.users` (with `email`, `raw_user_meta_data`) and `auth.uid()` via `request.jwt.claim.sub`, then load all `supabase/*.sql` and test as `set role authenticated`.

---

## 8. Android app

- **Version 1.4 (versionCode 5),** signed with the **permanent key**: secrets `MDE_KEYSTORE_B64` + `MDE_KEYSTORE_PASSWORD`; the owner keeps a private backup.
- **Updates install over the top.** Bump `versionCode` every release.
- **The build fails on purpose if the key secret is missing.** Never commit a keystore.
- **JS bridge `window.MDEApp`:** `share(text)`, `notify(title, body, tag)`, `canNotify()`, `askNotify()`. Downloads open in the browser. The photo picker handles ClipData. The user agent ends in `MatchdayEdgeApp/1.4`.
- **Rebuild:** change `android/**` → push → wait for `android.yml` → download from release `app` → copy into `site/MatchdayEdge.apk` → push. Check the signature (the APK contains the permanent cert) and the version string.
- **Only rebuild for wrapper changes.** Everything else is a website change.

---

## 9. How to work on it (proven method)

1. **Clone:** the repo is attached (push access). `git pull --rebase origin main` before work; **another chat sometimes pushes too**, so expect rebase conflicts.
2. **Edit `site/index.html` with small Python scripts** that `assert s.count(old) == 1` before replacing. The file is big; never rewrite it wholesale.
3. **Syntax check after every change:**
   `node -e "const s=require('fs').readFileSync('site/index.html','utf8');const m=s.match(/<script>([\s\S]*?)<\/script>/g);new Function(m[m.length-1].replace(/<\/?script>/g,''));console.log('ok')"`
4. **Local server:** run `cd site && exec python3 -m http.server 8769` with Bash `run_in_background: true` and `timeout: 7200000`. A plain `&` server dies between calls.
5. **Playwright** (Chromium preinstalled, `require('playwright')`):
   - **Route ESPN through curl** (the sandbox proxy blocks browser fetches):
     ```js
     await ctx.route('https://site.api.espn.com/**', r => r.fulfill({ status: 200, contentType: 'application/json',
       headers: { 'access-control-allow-origin': '*' },
       body: require('child_process').execFileSync('curl', ['-s','--compressed','-m','20', r.request().url()], { maxBuffer: 64e6 }) }));
     ```
     Do the same for jsDelivr/Tesseract when testing screenshot import (worker, wasm and language data).
   - **Mock Supabase:** route `**/supabase-js@*/**` to a small mock defining `window.supabase.createClient` with:
     - `auth.onAuthStateChange` (call back with SIGNED_IN);
     - a `from(table)` chain (`select/eq/in/order/limit/maybeSingle/single/insert/update/upsert/delete/then`). **Update must support `.eq().eq().select()`**, because `settleBet` uses a conditional update.
     - `rpc(name, args)` and `storage`.

     Put tables in a `DB` object (profiles, bets, challenges, wallets, follows, …). The old mocks lived in the session scratchpad and are gone; write a fresh one.
   - **Screenshot** at 400 px and 360 px, plus 1300 px for layout. Look at the screenshots before publishing.
   - **Expose internals** for unit tests with a throwaway copy: `dbg.html` with `window.__T = {fn1, fn2}` inserted before the final `})();`. Delete it afterwards and never commit it.
6. **Commit** as `snuzzyyy <337362346+snuzzyyy@users.noreply.github.com>`, then `git pull --rebase origin main && git push origin main`. Pages redeploys in about 1 minute.
   - Verify: `curl -s "https://snuzzyyy.github.io/matchday-edge/?x=$RANDOM" | grep <new-function-name>`.
   - Start a workflow run by REST: `gh api -X POST repos/snuzzyyy/matchday-edge/actions/workflows/update.yml/dispatches -f ref=main`. (`gh workflow run` fails: GraphQL is blocked.)
   - Read a job log: `gh api repos/.../actions/jobs/<id>/logs`.
7. **Users get updates within ~3 minutes** (self-update via the `mde-build` meta), or on reopen. Self-update is skipped while typing or importing.

**GitHub from the sandbox:** REST works (runs, releases, dispatch, logs). Secrets can't be written (403), so the owner adds them. GraphQL is blocked.

---

## 10. Known limits and ideas (backlog)

- No real UK prices or Sky Bet slip links (needs a paid feed, see §0.4). Sky bet IDs can't be looked up.
- Alerts can't reach a fully closed app (that needs a push server). The overnight job settles but doesn't notify.
- **Push server: owner said "later" (2 Nov 2026).** Plan agreed: free. A Supabase Edge Function runs every minute via pg_cron and checks bets plus followed games (would need `gfollow` and alert prefs synced to Supabase). It sends through Firebase Cloud Messaging for the Android app (needs an app rebuild) and Web Push/VAPID for browsers and iPhone home-screen apps. Owner steps: create a Firebase project, add a Supabase secret, run one SQL line. Don't start until they ask.
- ESPN is 1–3 minutes behind TV. The play-by-play can lag and sometimes revises or removes events.
- Football props in the builder: not yet. Football first-half bets track from the play-by-play only.
- Ideas the owner liked but hasn't asked for yet: group leagues, safer-gambling limits, more leagues (League One/Two, Eredivisie, Portugal), a push server.

---

## 11. Lessons learned the hard way (read before editing)

1. **Never put a `//` comment in the middle of a line of code.** A note added after `S.bets = …;` swallowed `S.chalAll = …; S.board = …` on the same line, and the owner's £1K ladders "disappeared". Use `/* */` or a new line, and re-read the edited line.
2. **CSS class-name clashes:** the file already uses `.fav`, `.statrow`, `.chev`, `.soon`, `.links` and more. **grep a class name before adding it** (`grep -cE "\.name\b"`). Clashes broke the tables, the profile rows and the perks page.
3. **"My" queries must filter by user:** RLS lets friends and public bets through, so `from("bets").select()` returned friends' bets into My Bets.
4. **`render()` runs every 10 s.** Anything people type into, or pick files with, must live outside `#main`/`#layer`:
   - the import sheet → `#implayer`
   - cash-out → `#cashlayer`
   - photo and screenshot pickers → persistent `<input>`s in `<body>`
5. **Don't settle from stale data:** player legs only lose from a box score fetched after full time; finished-before-open games fetch final stats (`loadDetail` re-renders).
6. **The feed lists each foul twice** (once per player). Dedupe plays by `play.id`.
7. **Names:** `norm()` handles accents and Ø/æ/ß (`deLetter`). Match players by full name or by surname + first initial.
8. **Bookie prices are shorter than fair.** In-play we show `livePrice`; pre-match uses the DraftKings price or fair. Expect the owner to compare with Sky.
9. **Mid-turn images aren't saved as files.** Ask for a resend, or a GitHub upload.

---

## 12. Quick reference

| Request | Where / how |
|---|---|
| Give Pro / badge | SQL in §7 (the owner runs it); the app picks it up within 5 minutes or on return |
| Add a tab or sub-page | `NAV` + `SUBNAME` + `view()` + the `render()` switch |
| Colours | `:root` tokens at the top of `<style>` |
| Add a league | `LEAGUES` in `engine/build.py` |
| Seasonal art | `site/img/halloween/` + `HW_ART` + `art()`; dates in `HW_SEASON` and in the inline splash script and `app.html` |
| Team logo fix | `LOGO_FIX` (+ an image in `site/img/logos/`) |
| Acca levels | `RISK` (lo, hi, target) |
| New stat for imports | `PROPS` (regex, stat key, label) + `legValue`/`halfStat` + `engine/settle.py` |
| New team stat bet | `teamStatIn` / `teamStatVals` / `TSTAT` + `engine/settle.py` (`T:`) |
| Rebuild APK | §8 |

## Bet cards (My Bets, bet sheets, £1K)
- Legs are grouped by game (`legGroups`): one header per game (badges, match, kick-off countdown `untilTxt`, or live score + clock), then one line per bet (`legLine`): status dot, bet, its own % chance (owner likes this), and while live a thin progress bar + "8 / 9 corners · 1 to go" parsed from `legInfo0`. Typed-in legs and games that left the feed keep the old rows.
- `betCard` header: "Starts 19:45 · in 3h" before, red-dot "x of n landed" live; `.segbar` shows each leg's state (pulses while live).

## Game page ready-made accas
- `gameAccas(opts, price)` (bands in `GA_LEVELS`) builds Low / Medium / High bet builders per game. `gaPicks` caches the pre-match picks in `mde:ga` so the same three are tracked once the game starts (`gaTracked`: leg lines, segbar, chance now; finished games show the result). Overview is one wide column (`.ovw`).
- My Bets: Live / Upcoming / Settled tabs (`S.mbTab`, `data-mbtab`).

## Update timer (Nov 3)
- GitHub's own cron for update.yml is unreliable (often hours apart). The owner set up cron-job.org ("Accabox update", every 15 min) to POST `https://api.github.com/repos/snuzzyyy/matchday-edge/actions/workflows/update.yml/dispatches` with body `{"ref":"main"}` and headers Authorization: Bearer <fine-grained token, matchday-edge only, Actions read & write>, Accept: application/vnd.github+json, Content-Type: application/json, User-Agent: accabox-timer. Runs show as event `workflow_dispatch`. When the token expires, the owner makes a new one and pastes it into that header. Never ask for the token in chat.
- The cron-job.org job runs every 2 min. update.yml's first step checks the published data.json age: under 13 min → settle only (no build, no Pages publish; Pages allows ~10 builds an hour); otherwise the full build. Pushes always do the full build.

## Bets tabs and Bet checker
- Bets sub-tabs are Tips · Accas · Checker · My Bets. Multi-sport is reached from the Accas header button, Stats from My Bets → Settled; `NAV_ALIAS` keeps the tab highlighted for them.
- `#check` (`viewCheck`): parses with `parseBet`; each leg's chance via `chkLeg` (match markets → `legChance`; player props → the player's model line, else `CHK_PRIOR`, combined for `foulInvolvements` / `goalOrAssist`, halves ×0.46/0.54, live → `paceChance`). Fair odds = 1/p; with typed odds, value > +10% good, ±10% fair, below poor. "Track this bet" opens the import pre-filled. `render()` now keeps focus/caret in #main inputs.
- Ready-made source tag: legs added from a game page acca (`data-gbb` 5th part = level) or an Accas-page preset (`data-ptitle`) carry `src`; `betSrc()` shows "📦 Medium acca · A v B" on the bet card, and recognises older copies by matching the game's `gaPicks` legs.
- Edit a saved open bet: ✏️ Edit bet (`editBtn`, card foot + bet view) → import sheet with `S.impEdit` and `betToText(b)` (one leg per line); Save updates the row in place and moves the balance by the stake change.
- Import: combined player stats (`combo:a,b`, e.g. "combine for 8+ shots & foul involvements") are summed in `legValue`/`chkLam`/settle.py. "Away Over/Under 0.5 Goals: Over" → "<team> to score". OCR odds that lose the dot ("@136") read as 1.36. `SKIP` is now only "12" (Over 0.5 goals is allowed in picks).
- Both teams to score legs: one bar, half full per team that has scored, with "Needs <team> to score".

## Streamline pass (Nov 6)
- Fixtures: one day at a time (`data-fxday`, `S.fxDay`) instead of the whole week. Live "Up next" = next 4 + "All fixtures ›".
- Accas page: one `.acca-panel` card at the top (Pre-match / In-play / ⚽+🏀 multi-sport via `data-gomulti`, level, day chips on one swipeable line); Ready-made accas first (no second set of day chips); "Build your own" (pick best 3/5, same-game option, your acca, game list) below; themed accas folded in a `<details class="maths">`.
- £1K: the "Step N · no bet picked yet" box is hidden when the picks are right below; The maths is folded.

## Import + speed (Nov 7)
- `skyText()` turns Sky's copied slip ("Selection / Market - A @ B / 1.14") into "A v B: Selection to win @ 1.14" (NBA "@" becomes "v" so it isn't read as odds); "N Fold @ 40.68" is taken as the slip total and dropped as a leg.
- `fixManualLegs()` (every 30 s): open bets with "you mark this one" legs are re-read with `parseBet`; legs that now match switch to tracking and the bet is updated.
- Every open bet of yours has "💷 Update returns" (`data-retbet` opens an inline box, `data-retsave` sets odds = returns ÷ stake); it turns amber "⚠️ Void leg · update returns" when a leg is void. Edit bet also has a "Returns £" box. Legs you mark yourself have Landed / Lost / Void.
- Already tracked: saving a bet whose legs match an open saved or tracked bet first turns the button amber ("Already tracked · tap again to add it twice", `S._dupOk`); a second tap saves it.
- Save buttons (import and slip) lock with "Saving…" until the save finishes (`S._saving`), so repeated taps can't save the same bet many times.
- `findGame` uses an id index and `mkt` a per-game Map (both WeakMap caches), as the extra games made the old scans slow.

## Funded tab (Nov 7)
- `#funded` (`viewFunded`), nav tab "Funded". "📥 Import bets from BetPro": paste or screenshot (`fundedParse`: each bet is found by its game line; My Bets layout "Market · A vs B" with the selection above, or bet-slip layout with the game on its own line, market above, selection (and price) above that; slips have no stake, so they are listed but not added; player "X Assists and Rebounds Over/Under N" → over/under player leg; stake/returns/odds/status; "Returns" without "Potential" = settled; odds = returns ÷ stake). Screenshots are read twice (`shotToCanvas(f, 3000)` and the `crisp` threshold version) and the one that finds more bets wins. Match winner, totals and full-game handicaps get a live leg; halves/first-to-score keep BetPro's result. Duplicates (same text, stake, time) are skipped. Fully separate from My Bets and the wallet: funded bets never appear in My Bets, counts or the main balance; liveTick still refreshes their games every round. Bet picker (`fundedPicks`): Low odds 1.25–1.7, Medium odds 1.7–2.6, High odds 2.6–6; Football / NBA / Both; singles in the next 24 h, one per game, at most 2 of a kind, best expected return first, ↻ shuffles; tapping one opens a small drop-down (`S.fpOpen`, `.fp-drop`) with odds (prefilled) and stake; Enter or Add saves it (`data-fpadd`). The free-text form is folded away as "Add a bet that isn't listed" (Enter submits there too). A funded-betting evaluation (owner uses BetPro IQ): start £125, target +40% (£175), singles only (`parseBet` > 1 leg is refused), stake can't exceed available balance. Saved inside the £1K `challenges` row as `S.chalAll.funded` (`fundedSave` → `saveChalAll`), so it's on every device with no SQL. Bets track live via their leg and settle themselves (`fundedAuto`), else Won/Lost/Void buttons; settings (name, start, target %) and "Start a new evaluation" (old ones kept in `funded.past`).

## Fold / tablet layout (Nov 7)
- @media (min-width:600px) (the unfolded Fold is ~690 CSS px): My Bets `.trk` becomes 2 columns (CSS columns, cards don't split), 3 from 1500px; game page `.g-cols` two columns from 700px (was 1100). Other grids (live cards, tips, presets, ready-mades) already auto-fill.

## Notifications inbox (Nov 7)
- 🔔 in the header (`#inboxBtn`, `data-inbox`) next to the account button: every `toast()` and `sendAlert()` is saved by `logNote()` (localStorage "notes", last 40; alerts marked 🔔). Red count = unseen since "notesSeen". The sheet lists them newest first with times; "Clear all". (Game-follow bells are a different thing: `bellBtn`.)

## Live speed (Nov 7)
- `playerIndex(full)`: light by default (priced player bets, box scores, line-ups: no downloads). Squad lists (ESPN rosters, ~37 MB for all teams) only via `playerIndexFor(text)` when a typed name isn't found, or when reading a screenshot. Never call `playerIndex(true)` on page load.
- `isOlder()` / `gameProg()`: applySB and applyHeader ignore a score/clock that is behind what the app already shows (the game-details copy can lag the scoreboard), so scores never jump backwards.
- liveTick: no `soccer/all` scoreboard (860 KB); track-only games refresh through their own summary only when in your bets. Full game summaries every round only for games in your bets / followed / open; others once a minute. `getJ` aborts after 6 s; a 20 s watchdog clears a stuck round. A phone now pulls ~0.4 MB per 30 s instead of ~40 MB.

## Half-by-half team bets (Nov 7)
- NBA `nbaTeamPts()`: "each team to score 55+ points in each half" → `T:hpts:each:55`; also `pts` (game), `h1pts`/`h2pts`, for each/home/away. Tracked from `g.home/away.lines` (quarters); settle.py uses summary header linescores.
- Football `fbHalfGoals()`: "both teams to score in both halves" → `T:hgoals:each:1`; "X to score in both halves / 1st half / 2nd half" (`h1goals`/`h2goals`). Tracked from `g.events` goal minutes (≤45 = 1st half); settle.py uses keyEvents period numbers.
- legChance returns null for these (no made-up chance).
- Player unders: "Luka Doncic under 35.5 points" → leg `under: true, line, max` (35); lost once over, landed at FT; legChance = 1 − over chance; settle.py flips the over result. LEG regex lets "under/over N" start the bet part. `nbaTeamPts` ignores a team alias with words before it unless they are the other team (P.J. Washington ≠ Washington Wizards).
- Any Over/Under line (incl. Sky's "Over +208.5 Total Points"): `ouAny()` in marketIn → `OU:o|u:line:unit`, label "Over 208.5 points"; tracked and called from the score in legInfo0; settle.py handles `OU:` (goals/corners/cards) and NBA points by label. Team totals only when the team is named before "over" (not "A v B over …").

## Ready-made cards (Nov 6)
- `pLegs()` / `legIcon()`: each leg on a ready-made card is a row with an icon: ESPN headshot (combiner, team badge in the corner, falls back to the badge) for player bets, the team's badge for team bets, both badges for match bets.
- `playerAvail()`: NBA injuries (Out/Doubtful/Suspended) and NBA.com line-ups (`g.lu` out), football confirmed line-ups (not in squad = out, sub = bench). `legOptions` drops out players (and football subs), so ready-mades, swaps, Add a leg, £1K and the bot never pick them. Ready-made player legs show `playerTag` (Starting / Expected / Off the bench).
- Game-page ready-mades: "＋ Add a leg" (`data-gaadd`, `S.gaAdd`) appends the likeliest non-clashing bet in that game, "Undo" removes the last; odds and Add to slip include them.
- Swap a leg: each leg on a ready-made card has a ↻ (`data-pswap`); game-page Low/Medium/High accas too (`data-gaswap`, `S.gaSwap`, same game only, odds recalculated). `S.pswap[swKey(id)][slot]` lists ruled-out bets; `applySwaps` picks the next best (`altLeg`: same game or another game, closest price, likelier first) for cards and for `presetLegs` when loading the slip. New leg flips in (`.pl-new`). Cards are `div role=button` now (no button-in-button).
- Ready-mades now include Five-fold and Six-fold (shown only when they fit the level's odds range).
- PC: the Accas control panel is two rows (type + level side by side, chips below) via `.acca-panel:has(> .acmode)`.

## Winners-only accas (Nov 6)
- "🏆 Outrights" chip (was "Winners only") on Accas and Multi-sport (`S.winOnly`, saved): `legOptions` keeps only `WIN_KEYS` (football 1/2, NBA ML1/ML2), so ready-mades, Build your own and multi-sport use straight winners at the chosen level; titles read "Balanced outrights treble"; themed accas/mixes hidden while on.

## Live pitch (Nov 6)
- `livePitch(g)`: first section on a live football game (Overview and Stats tabs). Uses ESPN commentary positions (`fieldPositionX/Y`, kept on `g.plays` as x, y, x2, y2, tid = team id or name, clk, txt). Positions are from the acting team's view, so away actions are flipped (home attacks right). Ball at the latest action with a pulse, trail of the last 5, shot line, box flashes on danger, "Pressure" bar = share of the last 12 actions. Not true ball tracking (that's a paid feed); it moves on each action, refreshed every 10 s.

## Every game tracked (Nov 6)
- Cup ties where neither club is in a covered league (e.g. Coupe de France in French Guiana) are skipped in football() (not priced by UK bookies); football_extra() still keeps them for imports.
- LEAGUES now include the cups: FA Cup, Carabao Cup, EFL Trophy, Conference League, Scottish Cup and League Cup, Copa del Rey, Coppa Italia, DFB-Pokal, Coupe de France (full games: tips, accas, props).
- `football_extra()` adds every other game from ESPN's `soccer/all/scoreboard` (yesterday to +2 days, ~500–700 games, league "all", `lite: true`, model at league-average strength, no corners/cards) as `data.extra`. Client: `anyGames()` / `findGame` / `gamesInText` / `oneTeamGame` / liveTick use them; `games()` (tips, fixtures, accas, bot) does not. settle.py's GAMES includes them. Summaries work under `soccer/all/`.

## Import fixes (Nov 6)
- `matchLegsIn` normalises accents (NFD) so "Alavés" matches. `marketIn.pickTeam` falls back to counting team names with spaces removed (OCR "Derb y").
- `readShot`: Sky slips' "Full Time Result - A v B" for games we don't cover become manual legs ("A v B: X to win"); the slip total is read from "N Fold … Odds 195.25"; Sky's price-drop arrow (OCR "V"/"Vv") and "✕" are stripped.
- Player legs: `sportOf(rest)` limits the lookup to football or NBA by the wording (no more footballers matched to NBA surnames). "X v Y" lines we don't cover never swap in another game; they're saved as manual legs.

## Makeover (Nov 6, part 2)
- Every page opens with one `.acca-panel` control card (Tips: Every game/Top picks + days; Fixtures: leagues + days; Accas; Feed: Up next/Winners + one line); page titles/intro lines removed where the tab already says it.
- `fixtureBlocks`: one card per day, leagues as thin `.lg-sub` labels inside (no box per league). Fixtures shows one day (`fixtureBlocks(…, false)`, no repeated day heading).
- Live: no £1K promo strip (it has a tab; `promo()` now unused), no intro line, "+ Track a bet", slim `.idle-line` instead of the "Nothing in play" box.
- Feed posts: the inner acca box is flattened (`.fi.bot .bot-card`).

## Feed tab (Nov 6)
- Nav: Live · Games · Bets · £1K · Feed (`#feed`, `viewFeed()`). Only Accabox posts: "Up next" = the Low/Medium/High `gaPicks` for the next 6 games within 24 h (Add to slip via `data-gbb`, so bets get the source tag); "Winners" = `bot_accas` won in the last 7 days (`loadBotWins`, refreshed every 5 min, needs sign-in). No other users' posts.

## Social (was Friends) — SWITCHED OFF (Nov 6, owner: "for future updates"). `SOCIAL_ON = false` hides the tab, sends #friends to Live and hides the Friends link in Account; all code kept. Set it to true to bring it back.
- Nav label "Social". Tabs (`S.friendTab`): Timeline (`feedView("timeline")`: `S.feedBets` + `S.pubBets` (unfiltered bets query; RLS returns public ones) + Accabox bot winners), Friends (friends' feed, week, live, £1K), Leaderboards (`S.lbScope` friends → `boardView`, everyone → `topView`), People. Posts render via `feedPost`; one centred column (`.soc`).
- Declutter (Nov 2): Live results are one-line `resRow`s (8, then "Show all"), compact idle box, iPhone install tip only on Live, £1K banner only before the first challenge, 4 suggestions, 4 locked badges.
- Player bet legs show `playerTag()`: pre-match Starting / On the bench / Not in squad (line-ups fetched within 90 min of kick-off), live On pitch / On the bench / Subbed off / Sent off; NBA On court / On the bench.

## Accabox bot (feed)
- `supabase/bot.sql`: `bot_accas` (id `day|sport|level|n`, legs, odds, chance, result). Only `result='won'` rows are readable by users; owner/dev can read all. Inserts only via `bot_snapshot(rows)` (owner/dev badge, first save wins).
- `botSnapshot()` runs in owner/dev apps every 15 min: for every game kicking off in the next 36 h, the game page's three accas (`gameAccas`: Low evens–6/4, Medium 6/4–4/1, High 5/1+; id `day|sport|gid|level`). settle.py `settle_bot()` settles them with `outcome()`; unsure after 3 days → void. Feed (`loadSocial` → `S.botWins`, last 4 days) shows winners as Accabox posts (`botPost`).
- Tweet maker → Previews & recaps → Preview: "Betting picks" chip (`T.bets`) off = no picks/prices/18+, shows win chances, form/records, venue. `.tw-games` keeps its scroll on redraw.
- Tweet maker → Preview: tick several games (or All); `twMulti`, `T.pick`; card type "previews" (up to 6 games, "+N more in the thread"), tweet is one line per game with our likeliest pick, threaded if long.
- NBA logos: all 30 primary badges from the NBA site (cdn.nba.com) saved as `site/img/logos/nba-<espn id>.webp`; `LOGO_FIX` (UI) and `nbaLogoFix` (tweet images) use them instead of ESPN's. Tweet preview image: teams centred with badges, "@"/"V", league · time under.
- Accabox profile (SWITCHED OFF Nov 2 at the owner's request; nothing opens it): was tap the bot's name/avatar on a Timeline post (`data-botprof`) → `botSheet()` (loads settled rows via `loadBotAll`, last 60 days): record, profit at £10 a go, biggest winner, form, Low/Medium/High and sport table, recent results, "How Accabox works". Needs the policy "bot results are public" (`result <> 'open'`) from bot.sql; owner/dev already see everything.
- £1K picks (`challengeOptions`): Next 24 hrs / Today only (`S.chalWin`), every market incl. player props, at most one of each kind (`chKind`), max 4 per sport; refresh button (`data-chalshuffle`, `S.chalSeed`) draws a new random set from the top 5 of each kind.
- settle.py now also settles NBA handicap legs ("Celtics +5.5 handicap", "Pacers -4.5").

## Tweet maker (owner only)
- `#tweets` (`viewTweets`, link in Account only when `isOwner()` = profile badge `owner`). Sport (football/NBA/both), type (`TW_KINDS`: top performers, results, one game recap/preview, player spotlight, acca of the day, live now), window, game picker, style toggles.
- `twBuild()` writes the text from real data: NBA box scores (`g.box`), football goals from `g.events`, assists/shots/saves after "Load player stats" (`loadDetail` → `g.lineups`), previews from `g.model`, accas from `levelPreset`. Fits to 280 (`twLen`, emojis count 2) by dropping weakest rows / question / hashtags; results become a numbered thread. Editable text, Copy, Post on X (intent link).
- `twCard()` draws a 1600×900 PNG card on a canvas (brand colours, `mark.png`). `twSaveImage()`: Android app 1.6+ uses the bridge `MDEApp.saveImage(b64, name)` (MediaStore, Pictures/Accabox) and `MDEApp.shareImage(b64, name, text)` (share sheet with picture + tweet text); browsers use Web Share with files on phones, else a download. `APP_LATEST` drives the in-app Update banner.
- **Badges:** 23 in `profileShowcase` (earned first, locked with progress, "Show all" via `S.allBadges`).

## Rename to Accabox (2 Nov 2026)
- Name shown everywhere is **Accabox** (header wordmark `Acca<b>box</b>`, title, manifest, share texts, download page, Android label from app 1.5).
- Unchanged on purpose: the repo/URL `snuzzyyy.github.io/matchday-edge`, localStorage keys `mde:*`, the Android package `com.snuzzyyy.matchdayedge`, the user-agent token `MatchdayEdgeApp/1.x` (the site detects it), secrets `MDE_*`. Changing any of these breaks installs or saved data.
- The release publishes both `Accabox.apk` (download page links here) and `MatchdayEdge.apk` (old links).
- Splash (normal + Halloween), og.png and the download banners were re-lettered; originals are in `art/brand-originals/`.

## Funded: winner accas + two tabs (Nov 2026)
- The funder allows accas of **match winners only**. Picker has a Singles / Winner accas switch (`S.fpType`); `FA_BANDS` low 1.9–3.2, medium 3.2–6.5, high 6.5–18; `fundedAccas()` combines the best winner market per game (2–5 legs). Adding by hand allows several legs only if all are `WIN_KEYS`. `fundedAuto` settles multi-leg (any miss = lost, void legs drop out).
- Funded page has two tabs under the balance card: Bet picker / My bets (`S.fdTab`). My bets = open bets, Import / Add by hand buttons (`S.fdPanel`), history, settings.
- Don't show the funder's name anywhere (owner's request): default name is "Funded account" and `fundedNow` replaces any saved name containing "BetPro".
- Pasting/dropping a screenshot while on #funded goes to `fundedShot` (Funded import), not the main Bets drawer. A funded slip pasted into the main Bets import (`looksFunded`) shows "Add it to Funded" instead of guessing legs.
- Half and quarter handicaps track live: leg key `T:(h1|h2|q1..q4)hc[3]:home|away:line` (3 = three-way "Home Draw Away with Handicap", a tie loses; else a tie is void). Built in `fundedParse` from "X (-4)" + a market naming the half/quarter; shown in `legInfo0`; settled in settle.py (void legs there leave the bet open). Funded bets saved before a market was trackable are re-linked once in `fundedAuto` from their text.
- Funded open bets render with the My Bets `betCard` (+ Won/Lost/Void/Delete row). Handicap legs show the margin like Unders: "74–46 · Nuggets win by 9+ · 19 to spare" (full-game spreads use the bet's own line from `l.label`, not the market's current line). `T:fthc[3]` = full-game (regulation) handicap; the Funded card has a "Track as full game / 1st half" switch (`data-fdhc`) because the owner says BetPro's "1st Half (Ordinary Time)" wording was on a full-game bet.
- Handicap legs show a row per team (`hcRows`: "74 − 8.5 = 65.5 pts" vs "46 pts", with bars); `legLine` keeps `.hc-rows` like `.tl-teams`.
- Funded balance = start + settled P/L − open stakes (the account's cash); a win pays stake × odds back. Target progress uses settled profit (`X.eq`, "N% of the way · £X profit to go").
- Funded "My bets" has Live / Upcoming / Settled tabs (`S.fdbTab`, same look as the Bets page); every bet, settled too, is a `betCard` (`fdCard`) with Won/Lost/Void or Reopen/Delete underneath.
- Funded picker: Today & tonight (until 6am, default) / Next 24 hours switch (`S.fpDay`, `fpInWindow`). The stake drop-down opens as an overlay under its card so the grid never moves.
- Bet cards (`legLine`) show the player photo (`legIcon`) next to NBA player legs only (owner: football badges looked odd), on Bets and Funded. Ready-made accas use CSS columns (`.presets{columns:290px}`, break-inside:avoid) so cards pack with no gaps; odds row right under the legs. Owner disliked both stretched cards and gappy grid rows.
- Bet slip legs have a ↻ swap (`data-slipswap`) and the header has "Refresh all" (`data-slipall`), both via `slipSwapAt(i)`: uses `altLeg` (same game first, then a similar price elsewhere), remembers what was swapped out in `S.slipEx`.
- Slip legs show the player's status (`playerTag`); NBA pre-game `playerTag` now checks `g.injuries` first ("Out tonight" / "Doubtful"), with "Tap ↻ to swap it". Slip swap works on unpriced legs (falls back to the leg's own odds). Slip clears after Save to My Bets.
- `dayWord`: between midnight and 6am UK, "Tonight" = games before 6am today; today's later games say "Today"; the next night's after-midnight games use the weekday ("Mon 01:00").
- Funded Stats tab (`fundedStatsHTML`): balance-after-each-bet SVG line (sized to the screen, hover tooltip via `data-fstips`), pass-mark line, 8 tiles, last-12 form, breakdowns by bet type / odds / sport, and `fundedHistoryHTML` (past challenges, best ⭐, pass rate).
- Stages: `F.stage` 1 = evaluation (demo money, +target% to pass) / 2 = funded (real money, no target). Stepper above the hero; "Start Stage 2" appears once passed (archives Stage 1 into `F.past` with `passed`). When the balance hits £0 the hero offers a new challenge (`data-fdnew`: type balance + target %), also under Account settings. `F.past` keeps 30.
- NBA clock ticks smoothly between feed updates: `clockLabel` keeps a per-game model in `CLK` (own display time `disp`; on a new feed value it only jumps if the feed is >1.5s lower or >6s higher, otherwise carries on; never more than 12s ahead of the feed; stops after 16s of the same clock). A 250ms interval swaps just the clock text (TreeWalker), no full re-render. Tested with a jittery feed: no skips, no going backwards.
- Funded cards have no manual marking (owner: "I never want to mark bets myself"): tracked bets settle themselves; untracked ones fill their result when re-imported from BetPro. Funded import: a bet that's already in (same legs via `legSig` + same stake, or same text) is updated to BetPro's exact odds/result instead of being skipped or duplicated. Funded bets with no live link show the market and game ("Indiana Pacers · First Team To Score / Indiana Pacers v Denver Nuggets") and their result.
- Live tick: scores/clocks render right after the small scoreboard fetch; the heavy per-game summaries (300-400KB each for live NBA) run in the background with their own busy flag (`S._sumBusy`, 20s watchdog) and re-render when done, so a slow summary never freezes the clock or blocks the next tick. Bet games' summaries every 8s, others every 60s.
- Funded card: "Open bets / If all land / Account at" row (stake, profit and returns if every open bet wins, the balance and % of target it would make) and a faint green section on the progress bar showing where you'd land.
- ESPN's NBA clock sometimes sticks at "0.0" mid-quarter (or before a quarter starts) while plays carry on. `periodStart` (in `applySB`/`applyHeader`) then uses the latest play's clock from the summary (`_fix`), keeps it for scoreboard updates, or shows the full quarter at a period change; `gameProg` ranks a bare 0.0 as the start so the right clock isn't thrown out. NBA.com's live JSON (cdn.nba.com) returned 403 from the cloud container; it would need the server.
- Combined player bets (PRA, points + assists, any `combo:`) show one line per stat under the main bar (`cbRows`, `.pr-rows`, kept by `legLine`).
- Funded cards have Edit (odds / stake / returns, Enter saves). Changing only the returns works the odds out from it (to match the bookie to the penny).
- Sky "Super Sub" (football player legs): `parseBet` strips the phrase and sets `l.ss`; `legValue` adds the replacement's numbers once he's subbed off (`subFor` from ESPN `subbedOutFor`); card tag "⇄ Super Sub: <name>"; settle.py does the same.
- Ready-made accas: category chips (Accas / Same game / Themed, `S.pcat`); on phones (≤600px) each category is a sideways swipe row (`.pscroll`, scroll-snap, scroll kept across redraws). "Build your own" has its own Safest/Balanced/Bigger odds switch (`.byo-risk`), same `data-accarisk`.
- Funded picker third type "Pick a game" (`fundedGameHTML`, `S.fpType === "game"`): games in the window (Today/24h, sport); open one (`S.fpGame`) to see its bets grouped Result / Totals / Handicaps / Players / Other, 6 each with "Show all" (`S.fgMore`); tap → same stake drop-down and `data-fpadd` as Singles.
- Super Sub without typing it: import preview shows a "Super Sub" tick on each footballer (`data-ssleg`, `S.impSS`, flips `l.ss` in `impParse`). Cards show a yellow Super Sub badge (`SS_ICON`); once he's subbed off, Sky-style: name struck through, green-up/red-down arrows (`SUB_ARR`), replacement in bold.
- Bet card game headers (started games) are a mini scoreboard (`legGroups`: `.lgg-sb` two rows badge / name / score, leader bold; clock and league on the right).
