#!/usr/bin/env python3
"""
Wöchentlicher Kalibrier-Report: diskriminieren die Bewerter-Scores echte Qualität?

- Score-Terzile je Bewerter vs realisierte Outcomes (engine_r für genommene Trades,
  r168-Forward-Proxy für geblockte/alle)
- Veto-Counterfactuals: was hätten vetote Setups gemacht?
- Disagreement claude vs hermes
- Briefing-Backcheck: 8:00-Bias vs 24h-Move (falls BRIEFING_DIR + Bias-JSON-Zeile)

Scharfschalten des Vetos ERST wenn: unterstes Terzil über >=50 Setups klar schlechter
als das oberste UND die Veto-Counterfactuals netto negativ sind.

Nutzung: python3 calibration_report.py [--db journal.db] [--out reports/]
"""
import os, sys, json, glob, sqlite3, argparse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))


def tercile_stats(rows):
    """rows: [(score, outcome)] -> Stats je Terzil."""
    rows = [(s, o) for s, o in rows if s is not None and o is not None]
    if len(rows) < 6:
        return None
    rows.sort(key=lambda x: x[0])
    n = len(rows); k = n // 3
    out = []
    for name, part in (('unten', rows[:k]), ('mitte', rows[k:n - k]), ('oben', rows[n - k:])):
        os_ = [o for _, o in part]
        out.append((name, len(os_), sum(os_) / len(os_), sum(os_)))
    return out


def fmt_terc(t):
    if not t:
        return "  (zu wenig Daten, N<6)\n"
    return "".join(f"  {name:6s} N {n:3d}  ØR {avg:+.2f}  ΣR {tot:+.1f}\n"
                   for name, n, avg, tot in t)


def briefing_backcheck(brief_dir, con):
    if not brief_dir or not os.path.isdir(brief_dir):
        return "  (BRIEFING_DIR nicht gesetzt/gefunden)\n"
    lines = []
    hits = tot = 0
    for f in sorted(glob.glob(os.path.join(brief_dir, '*'))):
        try:
            txt = open(f, errors='replace').read()
        except OSError:
            continue
        bias = None
        for cand in ('"bias"', "'bias'"):
            if cand in txt.lower():
                import re
                m = re.search(r'\{[^{}]*bias[^{}]*\}', txt, re.I | re.S)
                if m:
                    try:
                        bias = json.loads(m.group(0).replace("'", '"')).get('bias')
                    except (ValueError, AttributeError):
                        pass
        if not bias:
            low = txt.lower()
            bias = ('long' if ('bullish' in low or 'bias: long' in low) else
                    'short' if ('bearish' in low or 'bias: short' in low) else None)
        if bias not in ('long', 'short', 'bullish', 'bearish'):
            continue
        d = 1 if bias in ('long', 'bullish') else -1
        day = dt.datetime.fromtimestamp(os.path.getmtime(f))
        t0 = int(day.replace(hour=8, minute=0, second=0).timestamp())
        px0 = _px_at(t0); px1 = _px_at(t0 + 86400)
        if not (px0 and px1):
            continue
        mv = (px1 - px0) / px0 * d
        tot += 1; hits += 1 if mv > 0 else 0
        lines.append(f"  {day:%d.%m.} {bias:8s} 24h-Move {'+' if mv>0 else ''}{mv*100:.2f}%\n")
    if not tot:
        return ("  (keine Briefings mit erkennbarem Bias gefunden — bitte JSON-Zeile "
                "{\"bias\": \"long|short\"} ans Briefing anhängen)\n")
    return "".join(lines) + f"  Trefferquote: {hits}/{tot} ({hits/tot*100:.0f}%)\n"


_PX_CACHE = None

