"""
Europass CV Generator MCP Server

Uses MAC (Manfred Awesomic CV) JSON as internal format, then converts to Europass XML for PDF generation.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4
from xml.sax.saxutils import escape

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
    
    Workflow:
    1. Use parse_document to extract text from DOCX/PDF files
    2. Use create_resume with MAC JSON structure to store CV data
    3. Use generate_pdf to create the final Europass PDF
    
    The internal format is MAC (Manfred Awesomic CV) JSON schema.
    See: https://github.com/getmanfred/mac
    """,
)

# Storage for resumes by ID (session-safe)
_resumes: dict[str, dict[str, Any]] = {}

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
    studies = mac_json.get("knowledge", {}).get("studies", [])
    
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
        List of resume IDs with their summaries
    """
    global _resumes
    
    resumes_list = []
    for resume_id, mac_json in _resumes.items():
        profile = mac_json.get("aboutMe", {}).get("profile", {})
        name = f"{profile.get('name', '')} {profile.get('surnames', '')}".strip()
        resumes_list.append({
            "resume_id": resume_id,
            "name": name,
            "title": profile.get("title", ""),
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
    
    return {
        "status": "success",
        "message": f"Resume for {name} (ID: {resume_id}) deleted.",
        "remaining_count": len(_resumes)
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
    title = profile.get("title", "")
    description = profile.get("description", "")
    
    xml_parts.extend([
        '    <CandidatePerson>',
        '        <PersonName>',
        f'            <oa:GivenName>{escape(name)}</oa:GivenName>',
        f'            <hr:FamilyName>{escape(surnames)}</hr:FamilyName>',
        '        </PersonName>',
    ])
    
    # Professional title
    if title:
        xml_parts.append(f'        <hr:PersonTitle>{escape(title)}</hr:PersonTitle>')
    
    # Professional summary/description
    if description:
        xml_parts.append(f'        <hr:PersonDescription>{escape(description)}</hr:PersonDescription>')
    
    if email:
        xml_parts.extend([
            '        <Communication>',
            '            <ChannelCode>Email</ChannelCode>',
            f'            <oa:URI>{escape(email)}</oa:URI>',
            '        </Communication>',
        ])
    
    # Relevant links (LinkedIn, GitHub, etc.)
    relevant_links = mac.get("aboutMe", {}).get("relevantLinks", [])
    for link in relevant_links:
        url = link.get("URL", "")
        link_type = link.get("type", "website").lower()
        if url:
            xml_parts.extend([
                '        <Communication>',
                f'            <ChannelCode>{escape(link_type.capitalize())}</ChannelCode>',
                f'            <oa:URI>{escape(url)}</oa:URI>',
                '        </Communication>',
            ])
    
    # Phone - handle both dict format and plain string
    if phones:
        phone = phones[0]
        if isinstance(phone, dict):
            country_code = phone.get("countryCode", "")
            number = phone.get("number", "")
        else:
            # Plain string like "+33631092519" - extract country code
            phone_str = str(phone).strip()
            if phone_str.startswith("+"):
                # Extract country code (assume 2-3 digits after +)
                for i in range(2, 5):
                    if i < len(phone_str) and not phone_str[i].isdigit():
                        break
                country_code = phone_str[:i]
                number = phone_str[i:]
            else:
                country_code = ""
                number = phone_str
        xml_parts.extend([
            '        <Communication>',
            '            <ChannelCode>Telephone</ChannelCode>',
            '            <UseCode>work</UseCode>',
            f'            <CountryDialing>{escape(country_code)}</CountryDialing>',
            f'            <oa:DialNumber>{escape(number)}</oa:DialNumber>',
            '        </Communication>',
        ])
    
    # Address
    if location:
        city = location.get("municipality", "")
        country = location.get("country", "")
        region = location.get("region", "")
        country_code = _country_to_code(country)
        
        xml_parts.extend([
            '        <Communication>',
            '            <UseCode>home</UseCode>',
            '            <Address type="home">',
            f'                <oa:AddressLine>{escape(region)}</oa:AddressLine>',
            f'                <oa:CityName>{escape(city)}</oa:CityName>',
            f'                <CountryCode>{country_code}</CountryCode>',
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
                
                # Build description from challenges
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
                    '                </PositionHistory>',
                    '            </EmployerHistory>',
                ])
        
        xml_parts.append('        </EmploymentHistory>')
    
    # Education History (exclude certifications - they go in Certifications section)
    studies = knowledge.get("studies", [])
    education_studies = [s for s in studies if s.get("studyType") != "certification"]
    if education_studies:
        xml_parts.append('        <EducationHistory>')
        for study in education_studies:
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
            
            if date:
                xml_parts.extend([
                    '                <hr:CertificationDate>',
                    f'                    <hr:FormattedDateTime>{date}</hr:FormattedDateTime>',
                    '                </hr:CertificationDate>',
                ])
            
            xml_parts.append('            </Certification>')
        
        xml_parts.append('        </Certifications>')
    
    # Languages
    languages = knowledge.get("languages", [])
    if languages:
        xml_parts.append('        <PersonQualifications>')
        for lang in languages:
            lang_name = lang.get("name", "").lower()[:3]
            level = _level_to_cef(lang.get("level", ""))
            
            xml_parts.extend([
                '            <PersonCompetency>',
                f'                <CompetencyID schemeName="NORMAL">{lang_name}</CompetencyID>',
                '                <hr:TaxonomyID>language</hr:TaxonomyID>',
            ])
            
            for dim in ["CEF-Understanding-Listening", "CEF-Understanding-Reading", 
                       "CEF-Speaking-Interaction", "CEF-Speaking-Production", "CEF-Writing-Production"]:
                xml_parts.extend([
                    '                <eures:CompetencyDimension>',
                    f'                    <hr:CompetencyDimensionTypeCode>{dim}</hr:CompetencyDimensionTypeCode>',
                    '                    <eures:Score>',
                    f'                        <hr:ScoreText>{level}</hr:ScoreText>',
                    '                    </eures:Score>',
                    '                </eures:CompetencyDimension>',
                ])
            
            xml_parts.append('            </PersonCompetency>')
        
        # Add hard and soft skills using helper
        _add_skills_to_xml(xml_parts, knowledge)
        
        xml_parts.append('        </PersonQualifications>')
    
    # If no languages but we have skills, still output them
    if not languages and (knowledge.get("hardSkills") or knowledge.get("softSkills")):
        xml_parts.append('        <PersonQualifications>')
        _add_skills_to_xml(xml_parts, knowledge)
        xml_parts.append('        </PersonQualifications>')
    
    xml_parts.extend([
        '        <EmploymentReferences />',
        '    </CandidateProfile>',
        '</Candidate>',
    ])
    
    return '\n'.join(xml_parts)


def _country_to_code(country: str) -> str:
    """Convert country name to ISO 2-letter code (uppercase)."""
    if not country:
        return ""
    
    country_lower = country.lower().strip()
    
    # Already a 2-letter code - return uppercase
    if len(country_lower) == 2:
        return country_lower.upper()
    
    mapping = {
        # Full names - all uppercase ISO codes
        "france": "FR",
        "united states": "US",
        "united states of america": "US",
        "usa": "US",
        "united kingdom": "GB",
        "uk": "GB",
        "great britain": "GB",
        "germany": "DE",
        "deutschland": "DE",
        "spain": "ES",
        "españa": "ES",
        "italy": "IT",
        "italia": "IT",
        "belgium": "BE",
        "belgique": "BE",
        "netherlands": "NL",
        "pays-bas": "NL",
        "switzerland": "CH",
        "suisse": "CH",
        "portugal": "PT",
        "austria": "AT",
        "poland": "PL",
        "ireland": "IE",
        "sweden": "SE",
        "norway": "NO",
        "denmark": "DK",
        "finland": "FI",
        "greece": "GR",
        "czech republic": "CZ",
        "czechia": "CZ",
        "hungary": "HU",
        "romania": "RO",
        "bulgaria": "BG",
        "croatia": "HR",
        "slovakia": "SK",
        "slovenia": "SI",
        "luxembourg": "LU",
        "canada": "CA",
        "australia": "AU",
        "japan": "JP",
        "china": "CN",
        "india": "IN",
        "brazil": "BR",
        "mexico": "MX",
    }
    
    return mapping.get(country_lower, "")


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
    """Build HTML description from MAC challenges."""
    if not challenges:
        return ""
    
    items = []
    for challenge in challenges:
        desc = challenge.get("description", "")
        if desc:
            items.append(f"<li>{desc}</li>")
    
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
    """Handle the 'Resume last CV' dialog if present."""
    try:
        resume_btn = page.get_by_role("button", name="Commencer à partir du CV Europass")
        try:
            await resume_btn.wait_for(state="visible", timeout=3000)
        except PlaywrightTimeout:
            return
        
        await resume_btn.click()
        logger.info("  Dismissed 'Resume last CV' prompt")
        await _wait_for_network_idle(page, timeout=5000)
        
        continue_btn = page.get_by_role("button", name="Continuer")
        try:
            await continue_btn.wait_for(state="visible", timeout=3000)
            await continue_btn.click()
            logger.info("  Clicked 'Continuer'")
            await _wait_for_network_idle(page, timeout=5000)
        except PlaywrightTimeout:
            pass
    except Exception as e:
        logger.debug(f"  No resume dialog or error: {e}")


async def _upload_xml_file(page: Page, xml_path: Path, timeout: int) -> bool:
    """Upload XML file using file chooser."""
    try:
        file_button = page.get_by_role("button", name="Sélectionner un fichier")
        await file_button.wait_for(state="visible", timeout=timeout)
        
        async with page.expect_file_chooser(timeout=timeout) as fc_info:
            await file_button.click()
        
        file_chooser = await fc_info.value
        await file_chooser.set_files(str(xml_path))
        
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
    
    # Convert MAC to Europass XML
    europass_xml = _mac_to_europass_xml(resume_data)
    xml_path = pdf_path.with_suffix('.xml')
    xml_path.write_text(europass_xml, encoding='utf-8')
    
    logger.info("=" * 60)
    logger.info("Europass CV PDF Generator (Beta Builder)")
    logger.info("=" * 60)
    logger.info(f"Resume:   {resume_id}")
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
                template_select = page.locator("select.ecl-select").first
                await template_select.wait_for(state="visible", timeout=10000)
                await template_select.select_option(value=template)
                logger.info(f"  ✓ Selected template: {template}")
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
