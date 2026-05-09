import csv
import io
import os
import time
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/New_York")

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from google.transit import gtfs_realtime_pb2

load_dotenv()

app = FastAPI()

BASE     = "https://pcsdata.njtransit.com/api/GTFSG2"
USERNAME = os.environ.get("NJT_USERNAME", "")
PASSWORD = os.environ.get("NJT_PASSWORD", "")

# Keyed by SMS stop code (what you text to 69287)
STOP_CODES = {
    "29651": {"name": "US-22 70'E OF DUNDAR RD",  "routes": None},   # all routes
    "29763": {"name": "MORRIS AVE AT CREGER AVE",  "routes": {"114"}},
}

_auth = {"token": None, "expires": 0.0}
_gtfs = {"stop_map": None, "trip_map": None, "expires": 0.0}


# ── auth ─────────────────────────────────────────────────────────────────────

async def get_token() -> str:
    if _auth["token"] and time.time() < _auth["expires"]:
        return _auth["token"]
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/authenticateUser",
                         data={"username": USERNAME, "password": PASSWORD})
        r.raise_for_status()
        _auth["token"] = r.json()["UserToken"]
        _auth["expires"] = time.time() + 23 * 3600
    return _auth["token"]


# ── static GTFS (cached 24 h) ─────────────────────────────────────────────

async def get_gtfs_maps() -> tuple[dict, dict]:
    """
    Returns:
      stop_map: SMS stop_code  → GTFS stop_id   (e.g. "29651" → "2968")
      trip_map: GTFS trip_id   → route_id        (e.g. "12345" → "114X")
    Downloaded once and cached for 24 hours.
    """
    if _gtfs["stop_map"] and time.time() < _gtfs["expires"]:
        return _gtfs["stop_map"], _gtfs["trip_map"]

    tok = await get_token()
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(f"{BASE}/getGTFS", data={"token": tok})
        r.raise_for_status()

    stop_map: dict[str, str] = {}
    trip_map: dict[str, str] = {}

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open("stops.txt") as f:
            for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                code = row.get("stop_code", "").strip()
                sid  = row.get("stop_id",   "").strip()
                if code and sid:
                    stop_map[code] = sid

        with z.open("trips.txt") as f:
            for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                tid   = row.get("trip_id",  "").strip()
                route = row.get("route_id", "").strip().upper()
                if tid and route:
                    trip_map[tid] = route

    _gtfs.update(stop_map=stop_map, trip_map=trip_map,
                 expires=time.time() + 24 * 3600)
    return stop_map, trip_map


# ── real-time arrivals ────────────────────────────────────────────────────

