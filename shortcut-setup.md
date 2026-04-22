# Daily Bus Times — Setup & Deployment

The Shortcut is a single action. The Python server handles auth, protobuf
parsing, stop filtering, and HTML rendering. You open a URL; it returns a
live bus timeline.

---

## Part 1 — Local setup (Mac)

### Fix Homebrew permissions (one-time)

```bash
sudo chown -R kartiknath /opt/homebrew /opt/homebrew/share/zsh /opt/homebrew/share/zsh/site-functions /opt/homebrew/var/homebrew/locks
chmod u+w /opt/homebrew /opt/homebrew/share/zsh /opt/homebrew/share/zsh/site-functions /opt/homebrew/var/homebrew/locks
```

### Install uv

```bash
brew install uv
```

### Set up the project

```bash
cd /Users/kartiknath/Documents/code/code/ai_projects/daily-bus
cp .env.example .env
```

Open `.env` and fill in your NJT developer portal credentials
(from the email you received when registering at developer.njtransit.com):

```
NJT_USERNAME=your_username_here
NJT_PASSWORD=your_password_here
```

### Install dependencies and run

```bash
uv venv
uv pip install -r requirements.txt
uv run uvicorn server:app
```

Open `http://localhost:8000` in your browser to verify it works.

---

## Part 2 — Deploy to Railway (so iPhone can reach it)

Railway has a free tier and deploys in under 2 minutes.

### Step 1 — Push to GitHub

```bash
cd /Users/kartiknath/Documents/code/code/ai_projects/daily-bus
git init
git add .
git commit -m "daily bus server"
```

Go to github.com → New repository → name it `daily-bus` → Create.
Then push:

```bash
git remote add origin https://github.com/kartiknath/daily-bus.git
git push -u origin main
```

### Step 2 — Deploy on Railway

1. Go to **railway.app** and sign in with GitHub
2. Click **New Project → Deploy from GitHub repo**
3. Select the `daily-bus` repository
4. Railway auto-detects Python and uses `requirements.txt`

### Step 3 — Add environment variables

In your Railway project dashboard:

1. Click the service → **Variables** tab
2. Add two variables:
   - `NJT_USERNAME` = your NJT username
   - `NJT_PASSWORD` = your NJT password
3. Railway redeploys automatically

### Step 4 — Get your URL

In the Railway dashboard → **Settings** → **Networking** → click **Generate Domain**.
You'll get a URL like `https://daily-bus-production.up.railway.app`.

Open that URL in your browser to confirm it works.

---

## Part 3 — Apple Shortcut (1 action)

1. Open the **Shortcuts** app
2. Tap **+** → Add Action → **Open URL**
3. Set URL to your Railway URL (e.g. `https://daily-bus-production.up.railway.app`)
4. Name the shortcut **Bus Times**
5. Add it to your Home Screen

Tap it each morning — Safari opens with the live timeline.

---

## Notes

- Token is cached in memory for 23 hours — no re-auth each request
- `getTripUpdates` only contains trips that have left their origin; very early
  morning runs may show fewer buses until service starts
- If the page shows 0 buses at a normal commute hour, the stop IDs in the
  protobuf feed may differ from the SMS format — open an issue and I can add
  a debug endpoint to inspect what IDs are actually in the feed
