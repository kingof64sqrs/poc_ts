## JD Skills Extractor (Codestral + uv)

This script takes a Job Description (JD) as input and lists all required skills.

### 1. Install dependencies (uv only)

```bash
uv sync
```

### 2. Set Codestral environment variables

```bash
export CODESTRAL_ENDPOINT="https://<your-host>.services.ai.azure.com/models/chat/completions"
export CODESTRAL_API_KEY="<your-api-key>"
export CODESTRAL_MODEL="Codestral-2501"
export CODESTRAL_API_VERSION="2024-05-01-preview"
```

Or create a local `.env` file (auto-loaded by the app):

```env
CODESTRAL_ENDPOINT=https://<your-host>.services.ai.azure.com/models/chat/completions
CODESTRAL_API_KEY=your_key_here
CODESTRAL_MODEL=Codestral-2501
CODESTRAL_API_VERSION=2024-05-01-preview
REDIRECT_URL=https://www.microsoft.com
```

Output includes:
- Structured skills list
- Naukri-ready boolean search string

### 3. Run with `uv` (CLI)

Use inline JD text:

```bash
uv run main.py --jd "We need a Python backend engineer with FastAPI, Azure, Docker, CI/CD and communication skills."
```

Use a JD file:

```bash
uv run main.py --jd-file jd.txt
```

Use stdin piping:

```bash
cat jd.txt | uv run main.py
```

JSON output:

```bash
uv run main.py --jd-file jd.txt --json
```

## Web UI

You can use a professional web UI to paste the JD and get skills with copy buttons.

Optional redirect target for the `Redirect` button:

```bash
export REDIRECT_URL="https://your-app.example.com"
```

Start the web app:

```bash
uv run main.py --serve --host 0.0.0.0 --port 8000
```

Open in browser:

```text
http://localhost:8000
```

UI features:
- Paste JD and extract skills
- Clean categorized skill cards
- Copy button on each skill
- Copy all skill names
- Redirect button to your configured URL

## Separate React Frontend

This repo now includes a separate React app in `frontend/` that calls the backend API.

### 1. Start backend API (FastAPI)

```bash
uv run main.py --serve --host 0.0.0.0 --port 8000
```

### 2. Start React app

```bash
cd frontend
npm install
npm run dev
```

Open: `http://localhost:5173`

The React app calls:
- `POST http://localhost:8000/api/extract`

Frontend env example is in `frontend/.env.example`.
