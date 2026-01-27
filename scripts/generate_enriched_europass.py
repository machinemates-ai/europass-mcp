#!/usr/bin/env python3
"""
Europass CV Enrichment + Authentic PDF Generation

This script:
1. Extracts the embedded XML from the original Europass PDF
2. Enriches it with new experiences (MachineMates.AI, MCP, AI SDK, LangGraph, LangChain Ambassador)
3. Removes the website field
4. Saves the enriched XML for import into Europass portal

The enriched XML can be imported at https://europa.eu/europass/eportfolio/screen/cv-editor
to generate an authentic Europass PDF.
"""

import xml.etree.ElementTree as ET
import base64
from datetime import datetime
from pathlib import Path
from pypdf import PdfReader


def get_profile_photo_base64(image_path: Path) -> str:
    """Convert profile photo to Europass-compatible base64 format.
    
    Europass expects: data:image/jpeg;base64,<base64_data>
    """
    with open(image_path, 'rb') as f:
        image_data = f.read()
    
    # Determine mime type from extension
    suffix = image_path.suffix.lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
    }
    mime_type = mime_types.get(suffix, 'image/jpeg')
    
    # Create data URL and encode it in base64
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
    return base64.b64encode(data_url.encode('utf-8')).decode('ascii')


def extract_xml_from_pdf(pdf_path: str) -> str:
    """Extract the embedded XML attachment from a Europass PDF."""
    pdf = PdfReader(pdf_path)
    if 'attachment.xml' in pdf.attachments:
        xml_data = pdf.attachments['attachment.xml'][0]
        return xml_data.decode('utf-8')
    raise ValueError("No embedded XML found in PDF")


def create_enriched_experience() -> str:
    """Create the enriched experience entry for MachineMates.AI.
    
    NOTE: We return the raw HTML, NOT html.escape(). ElementTree will handle
    the XML escaping automatically. The original Europass XML stores descriptions
    as HTML-encoded content (e.g., &lt;p&gt;) which is what ElementTree produces.
    
    If we html.escape() ourselves AND let ElementTree escape, we get double-escaping
    like &amp;lt;p&amp;gt; which displays as raw <p> tags in the PDF.
    """
    description = """<p><strong>Contexte :</strong> Fondateur de MachineMates.AI, plateforme dédiée au développement de systèmes IA agentiques, d'assistants intelligents et de solutions d'IA Générative de nouvelle génération.</p>

<ol>
<li data-list="bullet"><span class="ql-ui"></span><strong>LangChain Ambassador :</strong> Membre officiel du programme LangChain Ambassador, contribuant à l'écosystème LangChain à travers le partage de connaissances, les retours sur les produits, et la participation à la communauté.</li>
<li data-list="bullet"><span class="ql-ui"></span><strong>Contribution MCP Open Source (SEP-1686) :</strong> Auteur de la <a href="https://github.com/anthropics/anthropic-cookbook/pull/147" target="_blank" rel="noopener noreferrer">SEP-1686</a> du Model Context Protocol (MCP), le standard ouvert d'Anthropic pour la communication entre LLMs et sources de données externes. Amélioration de la spécification concernant les status messages pour le retour progressif.</li>
<li data-list="bullet"><span class="ql-ui"></span><strong>Expertise AI SDK v6 (Vercel) :</strong> Développement d'applications IA avec l'AI SDK v6 de Vercel, permettant l'intégration fluide de LLMs dans les applications Next.js/React avec streaming, tool calling, et structured outputs.</li>
<li data-list="bullet"><span class="ql-ui"></span><strong>Systèmes Multi-Agents avec LangGraph :</strong> Conception et développement de systèmes multi-agents IA en Python avec LangGraph pour orchestrer des workflows complexes, incluant des agents de recherche, validation, et synthèse.</li>
<li data-list="bullet"><span class="ql-ui"></span><strong>Pipelines RAG Avancés :</strong> Implémentation de systèmes RAG (Retrieval-Augmented Generation) avec LangChain, Azure OpenAI, et bases vectorielles (pgvector, Azure AI Search, Pinecone).</li>
<li data-list="bullet"><span class="ql-ui"></span><strong>Monitoring LLM avec LangSmith :</strong> Utilisation de LangSmith pour le debugging interactif, le traçage, l'évaluation rigoureuse et le monitoring des applications LLM et agents IA.</li>
</ol>

<p><strong>Technologies :</strong> Python, TypeScript, LangChain, LangGraph, LangSmith, AI SDK v6, FastAPI, Next.js, React, Model Context Protocol (MCP), Azure OpenAI, pgvector, Docker, GitHub Actions.</p>"""
    
    # Return raw HTML - ElementTree will handle XML escaping automatically
    return description


