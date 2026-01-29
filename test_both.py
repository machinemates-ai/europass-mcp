#!/usr/bin/env python3
"""Test CV import and PDF generation from both PDF and DOCX."""

import asyncio
from pathlib import Path
import sys

# Add parent directory to path so 'src' is treated as a package
sys.path.insert(0, str(Path(__file__).parent))

from src.mcp_server import import_cv, generate_pdf


async def test_pdf_workflow():
    """Test PDF (Europass) -> PDF Generation."""
    print("=" * 60)
    print("TEST 1: PDF (Europass) -> PDF Generation")
    print("=" * 60)
    
    result = import_cv("input/CV-Europass-20250917-Fortaine-FR.pdf", parse_to_mac=True)
    print(f"Status: {result.get('status')}")
    print(f"Format: {result.get('format')}")
    print(f"Mode: {result.get('mode')}")
    
    if result.get("summary"):
        s = result["summary"]
        print(f"Summary: {s['name']} - {s['jobs_count']} jobs, {s['education_count']} education")
    
    if result.get("resume_id"):
        resume_id = result["resume_id"]
        print(f"\nGenerating PDF from resume {resume_id}...")
        pdf_result = await generate_pdf("output/from_pdf.pdf", resume_id=resume_id)
        print(f"PDF Status: {pdf_result.get('status')}")
        print(f"PDF Path: {pdf_result.get('pdf_path')}")
        print(f"PDF Size: {pdf_result.get('file_size_bytes', 0):,} bytes")
        return pdf_result.get("status") == "success"
    return False


async def test_docx_workflow():
    """Test DOCX -> PDF Generation."""
    print("\n" + "=" * 60)
    print("TEST 2: DOCX -> PDF Generation")
    print("=" * 60)
    
    result = import_cv("input/CV-Europass-20250917-Fortaine-FR.docx", parse_to_mac=True)
    print(f"Status: {result.get('status')}")
    print(f"Format: {result.get('format')}")
    print(f"Mode: {result.get('mode')}")
    
    if result.get("summary"):
        s = result["summary"]
        print(f"Summary: {s['name']} - {s['jobs_count']} jobs, {s['education_count']} education")
    
    if result.get("resume_id"):
        resume_id = result["resume_id"]
        print(f"\nGenerating PDF from resume {resume_id}...")
        pdf_result = await generate_pdf("output/from_docx.pdf", resume_id=resume_id)
        print(f"PDF Status: {pdf_result.get('status')}")
        print(f"PDF Path: {pdf_result.get('pdf_path')}")
        print(f"PDF Size: {pdf_result.get('file_size_bytes', 0):,} bytes")
        return pdf_result.get("status") == "success"
    elif result.get("text_content"):
        # LLM extraction not available, show text preview
        print(f"\nNote: LLM extraction not available")
        print(f"Text preview (first 500 chars):\n{result['text_content'][:500]}...")
        return False
    return False


async def main():
    """Run all tests."""
    print("\n🚀 Starting CV Import & Generation Tests\n")
    
    pdf_ok = await test_pdf_workflow()
    docx_ok = await test_docx_workflow()
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"PDF workflow:  {'✅ PASSED' if pdf_ok else '❌ FAILED'}")
    print(f"DOCX workflow: {'✅ PASSED' if docx_ok else '⚠️ PARTIAL (no LLM)'}")
    
    # List output files
    print("\nOutput files:")
    output_dir = Path("output")
    for f in sorted(output_dir.glob("*.pdf")):
        print(f"  - {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    asyncio.run(main())