def _px_at(ts):
    """Close-Preis zum Zeitpunkt ts aus der Live-CSV des Watchers."""
    global _PX_CACHE
    import bisect, csv as _csv
    if _PX_CACHE is None:
        sym = os.environ.get('SYMBOL', 'BTCUSDT')
        p = os.path.join(os.environ.get('SERVER_DIR', HERE), 'data', f'{sym}_15m_live.csv')
        ts_l, cl_l = [], []
        if os.path.exists(p):
            with open(p) as f:
                for row in _csv.DictReader(f):
                    ts_l.append(int(float(row['time']))); cl_l.append(float(row['close']))
        _PX_CACHE = (ts_l, cl_l)
    ts_l, cl_l = _PX_CACHE
    if not ts_l:
        return None
    j = bisect.bisect_right(ts_l, ts) - 1
    return cl_l[j] if j >= 0 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', default=os.path.join(os.environ.get('SERVER_DIR', HERE), 'journal.db'))
    ap.add_argument('--out', default=os.path.join(HERE, 'reports'))
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    L = []
    L.append(f"# Kalibrier-Report {dt.date.today():%Y-%m-%d}\n")
    n_sig = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    n_pass = con.execute("SELECT COUNT(*) FROM signals WHERE gate LIKE 'pass%'").fetchone()[0]
    L.append(f"\nSignale: {n_sig} gesamt, davon {n_pass} genommen (Gate pass).\n")
    L.append("\n## Gate-Verteilung\n\n")
    for g, c in con.execute("SELECT gate,COUNT(*) FROM signals GROUP BY gate ORDER BY 2 DESC"):
        L.append(f"  {g:15s} {c}\n")
    for ev in [r[0] for r in con.execute("SELECT DISTINCT evaluator FROM verdicts")]:
        L.append(f"\n## Bewerter: {ev}\n")
        # genommene Trades: engine_r
        rows = con.execute(
            "SELECT v.score, o.engine_r FROM verdicts v JOIN signals s ON s.id=v.signal_id "
            "JOIN outcomes o ON o.signal_id=s.id WHERE v.evaluator=? AND s.gate LIKE 'pass%' "
            "AND o.engine_r IS NOT NULL", (ev,)).fetchall()
        L.append(f"\nScore-Terzile — genommene Trades (engine_r, N={len(rows)}):\n\n")
        L.append(fmt_terc(tercile_stats(rows)))
        # alle Signale: r168-Proxy
        rows = con.execute(
            "SELECT v.score, o.r168 FROM verdicts v JOIN signals s ON s.id=v.signal_id "
            "JOIN outcomes o ON o.signal_id=s.id WHERE v.evaluator=? AND o.r168 IS NOT NULL",
            (ev,)).fetchall()
        L.append(f"\nScore-Terzile — alle Signale (r168-Proxy, N={len(rows)}):\n\n")
        L.append(fmt_terc(tercile_stats(rows)))
        # Vetos counterfactual
        rows = con.execute(
            "SELECT o.r168, o.engine_r FROM verdicts v JOIN outcomes o ON o.signal_id=v.signal_id "
            "WHERE v.evaluator=? AND v.veto=1", (ev,)).fetchall()
        cf = [(er if er is not None else r1) for r1, er in rows if (er is not None or r1 is not None)]
        if cf:
            L.append(f"\nVeto-Counterfactual: N {len(cf)}  ΣR {sum(cf):+.1f} "
                     f"(negativ = Vetos haben R gespart)\n")
        else:
            L.append("\nVetos: keine (gut — Shadow-Phase, Vetoquote soll <5% sein)\n")
    # Disagreement
    rows = con.execute(
        "SELECT a.score, b.score FROM verdicts a JOIN verdicts b ON a.signal_id=b.signal_id "
        "AND a.evaluator='claude' AND b.evaluator='hermes' "
        "WHERE a.score IS NOT NULL AND b.score IS NOT NULL").fetchall()
    if rows:
        d = [abs(x - y) for x, y in rows]
        L.append(f"\n## Disagreement claude vs hermes: N {len(d)}, Ø|Δscore| {sum(d)/len(d):.1f}\n")
    L.append("\n## Briefing-Backcheck (8:00-Bias vs 24h)\n\n")
    L.append(briefing_backcheck(os.environ.get('BRIEFING_DIR', ''), con))
    rep = "".join(L)
    os.makedirs(a.out, exist_ok=True)
    p = os.path.join(a.out, f"{dt.date.today():%Y-W%W}.md")
    open(p, 'w').write(rep)
    print(rep)
    print(f"\n-> gespeichert: {p}")


if __name__ == '__main__':
    main()
