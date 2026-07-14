#!/usr/bin/env python3
"""
Bewerter-Hook: ruft `claude -p` (und optional Hermes) mit einem Signal-Event auf.

STRENG ASYMMETRISCH + FAIL-OPEN:
- Bewerter kann Trades nur ABWERTEN (veto / size_factor <= 1.0), nie öffnen/erhöhen.
- Kein/ungültiges Verdict -> size_factor 1.0, veto false, Trade läuft normal.
- Alle Verdicts (auch Fehlschläge) landen im Journal — Shadow-Modus per Default:
  es gibt bewusst KEINEN Executor, der die Verdicts liest.

Nutzung: python3 evaluator.py <event.json>
Env: CLAUDE_BIN (claude) | HERMES_CMD (optional, Prompt via stdin, JSON via stdout)
     BRIEFING_DIR (Ordner der 8:00-Briefings) | EVAL_TIMEOUT (300)
"""
import os, sys, json, re, glob, time, sqlite3, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.environ.get('SERVER_DIR', HERE), 'journal.db')
CLAUDE_BIN = os.environ.get('CLAUDE_BIN', 'claude')
HERMES_CMD = os.environ.get('HERMES_CMD', '')
BRIEF_DIR = os.environ.get('BRIEFING_DIR', '')
TIMEOUT = int(os.environ.get('EVAL_TIMEOUT', '300'))


def latest_briefing():
    if not BRIEF_DIR or not os.path.isdir(BRIEF_DIR):
        return ''
    files = sorted(glob.glob(os.path.join(BRIEF_DIR, '*')), key=os.path.getmtime)
    if not files:
        return ''
    try:
        txt = open(files[-1], errors='replace').read()
        return f"\n## Aktuellstes 8:00-Briefing ({os.path.basename(files[-1])})\n{txt[-6000:]}\n"
    except OSError:
        return ''


def build_prompt(event):
    rubrik = open(os.path.join(HERE, 'RUBRIK.md'), errors='replace').read()
    return (f"{rubrik}\n\n## Signal-Event (JSON)\n```json\n{json.dumps(event, indent=1)}\n```\n"
            f"{latest_briefing()}\n"
            "Bewerte jetzt dieses Setup gemäß Rubrik. Hole die orthogonalen Daten, "
            "die dir fehlen. Antworte am ENDE mit GENAU EINEM JSON-Objekt im Verdict-Schema.")


def parse_verdict(text):
    m = re.findall(r'\{[^{}]*\}', text, re.S)
    for cand in reversed(m):
        try:
            v = json.loads(cand)
            if 'score' in v:
                score = max(0.0, min(100.0, float(v['score'])))
                sf = max(0.0, min(1.0, float(v.get('size_factor', 1.0))))  # NIE > 1.0
                return dict(score=score, veto=bool(v.get('veto', False)), size_factor=sf,
                            confidence=str(v.get('confidence', 'med'))[:8],
                            reasoning=str(v.get('reasoning', ''))[:2000])
        except (ValueError, TypeError):
            continue
    return None


def run_eval(name, cmd, prompt, use_stdin_arg):
    try:
        if use_stdin_arg:
            r = subprocess.run([cmd, '-p'], input=prompt, capture_output=True,
                               text=True, timeout=TIMEOUT)
        else:
            r = subprocess.run(cmd, shell=True, input=prompt, capture_output=True,
                               text=True, timeout=TIMEOUT)
        out = r.stdout or ''
        v = parse_verdict(out)
        if v:
            return v, out
        return None, out or (r.stderr or 'leer')
    except Exception as e:
        return None, f'EXCEPTION: {e}'


def store(con, signal_id, evaluator, v, raw):
    if v is None:  # fail-open: neutral, aber protokolliert
        v = dict(score=None, veto=False, size_factor=1.0, confidence='none',
                 reasoning='NO_VERDICT (fail-open)')
    con.execute(
        "INSERT OR REPLACE INTO verdicts(signal_id,evaluator,score,veto,size_factor,"
        "confidence,reasoning,raw,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (signal_id, evaluator, v['score'], int(v['veto']), v['size_factor'],
         v['confidence'], v['reasoning'], (raw or '')[-8000:], int(time.time())))
    con.commit()


def main():
    ev_path = sys.argv[1]
    event = json.load(open(ev_path))
    sid = event.get('signal_id')
    if sid is None:
        print('[evaluator] kein signal_id im Event'); return
    prompt = build_prompt(event)
    con = sqlite3.connect(DB_PATH)
    v, raw = run_eval('claude', CLAUDE_BIN, prompt, use_stdin_arg=True)
    store(con, sid, 'claude', v, raw)
    print(f"[evaluator] claude: {v if v else 'NO_VERDICT'}")
    if HERMES_CMD:
        v2, raw2 = run_eval('hermes', HERMES_CMD, prompt, use_stdin_arg=False)
        store(con, sid, 'hermes', v2, raw2)
        print(f"[evaluator] hermes: {v2 if v2 else 'NO_VERDICT'}")
    # Verdict neben das Event legen (Sichtbarkeit/Debug)
    with open(ev_path.replace('.json', '.verdict.json'), 'w') as f:
        json.dump(v or {'status': 'no_verdict'}, f, indent=1)
    con.close()


if __name__ == '__main__':
    main()
