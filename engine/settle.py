"""Settle finished bets and £1K challenge bets while nobody has the app open.

Runs after build.py in the "Update predictions and deploy" workflow (every 20 minutes).
Needs the GitHub secret SUPABASE_SERVICE_KEY (Supabase secret key). Without it, it does nothing.
It mirrors the app's rules: a bet is settled only when the result is certain from the final score,
final team stats or the final box score. Anything it can't be sure about (void legs, unknown
markets, players who didn't play) is left for the app or for you to settle.
"""
from urllib.parse import quote
import json, os, re, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "..", "site")
BASE = "https://site.api.espn.com/apis/site/v2/sports"
KEY = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
URL = re.search(r'supabaseUrl:\s*"([^"]+)"', open(os.path.join(SITE, "config.js")).read()).group(1)


def http(method, path, body=None, prefer=None):
    h = {"apikey": KEY, "Content-Type": "application/json"}
    if KEY.startswith("eyJ"): h["Authorization"] = "Bearer " + KEY   # older-style keys
    if prefer: h["Prefer"] = prefer
    req = urllib.request.Request(URL + "/rest/v1/" + path, method=method, headers=h, data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        t = r.read().decode()
        return json.loads(t) if t else None


def espn(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "matchday-edge"}), timeout=30) as r:
        return json.loads(r.read().decode())


def num(v):
    try: return float(str(v).split("-")[0])
    except Exception: return 0.0


data = json.load(open(os.path.join(SITE, "data.json")))
GAMES = {("football", str(g["id"])): g for g in data.get("football", []) + data.get("extra", [])}   # extra: every other league/cup, track-only
GAMES.update({("nba", str(g["id"])): g for g in data.get("nba", [])})
SUM = {}


def summary(sport, g):
    k = (sport, str(g["id"]))
    if k not in SUM:
        u = f"{BASE}/basketball/nba/summary?event={g['id']}" if sport == "nba" else f"{BASE}/soccer/{g['league']}/summary?event={g['id']}"
        try: SUM[k] = espn(u)
        except Exception: SUM[k] = None
    return SUM[k]


def final_state(sport, g):
    """Fresh final score and status from the summary (data.json may be up to 20 minutes old)."""
    s = summary(sport, g)
    if not s: return None
    comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
    if ((comp.get("status") or {}).get("type") or {}).get("state") != "post": return None
    sc = {c["team"]["id"]: num(c.get("score")) for c in comp.get("competitors", [])}
    hs, as_ = sc.get(str(g["home"]["id"]), 0), sc.get(str(g["away"]["id"]), 0)
    team = {}
    for t in (s.get("boxscore") or {}).get("teams", []):
        team[t["team"]["id"]] = {x.get("name"): num(x.get("displayValue")) for x in t.get("statistics", [])}
    if sport == "football":   # count cards from the events like bookies do: ESPN's totals turn a second yellow into "0 yellow, 1 red"
        ev, booked = {}, set()
        for k in s.get("keyEvents", []) or []:
            ty, tid = (k.get("type") or {}).get("text", ""), (k.get("team") or {}).get("id")
            who = (((k.get("participants") or [{}])[0]).get("athlete") or {}).get("displayName", "")
            c = ev.setdefault(tid, {"y": 0, "r": 0})
            if "Yellow Card" in ty: c["y"] += 1; booked.add((tid, who))
            elif "Red Card" in ty:
                c["r"] += 1
                if (tid, who) in booked or "second yellow" in (k.get("text") or "").lower(): c["y"] += 1
        for tid, c in ev.items():
            if tid in team:
                team[tid]["yellowCards"] = max(team[tid].get("yellowCards", 0), c["y"]); team[tid]["redCards"] = max(team[tid].get("redCards", 0), c["r"])
    return s, hs, as_, team


