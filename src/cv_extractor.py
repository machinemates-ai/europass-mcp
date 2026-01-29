"""
Structured CV Extraction using LLM + trustcall

This module provides LLM-based extraction of CV data from unstructured text
(e.g., DOCX content) into the MAC JSON schema.

Uses trustcall for reliable structured output with:
- JSON Patch for error recovery (instead of full regeneration)
- Pydantic validation
- Support for complex nested schemas

Architecture:
    DOCX Text → LLM (with trustcall) → ExtractedCV → MAC JSON → Europass XML → PDF
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Try to import LLM dependencies (optional)
try:
    from trustcall import create_extractor
    from langchain_openai import ChatOpenAI
    TRUSTCALL_AVAILABLE = True
except ImportError:
    TRUSTCALL_AVAILABLE = False
    logger.warning("trustcall or langchain-openai not installed. DOCX → MAC extraction disabled.")
    logger.warning("Install with: pip install trustcall langchain-openai")

from .mac_schema import ExtractedCV, extracted_cv_to_mac


# Extraction prompt template
EXTRACTION_PROMPT = """Extract CV/resume information from the following document text.

Be thorough and extract ALL available information including:
- Personal details (name, email, phone, location)
- Professional summary/about me
- Work experience (all jobs with dates, titles, descriptions)
- Education (all degrees, certifications, courses)
- Languages (with proficiency levels)
- Skills (technical, soft, tools)
- Links (LinkedIn, GitHub, website)

For dates:
- Use YYYY-MM-DD or YYYY-MM format
- If only year is mentioned, use YYYY-01-01
- If "Present" or "Current", leave end_date as null

For proficiency levels:
- Use: native, fluent, advanced, intermediate, basic

<document>
{text}
</document>

Extract all CV information into the structured format."""


def extract_cv_from_text(
    text: str,
    model: str = "gpt-4o-mini",
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Extract structured CV data from unstructured text using LLM.
    
    Uses trustcall for reliable structured extraction with:
    - Pydantic schema validation
    - Automatic error recovery via JSON Patch
    - Complex nested schema support
    
    Args:
        text: CV text content (e.g., from DOCX)
        model: OpenAI model to use
        temperature: LLM temperature (0.0 for deterministic)
        
    Returns:
        dict with:
        - status: "success" or "error"
        - mac_json: MAC-formatted CV (if success)
        - extracted: Raw extracted data (if success)
        - message: Error message (if error)
    """
    if not TRUSTCALL_AVAILABLE:
        return {
            "status": "error",
            "message": "trustcall not installed. Run: pip install trustcall langchain-openai",
        }
    
    if not text or len(text.strip()) < 50:
        return {
            "status": "error",
            "message": "Text too short to extract CV data",
        }
    
    try:
        # Create LLM
        llm = ChatOpenAI(model=model, temperature=temperature)
        
        # Create extractor with ExtractedCV schema
        extractor = create_extractor(
            llm,
            tools=[ExtractedCV],
            tool_choice="ExtractedCV",
        )
        
        # Run extraction
        prompt = EXTRACTION_PROMPT.format(text=text[:15000])  # Limit text length
        result = extractor.invoke({"messages": [("user", prompt)]})
        
        # Get extracted CV
        if not result.get("responses"):
            return {
                "status": "error",
                "message": "LLM did not return structured data",
            }
        
        extracted_cv: ExtractedCV = result["responses"][0]
        
        # Convert to MAC JSON
        mac_json = extracted_cv_to_mac(extracted_cv)
        
        logger.info(f"Extracted CV: {extracted_cv.first_name} {extracted_cv.last_name}")
        logger.info(f"  Jobs: {len(extracted_cv.jobs)}")
        logger.info(f"  Education: {len(extracted_cv.education)}")
        logger.info(f"  Skills: {len(extracted_cv.skills)}")
        
        return {
            "status": "success",
            "mac_json": mac_json,
            "extracted": extracted_cv.model_dump(),
            "message": f"Extracted CV for {extracted_cv.first_name} {extracted_cv.last_name}",
        }
        
    except Exception as e:
        logger.error(f"CV extraction failed: {e}")
        return {
            "status": "error",
            "message": f"Extraction failed: {str(e)}",
        }


def is_extraction_available() -> bool:
    """Check if LLM extraction is available."""
    return TRUSTCALL_AVAILABLE
