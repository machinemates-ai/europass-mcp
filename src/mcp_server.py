"""
Europass CV Generator MCP Server

Uses MAC (Manfred Awesomic CV) JSON as internal format, then converts to Europass XML for PDF generation.

Supported input formats:
- PDF: Extracts embedded XML from Europass PDFs (europa.eu format)
- DOCX: Parses document content and creates MAC JSON structure
- XML: Directly imports Europass XML files
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.sax.saxutils import escape

import phonenumbers
import pypdf
from fastmcp import FastMCP
from markitdown import MarkItDown
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout, expect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# Europass configuration
EUROPASS_URL = "https://europa.eu/europass/eportfolio/screen/cv-editor?lang=fr"
DEFAULT_TEMPLATE = "cv-formal"
VALID_TEMPLATES = {
    "cv-formal",
    "cv-elegant",
    "cv-modern",
    "cv-academic",
    "cv-creative",
    "cv-semi-formal",
}

# Initialize MCP server
mcp = FastMCP(
    "europass-cv-generator",
    instructions="""
    Europass CV Generator - Creates professional CVs in PDF format.
    
    Workflows:
    
    Option A - Import existing CV (recommended):
    1. Use import_cv to load a PDF, DOCX, or XML file
       - PDF: Extracts embedded XML from Europass PDFs (europa.eu format)
       - DOCX: Returns text content for processing
       - XML: Directly imports Europass XML
    2. Use generate_pdf to create the final PDF
    
    Option B - Create from scratch:
    1. Use create_resume with MAC JSON structure to store CV data
    2. Use generate_pdf to create the final Europass PDF
    
    The internal format is MAC (Manfred Awesomic CV) JSON schema.
    See: https://github.com/getmanfred/mac
    """,
)

# Storage for resumes by ID (session-safe)
_resumes: dict[str, dict[str, Any]] = {}

# Storage for raw Europass XML by resume ID (bypasses MAC conversion)
_raw_europass_xml: dict[str, str] = {}

# Maximum number of resumes to keep in memory (LRU-style cleanup)
_MAX_RESUMES = 50


@mcp.tool
def parse_document(file_path: str) -> dict[str, Any] | str:
    """
    Parse a document (DOCX, PDF, etc.) and extract text content.
    
    Uses markitdown to convert documents to Markdown format for LLM processing.
    
    Args:
        file_path: Absolute path to the document file
        
    Returns:
        Extracted text content in Markdown format, or error dict if failed
    """
    path = Path(file_path)
    
    if not path.exists():
        return {
            "status": "error",
            "message": f"File not found: {file_path}"
        }
    
    if not path.is_file():
        return {
            "status": "error",
            "message": f"Path is not a file: {file_path}"
        }
    
    try:
        md = MarkItDown()
        result = md.convert(file_path)
        return result.text_content
    except Exception as e:
        logger.error(f"Failed to parse document {file_path}: {e}")
        return {
            "status": "error",
            "message": f"Failed to parse document: {str(e)}",
            "file_path": file_path
        }


def _extract_europass_xml_from_pdf(pdf_path: Path) -> str | None:
    """
    Extract embedded Europass XML from a PDF file.
    
    Europass PDFs generated from europa.eu contain an embedded XML attachment
    (typically named 'attachment.xml') with the full CV data in HR-XML 3.0 format.
    
    Args:
        pdf_path: Path to the Europass PDF file
        
    Returns:
        The XML content as string, or None if no XML attachment found
    """
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        
        if not reader.attachments:
            logger.warning(f"No attachments found in PDF: {pdf_path}")
            return None
        
        # Look for XML attachment (Europass uses 'attachment.xml')
        for name, data_list in reader.attachments.items():
            if name.lower().endswith('.xml'):
                # Take the first XML attachment
                xml_bytes = data_list[0]
                xml_content = xml_bytes.decode('utf-8')
                logger.info(f"Extracted XML from PDF: {name} ({len(xml_bytes)} bytes)")
                return xml_content
        
        logger.warning(f"No XML attachment found in PDF attachments: {list(reader.attachments.keys())}")
        return None
        
    except Exception as e:
        logger.error(f"Failed to extract XML from PDF {pdf_path}: {e}")
        return None


def _europass_xml_to_mac(xml_content: str) -> dict[str, Any]:
    """
    Parse Europass XML and convert to MAC JSON format.
    
    This extracts ALL data from the XML including rich descriptions, preserving
    everything in the MAC structure for later editing or conversion back to XML.
    
    The key insight is that MAC can hold MORE data than Europass (Europass is a subset of MAC).
    We store:
    - Full HTML descriptions in roles[].challenges or a dedicated field
    - Organization names exactly as they appear
    - All location details (postal code, address, city)
    - Education descriptions
    """
    import re
    import html
    from xml.etree import ElementTree as ET
    
    # Parse XML
    root = ET.fromstring(xml_content)
    
    # Define namespaces
    ns = {
        'ep': 'http://www.europass.eu/1.0',
        'hr': 'http://www.hr-xml.org/3',
        'oa': 'http://www.openapplications.org/oagis/9',
        'eures': 'http://www.europass_eures.eu/1.0',
    }
    
    def get_text(elem, path, default=""):
        """Get text from element path, handling namespaces."""
        if elem is None:
            return default
        found = elem.find(path, ns)
        return found.text.strip() if found is not None and found.text else default
    
    def unescape_html(text):
        """Unescape HTML entities in descriptions."""
        if not text:
            return text
        return html.unescape(text)
    
    # Extract person info from CandidatePerson
    candidate_person = root.find('.//ep:CandidatePerson', ns)
    
    given_name = get_text(candidate_person, 'ep:PersonName/oa:GivenName')
    family_name = get_text(candidate_person, 'ep:PersonName/hr:FamilyName')
    birthday = get_text(candidate_person, 'hr:BirthDate')
    nationality = get_text(candidate_person, 'ep:NationalityCode')
    
    # Extract contact info
    email = ""
    phone = ""
    phone_country = ""
    address_line = ""
    city = ""
    postal_code = ""
    country_code = ""
    
    for comm in candidate_person.findall('.//ep:Communication', ns) if candidate_person is not None else []:
        channel = get_text(comm, 'ep:ChannelCode')
        if channel == 'Email':
            email = get_text(comm, 'oa:URI')
        elif channel == 'Telephone':
            phone_country = get_text(comm, 'ep:CountryDialing')
            phone = get_text(comm, 'oa:DialNumber')
        else:
            # Address
            addr = comm.find('ep:Address', ns)
            if addr is not None:
                address_line = get_text(addr, 'oa:AddressLine')
                city = get_text(addr, 'oa:CityName')
                postal_code = get_text(addr, 'oa:PostalCode')
                country_code = get_text(addr, 'ep:CountryCode')
    
    # Build profile location
    location = {}
    if country_code:
        location["country"] = country_code.upper() if len(country_code) == 2 else country_code
    if city:
        location["municipality"] = city
    if postal_code:
        location["postalCode"] = postal_code
    if address_line:
        location["address"] = address_line
    
    # Extract jobs from EmploymentHistory
    jobs = []
    employment_history = root.find('.//ep:EmploymentHistory', ns)
    
    if employment_history is not None:
        for employer in employment_history.findall('ep:EmployerHistory', ns):
            org_name = get_text(employer, 'hr:OrganizationName')
            
            # Organization location
            org_city = ""
            org_country = ""
            org_contact = employer.find('ep:OrganizationContact', ns)
            if org_contact is not None:
                org_addr = org_contact.find('.//ep:Address', ns)
                if org_addr is not None:
                    org_city = get_text(org_addr, 'oa:CityName')
                    org_country = get_text(org_addr, 'ep:CountryCode')
            
            org_location = {}
            if org_country:
                org_location["country"] = org_country.upper() if len(org_country) == 2 else org_country
            if org_city:
                org_location["municipality"] = org_city
            
            # Extract roles/positions
            roles = []
            for position in employer.findall('ep:PositionHistory', ns):
                title = get_text(position, 'ep:PositionTitle')
                
                # Employment period
                emp_period = position.find('eures:EmploymentPeriod', ns)
                start_date = ""
                end_date = ""
                is_current = False
                
                if emp_period is not None:
                    start_elem = emp_period.find('eures:StartDate/hr:FormattedDateTime', ns)
                    end_elem = emp_period.find('eures:EndDate/hr:FormattedDateTime', ns)
                    current_elem = emp_period.find('hr:CurrentIndicator', ns)
                    
                    if start_elem is not None and start_elem.text:
                        start_date = start_elem.text.strip()
                    if end_elem is not None and end_elem.text:
                        end_date = end_elem.text.strip()
                    if current_elem is not None and current_elem.text:
                        is_current = current_elem.text.lower() == 'true'
                
                # Description - this is the RICH content with HTML
                description_raw = get_text(position, 'oa:Description')
                description = unescape_html(description_raw)
                
                # City from position
                pos_city = get_text(position, 'ep:City')
                pos_country = get_text(position, 'ep:Country')
                
                # Build role - store full description in challenges
                role = {
                    "name": title,
                    "startDate": start_date,
                }
                
                if end_date and not is_current:
                    role["finishDate"] = end_date
                
                # Store the full HTML description - this is key!
                # MAC doesn't have a direct "fullDescription" in the schema, 
                # but we can use the notes field or store in challenges
                if description:
                    # Store as a single challenge with the full description
                    role["challenges"] = [{"description": description}]
                    # Also store in notes for backup
                    role["notes"] = description
                
                roles.append(role)
            
            job = {
                "organization": {
                    "name": org_name,
                }
            }
            if org_location:
                job["organization"]["location"] = org_location
            if roles:
                job["roles"] = roles
            
            jobs.append(job)
    
    # Extract education from EducationHistory
    studies = []
    education_history = root.find('.//ep:EducationHistory', ns)
    
    if education_history is not None:
        for edu in education_history.findall('ep:EducationOrganizationAttendance', ns):
            inst_name = get_text(edu, 'hr:OrganizationName')
            
            # Institution location
            inst_city = ""
            inst_country = ""
            inst_url = ""
            inst_contact = edu.find('ep:OrganizationContact', ns)
            if inst_contact is not None:
                for comm in inst_contact.findall('ep:Communication', ns):
                    channel = get_text(comm, 'ep:ChannelCode')
                    if channel == 'Web':
                        inst_url = get_text(comm, 'oa:URI')
                    else:
                        addr = comm.find('ep:Address', ns)
                        if addr is not None:
                            inst_city = get_text(addr, 'oa:CityName')
                            inst_country = get_text(addr, 'ep:CountryCode')
            
            # Attendance period
            att_period = edu.find('ep:AttendancePeriod', ns)
            start_date = ""
            end_date = ""
            ongoing = False
            
            if att_period is not None:
                start_elem = att_period.find('ep:StartDate/hr:FormattedDateTime', ns)
                end_elem = att_period.find('ep:EndDate/hr:FormattedDateTime', ns)
                ongoing_elem = att_period.find('ep:Ongoing', ns)
                
                if start_elem is not None and start_elem.text:
                    start_date = start_elem.text.strip()
                if end_elem is not None and end_elem.text:
                    end_date = end_elem.text.strip()
                if ongoing_elem is not None and ongoing_elem.text:
                    ongoing = ongoing_elem.text.lower() == 'true'
            
            # Degree info
            degree = edu.find('ep:EducationDegree', ns)
            degree_name = get_text(degree, 'hr:DegreeName') if degree is not None else ""
            skills_covered = get_text(degree, 'ep:OccupationalSkillsCovered') if degree is not None else ""
            skills_covered = unescape_html(skills_covered)
            
            # Build study entry
            # Infer studyType from name/institution:
            # - "Certified" or short duration (same start/end) → certification
            # - Otherwise → officialDegree
            is_certification = (
                "certif" in degree_name.lower() or
                "safe" in degree_name.lower() or
                (start_date == end_date and start_date)  # Same month → certification
            )
            study = {
                "studyType": "certification" if is_certification else "officialDegree",
                "degreeAchieved": not ongoing and bool(end_date),
                "name": degree_name,
                "startDate": start_date,
            }
            
            if end_date:
                study["finishDate"] = end_date
            
            if skills_covered:
                study["description"] = skills_covered
            
            institution = {"name": inst_name}
            if inst_url:
                institution["URL"] = inst_url
            if inst_city or inst_country:
                inst_loc = {}
                if inst_country:
                    inst_loc["country"] = inst_country.upper() if len(inst_country) == 2 else inst_country
                if inst_city:
                    inst_loc["municipality"] = inst_city
                institution["location"] = inst_loc
            
            study["institution"] = institution
            studies.append(study)
    
    # Extract languages from LanguageSkills (basic listing)
    languages = []
    lang_skills = root.find('.//ep:LanguageSkills', ns)
    if lang_skills is not None:
        for lang in lang_skills.findall('ep:MotherLanguage', ns):
            lang_code = get_text(lang, 'ep:LanguageCode')
            if lang_code:
                languages.append({
                    "name": lang_code,
                    "fullName": lang_code,
                    "level": "Native or bilingual proficiency"
                })
        for lang in lang_skills.findall('ep:ForeignLanguage', ns):
            lang_code = get_text(lang, 'ep:LanguageCode')
            if lang_code:
                languages.append({
                    "name": lang_code,
                    "fullName": lang_code,
                    "level": "Professional working proficiency"
                })
    
    # Extract detailed CEFR scores from PersonQualifications (for round-trip preservation)
    # These are stored in PersonCompetency elements with TaxonomyID="language"
    language_cefr_scores = {}  # {lang_code: {dimension: score}}
    candidate_profile = root.find('.//ep:CandidateProfile', ns)
    if candidate_profile is not None:
        person_quals = candidate_profile.find('ep:PersonQualifications', ns)
        if person_quals is not None:
            for competency in person_quals.findall('ep:PersonCompetency', ns):
                # Check if this is a language competency
                taxonomy_id = get_text(competency, 'hr:TaxonomyID')
                if taxonomy_id == 'language':
                    comp_id_elem = competency.find('ep:CompetencyID', ns)
                    if comp_id_elem is not None and comp_id_elem.text:
                        lang_code = comp_id_elem.text.strip()
                        
                        # Extract all CEFR dimension scores
                        scores = {}
                        for dim in competency.findall('eures:CompetencyDimension', ns):
                            dim_code = get_text(dim, 'hr:CompetencyDimensionTypeCode')
                            score_text = get_text(dim, 'eures:Score/hr:ScoreText')
                            if dim_code and score_text:
                                scores[dim_code] = score_text
                        
                        if scores:
                            language_cefr_scores[lang_code] = scores
                            
                            # Check if this language is in our list, add CEFR scores
                            for lang in languages:
                                if lang.get("name", "").lower() == lang_code.lower():
                                    lang["cefrScores"] = scores
                                    break
                            else:
                                # Language not in basic list, add it with CEFR scores
                                languages.append({
                                    "name": lang_code,
                                    "fullName": lang_code,
                                    "level": "Professional working proficiency",
                                    "cefrScores": scores
                                })
    
    # Extract profile picture from eures:Attachment
    profile_picture = ""
    if candidate_profile is not None:
        for attachment in candidate_profile.findall('eures:Attachment', ns):
            file_type = get_text(attachment, 'oa:FileType')
            instructions = get_text(attachment, 'hr:Instructions')
            if file_type == 'photo' or instructions == 'ProfilePicture':
                embedded_data = get_text(attachment, 'oa:EmbeddedData')
                if embedded_data:
                    profile_picture = embedded_data
                    break
    
    # Build complete MAC structure
    mac = {
        "$schema": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
        "settings": {
            "language": "fr",  # Could extract from XML languageCode
        },
        "aboutMe": {
            "profile": {
                "name": given_name,
                "surnames": family_name,
            }
        },
    }
    
    if birthday:
        mac["aboutMe"]["profile"]["birthday"] = birthday
    if location:
        mac["aboutMe"]["profile"]["location"] = location
    
    # Contact info
    if email or phone:
        mac["careerPreferences"] = {"contact": {}}
        if email:
            mac["careerPreferences"]["contact"]["contactMails"] = [email]
        if phone:
            full_phone = f"+{phone_country}{phone}" if phone_country else phone
            mac["careerPreferences"]["contact"]["phoneNumbers"] = [full_phone]
    
    # Experience
    if jobs:
        mac["experience"] = {"jobs": jobs}
    
    # Knowledge
    knowledge = {}
    if studies:
        knowledge["studies"] = studies
    if languages:
        knowledge["languages"] = languages
    if knowledge:
        mac["knowledge"] = knowledge
    
    # Profile picture - stored at top level for converter to find
    if profile_picture:
        mac["profilePicture"] = profile_picture
    
    return mac


@mcp.tool
def import_cv(file_path: str, parse_to_mac: bool = True) -> dict[str, Any]:
    """
    Import a CV from PDF, DOCX, or XML file for editing and PDF generation.
    
    Uses MAC JSON as the IR (Intermediate Representation) - all formats
    are converted to this unified schema before Europass XML generation.
    
    Supported formats:
    
    1. **PDF (Europass)** - Extracts embedded XML from Europass PDFs
       - PDFs from europa.eu contain embedded XML attachment
       - Preserves all structured data (jobs, education, skills, photo, CEFR scores)
       - Returns resume_id for immediate PDF generation
    
    2. **PDF (other)** - LLM-based structured extraction
       - If no embedded XML, uses trustcall for structured extraction
       - Requires: pip install trustcall langchain-openai
       - Falls back to raw text if LLM unavailable
    
    3. **DOCX** - LLM-based structured extraction
       - Extracts text, then uses LLM to populate MAC schema
       - Uses trustcall for reliable structured output
       - Falls back to raw text if LLM unavailable
    
    4. **XML (Europass)** - Direct HR-XML 3.0 import
       - Full content preservation
    
    Modes for PDF (Europass) / XML:
    
    - parse_to_mac=True (default): Parse to MAC JSON for editing
    - parse_to_mac=False: Use XML directly (exact preservation, no editing)
    
    Args:
        file_path: Absolute path to PDF, DOCX, or XML file
        parse_to_mac: If True, parse to MAC for editing. If False, use XML directly.
        
    Returns:
        - resume_id: ID for use with generate_pdf
        - mac_json: MAC JSON structure (for inspection/editing)
        - summary: Quick overview of extracted data
    """
    global _resumes, _raw_europass_xml
    import re
    
    path = Path(file_path)
    
    if not path.exists():
        return {
            "status": "error",
            "message": f"File not found: {file_path}"
        }
    
    if not path.is_file():
        return {
            "status": "error",
            "message": f"Path is not a file: {file_path}"
        }
    
    suffix = path.suffix.lower()
    
    # Handle DOCX - text extraction only
    # Handle DOCX - extract text and optionally use LLM for structured extraction
    if suffix == '.docx':
        try:
            md = MarkItDown()
            result = md.convert(str(path))
            text_content = result.text_content
            
            # Try structured extraction if available
            try:
                from .cv_extractor import extract_cv_from_text, is_extraction_available
                
                if is_extraction_available():
                    logger.info(f"Extracting structured CV from DOCX: {path.name}")
                    extraction_result = extract_cv_from_text(text_content)
                    
                    if extraction_result.get("status") == "success":
                        # Store the MAC JSON
                        resume_id = str(uuid4())[:8]
                        mac = extraction_result["mac_json"]
                        mac["_imported_from"] = str(file_path)
                        _resumes[resume_id] = mac
                        
                        profile = mac.get("aboutMe", {}).get("profile", {})
                        full_name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
                        jobs = mac.get("experience", {}).get("jobs", [])
                        studies = mac.get("knowledge", {}).get("studies", [])
                        
                        logger.info(f"DOCX extracted to MAC: {resume_id} for {full_name} ({len(jobs)} jobs, {len(studies)} education)")
                        
                        return {
                            "status": "success",
                            "message": f"DOCX parsed and structured for {full_name}",
                            "resume_id": resume_id,
                            "format": "docx",
                            "mode": "extracted",
                            "summary": {
                                "name": full_name,
                                "source_file": str(path),
                                "jobs_count": len(jobs),
                                "education_count": len(studies),
                            },
                            "mac_json": mac,
                            "note": "CV extracted using LLM. Review and edit with create_resume if needed."
                        }
                    else:
                        logger.warning(f"LLM extraction failed: {extraction_result.get('message')}")
            except ImportError:
                pass  # cv_extractor not available, fall back to text
            
            # Fall back to returning raw text
            return {
                "status": "partial",
                "message": f"DOCX parsed: {path.name}",
                "format": "docx",
                "text_content": text_content,
                "note": "LLM extraction not available. Use create_resume with MAC JSON to store this CV. Install trustcall for automatic extraction: pip install trustcall langchain-openai"
            }
        except Exception as e:
            logger.error(f"Failed to parse DOCX {file_path}: {e}")
            return {
                "status": "error",
                "message": f"Failed to parse DOCX: {str(e)}"
            }
    
    # Handle PDF - extract embedded XML
    if suffix == '.pdf':
        xml_content = _extract_europass_xml_from_pdf(path)
        
        if xml_content is None:
            # No embedded XML - try text extraction + LLM as fallback
            try:
                md = MarkItDown()
                result = md.convert(str(path))
                text_content = result.text_content
                
                # Try structured extraction if available
                try:
                    from .cv_extractor import extract_cv_from_text, is_extraction_available
                    
                    if is_extraction_available():
                        logger.info(f"Extracting structured CV from non-Europass PDF: {path.name}")
                        extraction_result = extract_cv_from_text(text_content)
                        
                        if extraction_result.get("status") == "success":
                            resume_id = str(uuid4())[:8]
                            mac = extraction_result["mac_json"]
                            mac["_imported_from"] = str(file_path)
                            _resumes[resume_id] = mac
                            
                            profile = mac.get("aboutMe", {}).get("profile", {})
                            full_name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
                            jobs = mac.get("experience", {}).get("jobs", [])
                            studies = mac.get("knowledge", {}).get("studies", [])
                            
                            return {
                                "status": "success",
                                "message": f"PDF parsed and structured for {full_name}",
                                "resume_id": resume_id,
                                "format": "pdf",
                                "mode": "extracted",
                                "summary": {
                                    "name": full_name,
                                    "source_file": str(path),
                                    "jobs_count": len(jobs),
                                    "education_count": len(studies),
                                },
                                "mac_json": mac,
                                "note": "Non-Europass PDF. CV extracted using LLM."
                            }
                except ImportError:
                    pass
                
                return {
                    "status": "partial",
                    "message": f"PDF has no embedded Europass XML. Extracted text content instead.",
                    "format": "pdf_text",
                    "text_content": text_content,
                    "note": "Not a Europass PDF. Install trustcall for LLM extraction: pip install trustcall langchain-openai"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to extract content from PDF: {str(e)}"
                }
        
        # XML extracted successfully - continue processing as XML
        logger.info(f"Extracted Europass XML from PDF: {path.name}")
    
    # Handle XML - read directly
    elif suffix == '.xml':
        try:
            xml_content = path.read_text(encoding='utf-8')
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to read XML file: {str(e)}"
            }
    else:
        return {
            "status": "error",
            "message": f"Unsupported file format: {suffix}. Supported: .pdf, .docx, .xml"
        }
    
    # Validate XML content
    if 'europass' not in xml_content.lower() and 'Candidate' not in xml_content:
        return {
            "status": "error",
            "message": "File does not appear to be a valid Europass XML (missing Europass namespace or Candidate element)"
        }
    
    try:
        # Generate unique ID
        resume_id = str(uuid4())[:8]
        
        # Always store the raw XML for direct use option
        _raw_europass_xml[resume_id] = xml_content
        
        if parse_to_mac:
            # Parse XML to MAC JSON - allows editing
            mac = _europass_xml_to_mac(xml_content)
            mac["_imported_from"] = str(file_path)
            _resumes[resume_id] = mac
            
            profile = mac.get("aboutMe", {}).get("profile", {})
            full_name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
            
            jobs = mac.get("experience", {}).get("jobs", [])
            studies = mac.get("knowledge", {}).get("studies", [])
            
            logger.info(f"Europass XML parsed to MAC: {resume_id} for {full_name} ({len(jobs)} jobs, {len(studies)} education)")
            
            return {
                "status": "success",
                "message": f"CV imported and parsed for {full_name}",
                "resume_id": resume_id,
                "format": suffix.lstrip('.'),
                "mode": "parsed",
                "summary": {
                    "name": full_name,
                    "source_file": str(path),
                    "jobs_count": len(jobs),
                    "education_count": len(studies),
                },
                "mac_json": mac,  # Return for inspection/editing
                "note": "MAC JSON can be edited via create_resume before generate_pdf. Original XML also stored as backup."
            }
        else:
            # Direct mode - use XML as-is
            # Extract name from XML for summary
            given_name_match = re.search(r'<oa:GivenName>([^<]+)</oa:GivenName>', xml_content)
            family_name_match = re.search(r'<hr:FamilyName>([^<]+)</hr:FamilyName>', xml_content)
            
            given_name = given_name_match.group(1).strip() if given_name_match else "Unknown"
            family_name = family_name_match.group(1).strip() if family_name_match else "Unknown"
            full_name = f"{given_name} {family_name}"
            
            # Count jobs and education entries
            jobs_count = xml_content.count('<EmployerHistory>')
            education_count = xml_content.count('<EducationOrganizationAttendance>')
            
            # Create minimal MAC structure for compatibility
            _resumes[resume_id] = {
                "$schema": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
                "settings": {"language": "fr"},
                "aboutMe": {
                    "profile": {
                        "name": given_name,
                        "surnames": family_name,
                        "title": "(Imported from Europass XML - direct mode)",
                    }
                },
                "_imported_from": str(file_path),
                "_is_raw_europass": True
            }
            
            logger.info(f"Europass XML imported (direct): {resume_id} for {full_name} ({jobs_count} jobs, {education_count} education)")
            
            return {
                "status": "success",
                "message": f"CV imported (direct mode) for {full_name}",
                "resume_id": resume_id,
                "format": suffix.lstrip('.'),
                "mode": "direct",
                "summary": {
                    "name": full_name,
                    "source_file": str(path),
                    "jobs_count": jobs_count,
                    "education_count": education_count,
                },
                "note": "Original XML will be used directly by generate_pdf. No editing possible in this mode."
            }
        
        # LRU cleanup
        if len(_resumes) > _MAX_RESUMES:
            oldest_id = next(iter(_resumes))
            del _resumes[oldest_id]
            if oldest_id in _raw_europass_xml:
                del _raw_europass_xml[oldest_id]
        
    except Exception as e:
        logger.error(f"Failed to import CV {file_path}: {e}")
        return {
            "status": "error",
            "message": f"Failed to import CV: {str(e)}",
            "file_path": file_path
        }


# Legacy alias for backward compatibility
@mcp.tool
def import_europass_xml(file_path: str, parse_to_mac: bool = True) -> dict[str, Any]:
    """
    Legacy alias for import_cv. Use import_cv instead.
    
    Redirects to import_cv which supports PDF, DOCX, and XML files.
    """
    return import_cv(file_path, parse_to_mac)


@mcp.tool
def create_resume(mac_json: dict[str, Any]) -> dict[str, Any]:
    """
    Create or update a resume using MAC (Manfred Awesomic CV) JSON format.
    
    MAC is a modern, open CV format with JSON Schema validation.
    See schema: https://github.com/getmanfred/mac/blob/master/schema.json
    
    Required structure:
    {
        "$schema": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
        "settings": {"language": "FR"},
        "aboutMe": {
            "profile": {
                "name": "Guillaume",
                "surnames": "FORTAINE",
                "title": "Senior Full Stack Developer",
                "description": "...",
                "birthday": "1984-02-18",
                "avatar": {"link": "...", "alt": "..."},
                "location": {"country": "France", "region": "Île-de-France", "municipality": "Paris"}
            },
            "relevantLinks": [{"type": "linkedin", "URL": "..."}],
            "interestingFacts": [{"topic": "...", "fact": "..."}]
        },
        "experience": {
            "jobs": [
                {
                    "organization": {"name": "Company", "URL": "..."},
                    "roles": [
                        {
                            "name": "Job Title",
                            "startDate": "2024-01",
                            "finishDate": "2025-09",
                            "challenges": [{"description": "..."}],
                            "competences": [{"name": "Python", "type": "technology"}]
                        }
                    ]
                }
            ],
            "projects": [...],
            "publicArtifacts": [...]
        },
        "knowledge": {
            "languages": [{"name": "English", "fullName": "English", "level": "Full professional proficiency"}],
            "hardSkills": [{"skill": {"name": "Python", "type": "technology"}, "level": "expert"}],
            "softSkills": [{"skill": {"name": "Leadership", "type": "practice"}}],
            "studies": [
                {
                    "studyType": "certification",
                    "degreeAchieved": true,
                    "name": "Certified SAFe 6 Scrum Master",
                    "startDate": "2023-11",
                    "finishDate": "2023-11",
                    "institution": {"name": "Scaled Agile, Inc.", "URL": "..."}
                }
            ]
        },
        "careerPreferences": {
            "contact": {"publicProfiles": [...], "contactMails": ["..."], "phoneNumbers": [...]},
            "preferences": {"preferredRoles": ["Backend Developer"], "discardedRoles": [...]}
        }
    }
    
    Args:
        mac_json: Resume data in MAC JSON format
        
    Returns:
        Confirmation with resume_id and stored data summary
    """
    global _resumes
    
    # Validate required MAC fields
    profile = mac_json.get("aboutMe", {}).get("profile", {})
    name = profile.get("name", "").strip()
    surnames = profile.get("surnames", "").strip()
    
    if not name:
        return {
            "status": "error",
            "message": "Missing required field: aboutMe.profile.name"
        }
    if not surnames:
        return {
            "status": "error",
            "message": "Missing required field: aboutMe.profile.surnames"
        }
    
    # Generate unique ID for this resume
    resume_id = str(uuid4())[:8]
    
    # LRU-style cleanup: remove oldest if at capacity
    if len(_resumes) >= _MAX_RESUMES:
        oldest_id = next(iter(_resumes))
        del _resumes[oldest_id]
        logger.debug(f"Cleaned up old resume: {oldest_id}")
    
    _resumes[resume_id] = mac_json
    logger.info(f"Resume created: {resume_id} for {name} {surnames}")
    
    # Extract summary info
    profile = mac_json.get("aboutMe", {}).get("profile", {})
    name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
    
    jobs = mac_json.get("experience", {}).get("jobs", [])
    # Handle both formats: studies as list OR studies.studiesDetails
    studies_raw = mac_json.get("knowledge", {}).get("studies", [])
    studies = studies_raw.get("studiesDetails", []) if isinstance(studies_raw, dict) else studies_raw
    
    return {
        "status": "success",
        "message": f"Resume created for {name}",
        "resume_id": resume_id,
        "summary": {
            "name": name,
            "title": profile.get("title", ""),
            "jobs_count": len(jobs),
            "education_count": len(studies),
            "location": profile.get("location", {}).get("municipality", ""),
        }
    }


@mcp.tool
def list_resumes() -> dict[str, Any]:
    """
    List all resumes currently stored in memory.
    
    Returns:
        List of resume IDs with their summaries, including whether they have raw Europass XML
    """
    global _resumes, _raw_europass_xml
    
    resumes_list = []
    for resume_id, mac_json in _resumes.items():
        profile = mac_json.get("aboutMe", {}).get("profile", {})
        name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
        resumes_list.append({
            "resume_id": resume_id,
            "name": name,
            "title": profile.get("title", ""),
            "has_raw_xml": resume_id in _raw_europass_xml,
            "imported_from": mac_json.get("_imported_from", None),
        })
    
    return {
        "status": "success",
        "count": len(resumes_list),
        "resumes": resumes_list
    }


@mcp.tool
def delete_resume(resume_id: str) -> dict[str, Any]:
    """
    Delete a resume from memory.
    
    Args:
        resume_id: ID of the resume to delete
        
    Returns:
        Confirmation of deletion
    """
    global _resumes
    
    if resume_id not in _resumes:
        return {
            "status": "error",
            "message": f"Resume ID '{resume_id}' not found."
        }
    
    profile = _resumes[resume_id].get("aboutMe", {}).get("profile", {})
    name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
    
    del _resumes[resume_id]
    
    # Also clean up raw XML if present
    if resume_id in _raw_europass_xml:
        del _raw_europass_xml[resume_id]
    
    return {
        "status": "success",
        "message": f"Resume for {name} (ID: {resume_id}) deleted.",
        "remaining_count": len(_resumes)
    }


@mcp.tool
def update_resume(resume_id: str, mac_json: dict[str, Any], use_mac_conversion: bool = True) -> dict[str, Any]:
    """
    Update an existing resume with new MAC JSON data.
    
    When updating a resume that was imported from Europass XML, you can choose whether
    to use MAC→XML conversion or keep the original XML.
    
    Args:
        resume_id: ID of the resume to update
        mac_json: New MAC JSON data (can be partial update)
        use_mac_conversion: If True, clears raw XML so generate_pdf uses MAC conversion.
                           If False, keeps original XML for generate_pdf.
        
    Returns:
        Confirmation of update
    """
    global _resumes, _raw_europass_xml
    
    if resume_id not in _resumes:
        return {
            "status": "error",
            "message": f"Resume ID '{resume_id}' not found."
        }
    
    # Deep merge the new data with existing
    existing = _resumes[resume_id]
    
    # Simple merge: update top-level keys
    for key, value in mac_json.items():
        if isinstance(value, dict) and isinstance(existing.get(key), dict):
            # Merge nested dicts
            existing[key].update(value)
        else:
            existing[key] = value
    
    _resumes[resume_id] = existing
    
    # Clear raw XML if user wants MAC conversion
    if use_mac_conversion and resume_id in _raw_europass_xml:
        del _raw_europass_xml[resume_id]
        logger.info(f"Cleared raw XML for {resume_id}, will use MAC conversion")
    
    profile = existing.get("aboutMe", {}).get("profile", {})
    name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
    
    return {
        "status": "success",
        "message": f"Resume for {name} updated.",
        "resume_id": resume_id,
        "use_mac_conversion": use_mac_conversion,
        "has_raw_xml": resume_id in _raw_europass_xml
    }


def _mac_to_europass_xml(mac: dict[str, Any]) -> str:
    """
    Convert MAC JSON to Europass XML format.
    
    Maps MAC structure to EURES/HR-XML based Europass schema.
    """
    profile = mac.get("aboutMe", {}).get("profile", {})
    contact = mac.get("careerPreferences", {}).get("contact", {})
    experience = mac.get("experience", {})
    knowledge = mac.get("knowledge", {})
    settings = mac.get("settings", {})
    
    # Profile picture: check profilePicture (base64 data) or avatar (link)
    profile_picture = mac.get("profilePicture", "")
    avatar = profile.get("avatar", {})
    avatar_link = avatar.get("link", "") if isinstance(avatar, dict) else ""
    
    # Europass expects the profile picture as: base64(data:image/jpeg;base64,<raw_b64>)
    # This is a double-encoding: the entire data URI is base64 encoded again
    if profile_picture:
        # If profilePicture is raw base64 JPEG data, wrap it in data URI and re-encode
        if profile_picture.startswith("/9j/") or profile_picture.startswith("iVBOR"):
            # Determine image type from base64 header
            img_type = "jpeg" if profile_picture.startswith("/9j/") else "png"
            data_uri = f"data:image/{img_type};base64,{profile_picture}"
            # Double-encode: encode the entire data URI as base64
            import base64
            profile_picture = base64.b64encode(data_uri.encode("utf-8")).decode("utf-8")
    
    name = profile.get("name", "")
    surnames = profile.get("surnames", "")
    birthday = profile.get("birthday", "")
    location = profile.get("location", {})
    
    # Get contact info
    emails = contact.get("contactMails", [])
    phones = contact.get("phoneNumbers", [])
    email = emails[0] if emails else ""
    
    # Language code
    lang_code = settings.get("language", "EN").lower()
    
    # Build XML
    xml_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<Candidate xmlns="http://www.europass.eu/1.0" xmlns:eures="http://www.europass_eures.eu/1.0" xmlns:hr="http://www.hr-xml.org/3" xmlns:oa="http://www.openapplications.org/oagis/9" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.europass.eu/1.0 Candidate.xsd">',
        f'    <hr:DocumentID schemeID="MAC-{datetime.now().strftime("%Y%m%d")}" schemeName="DocumentIdentifier" schemeAgencyName="EUROPASS" schemeVersionID="4.0" />',
    ]
    
    # CandidateSupplier
    xml_parts.extend([
        '    <CandidateSupplier>',
        '        <hr:PartyID schemeID="MAC-001" schemeName="PartyID" schemeAgencyName="EUROPASS" schemeVersionID="1.0" />',
        '        <hr:PartyName>Owner</hr:PartyName>',
        '        <PersonContact>',
        '            <PersonName>',
        f'                <oa:GivenName>{escape(name)}</oa:GivenName>',
        f'                <hr:FamilyName>{escape(surnames)}</hr:FamilyName>',
        '            </PersonName>',
    ])
    
    if email:
        xml_parts.extend([
            '            <Communication>',
            '                <ChannelCode>Email</ChannelCode>',
            f'                <oa:URI>{escape(email)}</oa:URI>',
            '            </Communication>',
        ])
    
    xml_parts.extend([
        '        </PersonContact>',
        '        <hr:PrecedenceCode>1</hr:PrecedenceCode>',
        '    </CandidateSupplier>',
    ])
    
    # CandidatePerson
    # Note: PersonTitle and PersonDescription are NOT supported by Europass XML import
    # The working original XML does not include these elements

    xml_parts.extend([
        '    <CandidatePerson>',
        '        <PersonName>',
        f'            <oa:GivenName>{escape(name)}</oa:GivenName>',
        f'            <hr:FamilyName>{escape(surnames)}</hr:FamilyName>',
        '        </PersonName>',
    ])
    if email:
        xml_parts.extend([
            '        <Communication>',
            '            <ChannelCode>Email</ChannelCode>',
            f'            <oa:URI>{escape(email)}</oa:URI>',
            '        </Communication>',
        ])
    
    # Relevant links (LinkedIn, GitHub, etc.)
    # Note: ChannelCode must be a valid Europass value: Email, Telephone, Web
    # All URLs should use "Web" as the channel code
    relevant_links = mac.get("aboutMe", {}).get("relevantLinks", [])
    for link in relevant_links:
        url = link.get("URL", "")
        if url:
            xml_parts.extend([
                '        <Communication>',
                '            <ChannelCode>Web</ChannelCode>',
                f'            <oa:URI>{escape(url)}</oa:URI>',
                '        </Communication>',
            ])
    
    # Phone - use phonenumbers library (Google's libphonenumber) for robust parsing
    if phones:
        phone = phones[0]
        country_code = ""
        number = ""
        
        if isinstance(phone, dict):
            # Dict format: {"countryCode": "+33", "number": "631092519"}
            country_code = str(phone.get("countryCode", "")).lstrip("+")
            number = str(phone.get("number", ""))
        else:
            # Plain string like "+33631092519" - parse with phonenumbers
            phone_str = str(phone).strip()
            try:
                # Parse E.164 format (with +) or attempt with None region
                parsed = phonenumbers.parse(phone_str, None)
                country_code = str(parsed.country_code)
                number = str(parsed.national_number)
            except phonenumbers.NumberParseException:
                # Fallback: try to extract manually if parsing fails
                if phone_str.startswith("+"):
                    # Remove + and try to split (assume 2-digit country code)
                    digits = phone_str[1:]
                    country_code = digits[:2]
                    number = digits[2:]
                else:
                    number = phone_str
        
        # Get country code from phone country dialing code
        phone_country = _phone_country_to_iso(country_code)
        
        xml_parts.extend([
            '        <Communication>',
            '            <ChannelCode>Telephone</ChannelCode>',
            '            <UseCode>work</UseCode>',
            f'            <CountryDialing>{escape(country_code)}</CountryDialing>',
            f'            <oa:DialNumber>{escape(number)}</oa:DialNumber>',
            f'            <CountryCode>{phone_country}</CountryCode>',
            '        </Communication>',
        ])
    
    # Address
    if location:
        city = location.get("municipality", "")
        country = location.get("country", "")
        region = location.get("region", "")
        postal_code = location.get("postalCode", "")
        address_line = location.get("address", "")  # From parsed Europass XML
        country_code = _country_to_code(country)
        
        # Use address if available, fallback to region
        display_address = address_line if address_line else region
        
        xml_parts.extend([
            '        <Communication>',
            '            <UseCode>home</UseCode>',
            '            <Address type="home">',
            f'                <oa:AddressLine>{escape(display_address)}</oa:AddressLine>',
            f'                <oa:CityName>{escape(city)}</oa:CityName>',
            f'                <CountryCode>{country_code}</CountryCode>',
        ])
        if postal_code:
            xml_parts.append(f'                <oa:PostalCode>{escape(postal_code)}</oa:PostalCode>')
        xml_parts.extend([
            '            </Address>',
            '        </Communication>',
        ])
    
    # Nationality and birth date
    nationality = _country_to_code(location.get("country", ""))
    xml_parts.append(f'        <NationalityCode>{nationality}</NationalityCode>')
    
    if birthday:
        xml_parts.append(f'        <hr:BirthDate>{birthday}</hr:BirthDate>')
    
    # Primary language - use first language from knowledge.languages (native/primary)
    languages = knowledge.get("languages", [])
    if languages:
        first_lang = languages[0].get("name", "").lower()[:3]
        # Map to ISO 639-2 codes
        primary_lang = {
            "fr": "fre", "fra": "fre", "fre": "fre",
            "en": "eng", "eng": "eng",
            "de": "deu", "deu": "deu", "ger": "deu",
            "es": "spa", "spa": "spa",
            "it": "ita", "ita": "ita",
            "pt": "por", "por": "por",
            "nl": "nld", "nld": "nld", "dut": "nld",
        }.get(first_lang, first_lang)
    else:
        # Fallback to document language
        primary_lang = "eng" if lang_code == "en" else "fre" if lang_code == "fr" else lang_code
    xml_parts.append(f'        <PrimaryLanguageCode name="NORMAL">{primary_lang}</PrimaryLanguageCode>')
    xml_parts.append('    </CandidatePerson>')
    
    # CandidateProfile
    xml_parts.extend([
        f'    <CandidateProfile languageCode="{lang_code}">',
        '        <hr:ID schemeID="MAC-001" schemeName="CandidateProfileID" schemeAgencyName="EUROPASS" schemeVersionID="1.0" />',
    ])
    
    # Employment History
    jobs = experience.get("jobs", [])
    if jobs:
        xml_parts.append('        <EmploymentHistory>')
        for job in jobs:
            org = job.get("organization", {})
            org_name = org.get("name", "")
            # Use organization's address or location (MAC uses both)
            org_address = org.get("address") or org.get("location", {})
            org_country = _country_to_code(org_address.get("country", ""))
            org_city = org_address.get("municipality", org_address.get("city", ""))
            
            for role in job.get("roles", []):
                role_name = role.get("name", "")
                start_date = _validate_date(role.get("startDate", ""))
                finish_date = _validate_date(role.get("finishDate", ""))
                is_current = not finish_date
                
                # Use fullDescription if available (Europass rich HTML), 
                # then try notes (where we also store imported descriptions),
                # finally fallback to building from challenges
                description = role.get("fullDescription", "")
                if not description:
                    description = role.get("notes", "")
                if not description:
                    challenges = role.get("challenges", [])
                    description = _build_html_description(challenges)
                
                xml_parts.extend([
                    '            <EmployerHistory>',
                    f'                <hr:OrganizationName>{escape(org_name)}</hr:OrganizationName>',
                    '                <OrganizationContact>',
                    '                    <Communication>',
                ])
                # Only add Address block if we have city or country data
                if org_city or org_country:
                    xml_parts.append('                        <Address>')
                    if org_city:
                        xml_parts.append(f'                            <oa:CityName>{escape(org_city)}</oa:CityName>')
                    if org_country:
                        xml_parts.append(f'                            <CountryCode>{org_country}</CountryCode>')
                    xml_parts.append('                        </Address>')
                xml_parts.extend([
                    '                    </Communication>',
                    '                </OrganizationContact>',
                    '                <PositionHistory>',
                    f'                    <PositionTitle typeCode="FREETEXT">{escape(role_name)}</PositionTitle>',
                    '                    <eures:EmploymentPeriod>',
                    '                        <eures:StartDate>',
                    f'                            <hr:FormattedDateTime>{start_date}</hr:FormattedDateTime>',
                    '                        </eures:StartDate>',
                ])
                
                if finish_date:
                    xml_parts.extend([
                        '                        <eures:EndDate>',
                        f'                            <hr:FormattedDateTime>{finish_date}</hr:FormattedDateTime>',
                        '                        </eures:EndDate>',
                    ])
                
                xml_parts.extend([
                    f'                        <hr:CurrentIndicator>{"true" if is_current else "false"}</hr:CurrentIndicator>',
                    '                    </eures:EmploymentPeriod>',
                    f'                    <oa:Description>{escape(description)}</oa:Description>',
                ])
                # Add City and Country inside PositionHistory (required by Europass)
                if org_city:
                    xml_parts.append(f'                    <City>{escape(org_city)}</City>')
                if org_country:
                    xml_parts.append(f'                    <Country>{org_country}</Country>')
                xml_parts.extend([
                    '                </PositionHistory>',
                    '            </EmployerHistory>',
                ])
        
        xml_parts.append('        </EmploymentHistory>')
    
    # Education History - Europass puts ALL education here (degrees + certifications)
    # The separate Certifications section is optional and often empty
    # Handle both formats: studies as list OR studies.studiesDetails
    studies_raw = knowledge.get("studies", [])
    if isinstance(studies_raw, dict):
        studies = studies_raw.get("studiesDetails", [])
    else:
        studies = studies_raw
    # Include ALL studies (both education and certifications go in EducationHistory in Europass)
    if studies:
        xml_parts.append('        <EducationHistory>')
        for study in studies:
            institution = study.get("institution", {})
            inst_name = institution.get("name", "")
            inst_url = institution.get("URL", "")
            # Use institution's address or location (MAC uses both)
            inst_address = institution.get("address") or institution.get("location", {})
            inst_country = _country_to_code(inst_address.get("country", ""))
            inst_city = inst_address.get("municipality", inst_address.get("city", ""))
            
            degree_name = study.get("name", "")
            start_date = _validate_date(study.get("startDate", ""))
            finish_date = _validate_date(study.get("finishDate", ""))
            description = study.get("description", "")
            
            xml_parts.extend([
                '            <EducationOrganizationAttendance>',
                f'                <hr:OrganizationName>{escape(inst_name)}</hr:OrganizationName>',
                '                <OrganizationContact>',
                '                    <Communication>',
            ])
            # Only add Address block if we have city or country data
            if inst_city or inst_country:
                xml_parts.append('                        <Address>')
                if inst_city:
                    xml_parts.append(f'                            <oa:CityName>{escape(inst_city)}</oa:CityName>')
                if inst_country:
                    xml_parts.append(f'                            <CountryCode>{inst_country}</CountryCode>')
                xml_parts.append('                        </Address>')
            xml_parts.extend([
                '                    </Communication>',
            ])
            
            if inst_url:
                xml_parts.extend([
                    '                    <Communication>',
                    '                        <ChannelCode>Web</ChannelCode>',
                    f'                        <oa:URI>{escape(inst_url)}</oa:URI>',
                    '                    </Communication>',
                ])
            
            xml_parts.extend([
                '                </OrganizationContact>',
                '                <AttendancePeriod>',
                '                    <StartDate>',
                f'                        <hr:FormattedDateTime>{start_date}</hr:FormattedDateTime>',
                '                    </StartDate>',
                '                    <EndDate>',
                f'                        <hr:FormattedDateTime>{finish_date or start_date}</hr:FormattedDateTime>',
                '                    </EndDate>',
                f'                    <Ongoing>{"true" if not finish_date else "false"}</Ongoing>',
                '                </AttendancePeriod>',
                '                <EducationDegree>',
                f'                    <hr:DegreeName>{escape(degree_name)}</hr:DegreeName>',
            ])
            
            if description:
                xml_parts.append(f'                    <OccupationalSkillsCovered>{escape(description)}</OccupationalSkillsCovered>')
            
            xml_parts.extend([
                '                </EducationDegree>',
                '            </EducationOrganizationAttendance>',
            ])
        
        xml_parts.append('        </EducationHistory>')
    
    # Licenses section (required placeholder for Europass compatibility)
    xml_parts.append('        <eures:Licenses />')
    
    # Certifications (from studies with type "certification")
    certifications = [s for s in studies if s.get("studyType") == "certification"]
    if certifications:
        xml_parts.append('        <Certifications>')
        for cert in certifications:
            cert_name = cert.get("name", "")
            issuer = cert.get("institution", {}).get("name", "")
            date = _validate_date(cert.get("finishDate", cert.get("startDate", "")))
            description = cert.get("description", "")
            
            xml_parts.extend([
                '            <Certification>',
                f'                <hr:CertificationName>{escape(cert_name)}</hr:CertificationName>',
                f'                <hr:IssuingAuthority>{escape(issuer)}</hr:IssuingAuthority>',
            ])
            
            if description:
                xml_parts.append(f'                <hr:CertificationDescription>{escape(description)}</hr:CertificationDescription>')
            
            # CertificationDate is required even if empty
            xml_parts.append('                <hr:CertificationDate>')
            if date:
                xml_parts.append(f'                    <hr:FormattedDateTime>{date}</hr:FormattedDateTime>')
            xml_parts.append('                </hr:CertificationDate>')
            
            xml_parts.append('            </Certification>')
        
        xml_parts.append('        </Certifications>')
    
    # Languages
    languages = knowledge.get("languages", [])
    if languages:
        xml_parts.append('        <PersonQualifications>')
        for lang in languages:
            lang_name = lang.get("name", "").lower()
            # Map language names to ISO 639-2/B codes (used by Europass)
            lang_code = _language_to_iso639b(lang_name)
            default_level = _level_to_cef(lang.get("level", ""))
            
            # Get preserved CEFR scores if available, otherwise use default level for all
            cefr_scores = lang.get("cefrScores", {})
            
            xml_parts.extend([
                '            <PersonCompetency>',
                f'                <CompetencyID schemeName="NORMAL">{lang_code}</CompetencyID>',
                '                <hr:TaxonomyID>language</hr:TaxonomyID>',
            ])
            
            for dim in ["CEF-Understanding-Listening", "CEF-Understanding-Reading", 
                       "CEF-Speaking-Interaction", "CEF-Speaking-Production", "CEF-Writing-Production"]:
                # Use preserved score if available, otherwise use default
                score = cefr_scores.get(dim, default_level)
                xml_parts.extend([
                    '                <eures:CompetencyDimension>',
                    f'                    <hr:CompetencyDimensionTypeCode>{dim}</hr:CompetencyDimensionTypeCode>',
                    '                    <eures:Score>',
                    f'                        <hr:ScoreText>{score}</hr:ScoreText>',
                    '                    </eures:Score>',
                    '                </eures:CompetencyDimension>',
                ])
            
            xml_parts.append('            </PersonCompetency>')
        
        # NOTE: Hard/soft skills removed - Europass only supports language competencies
        # with schemeName="NORMAL" and TaxonomyID="language". Using HARDSKILL/SOFTSKILL
        # causes the Europass parser to fail silently.
        # _add_skills_to_xml(xml_parts, knowledge)
        
        xml_parts.append('        </PersonQualifications>')
    
    # NOTE: Removed skills-only section - Europass doesn't support HARDSKILL/SOFTSKILL
    # if not languages and (knowledge.get("hardSkills") or knowledge.get("softSkills")):
    #     xml_parts.append('        <PersonQualifications>')
    #     _add_skills_to_xml(xml_parts, knowledge)
    #     xml_parts.append('        </PersonQualifications>')
    
    xml_parts.append('        <EmploymentReferences />')
    
    # Add profile picture attachment if available
    if profile_picture:
        xml_parts.extend([
            '        <eures:Attachment>',
            f'            <oa:EmbeddedData>{profile_picture}</oa:EmbeddedData>',
            '            <oa:FileType>photo</oa:FileType>',
            '            <hr:Instructions>ProfilePicture</hr:Instructions>',
            '        </eures:Attachment>',
        ])
    
    # Empty placeholder sections for Europass compatibility
    xml_parts.extend([
        '        <CreativeWorks />',
        '        <Projects />',
        '        <SocialAndPoliticalActivities />',
        '        <Skills />',
        '        <NetworksAndMemberships />',
        '        <ConferencesAndSeminars />',
        '        <VoluntaryWorks />',
        '        <CourseCertifications />',
    ])
    
    xml_parts.append('    </CandidateProfile>')
    
    # RenderingInformation section for template settings
    xml_parts.extend([
        '    <RenderingInformation>',
        '        <Design>',
        '            <Template>Template3</Template>',
        '            <Color>Default</Color>',
        '            <FontSize>Medium</FontSize>',
        '            <Logo>FirstPage</Logo>',
        '            <PageNumbers>false</PageNumbers>',
        '            <SectionsOrder>',
        '                <Section>',
        '                    <Title>work-experience</Title>',
        '                </Section>',
        '                <Section>',
        '                    <Title>education-training</Title>',
        '                </Section>',
        '                <Section>',
        '                    <Title>language</Title>',
        '                </Section>',
        '            </SectionsOrder>',
        '        </Design>',
        '    </RenderingInformation>',
        '</Candidate>',
    ])
    
    return '\n'.join(xml_parts)


def _country_to_code(country: str) -> str:
    """Convert country name to ISO 2-letter code (lowercase for Europass compatibility)."""
    if not country:
        return ""
    
    country_lower = country.lower().strip()
    
    # Already a 2-letter code - return lowercase
    if len(country_lower) == 2:
        return country_lower
    
    mapping = {
        # Full names - all lowercase ISO codes for Europass
        "france": "fr",
        "united states": "us",
        "united states of america": "us",
        "usa": "us",
        "united kingdom": "gb",
        "uk": "gb",
        "great britain": "gb",
        "germany": "de",
        "deutschland": "de",
        "spain": "es",
        "españa": "es",
        "italy": "it",
        "italia": "it",
        "belgium": "be",
        "belgique": "be",
        "netherlands": "nl",
        "pays-bas": "nl",
        "switzerland": "ch",
        "suisse": "ch",
        "portugal": "pt",
        "austria": "at",
        "poland": "pl",
        "ireland": "ie",
        "sweden": "se",
        "norway": "no",
        "denmark": "dk",
        "finland": "fi",
        "greece": "gr",
        "czech republic": "cz",
        "czechia": "cz",
        "hungary": "hu",
        "romania": "ro",
        "bulgaria": "bg",
        "croatia": "hr",
        "slovakia": "sk",
        "slovenia": "si",
        "luxembourg": "lu",
        "canada": "ca",
        "australia": "au",
        "japan": "jp",
        "china": "cn",
        "india": "in",
        "brazil": "br",
        "mexico": "mx",
    }
    
    return mapping.get(country_lower, "")


def _phone_country_to_iso(country_dialing: str) -> str:
    """Convert phone country dialing code to ISO 2-letter country code (lowercase)."""
    mapping = {
        "1": "us",    # US/Canada - default to US
        "33": "fr",   # France
        "44": "gb",   # UK
        "49": "de",   # Germany
        "34": "es",   # Spain
        "39": "it",   # Italy
        "32": "be",   # Belgium
        "31": "nl",   # Netherlands
        "41": "ch",   # Switzerland
        "351": "pt",  # Portugal
        "43": "at",   # Austria
        "48": "pl",   # Poland
        "353": "ie",  # Ireland
        "46": "se",   # Sweden
        "47": "no",   # Norway
        "45": "dk",   # Denmark
        "358": "fi",  # Finland
        "30": "gr",   # Greece
        "420": "cz",  # Czech Republic
        "36": "hu",   # Hungary
        "40": "ro",   # Romania
        "359": "bg",  # Bulgaria
        "385": "hr",  # Croatia
        "421": "sk",  # Slovakia
        "386": "si",  # Slovenia
        "352": "lu",  # Luxembourg
        "61": "au",   # Australia
        "81": "jp",   # Japan
        "86": "cn",   # China
        "91": "in",   # India
        "55": "br",   # Brazil
        "52": "mx",   # Mexico
    }
    return mapping.get(str(country_dialing), "")


def _language_to_iso639b(lang_name: str) -> str:
    """Convert language name to ISO 639-2/B code (used by Europass)."""
    # ISO 639-2/B codes (bibliographic, used by Europass)
    mapping = {
        # French variations
        "french": "fre",
        "français": "fre",
        "francais": "fre",
        "fre": "fre",
        "fra": "fre",
        "fr": "fre",
        # English variations
        "english": "eng",
        "anglais": "eng",
        "eng": "eng",
        "en": "eng",
        # German variations
        "german": "ger",
        "deutsch": "ger",
        "allemand": "ger",
        "ger": "ger",
        "deu": "ger",
        "de": "ger",
        # Spanish variations
        "spanish": "spa",
        "español": "spa",
        "espagnol": "spa",
        "spa": "spa",
        "es": "spa",
        # Italian variations
        "italian": "ita",
        "italiano": "ita",
        "italien": "ita",
        "ita": "ita",
        "it": "ita",
        # Portuguese variations
        "portuguese": "por",
        "português": "por",
        "portugais": "por",
        "por": "por",
        "pt": "por",
        # Dutch variations
        "dutch": "dut",
        "nederlands": "dut",
        "néerlandais": "dut",
        "dut": "dut",
        "nld": "dut",
        "nl": "dut",
        # Chinese variations
        "chinese": "chi",
        "中文": "chi",
        "chinois": "chi",
        "chi": "chi",
        "zho": "chi",
        "zh": "chi",
        # Japanese variations
        "japanese": "jpn",
        "日本語": "jpn",
        "japonais": "jpn",
        "jpn": "jpn",
        "ja": "jpn",
        # Russian variations
        "russian": "rus",
        "русский": "rus",
        "russe": "rus",
        "rus": "rus",
        "ru": "rus",
        # Arabic variations
        "arabic": "ara",
        "العربية": "ara",
        "arabe": "ara",
        "ara": "ara",
        "ar": "ara",
    }
    lang_lower = lang_name.lower().strip()
    return mapping.get(lang_lower, lang_lower[:3] if lang_lower else "")


def _level_to_cef(level: str) -> str:
    """Convert MAC language level to CEF level."""
    level_lower = level.lower()
    if "native" in level_lower or "full professional" in level_lower:
        return "C2"
    elif "professional" in level_lower:
        return "C1"
    elif "limited" in level_lower or "intermediate" in level_lower:
        return "B2"
    elif "elementary" in level_lower or "basic" in level_lower:
        return "A2"
    else:
        return "B1"


def _build_html_description(challenges: list[dict]) -> str:
    """
    Build HTML description from MAC challenges.
    
    Handles two cases:
    1. Challenges with plain text descriptions → wraps in <ul><li>
    2. Single challenge with full HTML (from Europass import) → uses as-is
    """
    if not challenges:
        return ""
    
    # If there's exactly one challenge and it already contains HTML tags,
    # it's likely a full Europass description - use it directly
    if len(challenges) == 1:
        desc = challenges[0].get("description", "")
        if desc and ("<p>" in desc or "<ol>" in desc or "<ul>" in desc or "<li" in desc):
            return desc  # Already HTML, use as-is
    
    # Otherwise, build from multiple challenges
    items = []
    for challenge in challenges:
        desc = challenge.get("description", "")
        if desc:
            # Strip HTML tags if present (simple cleanup)
            import re
            clean_desc = re.sub(r'<[^>]+>', '', desc).strip()
            if clean_desc:
                items.append(f"<li>{clean_desc}</li>")
    
    if items:
        return f"<ul>{''.join(items)}</ul>"
    return ""


def _validate_date(date_str: str) -> str:
    """Validate and normalize date to YYYY-MM format. Returns empty string if invalid."""
    import re
    if not date_str:
        return ""
    
    date_str = date_str.strip()
    
    # Already valid YYYY-MM format
    if re.match(r"^\d{4}-\d{2}$", date_str):
        return date_str
    
    # Handle YYYY-MM-DD format (truncate day)
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str[:7]
    
    # Handle YYYY/MM format
    if re.match(r"^\d{4}/\d{2}$", date_str):
        return date_str.replace("/", "-")
    
    # Handle MM/YYYY format
    match = re.match(r"^(\d{2})/(\d{4})$", date_str)
    if match:
        return f"{match.group(2)}-{match.group(1)}"
    
    # Return as-is if it looks like a year (YYYY)
    if re.match(r"^\d{4}$", date_str):
        return f"{date_str}-01"
    
    logger.warning(f"Invalid date format: {date_str}")
    return ""


def _add_skills_to_xml(xml_parts: list[str], knowledge: dict[str, Any]) -> None:
    """Add hard skills and soft skills to XML parts list."""
    # Hard skills (technical skills)
    hard_skills = knowledge.get("hardSkills", [])
    for hard in hard_skills:
        skill = hard.get("skill", {})
        skill_name = skill.get("name", "")
        skill_level = hard.get("level", "")
        if skill_name:
            xml_parts.extend([
                '            <PersonCompetency>',
                f'                <CompetencyID schemeName="HARDSKILL">{escape(skill_name)}</CompetencyID>',
                '                <hr:TaxonomyID>hard-skill</hr:TaxonomyID>',
            ])
            if skill_level:
                level_map = {"expert": "5", "high": "4", "medium": "3", "low": "2", "basic": "1"}
                level_score = level_map.get(skill_level.lower(), "3")
                xml_parts.extend([
                    '                <eures:CompetencyDimension>',
                    '                    <hr:CompetencyDimensionTypeCode>Proficiency</hr:CompetencyDimensionTypeCode>',
                    '                    <eures:Score>',
                    f'                        <hr:ScoreText>{level_score}</hr:ScoreText>',
                    '                    </eures:Score>',
                    '                </eures:CompetencyDimension>',
                ])
            xml_parts.append('            </PersonCompetency>')
    
    # Soft skills
    soft_skills = knowledge.get("softSkills", [])
    for soft in soft_skills:
        skill = soft.get("skill", {})
        skill_name = skill.get("name", "")
        if skill_name:
            xml_parts.extend([
                '            <PersonCompetency>',
                f'                <CompetencyID schemeName="SOFTSKILL">{escape(skill_name)}</CompetencyID>',
                '                <hr:TaxonomyID>soft-skill</hr:TaxonomyID>',
                '            </PersonCompetency>',
            ])


async def _wait_for_network_idle(page: Page, timeout: int = 10000) -> None:
    """Wait for network to be idle (no pending requests)."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeout:
        logger.warning("Network idle timeout - continuing anyway")