def leg_result(l):
    """'won' / 'lost' / None (not certain yet, or not something we can check)."""
    if l.get("group"):   # "A, B & C 7+ shots between them": the players' numbers add up
        tot = 0
        for m in l["group"]:
            r, v = leg_result({**l, **m, "group": None})
            if r is None or v is None: return None, None
            tot += v
        return ("won" if tot >= l["target"] else "lost"), tot
    if str(l.get("stat", "")).startswith("combo:"):   # "8+ shots & foul involvements": the stats add up
        tot = 0
        for st in l["stat"][6:].split(","):
            r, v = leg_result({**l, "stat": st})
            if r is None or v is None: return None, None
            tot += v
        return ("won" if tot >= l["target"] else "lost"), tot
    sp, g = l.get("sport"), GAMES.get((l.get("sport"), str(l.get("gid"))))
    if not g: return None, None
    st = final_state(sp, g)
    if not st: return None, None
    s, hs, as_, team = st
    H, A = team.get(str(g["home"]["id"]), {}), team.get(str(g["away"]["id"]), {})
    if l.get("pid"):   # player bets
        if sp == "nba":
            for t in (s.get("boxscore") or {}).get("players", []):
                st0 = (t.get("statistics") or [{}])[0]; labels = st0.get("labels") or st0.get("names") or []
                for a in st0.get("athletes", []):
                    if str((a.get("athlete") or {}).get("id")) != str(l["pid"]): continue
                    if a.get("didNotPlay") or not a.get("stats"): return None, None
                    v = dict(zip(labels, a["stats"]))
                    n = lambda k: num(v.get(k, 0))
                    val = n("PTS") + n("REB") + n("AST") if l["stat"] == "PRA" else n("3PT") if l["stat"] == "3PM" else n(l["stat"])
                    return ("won" if val >= l["target"] else "lost"), val
            return None, None
        if l.get("half") or str(l.get("stat", "")).startswith("headed"):   # half bets and headers: count from the play-by-play (each play once)
            seen, v, nm = set(), 0, l.get("name", "").lower()
            last = nm.split(" ")[-1]
            me = lambda w: bool(w) and (w.lower() == nm or (w.lower().split(" ")[-1] == last and w.lower()[:1] == nm[:1]))
            for c in s.get("commentary", []):
                p = c.get("play") or {}
                if not p or p.get("id") in seen: continue
                seen.add(p.get("id"))
                if l.get("half") and (p.get("period") or {}).get("number", 1) != l["half"]: continue
                head = bool(re.search(r"\bheader\b", re.split(r"Assisted by", c.get("text") or "", flags=re.I)[0], re.I))
                t = (p.get("type") or {}).get("text", ""); who = [(q.get("athlete") or {}).get("displayName", "") for q in p.get("participants", [])] + ["", ""]
                own = "Own Goal" in t; shot = (t.startswith("Shot") or t.startswith("Goal") or t.startswith("Penalty - S") or t.startswith("Penalty - M")) and not own
                on = ("Shot On Target" in t or t.startswith("Goal") or t in ("Penalty - Scored", "Penalty - Saved")) and not own
                st = l["stat"]
                if (st == "headedShotsOnTarget" and on and head and me(who[0])) or (st == "headedShots" and shot and head and me(who[0])) or \
                   (st == "shotsOnTarget" and on and me(who[0])) or (st == "totalShots" and shot and me(who[0])) or \
                   (st == "totalGoals" and (t.startswith("Goal") or t == "Penalty - Scored") and not own and me(who[0])) or \
                   (st == "goalAssists" and t.startswith("Goal") and me(who[1])) or (st == "foulsSuffered" and t.startswith("Foul") and me(who[1])) or \
                   (st == "foulsCommitted" and t.startswith("Foul") and me(who[0])) or (st == "foulInvolvements" and t.startswith("Foul") and (me(who[0]) or me(who[1]))) or (st == "cards" and ("Yellow Card" in t or "Red Card" in t) and me(who[0])):
                    v += 1
            return ("won" if v >= l["target"] else "lost"), v
        for t in s.get("rosters", []):
            for p in t.get("roster", []):
                if str((p.get("athlete") or {}).get("id")) != str(l["pid"]): continue
                stx = {x.get("name"): num(x.get("value", x.get("displayValue"))) for x in p.get("stats", [])}
                if not (p.get("starter") or p.get("subbedIn")): return None, None
                val = stx.get("yellowCards", 0) + stx.get("redCards", 0) if l["stat"] == "cards" else stx.get("totalGoals", 0) + stx.get("goalAssists", 0) if l["stat"] == "goalOrAssist" else stx.get("foulsCommitted", 0) + stx.get("foulsSuffered", 0) if l["stat"] == "foulInvolvements" else stx.get(l["stat"], 0)
                return ("won" if val >= l["target"] else "lost"), val
        return None, None
    k, tot = str(l.get("k", "")), hs + as_
    if k.startswith("T:") and sp == "nba":   # team points, full game or by half, from the quarter scores: T:hpts:each:55 = each team 55+ in each half
        _, stat, who, n = k.split(":"); n = int(n)
        comp = ((s.get("header") or {}).get("competitions") or [{}])[0]
        ls = {c.get("homeAway"): [int(num(x.get("value", x.get("displayValue")))) for x in c.get("linescores", [])] for c in comp.get("competitors", [])}
        if len(ls.get("home", [])) < 4 or len(ls.get("away", [])) < 4: return None, None
        part = lambda q: [sum(q)] if stat == "pts" else [sum(q[0:2])] if stat == "h1pts" else [sum(q[2:4])] if stat == "h2pts" else [sum(q[0:2]), sum(q[2:4])]
        vals = (part(ls["home"]) if who != "away" else []) + (part(ls["away"]) if who != "home" else [])
        return ("won" if min(vals) >= n else "lost"), min(vals)
    if k.startswith("T:") and sp == "football" and k.split(":")[1] in ("hgoals", "h1goals", "h2goals"):   # goals by half, from the goal events
        _, stat, who, n = k.split(":"); n = int(n or 1)
        ev = [e for e in (s.get("keyEvents") or []) if str((e.get("type") or {}).get("text", "")).startswith("Goal")]
        cnt = lambda tid, h: sum(1 for e in ev if str((e.get("team") or {}).get("id")) == str(tid) and ((e.get("period") or {}).get("number") or 1) == h)
        halves = [1, 2] if stat == "hgoals" else [1] if stat == "h1goals" else [2]
        vals = [cnt(g[side]["id"], h) for side in ("home", "away") if who in ("each", side) for h in halves]
        return ("won" if min(vals) >= n else "lost"), min(vals)
    if k.startswith("T:") and sp == "football":   # team stat bets, e.g. 2+ cards for each team
        _, stat, who, n = k.split(":"); n = int(n)
        if stat == "goals": v = (hs, as_)
        elif stat == "cards": v = (H.get("yellowCards", 0) + H.get("redCards", 0), A.get("yellowCards", 0) + A.get("redCards", 0))
        else:
            key = {"corners": "wonCorners", "sot": "shotsOnTarget", "shots": "totalShots", "fouls": "foulsCommitted"}.get(stat)
            if not key or H.get(key) is None: return None, None
            v = (H.get(key, 0), A.get(key, 0))
        cur = min(v) if who == "each" else v[0] if who == "home" else v[1]
        return ("won" if cur >= n else "lost"), cur
    W = lambda c: "won" if c else "lost"
    if sp == "nba":
        if k == "ML1": return W(hs > as_), None
        if k == "ML2": return W(as_ > hs), None
        if k in ("SP1", "SP2") and (g.get("odds") or {}).get("spread") is not None:
            m = hs - as_ + float(g["odds"]["spread"])
            if m == 0: return None, None
            return W(m > 0 if k == "SP1" else m < 0), None
        mh = re.match(r"^(.+?) ([+-][\d.]+)(?: handicap)?$", l.get("label", ""))   # "Celtics +5.5 handicap", "Pacers -4.5"
        if mh and mh[1] in (g["home"].get("name"), g["away"].get("name")):
            mine, theirs = (hs, as_) if mh[1] == g["home"].get("name") else (as_, hs)
            m = mine - theirs + float(mh[2])
            if m == 0: return None, None
            return W(m > 0), None
        mm = re.match(r"^(Over|Under) ([\d.]+) points", l.get("label", ""))
        if mm: return W(tot > float(mm[2]) if mm[1] == "Over" else tot < float(mm[2])), None
        return None, None
    res = {"1": hs > as_, "X": hs == as_, "2": as_ > hs, "1X": hs >= as_, "X2": as_ >= hs, "12": hs != as_,
           "O05": tot > .5, "O15": tot > 1.5, "O25": tot > 2.5, "O35": tot > 3.5, "U25": tot < 2.5, "U35": tot < 3.5,
           "BTTS": hs > 0 and as_ > 0, "BTTSN": not (hs > 0 and as_ > 0), "HO05": hs > 0, "AO05": as_ > 0, "HO15": hs > 1.5, "AO15": as_ > 1.5}
    if k in res: return W(res[k]), None
    if k in ("DNB1", "DNB2"):
        if hs == as_: return None, None   # stake back: leave for the app / you
        return W(hs > as_ if k == "DNB1" else as_ > hs), None
    if k.startswith("C") and H.get("wonCorners") is not None:
        c = H.get("wonCorners", 0) + A.get("wonCorners", 0)
        return W(c < 10.5 if k == "CU105" else c > float(k[1:])), c
    if k.startswith("Y") and H.get("yellowCards") is not None:
        y = H.get("yellowCards", 0) + A.get("yellowCards", 0) + H.get("redCards", 0) + A.get("redCards", 0)
        return W(y > float(k[1:])), y
    return None, None


