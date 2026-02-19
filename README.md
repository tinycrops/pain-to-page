# Pain-to-Page — Lead Generation Funnel

Paste social media links → AI extracts pain points → dynamic sales funnel page captures leads.

```
frontend/   ← Static site deployed to GitHub Pages (public)
backend/    ← FastAPI server exposed via Tailscale Funnel (private)
```

---

## Frontend — GitHub Pages

The public sales funnel page. Dynamically loads content from the backend and captures leads.

### Setup

**1. Push to GitHub and enable Pages**

```bash
git init
git remote add origin git@github.com:YOUR_USERNAME/lead-generation-funnel.git
git add .
git commit -m "initial commit"
git push -u origin main
```

Then in your repo → **Settings → Pages → Source → GitHub Actions**.

The workflow at `.github/workflows/pages.yml` deploys the `frontend/` directory automatically on every push to `main`.

**2. Point the frontend at your backend**

Once you have your Tailscale funnel URL (see backend setup below), open `frontend/config.js` and set:

```js
const CONFIG = {
  BACKEND_URL: "https://YOUR-MACHINE.ts.net",
};
```

Push the change — GitHub Actions will redeploy within ~30 seconds.

> Without a backend URL, the page still works: it shows default copy and falls back to a `mailto:` link for form submissions.

---

## Backend — Tailscale Funnel

Private FastAPI server with Claude integration. Runs on your machine and is exposed to the internet via Tailscale Funnel.

### Setup

**1. Install dependencies**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Set your API key**

```bash
cp .env.example .env
# Edit .env and paste your Anthropic API key
```

**3. Run the server**

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Verify it's up: http://localhost:8000/health

**4. Expose via Tailscale Funnel**

Install Tailscale if you haven't: https://tailscale.com/download

```bash
tailscale up
tailscale funnel 8000
```

Tailscale will print your public URL — something like:
```
https://your-machine.ts.net
```

That's your `BACKEND_URL` for `frontend/config.js`.

**5. Open the admin interface**

```
https://your-machine.ts.net/admin
```

---

## Workflow

1. **Admin**: Visit `/admin`, paste social media content (TikTok comments, X threads, YouTube video descriptions + comments, Facebook posts), click **Generate Funnel Copy**.
2. Claude analyzes the content, extracts pain points, and writes funnel copy.
3. The public frontend page at `https://YOUR_USERNAME.github.io/lead-generation-funnel/` automatically shows the new content.
4. Visitors enter their email → leads are saved to `backend/leads.db`.
5. View leads at `/admin` → Leads tab, or hit `GET /api/leads` directly.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/admin` | Admin UI |
| POST | `/api/analyze` | Generate funnel from social sources |
| GET | `/api/funnel` | Get latest generated funnel |
| POST | `/api/leads` | Capture a lead (email, name, role, niche) |
| GET | `/api/leads` | List all leads |

### `POST /api/analyze`

```json
{
  "sources": [
    {
      "platform": "tiktok",
      "url": "https://www.tiktok.com/@...",
      "text": "Paste the comments/captions here..."
    }
  ]
}
```

### `POST /api/leads`

```json
{
  "email": "user@example.com",
  "name": "Jane Doe",
  "role": "agency owner",
  "niche": "fitness coaches"
}
```

---

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS — no framework, no build step
- **Backend**: Python + FastAPI + Anthropic SDK (Claude)
- **Database**: SQLite (`leads.db`) — zero infrastructure
- **Hosting**: GitHub Pages (frontend) + Tailscale Funnel (backend)
