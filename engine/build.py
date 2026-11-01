#!/usr/bin/env python3
"""Pulls fixtures, live stats, form and odds, runs the model, writes site/data.json + site/logos.json."""
import json, math, os, sys, time, gzip, base64, urllib.request, datetime as dt
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "..", "site")
CACHE = os.path.join(ROOT, "cache")
os.makedirs(CACHE, exist_ok=True); os.makedirs(SITE, exist_ok=True)

BASE = "https://site.api.espn.com/apis/site/v2/sports"
LEAGUES = [
    ("eng.1", "Premier League", "EPL"), ("eng.2", "Championship", "CHAMP"),
    ("uefa.champions", "Champions League", "UCL"), ("uefa.europa", "Europa League", "UEL"),
    ("esp.1", "La Liga", "LIGA"), ("ita.1", "Serie A", "SERIE A"), ("ger.1", "Bundesliga", "BUND"),
    ("fra.1", "Ligue 1", "L1"), ("sco.1", "Scottish Premiership", "SPFL"),
]
DAYS_BACK, DAYS_FWD = 1, 5

def get(url, cache_key=None, ttl=None):
    if cache_key:
        p = os.path.join(CACHE, cache_key + ".json")
        if os.path.exists(p) and (ttl is None or time.time() - os.path.getmtime(p) < ttl):
            try: return json.load(open(p))
            except Exception: pass
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b": raw = gzip.decompress(raw)
                d = json.loads(raw)
                if cache_key: json.dump(d, open(os.path.join(CACHE, cache_key + ".json"), "w"))
                return d
        except Exception as e:
            err = e; time.sleep(1 + attempt)
    print("FAIL", url, err, file=sys.stderr); return {}

def pmap(fn, items, n=16):
    with ThreadPoolExecutor(n) as ex: return list(ex.map(fn, items))

def f(x, d=0.0):
    try: return float(str(x).replace("+", "").replace("%", ""))
    except Exception: return d

def am2dec(a):
    a = f(a, None) if a is not None else None
    if a is None or a == 0: return None
    return round(1 + (a / 100 if a > 0 else 100 / -a), 3)

def poisson(k, lam): return math.exp(-lam) * lam ** k / math.factorial(k)
def p_over(line, lam):  # P(X > line) for poisson
    return 1 - sum(poisson(k, lam) for k in range(int(math.floor(line)) + 1))