def outcome(legs):
    M = [l for l in legs or [] if l.get("manual")]   # legs the owner marks themselves
    if any(l.get("fst") == "miss" for l in M): return "lost", legs
    L = [l for l in legs or [] if (l.get("pid") or l.get("k")) and l.get("gid")]
    if not L: return None, legs
    rs = [leg_result(l) for l in L]
    if any(r == "lost" for r, _ in rs): res = "lost"
    elif all(r == "won" for r, _ in rs) and all(l.get("fst") == "hit" for l in M): res = "won"
    else: return None, legs
    out, i = [], 0
    for l in legs:
        if (l.get("pid") or l.get("k")) and l.get("gid"):
            r, v = rs[i]; i += 1
            if r: l = {**l, "fst": "hit" if r == "won" else "miss", "final": v if l.get("pid") else None}
        out.append(l)
    return res, out


def now(): return datetime.now(timezone.utc).isoformat()


def settle_bets():
    bets = http("GET", "bets?result=eq.open&select=*&limit=1000") or []
    n = 0
    for b in bets:
        res, legs = outcome(b.get("legs"))
        if not res: continue
        free = min(float(b.get("free_stake") or 0), float(b["stake"]))   # a free bet pays the winnings only
        ret = round(float(b["stake"]) * float(b["odds_dec"]) - free, 2) if res == "won" else 0
        done = http("PATCH", f"bets?id=eq.{b['id']}&result=eq.open", {"result": res, "returns": ret, "settled_at": now(), "legs": legs}, "return=representation")
        if not done: continue   # the app got there first
        n += 1
        if res == "won": credit_wallet(b["user_id"], ret)
    return n


