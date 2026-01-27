# Talent - Europass CV Generator

Staffing and recruiting resources for Guillaume Fortaine — **LangChain Ambassador France**.

## 📁 Project Structure

```
Talent/
├── input/                    # Source files
│   ├── europass.xml          # CV data (Europass XML)
│   └── images/
│       ├── profile.jpeg
│       └── lanchainambassador.png
├── output/                   # Generated files (gitignored)
│   └── CV-Europass.pdf
├── src/                      # Python scripts
│   ├── europass_playwright.py
│   └── generate_enriched_europass.py
└── pyproject.toml            # Project config (uv)
```

## 🚀 Quick Start

```bash
# Install dependencies (uv)
uv sync
uv run playwright install chromium

# Generate PDF
uv run python src/europass_playwright.py
```

## 🔧 Options

```bash
python src/europass_playwright.py --help
python src/europass_playwright.py --visible          # Watch browser
python src/europass_playwright.py --template=cv-elegant
```

## Profile Highlights

**Guillaume FORTAINE** — Founder @ MachineMates.AI | Paris, France

### Current Roles
- 🚀 **Founder & AI Solutions Architect** at MachineMates.AI
- 🏆 **LangChain Forum Expert** (official recognition)
- 🌍 **LangChain Ambassador** for France

### Key Expertise (2025-2026)

#### Model Context Protocol (MCP)
- SEP-1686: Background Tasks & Asynchronous Workflows
- Server Elicitation (Form Mode & URL Mode per SEP-1036)
- SEP-1577: Agentic Sampling
- OAuth integration & Stateless Scaling

#### Vercel AI SDK v6
- Language Model Specification V3
- Custom Provider development
- ToolLoopAgent & Tool Execution Approval
- MCP integration (HTTP transport, OAuth, Resources, Prompts)

#### LangChain Ecosystem
- LangGraph: Multi-agent orchestration
- LangSmith: Production deployment & observability
- LangChain Adapters for AI SDK integration

#### Microsoft Foundry
- Microsoft Agent Framework SDK
- Entra Agent IDs & AgentOps
- MCP support in Azure Functions (GA Jan 2026)
- Computer Use & Browser Automation tools

## Regenerate CV

```bash
cd Talent
pip install reportlab
python generate_europass_cv.py
```

## Europass Format

[Europass](https://europass.europa.eu) is the EU-standard CV format:
- Recognized across all EU member states
- CEFR language proficiency levels
- Digital competences framework alignment

---

*MachineMates.AI — Building the agents of tomorrow*
