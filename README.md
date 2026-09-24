# Resume Worker

A local web app that tailors your résumé for a specific job posting using an LLM — and builds the
complete application kit around it: company research, a cover letter, interview questions, and tips.
For now working with Canada

## What you get

Provide your **résumé** (PDF/DOCX upload or pasted text), optionally the **job description** and
**company**, and your **seniority level** — every output is tailored to the **Canadian** job market:

| Section | Content |
|---|---|
| **Résumé** | Rewritten for the posting in the Canadian format (fixed section order: header, summary, experience, education, skills, projects, certifications, languages; CAR impact bullets; key skills/metrics rendered **in bold**; ATS-safe) with one-click **PDF download** |
| **Company** | What they do, products/tech stack, culture, why this role matters, and their interview process when it can be found online |
| **Cover letter** | Tone, length and structure calibrated to the role's seniority and Canadian business culture |
| **Interview prep** | HR + technical questions with answer tips; expands into per-stage question sets when real interview-process info is found |
| **Tips** | Canadian workplace-culture norms, application best practices, interview-day tips, and notes on how your résumé was adapted |

Leave the **job description blank** to get a general Canadian-format résumé instead of a targeted
one — the cover letter then becomes a reusable template with `[Company Name]` placeholders, and
the company tab is hidden unless a company is given. Side/personal projects are included only when
they genuinely support the target role. The app never invents experience: it only rephrases/realigns
what is already in your base résumé (plus whatever you answer in the intake questions).

## Optional intake questions

By default (checkbox on the form), after you submit, the app asks 4–6 short questions about things
your résumé doesn't quantify — scale of ownership, %/$ impact, timeframes, tools. Answering is
entirely optional: blanks are skipped, and your answers are treated as source material so real KPIs
can land in your bullets. Uncheck the box to generate immediately.

## Iterate on the result

Not happy with something? On the results page, the Résumé tab has a **Request changes** box:
type what you want adjusted (reorder engagements, shorten the summary, reword a bullet…) and hit
**Apply changes**. The résumé is rewritten in place under the same URL — you can iterate as many
times as you like, and the PDF download always reflects the latest version. Company research, cover
letter and interview prep are left untouched.

## Setup

Requirements: Python 3.11+, plus WeasyPrint system libraries for PDF generation.

```bash
# 1. System libs for PDF export (Debian/Ubuntu/WSL2)
sudo apt install libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libcairo2

# 2. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Configuration
cp .env.example .env        # then edit .env with your API keys
```

### API keys

| Key | Required | Purpose |
|---|---|---|
| `LLM_API_KEY` | Yes (except Ollama) | Provider-agnostic key for any model (Google Gemini, OpenRouter, OpenAI, Groq, Anthropic, etc.) |
| `TAVILY_API_KEY` | Recommended | Live web research about the company ([free tier](https://tavily.com)). Without it the app falls back to the model's own knowledge |

Pick any model by changing `LLM_MODEL`, e.g. `gemini/gemini-3.8-flash`,
`openrouter/anthropic/claude-sonnet-4.5`, `groq/llama-3.3-70b-versatile`, `openai/gpt-4o`, or point directly at Ollama (`ollama/llama3.1`) for a
fully local setup.

## Run

```bash
.venv/bin/uvicorn app.main:app --reload
```

Open http://localhost:8000 , fill the form, and hit **Generate application kit**
(typically 30–90 s). Results are kept in memory (last 20 runs) at shareable `/result/{id}` URLs
for the lifetime of the server process.

## How it works

```
upload/paste ──► parse ──► web research (Tavily, optional) ──► ONE structured LLM call
                                                                    │  (JSON schema-validated,
                                                                    ▼   retry once if malformed)
                     tabbed results page ◄── ApplicationKit (resume, company, letter,
                                │            questions, tips)
                                └──► WeasyPrint ──► ATS PDF download
```

- **Structured output**: the entire kit is returned as a single Pydantic-validated JSON object
  (`app/schemas.py` is the contract between prompt, code and UI).
- **Adaptive interview prep**: per-stage questions are generated only when research confirms the
  company's actual hiring process; otherwise generic HR + technical sets.
- **Honesty guardrails**: the system prompt forbids fabricated employers/dates/skills.

## Project layout

```
app/
├── main.py              # routes: / , /generate , /result/{id} , /download/{id}
├── config.py            # env-driven settings (.env)
├── schemas.py           # form inputs + ApplicationKit structured output model
├── prompts.py           # system & user prompts
├── services/
│   ├── parser.py        # PDF/DOCX/TXT text extraction
│   ├── research.py      # Tavily search wrapper (+ graceful no-key fallback)
│   ├── generator.py     # pipeline orchestration, LiteLLM call, validation retry
│   └── pdf.py           # WeasyPrint HTML→PDF rendering
├── templates/           # base / index / result / resume_pdf (ATS layout)
└── static/style.css
```

## Notes & limitations

- Results are stored in memory — restarting the server clears them. Download your PDF first.
- Generated content is AI-assisted: always review before applying.
- The PDF uses US Letter with standard fonts (Arial), single column, no tables/graphics — the
  layout most ATS parsers handle reliably.