def settle_bot():
    """The Accabox bot's ready-made accas: settle them like bets; only winners are ever shown. Older than 3 days and still unsure: void."""
    rows = http("GET", "bot_accas?result=eq.open&select=id,legs,kickoff,created_at&limit=500")
    if not isinstance(rows, list): return 0   # table not set up yet
    print(f"Accabox bot: {len(rows)} open acca(s) waiting to settle.")
    n, cutoff = 0, datetime.now(timezone.utc).timestamp() - 3 * 86400
    for r in rows:
        res, legs = outcome(r.get("legs"))
        if not res:
            k = r.get("kickoff") or r.get("created_at")
            try: old = datetime.fromisoformat(str(k).replace("Z", "+00:00")).timestamp() < cutoff
            except Exception: old = False
            if old: http("PATCH", f"bot_accas?id=eq.{quote(r['id'], safe='')}&result=eq.open", {"result": "void", "settled_at": now()})
            continue
        if http("PATCH", f"bot_accas?id=eq.{quote(r['id'], safe='')}&result=eq.open", {"result": res, "settled_at": now(), "legs": legs}, "return=representation"): n += 1
    return n


def credit_wallet(uid, amount):
    if amount <= 0: return
    w = http("GET", f"wallets?user_id=eq.{uid}&select=amount")
    if w: http("PATCH", f"wallets?user_id=eq.{uid}", {"amount": round(float(w[0]["amount"]) + amount, 2), "updated_at": now()})


def settle_ladder(C, uid):
    A = C.get("active")
    if not A: return False
    res, _ = outcome(A.get("legs"))
    if not res: return False
    stake, dec, d = C.get("bank", 1), float(A.get("dec") or 1), datetime.now(timezone.utc)
    entry = {"at": now(), "date": f"{d.day} {d:%b}", "bet": A.get("label", ""), "match": A.get("match", ""), "odds": f"{dec:.2f}", "stake": stake,
             "result": "W" if res == "won" else "L", "ret": round(stake * dec, 2) if res == "won" else 0, **({"sport": A["sport"]} if A.get("sport") else {})}
    C["history"] = [entry] + (C.get("history") or []); C["active"] = None
    if res == "won":
        C["bank"] = entry["ret"]; C["rung"] = C.get("rung", 0) + 1
        credit_wallet(uid, entry["ret"])   # £1K winnings land in the bookie balance too
    else:
        rets = [h.get("ret", 0) for h in C["history"] if h.get("result") in ("W", "C")]
        today = f"{d.day} {d:%b %Y}"
        C["past"] = [{"n": C.get("attempts") or 1, "started": C.get("started", ""), "ended": today, "outcome": "lost", "reached": C.get("rung", 0),
                      "peak": max([C.get("start", 1)] + rets), "taken": C.get("taken", 0), "added": C.get("added", 0), "history": C["history"]}] + (C.get("past") or [])
        C.update({"rung": 0, "bank": C.get("start", 1), "attempts": (C.get("attempts") or 1) + 1, "started": today, "history": [], "active": None, "taken": 0, "added": 0})
    return True


