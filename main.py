import argparse
import json
import os
import re
import sys
from typing import Any

import io
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    import docx as _docx_module
except ImportError:
    _docx_module = None
from dotenv import load_dotenv

try:
    from openai import AzureOpenAI
except ImportError:
    AzureOpenAI = None

load_dotenv()

app = FastAPI(title="Naukri Boolean Builder", version="2.0.0")

cors_origins = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
allow_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class JDRequest(BaseModel):
    jd: str
    strictness: int = 3  # 1 = broad, 3 = balanced, 5 = strict


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a senior technical recruiter with 10+ years sourcing candidates on Naukri.com India.

CORE TRUTH: Candidates write resumes in their own words, not the JD's words. Your boolean
string must match how Indian candidates actually describe themselves on Naukri .

═══════════════════════════════════════
STEP 1 — EXTRACT SKILLS
═══════════════════════════════════════
Extract skills/technologies from the JD. Classify each and make sure not to use speaking languages and all :
- "must": Clearly required (mandatory section, repeated, listed prominently)
- "good": Preferred / nice-to-have ("familiarity", "exposure", "plus", "bonus", "good to have")

═══════════════════════════════════════
STEP 2 — ASSESS RESUME COVERAGE FOR EACH MUST-HAVE SKILL
═══════════════════════════════════════
For every must-have skill, ask two questions:
  Q1. Would Indian candidates write this exact term on their Naukri resume? (YES / PARTIAL / NO)
  Q2. How many candidates in India realistically have this on their profile? (HIGH / MEDIUM / LOW)

Then apply the correct strategy:

COVERAGE: HIGH + candidates write it directly
  → Use the term as-is with standard abbreviations only.
  → Example: "Windows 11" → ["Windows 10", "Win 11"]

COVERAGE: MEDIUM or term is domain-specific / niche
  → Keep the primary term. Add 2-3 alternate phrasings candidates actually use for the same thing.
  → CRITICAL: Do NOT replace the primary term. Keep it AND add fallbacks.
  → Example: "gaming" → ["gaming", "games", "gaming PC", "gamer"]
  → Example: "GPU troubleshooting" → ["GPU", "graphics card", "display adapter", "Nvidia", "AMD"]
  → Example: "overclocking" → ["overclocking", "OC", "thermal management", "CPU tuning"]

COVERAGE: LOW (very niche, coined, or rare term)
  → Keep the exact term AND add its parent category as a wide-net fallback.
  → Example: "eBPF" → ["eBPF", "Linux kernel", "kernel networking"]
  → Example: "Weaviate" → ["Weaviate", "vector database", "vector store"]

BANNED — never use these in the boolean string:
✗ Full sentences from the JD ("Fluency in spoken and written English", "Fluency in Hindi")
✗ Threshold/criteria phrases ("Typing speed", "2+ years experience", "25 WPM", "minimum experience")
✗ Vague capability phrases ("gaming experience", "PC hardware knowledge", "strong troubleshooting")
✗ Generic soft skills ("problem-solving", "communication skills", "team player")
✗ Long brand+product strings ("Lenovo Legion Series laptop", "HP Omen gaming laptop")
✗ Composite job titles that don't exist as designations ("gaming support", "gaming technical support")
✗ Generic language phrases ("regional language", "local language") — use actual language names only
✗ Any phrase containing the word "experience" — it is always JD language, never resume language

SPECIFIC PHRASES PERMANENTLY BANNED (seen causing bad output — never use under any circumstance):
  "gaming support", "gaming experience", "regional language", "local language",
  "PC hardware knowledge", "gaming technical", "hardware knowledge", "support experience"

ALLOWED resume-language terms:
✓ Short technology/skill names: GPU, CPU, BIOS, Steam, "Windows 11", "graphic card"
✓ Domain terms candidates use: gaming, gamer, "gaming PC", FPS, lag, latency
✓ Job function terms: "technical support", "customer support", "L1 support", "tech support"
✓ Language skills as single words: Hindi, English, Telugu, Tamil

═══════════════════════════════════════
STEP 3 — BUILD THE BOOLEAN STRING
═══════════════════════════════════════
Structure in TWO tiers:

TIER 1 — CORE MUST-HAVES (3-5 blocks joined with AND):
  Each block covers one distinct must-have skill cluster.
  Block format: (primary_term OR fallback1 OR fallback2)
  Every block MUST be in its own parentheses.

TIER 2 — NICHE/RARE CLUSTER (optional, one OR block appended with AND):
  Group multiple low-coverage niche terms together:
  AND (niche_term1 OR fallback1 OR niche_term2 OR fallback2)

