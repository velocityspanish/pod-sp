"""Regression: continuity history + engine-synced karaoke + one-word highlight steps.

Standard library only:
    python test_karaoke.py        # exit 0 = pass, exit 1 = fail
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import podcast_generator as pg

FAILURES = []

# 1. Continuation history carries recent turns and strips markers.
_h = [{"speaker": "Host2" if i % 2 == 0 else "Host1",
       "spanish": "**w%d** text" % i, "english": "line%d" % i} for i in range(8)]
_b = pg._format_history_block(_h)
if "**" in _b or "line7" not in _b or "line0" in _b or "line1" in _b:
    FAILURES.append("history-window: %r" % (_b,))

# 2. Engine boundaries give exact per-token timings summing to the duration.
SAMPLE = "Hola mundo, buenos dias."
_sw = [b["text"] for b in [{"text": "Hola", "offset": 0.0, "duration": 0.3}, {"text": "mundo,", "offset": 0.5, "duration": 0.3}, {"text": "buenos", "offset": 1.0, "duration": 0.3}, {"text": "dias.", "offset": 1.5, "duration": 0.3}]]
_t0 = pg.karaoke_tokens_for_text(SAMPLE)
_t = pg.karaoke_tokens_for_text(SAMPLE, [{"text": "Hola", "offset": 0.0, "duration": 0.3}, {"text": "mundo,", "offset": 0.5, "duration": 0.3}, {"text": "buenos", "offset": 1.0, "duration": 0.3}, {"text": "dias.", "offset": 1.5, "duration": 0.3}])
_d = pg.karaoke_step_durations(_t or _t0, 1.9, [{"text": "Hola", "offset": 0.0, "duration": 0.3}, {"text": "mundo,", "offset": 0.5, "duration": 0.3}, {"text": "buenos", "offset": 1.0, "duration": 0.3}, {"text": "dias.", "offset": 1.5, "duration": 0.3}], SAMPLE)
if not (_t or _t0) or abs(sum(_d) - 1.9) > 0.05 or len(_d) != len(_t or _t0):
    FAILURES.append("engine-sync: %r stepped %r" % (_t, _d))

# 3. Exactly one non-space word highlighted per step; spacing kept.
_mt = _t0 or _t
_mp = SAMPLE.replace("**", "").strip()
for _k in range(len(_mt)):
    _m = pg._karaoke_marked(_mt, _k)
    if _m.count("**") != 2:
        FAILURES.append("mark-one: step %d markers %r" % (_k, _m))
        break
    if _m.split("**")[1].strip() == "":
        FAILURES.append("mark-space: step %d highlights blank %r" % (_k, _m))
        break
    if _m.replace("**", "") != _mp:
        FAILURES.append("mark-spacing: step %d moved text %r" % (_k, _m))
        break

# 4. English display text never carries ** highlight markers.
if pg.clean_english("Today we talk about a travel **kettle**, calmly.") != "Today we talk about a travel kettle, calmly.":
    FAILURES.append("english-markers: %r" % (pg.clean_english("Today we talk about a travel **kettle**, calmly."),))

# 5. ASS karaoke lines keep word spaces (not jammed syllables).
import tempfile as _tf
import re as _re2
_turns5 = [{"speaker": "Host2", "spanish": "Hola mundo, buenos dias.", "english": "Hello world."}]
_audio5 = [{"path": "x.mp3", "duration": 2.0, "speaker": "Host2", "word_boundaries": []}]
with _tf.TemporaryDirectory() as _td5:
    _ass5 = pg.write_karaoke_files(_turns5, _audio5, _td5)
    _txt5 = Path(_ass5).read_text(encoding="utf-8")
_plain5 = _re2.sub(r"\{[^}]*\}", "", _txt5)
if "Hola mundo" not in _plain5:
    FAILURES.append("ass-spacing: jammed karaoke line in %r" % (_plain5[-200:],))

if FAILURES:
    print("FAIL (%d):" % len(FAILURES))
    for f in FAILURES:
        print("  - " + f)
    sys.exit(1)
print("PASS: karaoke regression (5 checks)")
