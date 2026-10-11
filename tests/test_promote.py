"""Offline checks for promote.py's picking rules (no network).

    python tests/test_promote.py
"""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import promote as pm  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 11, 15, 0, tzinfo=UTC)  # 16:00 UK


def c(slug, mins_ago, views):
    pub = (NOW - dt.timedelta(minutes=mins_ago)).strftime("%Y-%m-%dT%H:%M:%S")
    return {"slug": slug, "date_gmt": pub, "views": views,
            "link": f"https://celtsarehere.com/{slug}/"}


buffered = {s: {"link": f"https://celtsarehere.com/{s}/"}
            for s in ("a", "b", "c", "d", "e", "f")}

cands = [c("a", 60, 900),    # 900/h
         c("b", 180, 2400),  # 800/h
         c("c", 20, 5000),   # too fresh
         c("d", 400, 9000),  # too old
         c("e", 90, 300),    # under threshold
         c("x", 90, 3000),   # not on main page
         c("f", 120, 4000)]  # already promoted
ranked = pm.rank(cands, {"f": {"at": "2026-10-11T09:00:00+00:00"}}, buffered, NOW)
assert [r["slug"] for r in ranked] == ["a", "b"], ranked

# quiet hours (UK)
assert pm.in_quiet_hours(dt.datetime(2026, 10, 11, 23, 30, tzinfo=pm.UK))
assert pm.in_quiet_hours(dt.datetime(2026, 10, 11, 6, 59, tzinfo=pm.UK))
assert not pm.in_quiet_hours(dt.datetime(2026, 10, 11, 7, 0, tzinfo=pm.UK))
assert pm.gate({}, dt.datetime(2026, 10, 11, 22, 30, tzinfo=UTC))  # 23:30 UK

# gap and daily cap
recent = {"z": {"at": (NOW - dt.timedelta(minutes=20)).isoformat()}}
assert "min ago" in pm.gate(recent, NOW)
six = {f"s{i}": {"at": (NOW - dt.timedelta(hours=i + 1)).isoformat()}
       for i in range(6)}
assert "cap" in pm.gate(six, NOW)
test_only = {"t": {"at": (NOW - dt.timedelta(minutes=5)).isoformat(), "mode": "test"}}
assert pm.gate(test_only, NOW) is None
assert pm.gate({}, NOW) is None

print("promote rules OK")