def phi(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def devig(decs):
    if not decs or any(d is None for d in decs): return None
    inv = [1 / d for d in decs]; s = sum(inv); return [i / s for i in inv]

today = dt.datetime.now(dt.timezone.utc).date()
dates = [(today + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(-DAYS_BACK, DAYS_FWD + 1)]

def team_obj(c):
    t = c["team"]
    return {"id": t["id"], "name": t.get("shortDisplayName") or t["displayName"], "full": t["displayName"],
            "abbr": t.get("abbreviation", ""), "color": "#" + (t.get("color") or "334155"),
            "alt": "#" + (t.get("alternateColor") or "94a3b8"), "logo": t.get("logo", ""),
            "score": c.get("score"), "form": c.get("form", ""),
            "record": (c.get("records") or [{}])[0].get("summary", "")}

def status_obj(e):
    s = e["status"]; ty = s["type"]
    return {"state": ty["state"], "detail": ty.get("shortDetail") or ty.get("detail"), "clock": s.get("displayClock"),
            "period": s.get("period"), "completed": ty.get("completed", False)}

# ---------------------------------------------------------------- FOOTBALL
logo_urls = {}
def football():
    sb_jobs = [(L, d) for L, *_ in LEAGUES for d in dates]
    def fetch_sb(j):
        L, d = j
        ttl = 6 if d >= (today - dt.timedelta(days=0)).strftime("%Y%m%d") else 3600
        return j, get(f"{BASE}/soccer/{L}/scoreboard?dates={d}", f"sb_{L}_{d}", ttl if d != dates[0] else 600)
    sbs = pmap(fetch_sb, sb_jobs)
    standings = dict(pmap(lambda L: (L, get(f"https://site.api.espn.com/apis/v2/sports/soccer/{L}/standings", f"st_{L}", 1800)), [l[0] for l in LEAGUES]))

    table = {}  # (league, teamId) -> stats
    league_avg = {}
    for L, st in standings.items():
        tot_g = tot_gp = 0
        for grp in st.get("children", []) or [st]:
            for e in grp.get("standings", {}).get("entries", []):
                s = {x["name"]: x.get("value", f(x.get("displayValue"))) for x in e["stats"]}
                gp = s.get("gamesPlayed") or 0
                table[(L, e["team"]["id"])] = {"gp": gp, "gf": s.get("pointsFor", 0), "ga": s.get("pointsAgainst", 0),
                                              "pts": s.get("points", 0), "rank": s.get("rank", 0), "w": s.get("wins", 0), "d": s.get("ties", 0), "l": s.get("losses", 0)}
                tot_g += s.get("pointsFor", 0); tot_gp += gp
        league_avg[L] = (tot_g / tot_gp) if tot_gp > 20 else 1.35

    events = {}
    for (L, d), sb in sbs:
        for e in sb.get("events", []): events[e["id"]] = (L, e)

    # summaries for every match (live/upcoming need lastFive + stats)
    def fetch_sum(item):
        eid, (L, e) = item
        st = e["status"]["type"]["state"]
        ttl = None if st == "post" else (5 if st == "in" else 1800)
        return eid, get(f"{BASE}/soccer/{L}/summary?event={eid}", f"sum_{eid}" + ("" if st == "post" else "_" + st), ttl)
    sums = dict(pmap(fetch_sum, list(events.items())))

    # last-5 event ids per team -> fetch those summaries for corners / cards
    hist_ids = {}
    for eid, s in sums.items():
        for t in s.get("lastFiveGames", []) or []:
            for ev in t.get("events", []):
                hist_ids[ev["id"]] = ev.get("leagueAbbreviation", "")
    league_slug_guess = {}
    def fetch_hist(eid):
        # league slug is not given; the summary endpoint works under any soccer league slug
        return eid, get(f"{BASE}/soccer/all/summary?event={eid}", f"sum_{eid}", None)
    hist = dict(pmap(fetch_hist, list(hist_ids)))

    def box(s):
        out = {}
        for t in (s.get("boxscore") or {}).get("teams", []):
            out[t["team"]["id"]] = {x["name"]: x.get("displayValue") for x in t.get("statistics", [])}
        return out

    def last5(team_block):
        tid = team_block["team"]["id"]; rows = []
        for ev in team_block.get("events", [])[:5]:
            home = ev["homeTeamId"] == tid
            gf, ga = (f(ev["homeTeamScore"]), f(ev["awayTeamScore"])) if home else (f(ev["awayTeamScore"]), f(ev["homeTeamScore"]))
            b = box(hist.get(ev["id"], {}))
            me = b.get(tid, {}); opp = next((v for k, v in b.items() if k != tid), {})
            rows.append({"date": ev["gameDate"][:10], "opp": ev["opponent"].get("abbreviation") or ev["opponent"]["displayName"],
                         "oppName": ev["opponent"]["displayName"], "ha": "H" if home else "A", "gf": int(gf), "ga": int(ga),
                         "res": ev.get("gameResult", ""), "comp": ev.get("leagueAbbreviation", ""),
                         "cf": f(me.get("wonCorners"), None) if me else None, "ca": f(opp.get("wonCorners"), None) if opp else None,
                         "yf": f(me.get("yellowCards"), None) if me else None, "ya": f(opp.get("yellowCards"), None) if opp else None})
        return rows

    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return (sum(v) / len(v), len(v)) if v else (None, 0)

    matches = []
    for eid, (L, e) in events.items():
        c = e["competitions"][0]
        comps = {x["homeAway"]: x for x in c["competitors"]}
        if "home" not in comps: continue
        h, a = team_obj(comps["home"]), team_obj(comps["away"])
        for t in (h, a): logo_urls[("soccer", t["id"])] = t["logo"]
        s = sums.get(eid, {})
        m = {"id": eid, "league": L, "kickoff": e["date"], "status": status_obj(e), "home": h, "away": a,
             "venue": (c.get("venue") or {}).get("fullName", "")}
        for side, t in (("home", h), ("away", a)):
            row = table.get((L, t["id"]))
            if row: t["pos"] = int(row["rank"]); t["pts"] = row["pts"]; t["gp"] = row["gp"]
        # odds
        o = (c.get("odds") or [None])[0]
        if o and o.get("moneyline"):
            ml = o["moneyline"]; tot = o.get("total") or {}
            pick = lambda x: (x.get("close") or x.get("open") or {}).get("odds")
            m["odds"] = {"book": o.get("provider", {}).get("name", "Market"),
                         "h": am2dec(pick(ml.get("home", {}))), "d": am2dec(pick(ml.get("draw", {}))), "a": am2dec(pick(ml.get("away", {}))),
                         "line": o.get("overUnder"), "o": am2dec(pick(tot.get("over", {}))), "u": am2dec(pick(tot.get("under", {})))}
        # live / final stats
        b = box(s)
        if b and m["status"]["state"] != "pre":
            hb, ab = b.get(h["id"], {}), b.get(a["id"], {})
            keys = [("wonCorners", "Corners"), ("yellowCards", "Yellow cards"), ("redCards", "Red cards"), ("possessionPct", "Possession %"),
                    ("totalShots", "Shots"), ("shotsOnTarget", "Shots on target"), ("foulsCommitted", "Fouls"), ("offsides", "Offsides"),
                    ("saves", "Saves"), ("accuratePasses", "Passes completed")]
            m["stats"] = [{"k": k, "label": lab, "h": f(hb.get(k)), "a": f(ab.get(k))} for k, lab in keys if k in hb or k in ab]
        evs = []
        for k in s.get("keyEvents", []) or []:
            ty = (k.get("type") or {}).get("text", "")
            if not any(w in ty for w in ("Goal", "Card", "Penalty", "Substitution")) or "Delay" in ty: continue
            tid = (k.get("team") or {}).get("id")
            evs.append({"min": (k.get("clock") or {}).get("displayValue", ""), "type": ty,
                        "side": "h" if tid == h["id"] else ("a" if tid == a["id"] else ""),
                        "who": ", ".join(p.get("athlete", {}).get("displayName", "") for p in (k.get("participants") or [])[:1]) or (k.get("shortText") or "")})
        m["events"] = evs
        # form / trends
        lf = {t["team"]["id"]: last5(t) for t in s.get("lastFiveGames", []) or []}
        h["last5"], a["last5"] = lf.get(h["id"], []), lf.get(a["id"], [])
        model(m, L, table, league_avg.get(L, 1.35))
        matches.append(m)
    matches.sort(key=lambda m: m["kickoff"])
    return matches

def model(m, L, table, mu):
    h, a = m["home"], m["away"]
    def strength(t):
        row = table.get((L, t["id"]))
        rs = t["last5"]
        att = dfn = 1.0; w_season = 0
        if row and row["gp"]:
            w_season = row["gp"] / (row["gp"] + 4)
            att = 1 + w_season * ((row["gf"] / row["gp"]) / mu - 1)
            dfn = 1 + w_season * ((row["ga"] / row["gp"]) / mu - 1)
        if rs:
            gf = sum(r["gf"] for r in rs) / len(rs); ga = sum(r["ga"] for r in rs) / len(rs)
            att = 0.7 * att + 0.3 * (gf / mu); dfn = 0.7 * dfn + 0.3 * (ga / mu)
        return max(att, 0.35), max(dfn, 0.35)
    ah, dh = strength(h); aa, da = strength(a)
    lh = mu * 1.12 * ah * da; la = mu * 0.88 * aa * dh
    lh, la = min(max(lh, 0.25), 4.0), min(max(la, 0.2), 3.5)
    grid = [[poisson(i, lh) * poisson(j, la) for j in range(11)] for i in range(11)]
    pH = sum(grid[i][j] for i in range(11) for j in range(11) if i > j)
    pD = sum(grid[i][i] for i in range(11)); pA = 1 - pH - pD
    lt = lh + la
    pO = {x: p_over(x, lt) for x in (0.5, 1.5, 2.5, 3.5)}
    pBTTS = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    od = m.get("odds") or {}
    mk = devig([od.get("h"), od.get("d"), od.get("a")]) if od else None
    if mk:  # blend with market: the market is sharper than any simple model
        pH, pD, pA = [0.35 * x + 0.65 * y for x, y in zip((pH, pD, pA), mk)]
        # rescale goal expectation so model agrees with blended outcome
    mo = devig([od.get("o"), od.get("u")]) if od and od.get("line") == 2.5 else None
    if mo:
        shift = 0.65 * mo[0] + 0.35 * pO[2.5]
        # solve lt so P(over 2.5)=shift, then recompute other lines from it
        lo, hi = 0.5, 6.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if p_over(2.5, mid) < shift: lo = mid
            else: hi = mid
        k = mid / lt; lh, la, lt = lh * k, la * k, mid
        pO = {x: p_over(x, lt) for x in (0.5, 1.5, 2.5, 3.5)}
        pBTTS = (1 - math.exp(-lh)) * (1 - math.exp(-la))
    # corners & cards from last-5 boxscores
    def trend(t, kf, ka):
        v = [r[kf] + r[ka] for r in t["last5"] if r.get(kf) is not None and r.get(ka) is not None]
        return v
    ch, ca_ = trend(h, "cf", "ca"), trend(a, "cf", "ca")
    yh, ya = trend(h, "yf", "ya"), trend(a, "yf", "ya")
    corners = cards = None
    if len(ch) >= 3 and len(ca_) >= 3:
        corners = round((sum(ch) / len(ch) + sum(ca_) / len(ca_)) / 2, 2)
    if len(yh) >= 3 and len(ya) >= 3:
        cards = round((sum(yh) / len(yh) + sum(ya) / len(ya)) / 2, 2)
    hn, an = h["name"], a["name"]
    def hits(t, fn): return sum(1 for r in t["last5"] if fn(r)), len(t["last5"])
    markets = [
        ("1", f"{hn} to win", pH, od.get("h")), ("X", "Draw", pD, od.get("d")), ("2", f"{an} to win", pA, od.get("a")),
        ("1X", f"{hn} or draw", pH + pD, None), ("X2", f"{an} or draw", pA + pD, None), ("12", "Either team to win", pH + pA, None),
        ("DNB1", f"{hn} draw no bet", pH / (pH + pA), None), ("DNB2", f"{an} draw no bet", pA / (pH + pA), None),
        ("O05", "Over 0.5 goals", pO[0.5], None), ("O15", "Over 1.5 goals", pO[1.5], None),
        ("O25", "Over 2.5 goals", pO[2.5], od.get("o") if od.get("line") == 2.5 else None),
        ("U25", "Under 2.5 goals", 1 - pO[2.5], od.get("u") if od.get("line") == 2.5 else None),
        ("U35", "Under 3.5 goals", 1 - pO[3.5], None), ("O35", "Over 3.5 goals", pO[3.5], None),
        ("BTTS", "Both teams to score", pBTTS, None), ("BTTSN", "Both teams to score: No", 1 - pBTTS, None),
        ("HO05", f"{hn} to score", 1 - math.exp(-lh), None), ("AO05", f"{an} to score", 1 - math.exp(-la), None),
        ("HO15", f"{hn} over 1.5 goals", p_over(1.5, lh), None), ("AO15", f"{an} over 1.5 goals", p_over(1.5, la), None),
    ]
    if corners:
        for line in (7.5, 8.5, 9.5, 10.5):
            # corners are over-dispersed vs poisson: widen with a normal approx (var ~ 1.6*mean)
            p = 1 - phi((line + 0.5 - 0.5 - corners) / math.sqrt(1.6 * corners))
            markets.append((f"C{line}", f"Over {line} corners", p, None))
        markets.append(("CU105", "Under 10.5 corners", phi((10.5 - corners) / math.sqrt(1.6 * corners)), None))
    if cards:
        for line in (2.5, 3.5, 4.5):
            markets.append((f"Y{line}", f"Over {line} cards", p_over(line, cards), None))
    out = []
    for key, label, p, dec in markets:
        p = max(min(p, 0.995), 0.005)
        mk_ = {"k": key, "label": label, "p": round(p, 4), "fair": round(1 / p, 3)}
        if dec: mk_["dec"] = dec; mk_["edge"] = round(p * dec - 1, 4)
        out.append(mk_)
    m["model"] = {"xgH": round(lh, 2), "xgA": round(la, 2), "corners": corners, "cards": cards,
                  "trend": {"h": {"btts": hits(h, lambda r: r["gf"] > 0 and r["ga"] > 0), "o25": hits(h, lambda r: r["gf"] + r["ga"] > 2),
                                  "cs": hits(h, lambda r: r["ga"] == 0), "c85": (sum(1 for x in ch if x > 8.5), len(ch)), "y35": (sum(1 for x in yh if x > 3.5), len(yh))},
                            "a": {"btts": hits(a, lambda r: r["gf"] > 0 and r["ga"] > 0), "o25": hits(a, lambda r: r["gf"] + r["ga"] > 2),
                                  "cs": hits(a, lambda r: r["ga"] == 0), "c85": (sum(1 for x in ca_ if x > 8.5), len(ca_)), "y35": (sum(1 for x in ya if x > 3.5), len(ya))}},
                  "markets": out}

# ---------------------------------------------------------------- NBA
# ---------- NBA player bets (props) ----------
PROP_LINES = {"PTS": (10, 15, 20, 25, 30, 35, 40), "REB": (4, 6, 8, 10, 12), "AST": (3, 4, 6, 8, 10),
              "3PM": (1, 2, 3, 4, 5), "PRA": (20, 25, 30, 35, 40, 45, 50)}
PROP_WORD = {"PTS": "points", "REB": "rebounds", "AST": "assists", "3PM": "threes", "PRA": "pts+reb+ast"}
NBA_SEASON = today.year + 1 if today.month >= 9 else today.year

def player_log(pid, season):
    d = get(f"https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{pid}/gamelog?season={season}",
            f"nba_gl_{pid}_{season}", 6 * 3600)
    labels = d.get("labels") or []
    if not labels: return []
    dates = {k: (v or {}).get("gameDate", "") for k, v in (d.get("events") or {}).items()}
    ix = {l: i for i, l in enumerate(labels)}
    out, seen = [], set()
    for stp in d.get("seasonTypes") or []:
        if "preseason" in (stp.get("displayName") or "").lower(): continue
        for cat in stp.get("categories") or []:
            if cat.get("type") not in (None, "event"): continue
            for ev in cat.get("events") or []:
                st = ev.get("stats") or []
                if len(st) < len(labels) or ev.get("eventId") in seen: continue
                seen.add(ev.get("eventId"))
                try:
                    mn = f(st[ix["MIN"]]); pts = f(st[ix["PTS"]]); reb = f(st[ix["REB"]]); ast = f(st[ix["AST"]])
                    tpm = f(str(st[ix["3PT"]]).split("-")[0])
                except Exception: continue
                if mn <= 0: continue
                out.append({"d": dates.get(ev.get("eventId"), ""), "MIN": mn, "PTS": pts, "REB": reb, "AST": ast, "3PM": tpm, "PRA": pts + reb + ast})
    out.sort(key=lambda x: x["d"], reverse=True)
    return out

def player_props(g, s):
    out_names = set()
    for t in s.get("injuries", []) or []:
        for i in t.get("injuries") or []:
            if (i.get("status") or "").lower() in ("out", "suspended"):
                out_names.add((i.get("athlete") or {}).get("id") or (i.get("athlete") or {}).get("displayName"))
    cands = []
    for side in ("h", "a"):
        team = g["home"] if side == "h" else g["away"]
        ro = get(f"{BASE}/basketball/nba/teams/{team['id']}/roster", f"nba_roster_{team['id']}", 6 * 3600)
        for A in ro.get("athletes") or []:
            if A.get("id") in out_names or A.get("displayName") in out_names: continue
            if any((x.get("status") or "").lower() == "out" for x in A.get("injuries") or []): continue
            cands.append((side, team["name"], A["id"], A.get("displayName") or A.get("fullName")))
    logs = pmap(lambda c: (player_log(c[2], NBA_SEASON), player_log(c[2], NBA_SEASON - 1)), cands)
    players = []
    for (side, tname, pid, name), (cur, prev) in zip(cands, logs):
        if not cur and not prev: continue
        base = cur if len(cur) >= 3 else (prev or cur)
        mins = sum(x["MIN"] for x in base) / len(base)
        if mins < 22: continue
        players.append((mins, side, tname, pid, name, cur, prev))
    # best 4 per team by minutes (about 8 per game)
    players.sort(key=lambda x: -x[0])
    keep, cnt = [], {"h": 0, "a": 0}
    for pl in players:
        if cnt[pl[1]] < 4: keep.append(pl); cnt[pl[1]] += 1
    mk = []
    for mins, side, tname, pid, name, cur, prev in keep:
        for stat, lines in PROP_LINES.items():
            n, k = len(cur), 6
            mc = sum(x[stat] for x in cur) / n if n else 0
            mp = sum(x[stat] for x in prev) / len(prev) if prev else mc
            if not prev and not n: continue
            m = (n * mc + k * mp) / (n + k)
            if m <= 0.2: continue
            recent = (cur + prev)[:20]
            if len(recent) >= 5:
                mu = sum(x[stat] for x in recent) / len(recent)
                esd = math.sqrt(sum((x[stat] - mu) ** 2 for x in recent) / (len(recent) - 1))
            else: esd = 0
            sd = max(esd, 0.25 * m + 2)
            opts = []
            for t in lines:
                p = p_over(t - 1, m) if stat == "3PM" else 1 - phi((t - 0.5 - m) / sd)
                if 0.12 <= p <= 0.92:
                    dist = 0 if 0.5 <= p <= 0.8 else min(abs(p - 0.5), abs(p - 0.8))
                    opts.append((dist, t, p))
            for dist, t, p in sorted(opts)[:3]:
                word = PROP_WORD[stat]; p = round(p, 4)
                mk.append({"k": f"P:{pid}:{stat}:{t}", "label": f"{name} {t}+ {word}", "p": p, "fair": round(1 / p, 3),
                           "prop": {"pid": pid, "name": name, "side": side, "team": tname, "stat": stat, "target": t, "label": word}})
    mk.sort(key=lambda x: (x["prop"]["side"], x["prop"]["pid"], x["prop"]["stat"], x["prop"]["target"]))
    return mk

def nba():
    nd = [(today + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(-1, 4)]
    sbs = pmap(lambda d: get(f"{BASE}/basketball/nba/scoreboard?dates={d}", f"nba_sb_{d}", 6), nd)
    st = get("https://site.api.espn.com/apis/v2/sports/basketball/nba/standings", "nba_st", 1800)
    tab = {}
    for grp in st.get("children", []):
        for e in grp["standings"]["entries"]:
            s = {x["name"]: x.get("value") for x in e["stats"]}
            ds = {x["name"]: x.get("displayValue") for x in e["stats"]}
            tab[e["team"]["id"]] = {"pf": s.get("avgPointsFor") or 112, "pa": s.get("avgPointsAgainst") or 112,
                                    "streak": ds.get("streak", ""), "home": ds.get("Home", ""), "road": ds.get("Road", ""),
                                    "seed": ds.get("playoffSeed", ""), "conf": grp.get("abbreviation") or grp.get("name", "")}
    evs = [e for sb in sbs for e in sb.get("events", [])]
    def fs(e):
        stt = e["status"]["type"]["state"]
        return e["id"], get(f"{BASE}/basketball/nba/summary?event={e['id']}", f"nsum_{e['id']}" + ("" if stt == "post" else "_" + stt), None if stt == "post" else (5 if stt == "in" else 1800))
    sums = dict(pmap(fs, evs))
    games = []
    for e in evs:
        c = e["competitions"][0]; comps = {x["homeAway"]: x for x in c["competitors"]}
        h, a = team_obj(comps["home"]), team_obj(comps["away"])
        for t, cc in ((h, comps["home"]), (a, comps["away"])):
            logo_urls[("nba", t["id"])] = t["logo"]
            t["lines"] = [int(f(x.get("value"))) for x in cc.get("linescores", [])]
            t.update({k: v for k, v in tab.get(t["id"], {}).items() if k in ("streak", "home", "road", "seed", "conf")})
            t["ppg"] = round(tab.get(t["id"], {}).get("pf", 0), 1); t["oppg"] = round(tab.get(t["id"], {}).get("pa", 0), 1)
        g = {"id": e["id"], "start": e["date"], "status": status_obj(e), "home": h, "away": a, "venue": (c.get("venue") or {}).get("fullName", "")}
        s = sums.get(e["id"], {})
        pc = (s.get("pickcenter") or [None])[0]
        if pc:
            g["odds"] = {"book": pc.get("provider", {}).get("name", "Market"), "h": am2dec((pc.get("homeTeamOdds") or {}).get("moneyLine")),
                         "a": am2dec((pc.get("awayTeamOdds") or {}).get("moneyLine")), "spread": pc.get("spread"),
                         "hs": am2dec((pc.get("homeTeamOdds") or {}).get("spreadOdds")), "as": am2dec((pc.get("awayTeamOdds") or {}).get("spreadOdds")),
                         "total": pc.get("overUnder"), "o": am2dec(pc.get("overOdds")), "u": am2dec(pc.get("underOdds"))}
        b = (s.get("boxscore") or {}).get("teams", [])
        if b and g["status"]["state"] != "pre":
            bs = {t["team"]["id"]: {x["name"]: x.get("displayValue") for x in t.get("statistics", [])} for t in b}
            keys = [("fieldGoalPct", "FG %"), ("threePointFieldGoalPct", "3PT %"), ("freeThrowPct", "FT %"), ("totalRebounds", "Rebounds"),
                    ("assists", "Assists"), ("steals", "Steals"), ("blocks", "Blocks"), ("totalTurnovers", "Turnovers"),
                    ("pointsInPaint", "Points in paint"), ("fastBreakPoints", "Fast break pts"), ("largestLead", "Largest lead")]
            g["stats"] = [{"k": k, "label": l, "h": f(bs.get(h["id"], {}).get(k)), "a": f(bs.get(a["id"], {}).get(k))} for k, l in keys]
            g["threes"] = {"h": bs.get(h["id"], {}).get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"), "a": bs.get(a["id"], {}).get("threePointFieldGoalsMade-threePointFieldGoalsAttempted")}
        # player box score + who is on court
        box = {}
        subs_by_team = {}
        for t in (s.get("boxscore") or {}).get("players", []) or []:
            tid = t["team"]["id"]; side = "h" if tid == h["id"] else "a"
            st0 = (t.get("statistics") or [{}])[0]
            labels = st0.get("labels") or st0.get("names") or []
            rows = []
            for ath in st0.get("athletes", []):
                A = ath.get("athlete", {})
                stats = dict(zip(labels, ath.get("stats") or []))
                rows.append({"id": A.get("id"), "n": A.get("displayName"), "short": A.get("shortName") or A.get("displayName"),
                             "pos": (A.get("position") or {}).get("abbreviation", ""), "no": A.get("jersey", ""),
                             "st": bool(ath.get("starter")), "dnp": bool(ath.get("didNotPlay")), "on": bool(ath.get("active")),
                             "ej": bool(ath.get("ejected")), "why": ath.get("reason", "") if ath.get("didNotPlay") else "", "s": stats})
            box[side] = {"players": rows, "totals": dict(zip(labels, st0.get("totals") or []))}
        if box and g["status"]["state"] == "in":
            # fallback when the feed's on-court flags don't add up to five: replay substitutions from the starters
            for side in box:
                ps = box[side]["players"]
                if sum(p["on"] for p in ps) != 5:
                    on = {p["id"] for p in ps if p["st"]}
                    for pl in s.get("plays", []) or []:
                        if "enters the game for" in pl.get("text", ""):
                            pp = [x.get("athlete", {}).get("id") for x in pl.get("participants", [])]
                            if len(pp) >= 2 and pp[1] in on: on.discard(pp[1]); on.add(pp[0])
                    for p in ps: p["on"] = p["id"] in on
        elif box:
            for side in box:
                for p in box[side]["players"]: p["on"] = False
        g["box"] = box
        lead = []
        for t in s.get("leaders", []) or []:
            tid = t.get("team", {}).get("id")
            for cat in t.get("leaders", [])[:3]:
                if cat.get("leaders"):
                    L0 = cat["leaders"][0]
                    lead.append({"side": "h" if tid == h["id"] else "a", "cat": cat.get("displayName") or cat.get("name"),
                                 "who": L0.get("athlete", {}).get("displayName"), "val": L0.get("displayValue")})
        g["leaders"] = lead
        inj = []
        for t in s.get("injuries", []) or []:
            tid = t.get("team", {}).get("id")
            for i in (t.get("injuries") or [])[:4]:
                inj.append({"side": "h" if tid == h["id"] else "a", "who": i.get("athlete", {}).get("displayName"), "status": i.get("status")})
        g["injuries"] = inj
        # model
        th, ta = tab.get(h["id"], {"pf": 113, "pa": 113}), tab.get(a["id"], {"pf": 113, "pa": 113})
        margin = ((th["pf"] - th["pa"]) - (ta["pf"] - ta["pa"])) / 2 + 2.3
        proj = (th["pf"] + ta["pa"]) / 2 + (ta["pf"] + th["pa"]) / 2
        pH = phi(margin / 12.5)
        od = g.get("odds") or {}
        mk = devig([od.get("h"), od.get("a")])
        if mk: pH = 0.3 * pH + 0.7 * mk[0]
        mk_list = [("ML1", f"{h['name']} to win", pH, od.get("h")), ("ML2", f"{a['name']} to win", 1 - pH, od.get("a"))]
        if od.get("spread") is not None:
            sp = f(od["spread"])  # home handicap from home perspective (negative = home favourite)
            fav_margin = -sp
            # implied margin from blended win prob
            mrg = 12.5 * math.sqrt(2) * erfinv(2 * pH - 1)
            pc_h = phi((mrg + sp) / 12.5)
            ph_dev = devig([od.get("hs"), od.get("as")])
            if ph_dev: pc_h = 0.4 * pc_h + 0.6 * ph_dev[0]
            lab = lambda n, s_: f"{n} {'+' if s_ > 0 else ''}{s_:g}"
            mk_list += [("SP1", lab(h["name"], sp), pc_h, od.get("hs")), ("SP2", lab(a["name"], -sp), 1 - pc_h, od.get("as"))]
        if od.get("total"):
            tl = f(od["total"]); po = phi((proj - tl) / 18)
            dv = devig([od.get("o"), od.get("u")])
            if dv: po = 0.35 * po + 0.65 * dv[0]
            mk_list += [("TO", f"Over {tl:g} points", po, od.get("o")), ("TU", f"Under {tl:g} points", 1 - po, od.get("u"))]
            # alt lines that UK books always offer
            mean_t = tl + 18 * math.sqrt(2) * erfinv(2 * po - 1)
            for alt in (-10, -6):
                mk_list.append((f"TO{alt}", f"Over {tl + alt:g} points", phi((mean_t - (tl + alt)) / 18), None))
        if mk:
            mrg = 12.5 * math.sqrt(2) * erfinv(2 * pH - 1)
            fav_is_h = pH >= 0.5
            fav = h["name"] if fav_is_h else a["name"]
            pf = pH if fav_is_h else 1 - pH
            # favourite with +5.5 head start (handicap) is a common UK 'banker' leg
            m_ = abs(mrg)
            mk_list.append(("FAVH", f"{fav} +5.5 handicap", phi((m_ + 5.5) / 12.5), None))
        g["model"] = {"proj": round(proj, 1), "margin": round(margin, 1),
                      "markets": [dict(k=k, label=l, p=round(max(min(p, .99), .01), 4), fair=round(1 / max(min(p, .99), .01), 3),
                                       **({"dec": d, "edge": round(p * d - 1, 4)} if d else {})) for k, l, p, d in mk_list]}
        try:
            hrs = (dt.datetime.fromisoformat(e["date"].replace("Z", "+00:00")) - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600
            if g["status"]["state"] == "pre" and hrs < 36:
                g["model"]["markets"] += player_props(g, s)
        except Exception as ex:
            print("props failed", e["id"], ex, file=sys.stderr)
        games.append(g)
    games.sort(key=lambda g: g["start"])
    return games

def erfinv(y):
    y = max(min(y, 0.999999), -0.999999)
    a = 0.147; ln = math.log(1 - y * y); t = 2 / (math.pi * a) + ln / 2
    return math.copysign(math.sqrt(math.sqrt(t * t - ln / a) - t), y)

def logos():
    out = {}
    def one(k):
        sport, tid = k; url = logo_urls[k]
        if not url: return k, None
        path = url.split("espncdn.com")[-1]
        p = os.path.join(CACHE, f"logo_{sport}_{tid}.b64")
        if os.path.exists(p): return k, open(p).read()
        try:
            req = urllib.request.Request(f"https://a.espncdn.com/combiner/i?img={path}&w=64&h=64", headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=20).read()
            b = "data:image/png;base64," + base64.b64encode(raw).decode(); open(p, "w").write(b); return k, b
        except Exception: return k, None
    for k, v in pmap(one, list(logo_urls)):
        if v: out[f"{k[0]}-{k[1]}"] = v
    return out

if __name__ == "__main__":
    t0 = time.time()
    fb = football(); nb = nba()
    data = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "leagues": [{"id": l, "name": n, "short": s} for l, n, s in LEAGUES],
            "football": fb, "nba": nb}
    chal = os.path.join(ROOT, "challenge.json")
    data["challenge"] = json.load(open(chal)) if os.path.exists(chal) else None
    tmp = os.path.join(SITE, "data.json.tmp"); json.dump(data, open(tmp, "w"), separators=(",", ":")); os.replace(tmp, os.path.join(SITE, "data.json"))
    if "--fast" not in sys.argv: json.dump(logos(), open(os.path.join(SITE, "logos.json"), "w"), separators=(",", ":"))
    print(f"football {len(fb)} | nba {len(nb)} | {time.time() - t0:.1f}s")