async def _handle_resume_dialog(page: Page) -> None:
    """Handle the initial dialog and select 'Commencer à partir du CV Europass'.
    
    This reveals the file input for XML upload.
    """
    try:
        # First check if there's a "Recommencer" (Start over) button
        start_over = page.get_by_role("button", name="Recommencer")
        try:
            await start_over.wait_for(state="visible", timeout=3000)
            await start_over.click()
            logger.info("  Dismissed 'Resume last CV' prompt")
            await _wait_for_network_idle(page, timeout=5000)
        except PlaywrightTimeout:
            pass
        
        # Click "Commencer à partir du CV Europass" to reveal file input
        europass_btn = page.get_by_role("button", name="Commencer à partir du CV Europass")
        try:
            await europass_btn.wait_for(state="visible", timeout=5000)
            await europass_btn.click()
            logger.info("  Selected 'Commencer à partir du CV Europass'")
            await _wait_for_network_idle(page, timeout=5000)
        except PlaywrightTimeout:
            logger.debug("  No 'Commencer à partir du CV Europass' button found")
        
    except Exception as e:
        logger.debug(f"  Resume dialog handling error: {e}")


async def _upload_xml_file(page: Page, xml_path: Path, timeout: int) -> bool:
    """Upload XML file using file input element.
    
    The Europass site now uses a direct file input instead of a button+file chooser.
    The file input is revealed after clicking 'Commencer à partir du CV Europass'.
    """
    try:
        # New flow: The file input is directly available after selecting Europass option
        file_input = page.locator('input[type=file]')
        
        # Wait for file input to be available
        await file_input.wait_for(state="attached", timeout=timeout)
        
        # Set the file directly on the input element
        await file_input.set_input_files(str(xml_path.absolute()))
        
        # Wait for upload to process
        await page.wait_for_timeout(2000)
        
        # Wait for builder buttons to appear (indicates successful upload)
        builder_button = page.get_by_role("button", name="Try the new CV builder (beta)")
        await builder_button.wait_for(state="visible", timeout=timeout)
        
        logger.info(f"✓ Uploaded: {xml_path.name}")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to upload file: {e}")
        return False