BLOCK ORDER — MANDATORY:
  Order blocks by SPECIFICITY descending — the most domain-specific term first,
  the most generic term (job function / years of experience) LAST.
  Rule: If the JD has a domain specialisation (gaming, finance, healthcare, e-commerce…)
  that domain block MUST come before "technical support", "customer support", etc.
  WRONG: ("technical support" OR "L1 support") AND (gaming OR gamer)
  RIGHT:  (gaming OR gamer OR "gaming PC") AND ("technical support" OR "L1 support")
  NEVER place job function first when a domain specialisation exists.

PARENTHESES — mandatory for Naukri to parse correctly:
  CORRECT: (A OR B) AND (C OR D) AND (E OR F)
  WRONG:   A OR B AND C OR D          ← operator precedence broken
  WRONG:   (A OR B AND C OR D)        ← mixed operators inside one block

OTHER RULES:
- Multi-word phrases MUST be in double quotes.
- Single words do NOT need quotes: GPU, gaming, Hindi, Steam
- Final string MUST be ≤ 500 characters. Drop lowest-priority blocks from end if needed.
- Do NOT use NOT, wildcards (*), or field-specific operators.
- Do NOT include good-to-have skills unless must-haves alone give fewer than 3 blocks.

═══════════════════════════════════════
WORKED EXAMPLES
═══════════════════════════════════════
EXAMPLE 1 — GAMING TECH SUPPORT (niche domain term: "gaming")
JD requires: gaming knowledge, PC hardware, Windows OS, technical support, English+Hindi, regional language

WRONG output:  ("gaming support" OR "technical support") AND ("gaming experience" OR "gaming PC") AND (English OR Hindi OR "regional language")
WRONG because: "gaming support" = fake designation. "gaming experience" = JD phrase. "regional language" = not a resume term.

RIGHT output:  (gaming OR gamer OR "gaming PC" OR Steam OR FPS) AND ("technical support" OR "customer support" OR "L1 support") AND (GPU OR CPU OR "PC hardware" OR "graphic card") AND ("Windows 10" OR "Windows 11") AND (English OR Hindi)
RIGHT because:
  - Domain first: gaming block leads because it is the domain specialisation.
  - Job function second: "technical support" / "customer support" / "L1 support"
  - Hardware: actual component names (GPU, CPU, "PC hardware", "graphic card")
  - Gaming domain: primary term "gaming" kept, expanded with how gamers self-describe (gamer, Steam, FPS)
  - Language: just the actual language names (English, Hindi) — NOT "regional language"
  - "gaming support" does not appear anywhere. "gaming experience" does not appear anywhere.
  NEVER put job function first unless there is no domain specialisation

EXAMPLE 2 — VECTOR DB ENGINEER (rare term: "Weaviate")
JD requires: Weaviate, Python, REST APIs

RIGHT: (Weaviate OR "vector database" OR "vector store") AND Python AND ("REST API" OR RESTful)
WHY RIGHT: Weaviate kept as primary. "vector database" catches candidates who didn't write Weaviate.

EXAMPLE 3 — KERNEL ENGINEER (niche: "eBPF")
JD requires: eBPF, Linux, C programming

RIGHT: (eBPF OR "Linux kernel" OR XDP) AND Linux AND (C OR "C programming" OR "systems programming")
WHY RIGHT: eBPF kept. Linux kernel and XDP are genuine co-occurring terms on such resumes.

═══════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════
Return ONLY a JSON object — no preamble, no markdown fences:
{
  "skills": [
    {
      "name": "<short resume-language skill name>",
      "type": "must|good",
      "rarity": "common|niche|rare",
      "coverage": "high|medium|low",
      "synonyms": ["<resume-language fallback terms>"],
      "evidence": "<short direct quote from JD, max 12 words>"
    }
  ],
  "boolean_string": "<properly parenthesised boolean query, ≤500 chars>",
  "boolean_char_count": <integer>,
  "reasoning": "<2-3 sentences: coverage assessment for key terms, how niche terms were expanded with fallbacks, how 500 char limit was handled>"
}"""

# ---------------------------------------------------------------------------
# Strictness instruction addendums (appended to system prompt at runtime).
# EACH LEVEL MUST PRODUCE A VISIBLY DIFFERENT BOOLEAN STRING.
# ---------------------------------------------------------------------------
STRICTNESS_INSTRUCTIONS: dict[int, str] = {
    1: """
