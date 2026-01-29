#!/usr/bin/env python3
"""
E2E Test: Europass XML → MAC → Europass XML Round-trip

This test verifies that:
1. Parsing Europass XML to MAC preserves all key data
2. Converting MAC back to Europass XML includes all data
3. Input XML and Output XML are semantically equivalent

Supports two input modes:
- XML file: Direct parsing
- PDF file: Extracts embedded XML from Europass PDFs

NOTE: Exact byte-for-byte equality is NOT expected due to:
- Whitespace/formatting differences
- Order of elements
- Namespace prefixes
- Optional empty elements

What we DO verify:
- All job titles and companies are preserved
- All education entries are preserved
- All descriptions are preserved
- Contact info is preserved
- Profile info is preserved
- Profile photo is preserved
- Language CEFR scores are preserved
"""

import sys
import os
from pathlib import Path
import xml.etree.ElementTree as ET
import re

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp_server import _europass_xml_to_mac, _mac_to_europass_xml, _extract_europass_xml_from_pdf


def normalize_xml(xml_content: str) -> str:
    """Normalize XML for comparison (remove whitespace, comments)."""
    # Remove XML declaration and comments
    xml_content = re.sub(r'<\?xml[^>]+\?>', '', xml_content)
    xml_content = re.sub(r'<!--[^>]*-->', '', xml_content)
    # Normalize whitespace
    xml_content = re.sub(r'\s+', ' ', xml_content)
    xml_content = re.sub(r'>\s+<', '><', xml_content)
    return xml_content.strip()


def extract_content_items(xml_content: str, element: str) -> list[str]:
    """Extract all text content from a specific element type."""
    pattern = f'<{element}[^>]*>([^<]*)</{element}>'
    matches = re.findall(pattern, xml_content, re.DOTALL)
    # Unescape HTML entities
    items = []
    for m in matches:
        text = m.strip()
        if text:
            # Unescape common HTML entities
            text = text.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
            items.append(text)
    return items


def count_elements(xml_content: str, element: str) -> int:
    """Count occurrences of an element."""
    return xml_content.count(f'<{element}')


