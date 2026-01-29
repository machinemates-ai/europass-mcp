#!/usr/bin/env python3
"""Benchmark gpt-5-mini vs gemini-3-flash for CV extraction."""

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from markitdown import MarkItDown
from src.cv_extractor import extract_cv_from_text
from src.mcp_server import import_cv


def main():
    print("=" * 60)
    print("LLM BENCHMARK: gpt-5-mini vs gemini-3-flash-preview")
    print("=" * 60)
    
    # Get reference from PDF
    print("\n1. Loading reference from PDF (embedded XML)...")
    pdf_result = import_cv("input/CV-Europass-20250917-Fortaine-FR.pdf", parse_to_mac=True)
    ref_mac = pdf_result["mac_json"]
    ref_jobs = len(ref_mac.get("experience", {}).get("jobs", []))
    ref_edu = len(ref_mac.get("knowledge", {}).get("studies", []))
    print(f"   Reference: {ref_jobs} jobs, {ref_edu} education")
    
    # Extract text from DOCX
    print("\n2. Extracting text from DOCX...")
    md = MarkItDown()
    result = md.convert("input/CV-Europass-20250917-Fortaine-FR.docx")
    text = result.text_content
    print(f"   Text length: {len(text)} chars")
    
    results = {}
    
    # Test gpt-5-mini
    print("\n" + "=" * 60)
    print("3. Testing gpt-5-mini...")
    print("=" * 60)
    start = time.time()
    r1 = extract_cv_from_text(text, model="gpt-5-mini")
    t1 = time.time() - start
    
    if r1["status"] == "success":
        jobs1 = len(r1["mac_json"].get("experience", {}).get("jobs", []))
        edu1 = len(r1["mac_json"].get("knowledge", {}).get("studies", []))
        skills1 = len(r1["extracted"].get("skills", []))
        langs1 = len(r1["extracted"].get("languages", []))
        print(f"   ✓ Jobs: {jobs1}/{ref_jobs}")
        print(f"   ✓ Education: {edu1}/{ref_edu}")
        print(f"   ✓ Skills: {skills1}")
        print(f"   ✓ Languages: {langs1}")
        print(f"   ⏱ Time: {t1:.1f}s")
        results["gpt-5-mini"] = {
            "jobs": jobs1, "edu": edu1, "skills": skills1, 
            "langs": langs1, "time": t1, "status": "success"
        }
    else:
        print(f"   ✗ Error: {r1['message']}")
        results["gpt-5-mini"] = {"status": "error", "message": r1["message"]}
    
    # Test gemini-3-flash-preview
    print("\n" + "=" * 60)
    print("4. Testing gemini-3-flash-preview...")
    print("=" * 60)
    start = time.time()
    r2 = extract_cv_from_text(text, model="gemini-3-flash-preview")
    t2 = time.time() - start
    
    if r2["status"] == "success":
        jobs2 = len(r2["mac_json"].get("experience", {}).get("jobs", []))
        edu2 = len(r2["mac_json"].get("knowledge", {}).get("studies", []))
        skills2 = len(r2["extracted"].get("skills", []))
        langs2 = len(r2["extracted"].get("languages", []))
        print(f"   ✓ Jobs: {jobs2}/{ref_jobs}")
        print(f"   ✓ Education: {edu2}/{ref_edu}")
        print(f"   ✓ Skills: {skills2}")
        print(f"   ✓ Languages: {langs2}")
        print(f"   ⏱ Time: {t2:.1f}s")
        results["gemini-3-flash-preview"] = {
            "jobs": jobs2, "edu": edu2, "skills": skills2,
            "langs": langs2, "time": t2, "status": "success"
        }
    else:
        print(f"   ✗ Error: {r2['message']}")
        results["gemini-3-flash-preview"] = {"status": "error", "message": r2["message"]}
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Reference: {ref_jobs} jobs, {ref_edu} education\n")
    print(f"{'Model':<18} {'Jobs':<8} {'Edu':<8} {'Skills':<8} {'Langs':<8} {'Time':<8}")
    print("-" * 60)
    
    for model, data in results.items():
        if data["status"] == "success":
            jobs_ok = "✓" if data["jobs"] == ref_jobs else "✗"
            edu_ok = "✓" if data["edu"] == ref_edu else "✗"
            print(f"{model:<18} {data['jobs']}/{ref_jobs} {jobs_ok:<3} {data['edu']}/{ref_edu} {edu_ok:<3} {data['skills']:<8} {data['langs']:<8} {data['time']:.1f}s")
        else:
            print(f"{model:<18} ERROR: {data.get('message', 'Unknown')[:35]}")
    
    # Recommendation
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    
    if all(r.get("status") == "success" for r in results.values()):
        # Compare accuracy first, then speed
        gpt = results["gpt-5-mini"]
        gem = results["gemini-3-flash-preview"]
        
        gpt_accuracy = (gpt["jobs"] == ref_jobs) + (gpt["edu"] == ref_edu)
        gem_accuracy = (gem["jobs"] == ref_jobs) + (gem["edu"] == ref_edu)
        
        if gpt_accuracy > gem_accuracy:
            winner = "gpt-5-mini"
            reason = "better accuracy"
        elif gem_accuracy > gpt_accuracy:
            winner = "gemini-3-flash-preview"
            reason = "better accuracy"
        elif gpt["time"] < gem["time"]:
            winner = "gpt-5-mini"
            reason = f"faster ({gpt['time']:.1f}s vs {gem['time']:.1f}s)"
        else:
            winner = "gemini-3-flash-preview"
            reason = f"faster ({gem['time']:.1f}s vs {gpt['time']:.1f}s)"
        
        print(f"Winner: {winner} ({reason})")
    else:
        # One failed, pick the working one
        for model, data in results.items():
            if data["status"] == "success":
                print(f"Winner: {model} (other model failed)")
                break


if __name__ == "__main__":
    main()
