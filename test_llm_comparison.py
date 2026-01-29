#!/usr/bin/env python3
"""Compare LLM extraction quality between OpenAI and Gemini."""

import asyncio
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.mcp_server import import_cv


def compare_extraction(pdf_mac: dict, extracted_mac: dict, model: str) -> dict:
    """Compare extracted MAC against reference PDF MAC."""
    
    # Get reference data from PDF (embedded XML)
    ref_profile = pdf_mac.get("aboutMe", {}).get("profile", {})
    ref_jobs = pdf_mac.get("experience", {}).get("jobs", [])
    ref_studies = pdf_mac.get("knowledge", {}).get("studies", [])
    
    # Languages can be a list or dict with motherTongue/other
    ref_langs = pdf_mac.get("knowledge", {}).get("languages", {})
    if isinstance(ref_langs, dict):
        ref_languages = ref_langs.get("motherTongue", []) + ref_langs.get("other", [])
    else:
        ref_languages = ref_langs if isinstance(ref_langs, list) else []
    
    # Get extracted data
    ext_profile = extracted_mac.get("aboutMe", {}).get("profile", {})
    ext_jobs = extracted_mac.get("experience", {}).get("jobs", [])
    ext_studies = extracted_mac.get("knowledge", {}).get("studies", [])
    
    ext_langs = extracted_mac.get("knowledge", {}).get("languages", {})
    if isinstance(ext_langs, dict):
        ext_languages = ext_langs.get("motherTongue", []) + ext_langs.get("other", [])
    else:
        ext_languages = ext_langs if isinstance(ext_langs, list) else []
    
    # Compare
    ref_name = f"{ref_profile.get('name', '')} {ref_profile.get('surnames', '')}".strip()
    ext_name = f"{ext_profile.get('name', '')} {ext_profile.get('surnames', '')}".strip()
    
    return {
        "model": model,
        "name_match": ref_name.lower() == ext_name.lower(),
        "ref_name": ref_name,
        "ext_name": ext_name,
        "jobs_ref": len(ref_jobs),
        "jobs_ext": len(ext_jobs),
        "jobs_match": len(ref_jobs) == len(ext_jobs),
        "education_ref": len(ref_studies),
        "education_ext": len(ext_studies),
        "education_match": len(ref_studies) == len(ext_studies),
        "languages_ref": len(ref_languages),
        "languages_ext": len(ext_languages),
    }


def test_model(docx_path: str, model: str, ref_mac: dict) -> dict:
    """Test extraction with a specific model."""
    print(f"\n--- Testing {model} ---")
    start = time.time()
    
    # Import DOCX with specific model
    # We need to call extract directly to specify model
    from markitdown import MarkItDown
    from src.cv_extractor import extract_cv_from_text
    
    md = MarkItDown()
    result = md.convert(docx_path)
    text_content = result.text_content
    
    extraction_result = extract_cv_from_text(text_content, model=model)
    duration = time.time() - start
    
    if extraction_result.get("status") != "success":
        return {
            "model": model,
            "status": "error",
            "message": extraction_result.get("message"),
            "duration": duration,
        }
    
    mac = extraction_result["mac_json"]
    comparison = compare_extraction(ref_mac, mac, model)
    comparison["status"] = "success"
    comparison["duration"] = duration
    
    return comparison


def main():
    print("🔬 LLM Extraction Comparison Test")
    print("=" * 60)
    
    # First, get reference MAC from PDF (embedded XML)
    print("\n1. Loading reference from PDF (embedded XML)...")
    pdf_result = import_cv("input/CV-Europass-20250917-Fortaine-FR.pdf", parse_to_mac=True)
    
    if pdf_result.get("status") != "success":
        print(f"❌ Failed to load PDF: {pdf_result.get('message')}")
        return
    
    ref_mac = pdf_result["mac_json"]
    ref_profile = ref_mac.get("aboutMe", {}).get("profile", {})
    ref_name = f"{ref_profile.get('name', '')} {ref_profile.get('surnames', '')}".strip()
    ref_jobs = len(ref_mac.get("experience", {}).get("jobs", []))
    ref_edu = len(ref_mac.get("knowledge", {}).get("studies", []))
    
    print(f"   Reference: {ref_name}")
    print(f"   Jobs: {ref_jobs}, Education: {ref_edu}")
    
    # Test models
    models = [
        "gpt-4o-mini",
        "gemini-2.5-flash",
    ]
    
    results = []
    for model in models:
        try:
            result = test_model(
                "input/CV-Europass-20250917-Fortaine-FR.docx",
                model,
                ref_mac
            )
            results.append(result)
            
            if result.get("status") == "success":
                print(f"   ✓ Name: {result['ext_name']} {'✓' if result['name_match'] else '✗'}")
                print(f"   ✓ Jobs: {result['jobs_ext']}/{result['jobs_ref']} {'✓' if result['jobs_match'] else '✗'}")
                print(f"   ✓ Education: {result['education_ext']}/{result['education_ref']} {'✓' if result['education_match'] else '✗'}")
                print(f"   ✓ Languages: {result['languages_ext']}/{result['languages_ref']}")
                print(f"   ⏱ Duration: {result['duration']:.1f}s")
            else:
                print(f"   ✗ Error: {result.get('message')}")
                
        except Exception as e:
            print(f"   ✗ Exception: {e}")
            results.append({"model": model, "status": "error", "message": str(e)})
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"{'Model':<20} {'Name':<6} {'Jobs':<8} {'Edu':<8} {'Time':<8}")
    print("-" * 60)
    for r in results:
        if r.get("status") == "success":
            name = "✓" if r["name_match"] else "✗"
            jobs = f"{r['jobs_ext']}/{r['jobs_ref']}"
            edu = f"{r['education_ext']}/{r['education_ref']}"
            time_s = f"{r['duration']:.1f}s"
            print(f"{r['model']:<20} {name:<6} {jobs:<8} {edu:<8} {time_s:<8}")
        else:
            print(f"{r['model']:<20} ERROR: {r.get('message', 'Unknown')[:30]}")


if __name__ == "__main__":
    main()
