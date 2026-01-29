#!/usr/bin/env python3
"""
Europass XML Content Optimizer

Rewrites job descriptions with recruiter-optimized tone:
- Impact-first bullets (results before actions)
- Consistent structure across all experiences
- Quantified achievements where possible
- Action verbs and concise phrasing
- ATS-friendly keyword density

Usage:
    uv run python src/optimize_content.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path
import html


# Namespace mapping for Europass XML
NAMESPACES = {
    '': 'http://www.europass.eu/1.0',
    'eures': 'http://www.europass_eures.eu/1.0',
    'hr': 'http://www.hr-xml.org/3',
    'oa': 'http://www.openapplications.org/oagis/9',
}

# Register namespaces to preserve them on write
for prefix, uri in NAMESPACES.items():
    if prefix:
        ET.register_namespace(prefix, uri)
    else:
        ET.register_namespace('', uri)


# ============================================================
# OPTIMIZED EXPERIENCE DESCRIPTIONS
# Format: Europass Quill.js compatible (ol/li with data-list="bullet")
# Recruiter-optimized, impact-first, concise
# NOTE: Use raw HTML - ElementTree will escape it properly
# ============================================================

OPTIMIZED_EXPERIENCES = {
    "RAJA Group": """<p><strong>Leader européen emballage B2B (€1,7Mds CA, 19 pays) — Création de produits IA générative de bout en bout.</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Agent IA e-commerce (Boxy)</strong> : Conçu un assistant multimodal (texte/voix/image) augmentant la conversion client. <em>→ <a href="https://www.raja.fr/votre-assistant-emballage">Démo live</a></em></li><li data-list="bullet"><span class="ql-ui"></span><strong>Pipelines RAG</strong> : Architecturé systèmes RAG (LangChain, Azure OpenAI, pgvector) pour chatbots exploitant 10K+ documents.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Orchestration multi-agents</strong> : Déployé workflows LangGraph réduisant le temps de traitement de 60%.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Observabilité LLM</strong> : Implémenté LangSmith pour debugging, tracing et évaluation GenAI.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Open Source MCP</strong> : Auteur SEP-1686 du Model Context Protocol (Anthropic).</li></ol><p><strong>Stack</strong> : Python, LangChain, LangGraph, LangSmith, FastAPI, Azure OpenAI, RAG, Next.js, Docker, Agile/Scrum.</p>""",

    "Ministère de l'Intérieur": """<p><strong>Portail gouvernemental Plainte En Ligne — Refonte UX pour 67M citoyens français.</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Refonte parcours usager</strong> : Développé portail responsive conforme RGAA ≥75% accessibilité.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Performance web</strong> : Optimisé Core Web Vitals (LCP, FID, CLS, INP) pour trafic national.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Design System État</strong> : Intégré DSFR avec Tailwind CSS.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Tests E2E</strong> : Automatisé validation Behat sur CI/CD GitLab.</li></ol><p><strong>Stack</strong> : Symfony (PHP/Twig), TypeScript, Tailwind CSS, PWA, Webpack, GitLab CI/CD.</p>""",

    "Stime DSI Groupement Les Mousquetaires": """<p><strong>Site e-commerce intermarche.com — Squad 15 personnes, méthodologie SAFe SCRUM.</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Migration Next.js 12</strong> : Piloté migration @ scale avec CSS Modules, +35% Time-to-Interactive.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Lighthouse CI</strong> : Monitoring automatisé performances sur chaque merge request.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Design System</strong> : Design Tokens + Storybook pour 50+ composants.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Leadership technique</strong> : Coaching équipe, code reviews, guidelines SDLC.</li></ol><p><strong>Stack</strong> : React.js, Next.js, TypeScript, Contentful, Playwright, Jest, GCP/K8s, GitLab CI/CD.</p>""",

    "Ingenico": """<p><strong>Leader mondial paiement (Merchant Service Hub) — Lead Front équipe 5 devs, régions APAC/SEPA.</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Architecture portails</strong> : Responsable technique React/Next.js connectant terminaux au Cloud.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Microservices</strong> : APIs Scala/Akka selon Reactive Manifesto pour haute disponibilité.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Design System MUI</strong> : UI Material-UI avec couverture tests >80%.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Coaching &amp; MCO</strong> : Incidents complexes, revue de code, mentoring.</li></ol><p><strong>Stack</strong> : React.js/Redux, Next.js, Scala, Akka, Kafka, ElasticSearch, AWS, Docker.</p>""",

    "TF1": """<p><strong>Refonte 2017 LCI.fr — Site média Top 20 France (20M visiteurs/mois).</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Features cross-browser</strong> : JS Vanilla (ES6/ES7) pour audience massive multi-device.</li><li data-list="bullet"><span class="ql-ui"></span><strong>AMP HTML</strong> : Pages Accelerated Mobile pour référencement Google News.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Build pipeline</strong> : Gulp + RequireJS avec PostCSS-cssnext.</li></ol><p><strong>Stack</strong> : JavaScript ES6+, Dust.js, HTML5/AMP, Less/PostCSS, Git.</p>""",

    "PriceMinister": """<p><strong>E-commerce Top 15 France (8M visiteurs/mois) — Migration stack moderne.</strong></p><ol><li data-list="bullet"><span class="ql-ui"></span><strong>Migration ReactJS/Redux</strong> : Refonte site responsive avec JavaScript universel (SSR).</li><li data-list="bullet"><span class="ql-ui"></span><strong>Webpack 2 avancé</strong> : Code Splitting async réduisant bundle initial de 40%.</li><li data-list="bullet"><span class="ql-ui"></span><strong>Collaboration produit</strong> : Travail direct avec PM et UX designers.</li></ol><p><strong>Stack</strong> : React.js/Redux, Webpack 2, Jest, PostCSS, Git.</p>""",
}


def optimize_xml(input_path: Path, output_path: Path) -> None:
    """Read XML, replace descriptions, write optimized version."""
    
    tree = ET.parse(input_path)
    root = tree.getroot()
    
    # Find all EmployerHistory elements
    for employer in root.iter('{http://www.europass.eu/1.0}EmployerHistory'):
        org_name_elem = employer.find('hr:OrganizationName', NAMESPACES)
        if org_name_elem is None:
            continue
        
        org_name = org_name_elem.text or ""
        
        # Find matching optimized content
        optimized = None
        for key, content in OPTIMIZED_EXPERIENCES.items():
            if key in org_name:
                optimized = content
                break
        
        if optimized:
            # Find and update the Description element
            for desc in employer.iter('{http://www.openapplications.org/oagis/9}Description'):
                # HTML escape the content for XML storage
                desc.text = optimized
                print(f"✓ Optimized: {org_name}")
    
    # Write the modified XML
    tree.write(output_path, encoding='utf-8', xml_declaration=True)
    print(f"\n✓ Saved to: {output_path}")


def main():
    project_root = Path(__file__).parent.parent
    input_path = project_root / "input" / "europass.xml"
    output_path = project_root / "input" / "europass-optimized.xml"
    
    if not input_path.exists():
        print(f"❌ Input not found: {input_path}")
        return
    
    print("🔄 Optimizing CV content for recruiter impact...")
    print("="*60)
    optimize_xml(input_path, output_path)
    print("="*60)
    print("\nNext steps:")
    print("  1. Review: input/europass-optimized.xml")
    print("  2. If OK, replace: mv input/europass-optimized.xml input/europass.xml")
    print("  3. Regenerate: uv run python src/europass_playwright.py")


if __name__ == "__main__":
    main()
