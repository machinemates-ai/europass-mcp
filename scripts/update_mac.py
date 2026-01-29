#!/usr/bin/env python3
"""Update MAC JSON with profile picture and full descriptions."""

import json
import base64
from pathlib import Path

# Paths
base_path = Path(__file__).parent.parent
input_path = base_path / "input"
mac_path = input_path / "gfortaine_mac.json"
photo_path = input_path / "images" / "profile.jpeg"

# Load MAC JSON
with open(mac_path, "r") as f:
    mac = json.load(f)

# Load profile picture and add as base64
with open(photo_path, "rb") as f:
    photo_data = base64.b64encode(f.read()).decode("utf-8")
    mac["profilePicture"] = photo_data

# Full descriptions from original Europass (HTML format)
full_descriptions = [
    # Job 1: RAJA Group - GenAI Specialist
    '<p><strong>Contexte :</strong> En tant que Spécialiste en IA Générative (LLM), pilotage de produits innovants centrés sur le <strong>RAG</strong> et les <strong>architectures agentiques</strong>.</p><ol><li data-list="bullet"><strong>Agent IA e-commerce (Projet Boxy)</strong> : Agent multimodal pour RAJA.</li><li data-list="bullet"><strong>Pipelines RAG avec LangChain</strong> : Systèmes RAG avec Azure OpenAI et pgvector.</li><li data-list="bullet"><strong>Systèmes Multi-Agents</strong> : Workflows LangGraph.</li><li data-list="bullet"><strong>Monitoring LangSmith</strong> : Debugging et évaluation des LLM.</li></ol><p><strong>Stack</strong> : Python, LangChain, LangGraph, LangSmith, FastAPI, Azure OpenAI, Next.js, Docker, Scrum.</p>',
    
    # Job 2: Ministère de l'Intérieur - Lead Dev Front
    '<p><strong>Contexte</strong> : Lead Dev Front pour le projet Plainte En Ligne (PEL) - portail gouvernemental.</p><ol><li data-list="bullet">Refonte pages responsives pour site à <strong>fort trafic</strong></li><li data-list="bullet"><strong>Accessibilité RGAA</strong> (score >= 75%)</li></ol><p><strong>Stack</strong> : Symfony, ES6/TypeScript, Tailwind CSS, PWA, Behat, GitLab CI/CD.</p>',
    
    # Job 3: Les Mousquetaires - Tech Lead
    '<p><strong>Contexte</strong> : Tech Lead site intermarche.com - Squad 15 personnes, <strong>SAFe SCRUM</strong>.</p><ol><li data-list="bullet">Architecture et évolution <strong>React/Next.js</strong></li><li data-list="bullet">Coaching équipes et coordination développements</li><li data-list="bullet">Migration Next.js v12 + CSS Modules @ scale</li></ol><p><strong>Stack</strong> : React.js, Next.js, TypeScript, Contentful, Jest, Playwright, GCP/K8s.</p>',
    
    # Job 4: Ingenico - Lead Front
    '<p><strong>Contexte</strong> : Lead Front chez Ingenico - leader mondial du paiement.</p><ol><li data-list="bullet">Architecture portails Web <strong>ReactJS/Redux/NextJS</strong></li><li data-list="bullet">Coaching équipes et résolution incidents complexes</li></ol><p><strong>Stack</strong> : ReactJS, NextJS, Scala, MUI, Kafka, ElasticSearch, AWS, Docker.</p>',
    
    # Job 5: TF1 - Developer
    '<p><strong>Contexte</strong> : Refonte site LCI.fr - 20M visiteurs/mois.</p><ol><li data-list="bullet">Fonctionnalités inter-navigateurs HTML/CSS/JavaScript</li></ol><p><strong>Stack</strong> : JavaScript ES6/ES7, Dust.js, HTML5, AMP, PostCSS, Gulp.</p>',
    
    # Job 6: Cdiscount - Developer
    '<p><strong>Contexte</strong> : Site e-commerce Top 15 français - 8M visiteurs/mois.</p><ol><li data-list="bullet">Implémentation <strong>ReactJS/Redux</strong></li></ol><p><strong>Stack</strong> : JavaScript ES6/ES7, ReactJS, Redux, Webpack2, Jest.</p>',
]

# Add fullDescription to each job role
jobs = mac.get("experience", {}).get("jobs", [])
for i, job in enumerate(jobs):
    if i < len(full_descriptions):
        for role in job.get("roles", []):
            role["fullDescription"] = full_descriptions[i]

# Save updated MAC JSON
with open(mac_path, "w") as f:
    json.dump(mac, f, indent=2, ensure_ascii=False)

print(f"✓ Updated MAC JSON with:")
print(f"  - Profile picture: {len(photo_data)} bytes (base64)")
print(f"  - Full descriptions: {len(full_descriptions)} jobs")
