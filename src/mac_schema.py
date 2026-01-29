"""
MAC (Manfred Awesomic CV) Pydantic Schema

This module defines Pydantic models that mirror the MAC JSON schema.
Used for:
1. Structured LLM extraction (DOCX → MAC) via trustcall
2. Validation of MAC JSON
3. Type hints throughout the codebase

See: https://github.com/getmanfred/mac/blob/master/schema.json
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class Location(BaseModel):
    """Geographic location."""
    country: Optional[str] = None
    region: Optional[str] = None
    municipality: Optional[str] = None
    address: Optional[str] = None
    postalCode: Optional[str] = None
    notes: Optional[str] = None


class Avatar(BaseModel):
    """Profile picture or avatar."""
    link: Optional[str] = Field(None, description="URL to the image")
    alt: Optional[str] = Field(None, description="Alt text for the image")


class Profile(BaseModel):
    """Personal profile information."""
    name: str = Field(..., description="First name")
    surnames: str = Field(..., description="Last name / Family name")
    title: Optional[str] = Field(None, description="Professional title, e.g. 'Senior Developer'")
    description: Optional[str] = Field(None, description="Professional summary / About me")
    birthday: Optional[str] = Field(None, description="Birth date in YYYY-MM-DD format")
    avatar: Optional[Avatar] = None
    location: Optional[Location] = None


class ContactInfo(BaseModel):
    """Contact information."""
    contactMails: Optional[list[str]] = Field(default_factory=list, description="Email addresses")
    phoneNumbers: Optional[list[str]] = Field(default_factory=list, description="Phone numbers in E.164 format")


class PublicProfile(BaseModel):
    """Link to a public profile (LinkedIn, GitHub, etc.)."""
    type: str = Field(..., description="Profile type: linkedin, github, twitter, website, other")
    URL: str = Field(..., description="Full URL to the profile")


class AboutMe(BaseModel):
    """The 'aboutMe' section of a MAC CV."""
    profile: Profile
    relevantLinks: Optional[list[PublicProfile]] = Field(default_factory=list)
    interpipi: Optional[ContactInfo] = None  # Internal contact - rarely used
    

class Organization(BaseModel):
    """An organization (employer or educational institution)."""
    name: str = Field(..., description="Organization name")
    description: Optional[str] = Field(None, description="Brief description of the organization")
    URL: Optional[str] = None
    image: Optional[Avatar] = None
    location: Optional[Location] = None


class Role(BaseModel):
    """A role within a job position."""
    name: str = Field(..., description="Role title, e.g. 'Tech Lead'")
    startDate: str = Field(..., description="Start date in YYYY-MM-DD format")
    finishDate: Optional[str] = Field(None, description="End date in YYYY-MM-DD format (None if current)")
    challenges: Optional[list[dict]] = Field(
        default_factory=list,
        description="List of challenges/achievements with 'description' field"
    )


class Job(BaseModel):
    """A job/work experience entry."""
    organization: Organization
    roles: list[Role] = Field(..., min_length=1, description="List of roles held at this organization")
    type: Optional[str] = Field("paid", description="Type: paid, freelance, volunteer, internship")


class Study(BaseModel):
    """An education entry."""
    studyType: str = Field(..., description="Type: degree, certification, course, selfTraining")
    degreeAchieved: bool = Field(True, description="Whether the degree was completed")
    name: str = Field(..., description="Name of the degree/certification")
    startDate: str = Field(..., description="Start date in YYYY-MM-DD format")
    finishDate: Optional[str] = Field(None, description="End date (None if ongoing)")
    institution: Organization
    description: Optional[str] = Field(None, description="Additional details about the study")


class Language(BaseModel):
    """A language proficiency entry."""
    name: str = Field(..., description="Language name, e.g. 'English', 'French'")
    fullName: Optional[str] = Field(None, description="Full name with locale, e.g. 'English (US)'")
    level: Optional[str] = Field(None, description="Proficiency level: native, fluent, advanced, intermediate, basic")
    cefrScores: Optional[dict[str, str]] = Field(
        None,
        description="CEFR scores per dimension: CEF-Understanding-Listening, CEF-Understanding-Reading, etc."
    )


class HardSkill(BaseModel):
    """A technical/hard skill."""
    skill: dict = Field(..., description="Skill with 'name' and optionally 'type' (tool, technology, framework)")
    level: Optional[str] = Field(None, description="Proficiency: expert, high, medium, low")


class SoftSkill(BaseModel):
    """A soft/interpersonal skill."""
    skill: dict = Field(..., description="Skill with 'name' field")
    level: Optional[str] = Field(None, description="Proficiency: expert, high, medium, low")


class Knowledge(BaseModel):
    """The 'knowledge' section: skills, education, languages."""
    languages: Optional[list[Language]] = Field(default_factory=list)
    hardSkills: Optional[list[HardSkill]] = Field(default_factory=list)
    softSkills: Optional[list[SoftSkill]] = Field(default_factory=list)
    studies: Optional[list[Study]] = Field(default_factory=list)


class Experience(BaseModel):
    """The 'experience' section: work history."""
    jobs: list[Job] = Field(default_factory=list)


class Settings(BaseModel):
    """CV settings."""
    language: str = Field("EN", description="CV language code: EN, FR, DE, ES, etc.")


class MACResume(BaseModel):
    """
    Complete MAC (Manfred Awesomic CV) Resume.
    
    This is the IR (Intermediate Representation) for the CV generator.
    All input formats (PDF, DOCX, XML) are converted to this schema.
    This schema is then converted to Europass XML for PDF generation.
    """
    settings: Settings = Field(default_factory=lambda: Settings(language="EN"))
    aboutMe: AboutMe
    experience: Optional[Experience] = Field(default_factory=Experience)
    knowledge: Optional[Knowledge] = Field(default_factory=Knowledge)


# Simplified schema for LLM extraction (fewer nested objects)
class ExtractedJob(BaseModel):
    """Simplified job for LLM extraction."""
    company_name: str = Field(..., description="Name of the company/employer")
    job_title: str = Field(..., description="Job title or role name")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or YYYY-MM)")
    end_date: Optional[str] = Field(None, description="End date (None if current position)")
    description: Optional[str] = Field(None, description="Job responsibilities and achievements")
    location: Optional[str] = Field(None, description="City, Country")


class ExtractedEducation(BaseModel):
    """Simplified education for LLM extraction."""
    institution_name: str = Field(..., description="Name of school/university")
    degree_name: str = Field(..., description="Degree or certification name")
    field_of_study: Optional[str] = Field(None, description="Major or field of study")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD or YYYY-MM)")
    end_date: Optional[str] = Field(None, description="End date (None if ongoing)")
    description: Optional[str] = Field(None, description="Additional details")


class ExtractedLanguage(BaseModel):
    """Simplified language for LLM extraction."""
    language: str = Field(..., description="Language name")
    level: str = Field(..., description="Proficiency: native, fluent, advanced, intermediate, basic")


class ExtractedSkill(BaseModel):
    """Simplified skill for LLM extraction."""
    name: str = Field(..., description="Skill name")
    category: str = Field("technical", description="Category: technical, soft, language, tool")


class ExtractedCV(BaseModel):
    """
    Simplified CV structure for LLM extraction.
    
    This schema is easier for LLMs to populate from unstructured text.
    It is then converted to the full MACResume format.
    """
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name / family name")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    title: Optional[str] = Field(None, description="Professional title")
    summary: Optional[str] = Field(None, description="Professional summary / about me")
    location: Optional[str] = Field(None, description="Current location (City, Country)")
    
    jobs: list[ExtractedJob] = Field(default_factory=list, description="Work experience")
    education: list[ExtractedEducation] = Field(default_factory=list, description="Education history")
    languages: list[ExtractedLanguage] = Field(default_factory=list, description="Languages spoken")
    skills: list[ExtractedSkill] = Field(default_factory=list, description="Skills")
    
    linkedin_url: Optional[str] = Field(None, description="LinkedIn profile URL")
    github_url: Optional[str] = Field(None, description="GitHub profile URL")
    website_url: Optional[str] = Field(None, description="Personal website URL")


def extracted_cv_to_mac(extracted: ExtractedCV) -> dict:
    """
    Convert ExtractedCV (LLM-friendly) to MAC JSON (full schema).
    
    This bridges the gap between what an LLM can easily extract
    and what the Europass converter needs.
    """
    # Build profile
    profile = {
        "name": extracted.first_name,
        "surnames": extracted.last_name,
    }
    if extracted.title:
        profile["title"] = extracted.title
    if extracted.summary:
        profile["description"] = extracted.summary
    if extracted.location:
        # Parse "City, Country" format
        parts = [p.strip() for p in extracted.location.split(",")]
        profile["location"] = {
            "municipality": parts[0] if parts else None,
            "country": parts[-1] if len(parts) > 1 else None,
        }
    
    # Build relevant links
    relevant_links = []
    if extracted.linkedin_url:
        relevant_links.append({"type": "linkedin", "URL": extracted.linkedin_url})
    if extracted.github_url:
        relevant_links.append({"type": "github", "URL": extracted.github_url})
    if extracted.website_url:
        relevant_links.append({"type": "website", "URL": extracted.website_url})
    
    # Build jobs
    jobs = []
    for job in extracted.jobs:
        # Parse location
        location = None
        if job.location:
            parts = [p.strip() for p in job.location.split(",")]
            location = {
                "municipality": parts[0] if parts else None,
                "country": parts[-1] if len(parts) > 1 else None,
            }
        
        jobs.append({
            "organization": {
                "name": job.company_name,
                "location": location,
            },
            "roles": [{
                "name": job.job_title,
                "startDate": job.start_date,
                "finishDate": job.end_date,
                "challenges": [{"description": job.description}] if job.description else [],
            }],
            "type": "paid",
        })
    
    # Build studies
    studies = []
    for edu in extracted.education:
        name = edu.degree_name
        if edu.field_of_study:
            name = f"{edu.degree_name} - {edu.field_of_study}"
        
        studies.append({
            "studyType": "degree",
            "degreeAchieved": True,
            "name": name,
            "startDate": edu.start_date,
            "finishDate": edu.end_date,
            "institution": {"name": edu.institution_name},
            "description": edu.description,
        })
    
    # Build languages
    languages = []
    for lang in extracted.languages:
        languages.append({
            "name": lang.language,
            "level": lang.level,
        })
    
    # Build skills
    hard_skills = []
    soft_skills = []
    for skill in extracted.skills:
        skill_entry = {"skill": {"name": skill.name}}
        if skill.category in ("technical", "tool", "technology", "framework"):
            hard_skills.append(skill_entry)
        else:
            soft_skills.append(skill_entry)
    
    # Assemble MAC JSON
    mac = {
        "$schema": "https://raw.githubusercontent.com/getmanfred/mac/v0.5/schema/schema.json",
        "settings": {"language": "EN"},
        "aboutMe": {
            "profile": profile,
            "relevantLinks": relevant_links,
        },
        "experience": {"jobs": jobs},
        "knowledge": {
            "studies": studies,
            "languages": languages,
            "hardSkills": hard_skills,
            "softSkills": soft_skills,
        },
    }
    
    # Add contact info if available
    contact = {}
    if extracted.email:
        contact["contactMails"] = [extracted.email]
    if extracted.phone:
        contact["phoneNumbers"] = [extracted.phone]
    if contact:
        mac["aboutMe"]["interpipi"] = contact
    
    return mac
