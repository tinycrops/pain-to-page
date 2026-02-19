import os
import json
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import openai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "leads.db"

_client: Optional[openai.OpenAI] = None


def get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY not set")
        _client = openai.OpenAI(api_key=api_key)
    return _client


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS funnels (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pain_points      TEXT    NOT NULL,
            headline         TEXT    NOT NULL,
            subheadline      TEXT    NOT NULL,
            problem_section  TEXT    NOT NULL,
            solution_section TEXT    NOT NULL,
            features         TEXT    NOT NULL,
            cta              TEXT    NOT NULL,
            cta_subtext      TEXT    NOT NULL,
            sources          TEXT    NOT NULL,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS leads (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT    NOT NULL,
            name       TEXT,
            role       TEXT,
            niche      TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(email)
        );
    """)
    conn.commit()
    conn.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Pain-to-Page API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------- Models ----------

class Source(BaseModel):
    platform: str           # tiktok | x | youtube | facebook | other
    url: Optional[str] = None
    text: str               # pasted content from the page


class AnalyzeRequest(BaseModel):
    sources: list[Source]


class LeadRequest(BaseModel):
    email: str
    name: Optional[str] = None
    role: Optional[str] = None
    niche: Optional[str] = None


# ---------- Endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
def admin():
    html_path = BASE_DIR / "admin.html"
    if not html_path.exists():
        raise HTTPException(404, "admin.html not found")
    return html_path.read_text()


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    if not req.sources:
        raise HTTPException(400, "Provide at least one source")

    blocks = []
    for s in req.sources:
        block = f"Platform: {s.platform.upper()}"
        if s.url:
            block += f"\nURL: {s.url}"
        block += f"\n\nContent:\n{s.text[:4000]}"
        blocks.append(block)

    combined = "\n\n" + ("=" * 60) + "\n\n".join(blocks)

    prompt = f"""You are analyzing social media content to identify the real, explicit pain points that people in this community express. Your goal is to generate compelling sales funnel copy for a software product called "Pain-to-Page" that solves these exact problems.

Pain-to-Page is a SaaS tool that:
- Takes social media links as input (TikTok, X/Twitter, YouTube Shorts, Facebook)
- Automatically extracts the recurring pain points and buying triggers from those posts
- Generates a ready-to-use landing page draft written in the customer's own language
- Helps founders, agencies, and consultants validate and launch offers faster

Social media content to analyze:
{combined}

Return ONLY valid JSON (no markdown fences, no explanation) with this exact structure:
{{
  "pain_points": [
    "Specific verbatim-style pain point from the content",
    "Specific verbatim-style pain point from the content",
    "Specific verbatim-style pain point from the content",
    "Specific verbatim-style pain point from the content",
    "Specific verbatim-style pain point from the content"
  ],
  "headline": "Bold, direct headline addressing the single biggest pain (10 words max)",
  "subheadline": "One sentence expanding on the value: what Pain-to-Page does and why it matters",
  "problem_section": "2-3 sentences describing the core problem these people face, using their language",
  "solution_section": "2-3 sentences explaining how Pain-to-Page solves it, concretely",
  "features": [
    {{"title": "Short feature name", "description": "One sentence on the specific benefit"}},
    {{"title": "Short feature name", "description": "One sentence on the specific benefit"}},
    {{"title": "Short feature name", "description": "One sentence on the specific benefit"}}
  ],
  "cta": "Beta access button text (3-5 words)",
  "cta_subtext": "Short reassurance line (e.g. 'Free during beta · No credit card needed')"
}}"""

    client = get_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    result = json.loads(raw)

    conn = get_db()
    conn.execute(
        """INSERT INTO funnels
           (pain_points, headline, subheadline, problem_section, solution_section,
            features, cta, cta_subtext, sources)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            json.dumps(result["pain_points"]),
            result["headline"],
            result["subheadline"],
            result["problem_section"],
            result["solution_section"],
            json.dumps(result["features"]),
            result["cta"],
            result.get("cta_subtext", "Free during beta · No credit card needed"),
            json.dumps([s.dict() for s in req.sources]),
        ),
    )
    conn.commit()
    conn.close()
    return result


@app.get("/api/funnel")
def get_funnel():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM funnels ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if not row:
        return None

    return {
        "pain_points":      json.loads(row["pain_points"]),
        "headline":         row["headline"],
        "subheadline":      row["subheadline"],
        "problem_section":  row["problem_section"],
        "solution_section": row["solution_section"],
        "features":         json.loads(row["features"]),
        "cta":              row["cta"],
        "cta_subtext":      row["cta_subtext"],
        "generated_at":     row["created_at"],
    }


@app.post("/api/leads")
def capture_lead(lead: LeadRequest):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO leads (email, name, role, niche) VALUES (?, ?, ?, ?)",
            (lead.email, lead.name, lead.role, lead.niche),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # already on the list — silently succeed
    finally:
        conn.close()
    return {"success": True}


@app.get("/api/leads")
def list_leads():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, email, name, role, niche, created_at FROM leads ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