=== STRICTNESS OVERRIDE: LEVEL 1 (VERY BROAD) ===
Target: Maximum candidate reach. Your output MUST be noticeably simpler
than level 3 — far fewer AND blocks, far more OR terms per block.
MANDATORY:
  AND-block count : exactly 2-3 blocks total.
  Synonyms/block  : 5-7 terms per block.
  Good-to-haves   : INCLUDE top 2 as extra OR terms.
  No version numbers, no niche sub-terms — use category names.
EXAMPLE (gaming support JD):
  RIGHT:  (gaming OR gamer OR "gaming PC" OR FPS OR Steam OR "PC games" OR esports) AND ("technical support" OR "customer support" OR "L1 support" OR "help desk" OR support OR troubleshooting OR "tech support")
  WRONG:  (gaming OR gamer) AND ("technical support" OR "customer support") AND (GPU OR CPU) AND (Hindi OR English)
""",
    2: """
=== STRICTNESS OVERRIDE: LEVEL 2 (BROAD) ===
Target: Wide net with some precision anchors.
MANDATORY:
  AND-block count : exactly 3 blocks.
  Synonyms/block  : 4-5 terms per block.
  Good-to-haves   : INCLUDE top 1 as an extra OR term.
EXAMPLE (gaming support JD):
  RIGHT:  (gaming OR gamer OR "gaming PC" OR FPS OR Steam) AND ("technical support" OR "customer support" OR "L1 support" OR "tech support") AND (GPU OR CPU OR "PC hardware" OR "graphic card")
""",
    3: """
=== STRICTNESS OVERRIDE: LEVEL 3 (BALANCED, DEFAULT) ===
Target: Standard output. Follow the base STEP 3 rules exactly.
MANDATORY:
  AND-block count : 4-5 blocks.
  Synonyms/block  : 2-3 terms per block.
  Good-to-haves   : Exclude unless fewer than 3 must-have blocks.
EXAMPLE (gaming support JD):
  RIGHT:  (gaming OR gamer OR "gaming PC") AND ("technical support" OR "customer support" OR "L1 support") AND (GPU OR CPU OR "PC hardware") AND ("Windows 10" OR "Windows 11") AND (Hindi OR English)
""",
    4: """
=== STRICTNESS OVERRIDE: LEVEL 4 (STRICT) ===
Target: Narrower candidate pool.
MANDATORY:
  AND-block count : 5-6 blocks. Each must-have gets its OWN block.
  Synonyms/block  : 1-2 terms MAXIMUM. Common terms get 0 synonyms.
  Good-to-haves   : EXCLUDE entirely.
  Use exact quoted JD phrases where possible.
EXAMPLE (gaming support JD):
  RIGHT:  (gaming OR gamer) AND "technical support" AND (GPU OR "graphic card") AND "Windows 11" AND Hindi AND English
""",
    5: """
=== STRICTNESS OVERRIDE: LEVEL 5 (VERY STRICT) ===
Target: Exact-match candidates only.
MANDATORY:
  AND-block count : 6-7 blocks.
  Synonyms/block  : ZERO synonyms for common/high-coverage terms.
                   ONE synonym ONLY for rare/niche terms.
  Good-to-haves   : EXCLUDE. No exceptions.
  Use exact quoted JD phrases verbatim.
EXAMPLE (gaming support JD):
  RIGHT:  gaming AND "technical support" AND GPU AND "Windows 11" AND Hindi AND English
  No OR alternatives for common terms — that is correct and intentional for level 5.
