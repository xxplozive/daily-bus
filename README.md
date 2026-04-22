# Daily Bus Times

A Python server that fetches real-time NJ Transit bus arrivals for two stops and renders them as a mobile-friendly HTML timeline. Tap a single iPhone Shortcut to see the next buses.

**Live:** `https://web-production-21e967.up.railway.app`

---

## Stops monitored

| SMS code | Location | Routes |
|---|---|---|
| 29651 | US-22 70'E OF DUNDAR RD | All (114X, 117, …) |
| 29763 | MORRIS AVE AT CREGER AVE | 114 only |

---

## How it works

1. On first request the server downloads the NJT static GTFS zip (`stops.txt`, `trips.txt`) and caches it for 24 hours
2. `stops.txt` translates SMS stop codes → GTFS stop IDs (29651 → 14749, 29763 → 14856)
3. `trips.txt` builds a `trip_id → route_id` lookup because NJT's real-time feed omits `route_id`
4. `getTripUpdates` is called on every request to get live arrival timestamps in protobuf format
5. Matching trips are filtered, sorted, and rendered as a dark-mode HTML timeline in Eastern time

---

## API

| Endpoint | Description |
|---|---|
| `GET /` | Live bus timeline (HTML) |
| `GET /debug` | Shows GTFS stop ID translation and map sizes — useful if `/` shows 0 buses |

---

## Local development

### Prerequisites

```bash
# Fix Homebrew permissions (one-time, if needed)
sudo chown -R kartiknath /opt/homebrew /opt/homebrew/share/zsh /opt/homebrew/share/zsh/site-functions /opt/homebrew/var/homebrew/locks
chmod u+w /opt/homebrew /opt/homebrew/share/zsh /opt/homebrew/share/zsh/site-functions /opt/homebrew/var/homebrew/locks

brew install uv
```

### Run

```bash
cp .env.example .env
# fill in NJT_USERNAME and NJT_PASSWORD

uv venv
uv pip install -r requirements.txt
uv run uvicorn server:app
```

Open `http://localhost:8000`. First load takes ~15 seconds to download the GTFS zip.

---

## Deployment (Railway)

The project is deployed on Railway via GitHub. Push to `main` to redeploy automatically.

```bash
git add .
git commit -m "your message"
git push
```

Environment variables set in the Railway dashboard:
- `NJT_USERNAME`
- `NJT_PASSWORD`

---

## iPhone Shortcut

1. Open the **Shortcuts** app → tap **+**
2. Add action: **Open URLs**
3. URL: `https://web-production-21e967.up.railway.app`
4. Rename to **Bus Times** → **Done**
5. Tap **···** → **Add to Home Screen**

---

## NJT Developer API

Uses the [NJ Transit BUS GTFS/GTFSRT G2 API](https://developer.njtransit.com/registration/docs).

| Call | Used for |
|---|---|
| `authenticateUser` | Get a token (cached 23 h) |
| `getGTFS` | Static schedule ZIP — stop ID mapping + trip→route lookup (cached 24 h) |
| `getTripUpdates` | Live arrival times in protobuf format (every request) |

All calls are HTTP POST to `https://pcsdata.njtransit.com/api/GTFSG2/`.