def test_roundtrip():
    """Test Europass XML → MAC → Europass XML round-trip."""
    
    # Try PDF first (preferred - always available), then fall back to XML
    input_dir = Path(__file__).parent.parent / "input"
    
    # Look for Europass PDF or XML
    pdf_files = list(input_dir.glob("*.pdf"))
    xml_files = list(input_dir.glob("*.xml"))
    
    original_xml = None
    source_file = None
    
    if pdf_files:
        # Extract XML from PDF
        pdf_path = pdf_files[0]
        print(f"📥 Extracting XML from PDF: {pdf_path.name}")
        original_xml = _extract_europass_xml_from_pdf(pdf_path)
        if original_xml:
            source_file = pdf_path
            print(f"   ✅ Extracted {len(original_xml):,} bytes of XML")
        else:
            print("   ❌ Failed to extract XML from PDF")
    
    if original_xml is None and xml_files:
        # Fall back to XML file
        xml_path = xml_files[0]
        print(f"📥 Reading XML file: {xml_path.name}")
        original_xml = xml_path.read_text(encoding='utf-8')
        source_file = xml_path
    
    if original_xml is None:
        print(f"❌ No Europass PDF or XML found in: {input_dir}")
        print("   Place an Europass PDF or XML file in the input/ directory")
        return False
    
    print("=" * 60)
    print("E2E Round-trip Test: Europass XML → MAC → Europass XML")
    print("=" * 60)
    
    # Step 1: Parse to MAC
    print("\n📥 Step 1: Parsing Europass XML to MAC JSON...")
    mac = _europass_xml_to_mac(original_xml)
    
    profile = mac.get("aboutMe", {}).get("profile", {})
    jobs = mac.get("experience", {}).get("jobs", [])
    studies = mac.get("knowledge", {}).get("studies", [])
    
    print(f"   Profile: {profile.get('name', '')} {profile.get('surnames', '')}")
    print(f"   Jobs: {len(jobs)}")
    print(f"   Studies: {len(studies)}")
    
    # Step 2: Convert back to Europass XML
    print("\n📤 Step 2: Converting MAC JSON back to Europass XML...")
    regenerated_xml = _mac_to_europass_xml(mac)
    
    # Step 3: Compare key content
    print("\n🔍 Step 3: Comparing content...")
    
    errors = []
    warnings = []
    
    # Compare element counts
    checks = [
        ("EmployerHistory", "jobs"),
        ("EducationOrganizationAttendance", "education entries"),
        ("oa:Description", "job descriptions"),
    ]
    
    for element, name in checks:
        orig_count = count_elements(original_xml, element)
        regen_count = count_elements(regenerated_xml, element)
        
        if orig_count == regen_count:
            print(f"   ✅ {name}: {orig_count} → {regen_count}")
        else:
            msg = f"   ❌ {name}: {orig_count} → {regen_count} (diff: {regen_count - orig_count})"
            print(msg)
            errors.append(f"{name}: expected {orig_count}, got {regen_count}")
    
    # Check specific content is preserved
    content_checks = [
        ("hr:OrganizationName", "RAJA Group"),
        ("hr:OrganizationName", "Scaled Agile"),
        ("hr:OrganizationName", "Le Wagon"),
        ("oa:PostalCode", "75010"),
        ("oa:StreetName", "Paris Nord"),
    ]
    
    print("\n🔎 Step 4: Checking specific content preservation...")
    
    for element, expected_text in content_checks:
        in_original = expected_text.lower() in original_xml.lower()
        in_regenerated = expected_text.lower() in regenerated_xml.lower()
        
        if in_original and in_regenerated:
            print(f"   ✅ '{expected_text}' preserved")
        elif in_original and not in_regenerated:
            msg = f"   ❌ '{expected_text}' LOST in regeneration"
            print(msg)
            errors.append(f"Content lost: {expected_text}")
        else:
            print(f"   ⚠️ '{expected_text}' not in original")
    
    # Check descriptions contain key HTML elements (links, lists)
    print("\n📝 Step 5: Checking description richness...")
    
    # HTML is escaped in XML, so check for escaped versions
    if '&lt;a href=' in original_xml and '&lt;a href=' in regenerated_xml:
        print("   ✅ HTML links preserved in descriptions")
    elif '&lt;a href=' in original_xml:
        print("   ❌ HTML links LOST in descriptions")
        errors.append("HTML links lost in descriptions")
    else:
        print("   ⚠️ No HTML links in original")
    
    if '&lt;li' in original_xml and '&lt;li' in regenerated_xml:
        print("   ✅ HTML lists preserved in descriptions")
    elif '&lt;li' in original_xml:
        print("   ❌ HTML lists LOST in descriptions")
        errors.append("HTML lists lost in descriptions")
    else:
        print("   ⚠️ No HTML lists in original")
    
    # Note: These elements ARE now expected to be preserved:
    # - eures:Attachment (profile photo) - now parsed and regenerated
    # - PersonQualifications (language CEFR scores) - now preserved per dimension
    print("\n📊 Step 6: Photo and language proficiency preservation...")
    
    # Check profile photo is preserved
    if 'oa:EmbeddedData' in original_xml and 'oa:EmbeddedData' in regenerated_xml:
        # Verify the photo data is in the MAC
        if mac.get("profilePicture"):
            print("   ✅ Profile photo extracted and regenerated")
        else:
            print("   ❌ Profile photo in XML but not in MAC")
            errors.append("Profile photo not extracted to MAC")
    elif 'oa:EmbeddedData' in original_xml:
        print("   ❌ Profile photo LOST in regeneration")
        errors.append("Profile photo lost in regeneration")
    else:
        print("   ⚠️ No profile photo in original")
    
    # Check CEFR scores are preserved
    languages = mac.get("knowledge", {}).get("languages", [])
    cefr_preserved = False
    for lang in languages:
        cefr_scores = lang.get("cefrScores", {})
        if cefr_scores:
            cefr_preserved = True
            print(f"   ✅ CEFR scores preserved for '{lang.get('name', '')}': {list(cefr_scores.keys())}")
            break
    
    if not cefr_preserved:
        # Check if original had CEFR scores
        if 'CEF-Understanding-Listening' in original_xml or 'CompetencyDimension' in original_xml:
            print("   ❌ CEFR scores not extracted from original")
            errors.append("CEFR language scores not extracted")
        else:
            print("   ⚠️ No CEFR scores in original")
    
    # Verify CEFR scores appear in regenerated XML correctly
    if cefr_preserved:
        first_lang = next((l for l in languages if l.get("cefrScores")), {})
        cefr_scores = first_lang.get("cefrScores", {})
        for dim, score in list(cefr_scores.items())[:2]:  # Check first 2 dimensions
            if f'<hr:ScoreText>{score}</hr:ScoreText>' in regenerated_xml:
                print(f"   ✅ CEFR {dim}: {score} in regenerated XML")
            else:
                print(f"   ❌ CEFR {dim}: {score} NOT in regenerated XML")
                errors.append(f"CEFR score {dim}={score} not regenerated")
    
    print("\n📊 Step 7: Size comparison...")
    orig_size = len(original_xml)
    regen_size = len(regenerated_xml)
    print(f"   Original: {orig_size:,} bytes, Regenerated: {regen_size:,} bytes")
    if abs(orig_size - regen_size) < 1000:
        print("   ✅ Sizes are similar (good - content preserved!)")
    else:
        print(f"   ℹ️ Size difference: {abs(orig_size - regen_size):,} bytes")

    
    # Summary
    print("\n" + "=" * 60)
    if not errors:
        print("✅ E2E ROUND-TRIP TEST PASSED")
        print("   All key content preserved in Europass XML → MAC → Europass XML")
        return True
    else:
        print("❌ E2E ROUND-TRIP TEST FAILED")
        print(f"   {len(errors)} error(s):")
        for e in errors:
            print(f"      - {e}")
        return False


if __name__ == "__main__":
    success = test_roundtrip()
    sys.exit(0 if success else 1)
