# Matchday Edge: handover

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

**Matchday Edge** is a UK sports-betting companion app for **football (14 leagues incl. League One/Two, Eredivisie, Portugal, MLS) and the NBA**, built for the owner (GitHub **snuzzyyy**, display name **Snuzzy**, friend code **690481**) and their friends.

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
- **Bet categories (audited 2 Nov 2026):** level accas always land in their RISK range (Safest ≤2.5, Balanced 2.5–4, Bigger odds 5+). Game-page "Popular bets" use strict bands: Around evens 1.8–2.5, Around 2/1 2.75–3.75, Around 5/1 5–8, picking the one closest to the named price. "Bigger punch" is four legs at 1.66–2.65 each, one per game, max two of a kind. Multi-sport themes are dropped unless they hold both sports (`multiTheme` → `multiTheme0`). Stats: manual legs count towards legs and type, `T:` keys are "Team stats", mixed-sport bets are "Multi-sport", odds bands are Under evens / Evens to 3/1 / Over 3/1 to 9/1 / Over 9/1.
- **Level minimum leg price:** `RISK[*].minLeg` (Safest none, Balanced 1.2, Bigger odds 1.4), relaxed to `target^(1/n)` for big accas, applied via `riskOpts()` in level/multi presets and the pre/in-play builders (`accaPreLegs`/`accaLiveLegs` wrap `withMinFallback`, which rebuilds without the minimum only if the level can't be hit). The "add the likeliest extra bet" suggestion respects it too.
- **£1K ladder:** one bar per bet (10), each labelled with what you'll have if it wins; amounts under £10 show pennies (`ladderLabel`, `fmtBank` → `money`).
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