def ladder_total(C):
    return round(float(C.get("bank") or 0) + sum(float(b.get("stake") or 0) for b in C.get("bets") or []), 2)


def ladder_rung(C):
    """The step you're on: each doubling of the ladder (a win at just under evens counts), same as the app."""
    st, n, t = float(C.get("start") or 1), int(C.get("rungs") or 10), ladder_total(C)
    if t >= float(C.get("target") or 1000) * st - 1e-9: return n
    r = 0
    for i in range(1, n):
        if t >= st * 2 ** i * 0.95 - 1e-9: r = i
    return r


def settle_ladder3(C, uid):
    """One ladder for football and NBA with up to 3 bets running (data v3)."""
    changed, d = False, datetime.now(timezone.utc)
    for b in list(C.get("bets") or []):
        res, _ = outcome(b.get("legs"))
        if not res: continue
        stake, dec = float(b.get("stake") or 0), float(b.get("dec") or 1)
        ret = round(stake * dec, 2) if res == "won" else 0
        C["history"] = [{"at": now(), "date": f"{d.day} {d:%b}", "bet": b.get("label", ""), "match": b.get("match", ""), "odds": f"{dec:.2f}", "stake": stake,
                         "result": "W" if res == "won" else "L", "ret": ret, "sport": b.get("sport")}] + (C.get("history") or [])
        C["bets"] = [x for x in C.get("bets") or [] if x.get("id") != b.get("id")]
        C["bank"] = round(float(C.get("bank") or 0) + ret, 2)
        if ret: credit_wallet(uid, ret)   # £1K winnings land in the bookie balance too
        changed = True
    if not changed: return False
    C["peak"] = max(float(C.get("peak") or 0), ladder_total(C)); C["rung"] = ladder_rung(C)
    if ladder_total(C) < 0.01:   # nothing left on the ladder: that attempt is over
        rets = [h.get("ret", 0) for h in C["history"] if h.get("result") in ("W", "C")]
        today = f"{d.day} {d:%b %Y}"
        C["past"] = [{"n": C.get("attempts") or 1, "started": C.get("started", ""), "ended": today, "outcome": "lost", "reached": C.get("rung", 0),
                      "peak": max([C.get("start", 1), C.get("peak", 0)] + rets), "taken": C.get("taken", 0), "added": C.get("added", 0), "history": C["history"]}] + (C.get("past") or [])
        C.update({"rung": 0, "bank": C.get("start", 1), "attempts": (C.get("attempts") or 1) + 1, "started": today, "history": [], "bets": [], "taken": 0, "added": 0, "peak": 0})
    return True


def settle_challenges():
    n = 0
    for row in http("GET", "challenges?select=user_id,data") or []:
        D, changed = row.get("data") or {}, False
        if D.get("v") == 4:   # up to 3 separate challenges, each with one bet at a time (football or NBA)
            for C in D.get("ladders") or []:
                if C and settle_ladder(C, row["user_id"]): changed = True
        elif D.get("v") == 3:
            if D.get("ladder") and settle_ladder3(D["ladder"], row["user_id"]): changed = True
        else:
            for C in ([D.get("football"), D.get("nba")] if D.get("v") == 2 else [D]):
                if C and settle_ladder(C, row["user_id"]): changed = True
        if changed:
            http("PATCH", f"challenges?user_id=eq.{row['user_id']}", {"data": D, "updated_at": now()}); n += 1
    return n


if __name__ == "__main__":
    if not KEY:
        print("No SUPABASE_SERVICE_KEY secret: skipping overnight settling."); sys.exit(0)
    try: print(f"Settled {settle_bets()} bet(s) and {settle_challenges()} £1K step(s).")
    except Exception as e: print("Settling skipped:", type(e).__name__, str(e)[:200])
    try: print(f"Settled {settle_bot()} Accabox bot acca(s).")
    except Exception as e: print("Settling skipped:", type(e).__name__, str(e)[:200])