async def fetch_arrivals() -> list[dict]:
    stop_map, trip_map = await get_gtfs_maps()

    # translate SMS stop codes → GTFS stop IDs
    targets: dict[str, dict] = {}
    for code, cfg in STOP_CODES.items():
        gtfs_id = stop_map.get(code)
        if gtfs_id:
            targets[gtfs_id] = cfg

    tok = await get_token()
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/getTripUpdates", data={"token": tok})
        r.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(r.content)

    now = int(time.time())
    results = []

    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        # NJT often omits route_id in RT; fall back to trips.txt lookup
        route = (tu.trip.route_id.strip().upper()
                 or trip_map.get(tu.trip.trip_id.strip(), ""))

        for stu in tu.stop_time_update:
            sid = str(stu.stop_id).strip()
            if sid not in targets:
                continue
            cfg = targets[sid]
            if cfg["routes"] and route.upper() not in {r.upper() for r in cfg["routes"]}:
                continue
            ts = stu.arrival.time or stu.departure.time
            if not ts or ts < now - 60:
                continue
            results.append({
                "stop_name": cfg["name"],
                "stop_cls":  "stop-a" if sid == list(targets.keys())[0] else "stop-b",
                "route":     route or "?",
                "ts":        ts,
                "time_fmt":  datetime.fromtimestamp(ts, TZ).strftime("%-I:%M %p"),
                "mins":      max(0, (ts - now) // 60),
            })

    results.sort(key=lambda x: x["ts"])
    return results


# ── HTML rendering ────────────────────────────────────────────────────────


def render_html(buses: list[dict]) -> str:
    now_str = datetime.now(TZ).strftime("%-I:%M %p")

    stop_pills = "".join(
        f'<div class="stop-pill {("stop-a" if i == 0 else "stop-b")}">{v["name"]}</div>'
        for i, v in enumerate(STOP_CODES.values())
    )

    if not buses:
        rows = '<p class="empty">No buses in real-time feed — service may not have started yet.</p>'
    else:
        rows = ""
        for i, b in enumerate(buses[:15]):
            is_next   = i == 0
            type_cls  = b["stop_cls"]
            next_cls  = " next-up" if is_next else ""
            next_tag  = '<span class="next-tag">Next</span>' if is_next else ""

            m = b["mins"]
            if m == 0:
                mins_html = '<div class="mins-away now">Arriving</div>'
            elif m <= 5:
                mins_html = f'<div class="mins-away soon">{m} min</div>'
            else:
                mins_html = f'<div class="mins-away">{m} min</div>'

            rows += f"""
      <div class="bus-entry{next_cls}">
        <div class="time-col">
          <div class="hour">{b["time_fmt"]}</div>
          {mins_html}
        </div>
        <div class="dot-col">
          <div class="dot {type_cls}{next_cls}"></div>
        </div>
        <div class="info-col">
          <div class="route-row">
            <span class="route-badge {type_cls}">{b["route"]}</span>
            {next_tag}
          </div>
          <div class="stop-name">{b["stop_name"]}</div>
        </div>
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Bus Times</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;
         background:#f2f2f7;color:#1c1c1e;padding:20px 16px 48px}}
    header{{display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:24px}}
    .header-left h1{{font-size:28px;font-weight:700;letter-spacing:-.5px;color:#1c1c1e}}
    .header-left p{{font-size:13px;color:#6c6c70;margin-top:2px}}
    .now-badge{{font-size:12px;font-weight:600;background:#fff;border:1px solid #d1d1d6;
               border-radius:20px;padding:4px 10px;color:#6c6c70}}
    .stops{{display:flex;gap:8px;margin-bottom:24px;flex-wrap:wrap}}
    .stop-pill{{font-size:11px;font-weight:700;padding:5px 12px;border-radius:20px}}
    .stop-pill.stop-a{{background:#dbeafe;color:#1d4ed8;border:1px solid #bfdbfe}}
    .stop-pill.stop-b{{background:#fce7f3;color:#be185d;border:1px solid #fbcfe8}}
    .timeline{{position:relative;background:#fff;border-radius:16px;
               padding:4px 16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
    .timeline::before{{content:"";position:absolute;left:88px;top:0;bottom:0;width:1px;background:#e5e5ea}}
    .bus-entry{{display:flex;align-items:center;padding:14px 0;position:relative}}
    .bus-entry+.bus-entry{{border-top:1px solid #f2f2f7}}
    .bus-entry.next-up{{background:linear-gradient(90deg,rgba(29,78,216,.04) 0%,transparent 100%);
                        border-radius:12px;padding:14px 8px;margin:0 -8px}}
    .time-col{{width:72px;flex-shrink:0;padding-right:16px;text-align:right}}
    .time-col .hour{{font-size:15px;font-weight:600;font-variant-numeric:tabular-nums;
                    line-height:1;color:#1c1c1e}}
    .mins-away{{font-size:10px;color:#aeaeb2;margin-top:2px}}
    .mins-away.soon{{color:#d97706;font-weight:600}}
    .mins-away.now {{color:#16a34a;font-weight:700}}
    .dot-col{{width:20px;flex-shrink:0;display:flex;justify-content:center;position:relative;z-index:1}}
    .dot{{width:10px;height:10px;border-radius:50%;border:2px solid}}
    .dot.stop-a{{background:#eff6ff;border-color:#1d4ed8}}
    .dot.stop-b{{background:#fdf2f8;border-color:#be185d}}
    .dot.next-up{{width:13px;height:13px}}
    .info-col{{flex:1;padding-left:14px}}
    .route-row{{display:flex;align-items:center;gap:8px}}
    .route-badge{{font-size:13px;font-weight:700;padding:2px 8px;border-radius:6px}}
    .route-badge.stop-a{{background:#dbeafe;color:#1d4ed8}}
    .route-badge.stop-b{{background:#fce7f3;color:#be185d}}
    .next-tag{{font-size:10px;font-weight:700;color:#d97706;text-transform:uppercase;letter-spacing:.5px}}
    .stop-name{{font-size:11px;color:#aeaeb2;margin-top:3px}}
    .empty{{text-align:center;color:#aeaeb2;font-size:14px;padding:40px 0}}
  </style>
</head>
<body>
  <header>
    <div class="header-left">
      <h1>Bus Times</h1>
      <p>{len(buses)} buses · Live</p>
    </div>
    <div class="now-badge">Now {now_str}</div>
  </header>
  <div class="stops">{stop_pills}</div>
  <div class="timeline">{rows}</div>
</body>
</html>"""


# ── routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    buses = await fetch_arrivals()
    return render_html(buses)


@app.get("/debug")
async def debug():
    """Check stop ID translation and confirm routes are resolving."""
    stop_map, trip_map = await get_gtfs_maps()

    translated = {
        code: stop_map.get(code, "NOT FOUND in stops.txt")
        for code in STOP_CODES
    }

    return {
        "stop_code_to_gtfs_id": translated,
        "trip_map_size": len(trip_map),
        "stop_map_size": len(stop_map),
    }
