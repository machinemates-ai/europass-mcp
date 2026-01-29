"""
Structured CV Extraction using LLM + trustcall

This module provides LLM-based extraction of CV data from unstructured text
(e.g., DOCX content) into the MAC JSON schema.

Uses trustcall for reliable structured output with:
- JSON Patch for error recovery (instead of full regeneration)
- Pydantic validation
- Support for complex nested schemas

Supports multiple LLM providers:
- OpenAI: gpt-4o, gpt-4o-mini, gpt-5-mini
- Google: gemini-3-flash, gemini-2.5-flash
- Anthropic: claude-4.5-haiku

Architecture:
    DOCX Text → LLM (with trustcall) → ExtractedCV → MAC JSON → Europass XML → PDF
"""

import logging
import os
import warnings
from typing import Any

# Suppress LangGraph deprecation warning from trustcall
# (trustcall uses deprecated import path, fixed in future versions)
warnings.filterwarnings(
    "ignore",
    message="Importing Send from langgraph.constants is deprecated",
    category=DeprecationWarning,
)

logger = logging.getLogger(__name__)

# Provider detection
OPENAI_AVAILABLE = False
GOOGLE_AVAILABLE = False
ANTHROPIC_AVAILABLE = False
TRUSTCALL_AVAILABLE = False

# Try to import trustcall
try:
    from trustcall import create_extractor
    TRUSTCALL_AVAILABLE = True
except ImportError:
    logger.warning("trustcall not installed. Run: pip install trustcall")

# Try to import OpenAI
try:
    from langchain_openai import ChatOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    pass

# Try to import Google
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GOOGLE_AVAILABLE = True
except ImportError:
    pass

# Try to import Anthropic
try:
    from langchain_anthropic import ChatAnthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    pass

if not TRUSTCALL_AVAILABLE:
    logger.warning("trustcall not installed. DOCX → MAC extraction disabled.")
    logger.warning("Install with: pip install trustcall")
elif not (OPENAI_AVAILABLE or GOOGLE_AVAILABLE or ANTHROPIC_AVAILABLE):
    logger.warning("No LLM provider installed. Install one of:")
    logger.warning("  pip install langchain-openai")
    logger.warning("  pip install langchain-google-genai")
    logger.warning("  pip install langchain-anthropic")

from .mac_schema import ExtractedCV, extracted_cv_to_mac

# Default model by provider
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "google": "gemini-3-flash-preview",  # Winner of benchmark: 6x faster, perfect accuracy
    "anthropic": "claude-3-5-haiku-latest",
}

# Model to provider mapping
MODEL_PROVIDERS = {
    # OpenAI
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "gpt-5-mini": "openai",
    "gpt-5-nano": "openai",
    # Google
    "gemini-3-flash-preview": "google",
    "gemini-2.5-flash": "google",
    "gemini-2.5-flash-lite": "google",
    "gemini-2.5-pro": "google",
    # Anthropic
    "claude-3-5-haiku-latest": "anthropic",
    "claude-4.5-haiku": "anthropic",
    "claude-4.5-sonnet": "anthropic",
}


def _get_default_model() -> tuple[str, str]:
    """Get the default model based on available providers and API keys."""
    # Prefer Gemini if available (best price/performance for extraction)
    if GOOGLE_AVAILABLE and os.getenv("GOOGLE_API_KEY"):
        return "gemini-2.5-flash", "google"
    # Fall back to OpenAI
    if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini", "openai"
    # Fall back to Anthropic
    if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
        return "claude-3-5-haiku-latest", "anthropic"
    # Default to OpenAI (will fail if no key, but that's expected)
    return "gpt-4o-mini", "openai"


def _create_llm(model: str, temperature: float):
    """Create LLM instance based on model name."""
    provider = MODEL_PROVIDERS.get(model, "openai")
    
    if provider == "google":
        if not GOOGLE_AVAILABLE:
            raise ImportError("langchain-google-genai not installed. Run: pip install langchain-google-genai")
        return ChatGoogleGenerativeAI(model=model, temperature=temperature)
    elif provider == "anthropic":
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("langchain-anthropic not installed. Run: pip install langchain-anthropic")
        return ChatAnthropic(model=model, temperature=temperature)
    else:  # openai
        if not OPENAI_AVAILABLE:
            raise ImportError("langchain-openai not installed. Run: pip install langchain-openai")
        return ChatOpenAI(model=model, temperature=temperature)


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
    model: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """
    Extract structured CV data from unstructured text using LLM.
    
    Uses trustcall for reliable structured extraction with:
    - Pydantic schema validation
    - Automatic error recovery via JSON Patch
    - Complex nested schema support
    
    Supports multiple providers:
    - OpenAI: gpt-4o-mini (default), gpt-4o, gpt-5-mini
    - Google: gemini-2.5-flash, gemini-3-flash
    - Anthropic: claude-3-5-haiku-latest
    
    Args:
        text: CV text content (e.g., from DOCX)
        model: LLM model to use (auto-detected if None)
        temperature: LLM temperature (0.0 for deterministic)
        
    Returns:
        dict with:
        - status: "success" or "error"
        - mac_json: MAC-formatted CV (if success)
        - extracted: Raw extracted data (if success)
        - model: Model used for extraction
        - message: Error message (if error)
    """
    if not TRUSTCALL_AVAILABLE:
        return {
            "status": "error",
            "message": "trustcall not installed. Run: pip install trustcall",
        }
    
    if not text or len(text.strip()) < 50:
        return {
            "status": "error",
            "message": "Text too short to extract CV data",
        }
    
    # Auto-detect model if not specified
    if model is None:
        model, provider = _get_default_model()
        logger.info(f"Auto-selected model: {model} ({provider})")
    else:
        provider = MODEL_PROVIDERS.get(model, "openai")
    
    try:
        # Create LLM
        llm = _create_llm(model, temperature)
        
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
                "model": model,
            }
        
        extracted_cv: ExtractedCV = result["responses"][0]
        
        # Convert to MAC JSON
        mac_json = extracted_cv_to_mac(extracted_cv)
        
        logger.info(f"Extracted CV: {extracted_cv.first_name} {extracted_cv.last_name}")
        logger.info(f"  Model: {model}")
        logger.info(f"  Jobs: {len(extracted_cv.jobs)}")
        logger.info(f"  Education: {len(extracted_cv.education)}")
        logger.info(f"  Skills: {len(extracted_cv.skills)}")
        
        return {
            "status": "success",
            "mac_json": mac_json,
            "extracted": extracted_cv.model_dump(),
            "model": model,
            "message": f"Extracted CV for {extracted_cv.first_name} {extracted_cv.last_name}",
        }
        
    except Exception as e:
        logger.error(f"CV extraction failed: {e}")
        return {
            "status": "error",
            "message": f"Extraction failed: {str(e)}",
            "model": model,
        }


def is_extraction_available() -> bool:
    """Check if LLM extraction is available."""
    return TRUSTCALL_AVAILABLE and (OPENAI_AVAILABLE or GOOGLE_AVAILABLE or ANTHROPIC_AVAILABLE)


def get_available_providers() -> list[str]:
    """Get list of available LLM providers."""
    providers = []
    if OPENAI_AVAILABLE:
        providers.append("openai")
    if GOOGLE_AVAILABLE:
        providers.append("google")
    if ANTHROPIC_AVAILABLE:
        providers.append("anthropic")
    return providers
