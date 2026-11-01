# Matchday Edge: handover

Everything a new Claude session (or developer) needs to keep building Matchday Edge without re-discovering anything.
Last updated: 31 Oct 2026, end of the first build session.

---

## 1. What it is

**Matchday Edge** is a UK-focused sports-betting companion app for **football and the NBA**, built for the owner (GitHub **snuzzyyy**, display name **Snuzzy**, friend code **690481**) and their friends.

It shows live scores and in-play stats, rates every market with a prediction model, builds accas, runs a £1 → £1K challenge, tracks player bets live, and has accounts with a friends feed and leaderboard.

**Live links**

| What | Where |
|---|---|
| Website / web app | https://snuzzyyy.github.io/matchday-edge/ |
| Android download page | https://snuzzyyy.github.io/matchday-edge/app.html |
| APK direct | https://snuzzyyy.github.io/matchday-edge/MatchdayEdge.apk (also GitHub release tag `app`) |
| Repo (public) | https://github.com/snuzzyyy/matchday-edge |
| Supabase project | `https://kbsdakacdiolzsiykeql.supabase.co` (region West EU / Paris, free plan) |
| Old Claude artifact | https://claude.ai/artifact/V4y115xpy1HgEQPvE98ab7 — now only a "has moved" page. Don't build there again. |

---

## 2. How the owner likes to work (important)