async def _wait_for_angular_stable(page: Page, timeout: int = 5000) -> bool:
    """Wait for Angular hydration to complete."""
    try:
        await expect(page.locator("button[aria-label='Télécharger']")).to_be_visible(timeout=timeout)
        
        async def check_hydration():
            return await page.evaluate("""() => {
                const btn = document.querySelector("button[aria-label='Télécharger']");
                return btn && (btn.__ngContext__ !== undefined || btn.hasAttribute('eclbutton'));
            }""")
        
        await expect.poll(check_hydration, timeout=timeout).to_be(True)
        return True
    except (PlaywrightTimeout, AssertionError):
        logger.debug("  Angular hydration check timeout - proceeding anyway")
        return False
    except Exception as e:
        logger.debug(f"  Angular check error: {e} - proceeding anyway")
        return False


async def _download_pdf_with_retry(
    page: Page,
    output_path: Path,
    timeout: int,
    max_retries: int = 5
) -> bool:
    """Download PDF with retry-action pattern for Angular hydration."""
    download_btn = page.locator("button[aria-label='Télécharger']")
    await _wait_for_angular_stable(page, timeout=5000)
    
    retry_intervals = [200, 300, 500, 1000, 2000]
    
    for attempt in range(1, max_retries + 1):
        try:
            await download_btn.wait_for(state="visible", timeout=timeout)
            attempt_timeout = 5000 if attempt < max_retries else timeout * 2
            
            async with page.expect_download(timeout=attempt_timeout) as download_info:
                await download_btn.click()
            
            download = await download_info.value
            await download.save_as(output_path)
            
            if output_path.exists() and output_path.stat().st_size > 0:
                if attempt > 1:
                    logger.info(f"  ✓ Download succeeded on attempt {attempt}")
                return True
            else:
                logger.warning(f"  Attempt {attempt}: Downloaded file empty")
                
        except PlaywrightTimeout:
            if attempt < max_retries:
                interval = retry_intervals[min(attempt - 1, len(retry_intervals) - 1)]
                logger.debug(f"  Attempt {attempt}: No download, retrying in {interval}ms...")
                await asyncio.sleep(interval / 1000)
            else:
                logger.warning(f"  All {max_retries} attempts failed")
        except Exception as e:
            logger.warning(f"  Attempt {attempt}: {e}")
            if attempt < max_retries:
                interval = retry_intervals[min(attempt - 1, len(retry_intervals) - 1)]
                await asyncio.sleep(interval / 1000)
    
    return False


