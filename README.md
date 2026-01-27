# Talent - Europass CV Generator

Staffing and recruiting resources for Guillaume Fortaine — **LangChain Ambassador France**.

## 📁 Files

| File | Description |
|------|-------------|
| **CV-Europass-Authentic.odt** | ⭐ Authentic ODT (open in LibreOffice → Export PDF) |
| **CV-Europass-Enriched-2026.pdf** | Ready-to-use PDF with enriched content |
| **europass_profile.json** | JSON for official Europass API |
| **CV-Europass-20250917-Fortaine-FR.pdf** | Original source PDF |

## 🔧 Scripts

| Script | Purpose |
|--------|---------|
| `generate_europass_odt.py` | Creates authentic ODT (official Europass approach) |
| `generate_europass_fpdf.py` | Generates PDF with fpdf2 |
| `europass_api_client.py` | Generates JSON for Europass ePortfolio API |

## 🚀 Quick Start

```bash
# Generate ODT with authentic Europass styling
python3 generate_europass_odt.py

# Generate PDF directly
uv run --with pypdf,fpdf2 generate_europass_fpdf.py
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
