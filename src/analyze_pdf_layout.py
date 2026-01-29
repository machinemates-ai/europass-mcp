#!/usr/bin/env python3
"""
PDF Layout Analyzer for Europass CVs

Analyzes page breaks, text distribution, and identifies potential
layout issues like orphaned headers or awkward splits.

Usage:
    uv run --extra enrich python src/analyze_pdf_layout.py
"""

from pathlib import Path
from pypdf import PdfReader


def analyze_pdf(pdf_path: Path) -> dict:
    """Analyze PDF structure and content distribution."""
    reader = PdfReader(pdf_path)
    
    analysis = {
        "file": pdf_path.name,
        "pages": len(reader.pages),
        "page_details": [],
        "issues": [],
    }
    
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        # Detect section headers (typically short, capitalized lines)
        headers = [l for l in lines if len(l) < 50 and l.isupper()]
        
        page_info = {
            "page": i,
            "char_count": len(text),
            "line_count": len(lines),
            "headers_found": headers,
            "first_line": lines[0][:60] if lines else "",
            "last_line": lines[-1][:60] if lines else "",
        }
        analysis["page_details"].append(page_info)
        
        # Check for orphaned headers at page bottom
        if lines and len(lines[-1]) < 40:
            last_words = lines[-1].lower()
            if any(kw in last_words for kw in ['expérience', 'formation', 'compétences', 'langues']):
                analysis["issues"].append({
                    "type": "orphan_header",
                    "page": i,
                    "text": lines[-1],
                    "suggestion": "Header at page bottom - content will be on next page"
                })
        
        # Check for very short last page
        if i == len(reader.pages) and len(text) < 200:
            analysis["issues"].append({
                "type": "short_last_page",
                "page": i,
                "char_count": len(text),
                "suggestion": "Consider condensing content to eliminate nearly-empty last page"
            })
    
    return analysis


def print_analysis(analysis: dict) -> None:
    """Pretty print the analysis results."""
    print(f"\n{'='*60}")
    print(f"📄 PDF Analysis: {analysis['file']}")
    print(f"{'='*60}")
    print(f"Total pages: {analysis['pages']}")
    
    print(f"\n📊 Page Distribution:")
    for page in analysis["page_details"]:
        fill = "█" * (page["char_count"] // 200)
        print(f"  Page {page['page']}: {page['char_count']:,} chars, {page['line_count']} lines {fill}")
        print(f"         First: {page['first_line']}")
        print(f"         Last:  {page['last_line']}")
        if page["headers_found"]:
            print(f"         Headers: {page['headers_found']}")
    
    if analysis["issues"]:
        print(f"\n⚠️  Potential Issues:")
        for issue in analysis["issues"]:
            print(f"  • Page {issue['page']}: {issue['type']}")
            print(f"    {issue['suggestion']}")
    else:
        print(f"\n✅ No layout issues detected")
    
    print(f"{'='*60}\n")


def main():
    project_root = Path(__file__).parent.parent
    pdf_path = project_root / "output" / "CV-Europass.pdf"
    
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        print("   Run: uv run python src/europass_playwright.py")
        return
    
    analysis = analyze_pdf(pdf_path)
    print_analysis(analysis)
    
    # Return analysis for programmatic use
    return analysis


if __name__ == "__main__":
    main()