@mcp.tool
async def generate_pdf(
    output_path: str,
    resume_id: str | None = None,
    template: str = DEFAULT_TEMPLATE,
    headless: bool = True
) -> dict[str, Any]:
    """
    Generate Europass PDF from resume data.
    
    Converts MAC JSON to Europass XML, uploads to europass.eu beta builder, and downloads PDF.
    Uses the new compact-cv-editor with proper Angular hydration handling.
    
    Args:
        output_path: Absolute path where to save the PDF file
        resume_id: ID returned by create_resume (uses most recent if not provided)
        template: CV template (cv-formal, cv-elegant, cv-modern, cv-academic, cv-creative, cv-semi-formal)
        headless: Run browser in headless mode (default: True)
        
    Returns:
        Result with PDF path and generation details
    """
    global _resumes
    start_time = time.time()
    timeout = 60000
    
    # Validate template
    if template not in VALID_TEMPLATES:
        return {
            "status": "error",
            "message": f"Invalid template '{template}'. Valid templates: {', '.join(sorted(VALID_TEMPLATES))}"
        }
    
    # Get resume by ID or use most recent
    if resume_id:
        if resume_id not in _resumes:
            return {
                "status": "error",
                "message": f"Resume ID '{resume_id}' not found. Call create_resume first."
            }
        resume_data = _resumes[resume_id]
    elif _resumes:
        # Use most recent (last inserted)
        resume_id = list(_resumes.keys())[-1]
        resume_data = _resumes[resume_id]
        logger.info(f"Using most recent resume: {resume_id}")
    else:
        return {
            "status": "error",
            "message": "No resume data. Call create_resume first with MAC JSON data."
        }
    
    pdf_path = Path(output_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if we have raw Europass XML (imported via import_europass_xml)
    # If so, use it directly instead of converting from MAC
    if resume_id in _raw_europass_xml:
        europass_xml = _raw_europass_xml[resume_id]
        logger.info("Using imported Europass XML (preserving original data)")
        source_type = "imported"
    else:
        # Convert MAC to Europass XML
        europass_xml = _mac_to_europass_xml(resume_data)
        source_type = "converted"
    
    xml_path = pdf_path.with_suffix('.xml')
    xml_path.write_text(europass_xml, encoding='utf-8')
    
    logger.info("=" * 60)
    logger.info("Europass CV PDF Generator (Beta Builder)")
    logger.info("=" * 60)
    logger.info(f"Resume:   {resume_id} ({source_type})")
    logger.info(f"Input:    {xml_path}")
    logger.info(f"Output:   {pdf_path}")
    logger.info(f"Template: {template}")
    logger.info("=" * 60)
    
    profile = resume_data.get("aboutMe", {}).get("profile", {})
    name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                accept_downloads=True,
                locale='fr-FR',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            page.set_default_timeout(timeout)
            
            try:
                # Step 1: Navigate to CV editor
                logger.info("1/7 Navigating to Europass...")
                await page.goto(EUROPASS_URL, wait_until="domcontentloaded")
                await _wait_for_network_idle(page)
                
                # Step 2: Handle any resume dialogs
                logger.info("2/7 Handling dialogs...")
                await _handle_resume_dialog(page)
                
                # Step 3: Upload XML file
                logger.info("3/7 Uploading XML...")
                if not await _upload_xml_file(page, xml_path, timeout):
                    raise Exception("Failed to upload XML file")
                
                # Step 4: Select new CV builder (beta)
                logger.info("4/7 Selecting beta builder...")
                builder_btn = page.get_by_role("button", name="Try the new CV builder (beta)")
                await builder_btn.click()
                
                # Handle "Continuer" dialog if it appears
                try:
                    continue_btn = page.get_by_role("button", name="Continuer")
                    await continue_btn.wait_for(state="visible", timeout=3000)
                    await continue_btn.click()
                    logger.info("  Clicked 'Continuer' to confirm")
                    await _wait_for_network_idle(page, timeout=5000)
                except PlaywrightTimeout:
                    pass
                
                # Wait for URL change to beta builder
                await page.wait_for_url("**/compact-cv-editor**", timeout=timeout)
                await _wait_for_network_idle(page)
                
                # Handle error dialog if present
                try:
                    ok_btn = page.get_by_role("button", name="OK")
                    await ok_btn.wait_for(state="visible", timeout=3000)
                    await ok_btn.click()
                    logger.info("  Dismissed validation dialog")
                except PlaywrightTimeout:
                    pass
                
                # Step 5: Select template
                logger.info(f"5/7 Selecting template: {template}...")
                # Template combobox - find by label text and use first combobox
                # The page has multiple comboboxes, template is the first one in "Customise your CV"
                try:
                    # Try to find combobox near "Template" label
                    template_select = page.locator("select, [role='combobox']").first
                    await template_select.wait_for(state="visible", timeout=10000)
                    await template_select.select_option(value=template)
                    logger.info(f"  ✓ Selected template: {template}")
                except PlaywrightTimeout:
                    logger.warning(f"  ⚠ Template selector not found, using default")
                await _wait_for_network_idle(page, timeout=10000)
                
                # Step 6: Enter CV name (REQUIRED before download)
                logger.info("6/7 Entering CV name...")
                name_input = page.get_by_role("textbox", name="Nom")
                await name_input.wait_for(state="visible", timeout=5000)
                await name_input.fill(pdf_path.stem)
                await name_input.press("Enter")
                await _wait_for_network_idle(page, timeout=5000)
                logger.info(f"  ✓ CV name validated: {pdf_path.stem}")
                
                # Step 7: Download PDF
                logger.info("7/7 Downloading PDF...")
                if not await _download_pdf_with_retry(page, pdf_path, timeout):
                    raise Exception("Failed to download PDF after retries")
                
                elapsed = time.time() - start_time
                file_size = pdf_path.stat().st_size
                
                logger.info("=" * 60)
                logger.info("✓ PDF generated successfully!")
                logger.info(f"  Path: {pdf_path}")
                logger.info(f"  Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
                logger.info(f"  Time: {elapsed:.1f}s")
                logger.info("=" * 60)
                
                return {
                    "status": "success",
                    "message": f"PDF generated for {name}",
                    "pdf_path": str(pdf_path),
                    "xml_path": str(xml_path),
                    "file_size_bytes": file_size,
                    "elapsed_seconds": round(elapsed, 1),
                    "template": template
                }
                
            finally:
                await context.close()
                await browser.close()
                
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("=" * 60)
        logger.error(f"✗ Failed after {elapsed:.1f}s: {e}")
        logger.error("=" * 60)
        
        # Clean up intermediate XML file on failure
        xml_existed = xml_path.exists()
        if xml_existed:
            try:
                xml_path.unlink()
                logger.debug(f"Cleaned up XML file: {xml_path}")
            except OSError:
                pass  # Ignore cleanup errors
        
        return {
            "status": "error",
            "message": f"PDF generation failed: {str(e)}",
            "elapsed_seconds": round(elapsed, 1),
            "xml_cleaned_up": xml_existed
        }


@mcp.tool
def get_mac_schema() -> dict[str, Any]:
    """
    Get the MAC (Manfred Awesomic CV) JSON Schema for reference.
    
    Returns the schema structure to help construct valid MAC JSON.
    
    Returns:
        MAC JSON Schema overview with key sections
    """
    return {
        "schema_url": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
        "version": "0.5",
        "sections": {
            "settings": "Language and display preferences",
            "aboutMe": {
                "profile": "Name, title, description, birthday, avatar, location",
                "relevantLinks": "LinkedIn, GitHub, Twitter, website URLs",
                "interestingFacts": "Fun facts and personal interests"
            },
            "experience": {
                "jobs": "Work history with roles, challenges, competences",
                "projects": "Personal/side projects",
                "publicArtifacts": "Publications, talks, open source contributions"
            },
            "knowledge": {
                "languages": "Spoken languages with proficiency levels",
                "hardSkills": "Technical skills (technology, tool, domain)",
                "softSkills": "Soft skills (practice, technique)",
                "studies": "Education and certifications"
            },
            "careerPreferences": {
                "contact": "Email, phone, public profiles",
                "preferences": "Preferred/discarded roles, salary, locations"
            }
        },
        "example_minimal": {
            "$schema": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
            "settings": {"language": "EN"},
            "aboutMe": {
                "profile": {
                    "name": "John",
                    "surnames": "Doe",
                    "title": "Software Engineer"
                }
            }
        }
    }


def main():
    """Entry point for the europass-mcp CLI command."""
    mcp.run()


if __name__ == "__main__":
    main()