""",
}


# ---------------------------------------------------------------------------
# Azure OpenAI client
# ---------------------------------------------------------------------------
def _get_client() -> "AzureOpenAI":
    if AzureOpenAI is None:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview").strip()

    if not endpoint or not api_key:
        raise RuntimeError(
            "Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY in .env"
        )

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _enforce_500_char_limit(boolean_string: str) -> str:
    """Hard-enforce 500 char limit by dropping trailing AND blocks until it fits."""
    if len(boolean_string) <= 500:
        return boolean_string

    blocks = boolean_string.split(" AND ")
    while len(blocks) > 1:
        blocks.pop()
        candidate = " AND ".join(blocks)
        if len(candidate) <= 500:
            return candidate

    return blocks[0][:500]


def _extract_first_json(text: str) -> dict[str, Any]:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Model did not return valid JSON.")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Parsed JSON is not an object.")
    return payload


def _normalize_skills(raw: list) -> list[dict[str, Any]]:
    normalized = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())

        skill_type = str(item.get("type", "good")).strip().lower()
        if skill_type not in ("must", "good"):
            skill_type = "good"

        rarity = str(item.get("rarity", "common")).strip().lower()
        if rarity not in ("common", "niche", "rare"):
            rarity = "common"

        coverage = str(item.get("coverage", "high")).strip().lower()
        if coverage not in ("high", "medium", "low"):
            coverage = "high"

        synonyms = item.get("synonyms", [])
        if not isinstance(synonyms, list):
            synonyms = []
        synonyms = [str(s).strip() for s in synonyms if str(s).strip()]

        evidence = str(item.get("evidence", "")).strip()

        normalized.append({
            "name": name,
            "type": skill_type,
            "rarity": rarity,
            "coverage": coverage,
            "synonyms": synonyms,
            "evidence": evidence,
        })

    # Must-haves first, then good-to-haves; alphabetical within each group
    normalized.sort(key=lambda s: (0 if s["type"] == "must" else 1, s["name"].lower()))
    return normalized


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------
def extract_from_jd(jd_text: str, strictness: int = 3) -> dict[str, Any]:
    client = _get_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini").strip()

    strictness_clamped = max(1, min(5, strictness))
    effective_prompt = SYSTEM_PROMPT + STRICTNESS_INSTRUCTIONS.get(strictness_clamped, "")

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": effective_prompt},
            {"role": "user", "content": f"Job Description:\n\n{jd_text}"},
        ],
        temperature=0.0,
        top_p=1.0,
        max_tokens=2048,
    )

    raw_text = response.choices[0].message.content or ""
    payload = _extract_first_json(raw_text)

    skills = _normalize_skills(payload.get("skills", []))
    boolean_string = str(payload.get("boolean_string", "")).strip()
    boolean_string = _enforce_500_char_limit(boolean_string)
    reasoning = str(payload.get("reasoning", "")).strip()

    return {
        "skills": skills,
        "boolean_string": boolean_string,
        "boolean_char_count": len(boolean_string),
        "reasoning": reasoning,
        "strictness": strictness_clamped,
    }


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------
@app.post("/api/extract")
def extract_api(payload: JDRequest) -> dict[str, Any]:
    jd_text = payload.jd.strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="JD text is required.")
    try:
        return extract_from_jd(jd_text, strictness=payload.strictness)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc


# ---------------------------------------------------------------------------
# File text extraction helpers
# ---------------------------------------------------------------------------
def _extract_text_from_pdf(data: bytes) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed.")
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def _extract_text_from_docx(data: bytes) -> str:
    if _docx_module is None:
        raise RuntimeError("python-docx is not installed.")
    doc = _docx_module.Document(io.BytesIO(data))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip()).strip()


@app.post("/api/extract-file")
async def extract_file_api(
    file: UploadFile = File(...),
    strictness: int = 3,
) -> dict:
    filename = (file.filename or "").lower()
    if not any(filename.endswith(ext) for ext in (".pdf", ".doc", ".docx")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Please upload a PDF, DOC, or DOCX file.",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        if filename.endswith(".pdf"):
            jd_text = _extract_text_from_pdf(data)
        else:
            jd_text = _extract_text_from_docx(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not read file: {exc}") from exc

    if not jd_text:
        raise HTTPException(status_code=422, detail="No readable text found in the uploaded file.")

    try:
        result = extract_from_jd(jd_text, strictness=strictness)
        result["extracted_text_preview"] = jd_text[:400]
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}") from exc


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Naukri Boolean Builder — extract skills and generate boolean search strings from JDs."
    )
    parser.add_argument("--jd", help="Job description text.")
    parser.add_argument("--jd-file", help="Path to a file containing the JD.")
    parser.add_argument("--json", action="store_true", help="Output raw JSON.")
    parser.add_argument("--serve", action="store_true", help="Run the API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def _read_jd(args: argparse.Namespace) -> str:
    if args.jd:
        return args.jd.strip()
    if args.jd_file:
        with open(args.jd_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    if not sys.stdin.isatty():
        return sys.stdin.read().strip()
    raise SystemExit("No JD provided. Use --jd, --jd-file, or pipe to stdin.")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.serve:
        import uvicorn
        uvicorn.run("main:app", host=args.host, port=args.port, reload=False)
        return

    jd_text = _read_jd(args)
    if not jd_text:
        raise SystemExit("JD is empty.")

    result = extract_from_jd(jd_text)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    print("\nExtracted Skills:")
    for i, s in enumerate(result["skills"], 1):
        syn = f" ({', '.join(s['synonyms'])})" if s["synonyms"] else ""
        print(f"  {i}. [{s['type'].upper()}][{s['rarity']}] {s['name']}{syn}")

    print(f"\nNaukri Boolean String ({result['boolean_char_count']} chars):")
    print(f"  {result['boolean_string']}")

    if result.get("reasoning"):
        print(f"\nReasoning: {result['reasoning']}")


if __name__ == "__main__":
    main()