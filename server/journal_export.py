#!/usr/bin/env python3
"""Journal -> pushbare CSVs (server/export/ ist NICHT in .gitignore).
Signale+Verdicts+Outcomes gejoint, damit die Daten via GitHub teilbar sind.

Nutzung: python3 server/journal_export.py  (dann git add server/export && commit && push)
"""
import os, csv, json, sqlite3, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.environ.get('SERVER_DIR', HERE), 'journal.db')
OUT = os.path.join(HERE, 'export')


def main():
    os.makedirs(OUT, exist_ok=True)
    con = sqlite3.connect(DB)
    rows = con.execute("""
        SELECT s.id, s.t, s.tag, s.side, s.dir, s.gate, s.px, s.sl_ref, s.ctx,
               o.engine_r, o.exit_reason, o.r24, o.r72, o.r168,
               v.evaluator, v.score, v.veto, v.size_factor, v.confidence, v.reasoning
        FROM signals s
        LEFT JOIN outcomes o ON o.signal_id = s.id
        LEFT JOIN verdicts v ON v.signal_id = s.id
        ORDER BY s.t, v.evaluator""").fetchall()
    p = os.path.join(OUT, 'journal_signals.csv')
    with open(p, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'zeit_utc2', 'tag', 'side', 'dir', 'gate', 'px', 'sl_ref', 'ctx',
                    'engine_r', 'exit_reason', 'r24', 'r72', 'r168',
                    'evaluator', 'score', 'veto', 'size_factor', 'confidence', 'reasoning'])
        for r in rows:
            r = list(r)
            r[1] = dt.datetime.utcfromtimestamp(r[1] + 7200).strftime('%Y-%m-%d %H:%M')
            w.writerow(r)
    print(f"{len(rows)} Zeilen -> {p}")
    n = con.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
    print(f"({n} Signale im Journal)")


if __name__ == '__main__':
    main()