def enrich_xml(xml_content: str, photo_path: Path = None) -> str:
    """Enrich the XML with new experience, remove website, and optionally update photo."""
    
    # Register namespaces to preserve them
    namespaces = {
        '': 'http://www.europass.eu/1.0',
        'oa': 'http://www.openapplications.org/oagis/9',
        'eures': 'http://www.europass_eures.eu/1.0',
        'hr': 'http://www.hr-xml.org/3',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
    }
    
    for prefix, uri in namespaces.items():
        if prefix:
            ET.register_namespace(prefix, uri)
        else:
            ET.register_namespace('', uri)
    
    root = ET.fromstring(xml_content)
    
    # Define namespace map for searching
    ns = {
        'ep': 'http://www.europass.eu/1.0',
        'oa': 'http://www.openapplications.org/oagis/9',
        'eures': 'http://www.europass_eures.eu/1.0',
        'hr': 'http://www.hr-xml.org/3'
    }
    
    # Remove website from CandidatePerson
    candidate_person = root.find('.//ep:CandidatePerson', ns)
    if candidate_person is not None:
        for comm in candidate_person.findall('ep:Communication', ns):
            channel = comm.find('ep:ChannelCode', ns)
            if channel is not None and channel.text == 'Web':
                candidate_person.remove(comm)
                print("Removed website field")
                break
    
    # Find EmploymentHistory
    employment_history = root.find('.//ep:EmploymentHistory', ns)
    
    if employment_history is not None:
        # Create new EmployerHistory for MachineMates.AI
        # Insert as first experience (most recent)
        
        new_employer = ET.Element('EmployerHistory')
        
        org_name = ET.SubElement(new_employer, '{http://www.hr-xml.org/3}OrganizationName')
        org_name.text = 'MachineMates.AI'
        
        org_contact = ET.SubElement(new_employer, 'OrganizationContact')
        comm = ET.SubElement(org_contact, 'Communication')
        addr = ET.SubElement(comm, 'Address')
        city = ET.SubElement(addr, '{http://www.openapplications.org/oagis/9}CityName')
        city.text = 'Paris'
        country = ET.SubElement(addr, 'CountryCode')
        country.text = 'fr'
        
        position = ET.SubElement(new_employer, 'PositionHistory')
        
        title = ET.SubElement(position, 'PositionTitle')
        title.set('typeCode', 'FREETEXT')
        title.text = 'Founder & AI Architect - LangChain Ambassador'
        
        period = ET.SubElement(position, '{http://www.europass_eures.eu/1.0}EmploymentPeriod')
        start = ET.SubElement(period, '{http://www.europass_eures.eu/1.0}StartDate')
        start_date = ET.SubElement(start, '{http://www.hr-xml.org/3}FormattedDateTime')
        start_date.text = '2024-09'
        
        # Mark as current position
        current = ET.SubElement(period, '{http://www.hr-xml.org/3}CurrentIndicator')
        current.text = 'true'
        
        desc = ET.SubElement(position, '{http://www.openapplications.org/oagis/9}Description')
        desc.text = create_enriched_experience()
        
        pos_city = ET.SubElement(position, 'City')
        pos_city.text = 'Paris'
        pos_country = ET.SubElement(position, 'Country')
        pos_country.text = 'fr'
        
        # Insert at the beginning
        employment_history.insert(0, new_employer)
        print("Added MachineMates.AI experience")
    
    # Update the first position (Groupe International) to have end date
    existing_employers = employment_history.findall('ep:EmployerHistory', ns)
    if len(existing_employers) > 1:
        # The second one is now "Groupe International"
        groupe_intl = existing_employers[1]
        current_indicator = groupe_intl.find('.//hr:CurrentIndicator', ns)
        if current_indicator is not None:
            current_indicator.text = 'false'
    
    # Update profile photo if provided
    if photo_path and photo_path.exists():
        attachment = root.find('.//eures:Attachment', ns)
        if attachment is not None:
            embedded_data = attachment.find('oa:EmbeddedData', ns)
            if embedded_data is not None:
                embedded_data.text = get_profile_photo_base64(photo_path)
                print(f"Updated profile photo from: {photo_path.name}")
    
    # Convert back to string
    return ET.tostring(root, encoding='unicode', xml_declaration=True)


def main():
    import os
    
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = script_dir.parent
    pdf_path = parent_dir / 'CV-Europass-Original.pdf'
    photo_path = parent_dir / 'images' / 'profile.jpeg'
    
    print("=" * 60)
    print("EUROPASS CV ENRICHMENT")
    print("=" * 60)
    
    # Step 1: Extract XML from PDF
    print("\n[1/4] Extracting XML from original Europass PDF...")
    xml_content = extract_xml_from_pdf(str(pdf_path))
    print(f"    Extracted XML: {len(xml_content)} bytes")
    
    # Step 2: Check for profile photo
    print("\n[2/4] Checking for profile photo...")
    if photo_path.exists():
        print(f"    Found: {photo_path}")
    else:
        print(f"    Not found: {photo_path} (will keep original)")
        photo_path = None
    
    # Step 3: Enrich the XML
    print("\n[3/4] Enriching XML with new content...")
    enriched_xml = enrich_xml(xml_content, photo_path)
    
    # Step 4: Save enriched XML
    output_path = parent_dir / 'europass-enriched.xml'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(enriched_xml)
    print(f"\n[4/4] Saved enriched XML to: {output_path}")
    
    print("\n" + "=" * 60)
    print("NEXT STEPS:")
    print("=" * 60)
    print("""
To generate an authentic Europass PDF:

1. Go to: https://europa.eu/europass/eportfolio/screen/cv-editor
2. Log in (or create an account)
3. Click "Import Europass CV" 
4. Upload the file: europass-enriched.xml
5. Review and adjust formatting if needed
6. Click "Download PDF"

Alternatively, run the Playwright automation script:
    python europass_playwright_import.py
""")


if __name__ == '__main__':
    main()
