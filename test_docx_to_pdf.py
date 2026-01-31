#!/usr/bin/env python3
"""Test script to generate PDF from DOCX using the new html_transform module."""

import asyncio
from pathlib import Path

# Import from src
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from mcp_server import import_cv, generate_pdf

def main():
    # Step 1: Import the DOCX file
    docx_path = Path(__file__).parent / "input/CV-Europass-20250917-Fortaine-FR.docx"
    print(f"Importing: {docx_path}")

    result = import_cv(str(docx_path))
    print(f"Import status: {result.get('status')}")

    if result.get("status") == "success":
        resume_id = result["resume_id"]
        print(f"Resume ID: {resume_id}")
        
        # Show summary
        summary = result.get("summary", {})
        print(f"Name: {summary.get('name', 'N/A')}")
        print(f"Jobs: {summary.get('job_count', 0)}")
        print(f"Skills: {summary.get('skill_count', 0)}")
        
        # Step 2: Generate PDF
        output_path = Path(__file__).parent / "output/CV-Europass-test-new-html-transform.pdf"
        print(f"\nGenerating PDF: {output_path}")
        
        pdf_result = asyncio.run(generate_pdf(
            output_path=str(output_path),
            resume_id=resume_id,
            template="cv-elegant",
            headless=True
        ))
        
        print(f"PDF status: {pdf_result.get('status')}")
        if pdf_result.get("status") == "success":
            print(f"PDF generated: {pdf_result.get('pdf_path')}")
            print(f"File size: {pdf_result.get('file_size_kb', 0):.1f} KB")
        else:
            print(f"Error: {pdf_result.get('message')}")
    else:
        print(f"Import error: {result.get('message')}")

if __name__ == "__main__":
    main()