- **Not technical. Wants things to just work.** Do everything yourself; only ask them for steps that genuinely need their account (Supabase SQL, GitHub permissions). Give click-by-click instructions with exact links when they must act.
- **Prefers short, plain answers** and screenshots/links over jargon. They send phone screenshots of problems; fix exactly what's shown, then check related screens.
- **Design: dark mode only.** They tried a bright theme and rejected it. Keep the current dark navy + tangerine/blue look.
- **Keep the artwork and icons** (they explicitly said don't remove images, e.g. the ball icons in the Football/NBA switch).
- **Call it "Friends", never "mates".**
- **UK conventions:** fractional odds by default (with decimal toggle), UK times (Europe/London), £, UK bookies (Sky Bet, Paddy Power, William Hill, Betfair).
- **Don't spam the chat.** They disliked frequent automated "published" messages. The site now updates itself; no background monitors are needed.
- **Mobile first.** They mostly use the Android app on a phone (~412–428px wide), sometimes a Windows PC (Chrome/Brave) and the Claude desktop app.
- Always test at phone width before pushing; they notice cut-off text, cramped layouts and faded colours.

---

## 3. Architecture

```
Browser / Android WebView
   │  every 10s: fetches live scores, stats, box scores, line-ups straight from ESPN (CORS: *)
   │  on demand: ESPN news, standings, injuries, transactions, team rosters
   │  data.json (predictions/fixtures) + logos.json from GitHub Pages
   │  accounts/friends via Supabase (supabase-js UMD from jsDelivr)
   ▼
GitHub Pages (gh-pages branch)  ◄── GitHub Actions "Update predictions and deploy"
                                     runs engine/build.py every 20 min (+ on every push to main)
```

- **No server of our own.** Static site + ESPN public API + Supabase.
- **Data sources:** ESPN `site.api.espn.com` (free, no key, ~1 min update cadence, 1–3 min behind TV). Odds come from the **DraftKings** feed inside ESPN (US book), converted to UK fractions. There are **no real UK bookmaker prices** yet; markets without a feed price show our *fair* price.

---

## 4. Repo layout

| Path | What it is |
|---|---|
| `site/index.html` | **The entire app** (~2,400 lines: HTML + CSS + JS in one file). |
| `site/config.js` | Supabase URL + publishable key (public by design; RLS protects data). |
| `site/data.json` | Snapshot built by `engine/build.py`: fixtures, model markets, form, NBA box scores. Overwritten by Actions every 20 min. |
| `site/logos.json` | Team logos as data URIs (built by the engine). |
| `site/img/*.webp` | Gemini artwork: splash, empty states, sign-in hero, challenge/Pro banners, sport icons. |
| `site/icon-192/512.png`, `mark.png`, `og.png`, `manifest.json` | App icons, header mark, link-preview image, PWA manifest. |
| `site/app.html`, `site/MatchdayEdge.apk` | Android download page + hosted APK. |
| `engine/build.py` | Python data engine + prediction model (see §6). |
| `engine/challenge.json` | Legacy signed-out challenge state (signed-in users use Supabase). |
| `supabase/schema.sql` | Base tables: profiles, bets, challenges, pro_waitlist, leaderboard(). |
| `supabase/social.sql` | Photos + friends: avatar bucket, friendships, reactions, add/remove_friend RPCs, friend-visibility policies. |
| `supabase/badges.sql` | `badges text[]`, protects plan/badges from self-edit, owner = Pro + owner/dev (matched by friend code 690481). |
| `android/` | Minimal WebView wrapper app (Java, no AndroidX). |
| `.github/workflows/update.yml` | Builds data + deploys site to `gh-pages`; stamps `mde-build` meta with the commit SHA. |
| `.github/workflows/android.yml` | Builds the APK on changes to `android/**` and uploads it to release `app`. |

All three SQL files **have been run** on the live Supabase project.

---

## 5. Features (what exists, where it lives in `index.html`)

Menu (`NAV`): **Live · Games · Bets · £1K · Friends**. Games holds Fixtures / Tables / News and Bets holds Tips (id `bets`) / Accas / My Bets, switched with the `subnav()` bar at the top of the page; the tab remembers the last sub-page (`S.lastSub`). `VIEWS` still lists every page id for routing, plus `#account` (👤 button). Routing is hash-based (`view()`), state lives in the global `S` object, everything renders through `render()`.

- **Live**: live cards with mini stats, plain-English in-play insights (corner pace vs expected, favourite losing), tracked bets at the top.
- **Games/Fixtures**: grouped by day/league, "In play" block with rich rows, "Your teams" (favourites), 1/X/2 price buttons.
- **Game page** (`drawerHTML`): full-screen. Score hero → win chances (live-adjusted) → **In-play angles** (`anglesHTML`) → **Best bets for this game** (`bestForGame`) → live stats → **grouped markets** (`marketGroups` / `marketsTable`) → quarters / line-ups & player stats / box score with on-court markers + team toggle / timeline / leaders / tappable injuries / form.
- **Live market maths** (`liveMarkets`): recalculates every market from score/corners/cards/time left (Poisson for football, normal approx for NBA). Settled markets show *Landed ✓* / *Lost*. In-play bets can be added at fair price (`data-liveleg`).
- **Best Bets**: Today/Tomorrow/48h/Week; Bankers / Strong / Evens shots / Value. Falls back to the other sport when today's games have kicked off.
- **Accas**: pick games → safest leg per game (`legFor`), safety levels (Safest/Balanced/Bigger odds), swap legs, "Pick the best 3/5", ready-made accas (`presetsHTML`).
- **Bet slip**: full-screen sheet on phones, editable odds per leg (type bookie price, reset), quick stakes, copy selections, bookie links (sport-aware), save to My Bets. Empty state shows quick picks.
- **£1 → £1K Challenge**: "Use for step N", tappable ladder steps, running bet card with auto result hint from the final score, won/lost buttons, previous attempts archive, toggle *Evens or bigger* vs *Include just under evens* (`S.chalOdds`).
- **Bet import + player tracker**: paste e.g. "Lillard & Maxey to score 25+ points each @ 3.00" → matched against team rosters (`playerIndex`, `parseBet`) → live progress bars (`trackerHTML`, `legValue`). Non-playing legs are Void. Stored in localStorage `mde:tracked`, optionally also saved to My Bets.
- **Tables**: ESPN standings with zone colours, "PLAYING" flags, favourites highlighted. **News**: football (all leagues or one; Injuries/Transfers keyword filters) and NBA (Latest / official injury report / signings & waivers).
- **Accounts (Supabase)**: sign-up/in (confirm email OFF), profile photo upload (cropped to 320px webp, `avatars/{uid}/avatar.webp`), My bets with P/L, favourite teams, privacy toggles.
- **Friends** (`#friends`): invite link `?invite=CODE` (auto-connects after sign-up), friend codes with Copy/Share, feed with reactions 🔥👏😂😬 and "Tail this bet", friends-only leaderboard, friend profiles (`mateSheet`).
- **Badges/plan**: `badgesHTML` (OWNER blue-violet, DEV orange-pink, PRO gold small), `planChip` ("★ PRO PLAN"). Pro is "Coming soon" with a waitlist; nothing is charged.
- **My Bets** (`#mybets`, `viewMyBets`): live-tracked bets (`trackerHTML(true)`, all sports) plus saved bets/P&L when signed in. Live page only shows a link card. The 👤 page links here instead of having its own bets tab.
- **Re-render gotcha**: `render()` runs every 10s and rebuilds `#main`/`#layer`. Anything the user is typing into or picking with must live outside them: the import sheet is in `#implayer` (built once, then `impRefresh()` updates only the results), the photo picker is the persistent `#avatarPick` input in `<body>`. The drawer keeps its scroll and skips the slide-in when the same sheet is re-rendered.
- **iPhone**: no native app. iPhones use the site as a home-screen web app (`apple-touch-icon.png`, `apple-mobile-web-app-*` meta). `iosTip()` shows a one-time "Add to Home Screen" card in iOS Safari; `app.html` has iPhone and Android steps (iPhone first on iOS). Text boxes are 16px on touch screens so Safari doesn't zoom.
- **Bets settle themselves**: `legInfo()` tracks any leg (player props via `legValue`, match markets via `liveMarkets`), `betCard()` shows the live card, `autoSettle()` (every ~15s from `render`) settles open saved bets and the £1K bet once the result is certain. Hand-typed bets have no game attached, so they keep Won/Lost/Void buttons. A bet reopened by hand is remembered in `mde:noAuto` and left alone.
- **£1K per sport**: `challenges.data` is now `{ v: 2, football: ladder, nba: ladder }` (`splitChal()` upgrades the old single-ladder format by the sport of its bet). `chalNow(sport)` / `saveChal(C, sport)`; `chalSummary()` shows both ladders plus the combined money in/out; friends' views use `chalPick()` (their furthest ladder).
- **Class-name clashes**: check a CSS class name isn't already used before adding one (`.fav`, `.statrow` and others exist). A clash broke the tables once.
- **£1K extras**: `chalPath()` builds the ladder from real returns; cash out a running bet or take money out (`cashSheet`, in `#cashlayer`).
- **Self-update**: `checkVersion()` compares the page's `mde-build` meta with the live one every 3 min / on focus and reloads, restoring view state from sessionStorage.

---

## 6. Data engine and model (`engine/build.py`)

- Pulls ESPN scoreboards (yesterday → +5 days) for 9 leagues: EPL, Championship, UCL, UEL, La Liga, Serie A, Bundesliga, Ligue 1, Scottish Prem, plus the NBA.
- Pulls summaries (form/last 5, box scores, odds), standings, and last-5 match summaries for corners/cards.
- **Football model**: Poisson on attack/defence strengths (season, shrunk + last-5 blend), home factor 1.12/0.88, **blended 65% with the market** for 1X2 and O/U 2.5. Corners use a normal approximation with variance 1.6×mean; cards Poisson.
- **NBA model**: margin from point differentials + home court, blended 70% with the devigged moneyline; spreads/totals use normal approximations (σ 12.5 margin, 18 total).
- Writes `site/data.json` atomically. `--fast` skips logos. A cache lives in `engine/cache/` (gitignored; Actions caches it).

---

## 7. Supabase

- Tables: `profiles` (display_name, avatar_url, fav_teams, plan, badges, friend_code, share_bets, show_on_leaderboard), `bets` (legs jsonb, odds_dec, stake, result, returns, settled_at), `challenges` (data jsonb), `pro_waitlist`, `friendships` (both directions), `reactions`.
- RPCs: `leaderboard()` (me + friends), `add_friend(code)`, `remove_friend(other)`, `is_friend`, `shares_bets`.
- Storage bucket `avatars` (public read, users write only their own folder).
- Users **cannot** change their own `plan` or `badges`. To give someone Pro or a badge, run SQL in Supabase, e.g. `update profiles set plan='pro' where friend_code='XXXXXX';`.
- Settings: **Confirm email OFF**; Site URL and redirect `https://snuzzyyy.github.io/matchday-edge/**` set.
- Claude only has the **publishable key** and cannot run SQL. The owner pastes SQL into the SQL Editor. Never ask for the service_role key or DB password.

---

## 8. Android app

- WebView wrapper loading the live site (so it updates itself). Has a photo picker (`onShowFileChooser`), and external links open in the browser.
- Version **1.3** (versionCode 4). Built by `android.yml` and published to release `app`; then copy the APK into `site/` and push. `app.html` downloads from the GitHub release link so it also works from inside the app.
- **Signed with a permanent key** (from 1.3). The key lives only in the GitHub secrets `MDE_KEYSTORE_B64` + `MDE_KEYSTORE_PASSWORD` and in the owner's private backup. The build fails on purpose if the secret is missing. Never commit a keystore or password to this public repo. Bump `versionCode` for every new APK so it installs over the old one.
- 1.3 adds `window.MDEApp.share(text)` (native share sheet), a download listener (opens in the browser) and ClipData handling in the photo picker. The user agent ends in `MatchdayEdgeApp/1.3`.
- Only rebuild the APK when the wrapper itself changes; normal app changes are website changes.

---

## 9. How to work on it in a new session

1. Attach the repo (`snuzzyyy/matchday-edge`, push access) and clone it. GitHub access works through the session proxy; `gh api repos/snuzzyyy/matchday-edge/...` works, but creating repos, enabling Pages via API, GraphQL and writing secrets are blocked.
2. Edit `site/index.html` (usually with small Python string replacements that assert each match is unique, since the file is long).
3. Check JS syntax:
   `node -e "const s=require('fs').readFileSync('site/index.html','utf8');const m=s.match(/<script>([\s\S]*?)<\/script>/g);new Function(m[m.length-1].replace(/<\/?script>/g,''));console.log('ok')"`
4. Test locally: `cd site && python3 -m http.server 8769`, then Playwright (Chromium is preinstalled; `require('playwright')`).
   - **Gotcha:** this sandbox's proxy breaks browser fetches to ESPN (`net::ERR_FAILED`). Route them through curl in tests:
     ```js
     await ctx.route('https://site.api.espn.com/**', r => r.fulfill({ status: 200, contentType: 'application/json',
       headers: { 'access-control-allow-origin': '*' },
       body: require('child_process').execFileSync('curl', ['-s', '--compressed', r.request().url()], { maxBuffer: 64e6 }) }));
     ```
     Real phones fetch ESPN directly and are fine.
   - For signed-in screens, stub supabase: route `**/supabase-js@*/**` to a small mock defining `window.supabase.createClient` (auth.onAuthStateChange, from() chain with select/eq/in/order/limit/maybeSingle/insert/update/upsert/delete, rpc, storage), and route `**/config.js` to a fake URL/key.
   - Always screenshot at **400px** wide (and 360px for header/tabs), plus desktop 1300px when layout changes.
5. Commit as `snuzzyyy <337362346+snuzzyyy@users.noreply.github.com>`, then `git pull --rebase origin main && git push origin main`. Actions redeploys in about 1 minute. Verify with `curl -s https://snuzzyyy.github.io/matchday-edge/?x=$RANDOM | grep <marker>`.
6. Users get the update automatically within ~3 minutes (self-update), or on reopening the app.

---

## 10. Known limitations and ideas not done yet

- **Live speed**: ESPN updates about once a minute and runs 1–3 min behind TV. Faster needs a paid feed (API-Football ~£15–20/mo for ~15–30s).
- **Real UK prices / pre-filled bookie slips**: need a paid odds API (e.g. The Odds API) with UK books and selection IDs. This is the natural first **Pro** feature.
- **Football injuries/transfers** are keyword-filtered news (no dedicated feed). NBA injuries are official.
- **Scheduled Actions** can lag; occasionally a run fails (GitHub emails the owner). The site keeps the last good data.
- **Pro payments**: not built. Before charging for tips in the UK, check ASA/CAP advertising rules, 18+ age checks and UK GDPR (the owner was told this). Stripe Checkout + a Supabase webhook would set `plan='pro'`.
- **Fixed Android signing key**: pending owner approval (see §8).
- Possible next asks: push notifications/bet alerts, more leagues/sports, friend comments, group leagues, in-play alerts when a tracked player is close.

---

## 11. Quick reference for common requests

| Request | Where / how |
|---|---|
| Give someone Pro/badges | SQL: `update profiles set plan='pro', badges=array['dev'] where friend_code='CODE';` |
| Change tabs | `VIEWS` array + the mobile `.tabs` grid column count in CSS |
| Change colours | `:root` tokens at the top of the `<style>` |
| Add a league | `LEAGUES` in `engine/build.py` (the client picks it up from `data.json`) |
| New artwork | Put the webp in `site/img/`. Make black backgrounds transparent (unpremultiply max channel → alpha) before use. |
| Rebuild the APK | Change `android/**`, push, wait for `android.yml`, download from release `app` into `site/MatchdayEdge.apk`, push |
