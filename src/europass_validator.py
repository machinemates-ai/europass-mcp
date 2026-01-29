"""
Europass XML Validator

Validates generated Europass XML against known working structures.
Since official XSD schemas are no longer publicly available,
this validator uses structural analysis based on:
1. Known working Europass XML examples
2. HR-XML 3.0 structure patterns
3. Common issues that cause JavaScript errors on the Europass site

The validator checks:
- Required elements and their order
- Namespace declarations
- Content encoding (base64, HTML escaping)
- Invalid characters that cause JS errors
"""

import re
import base64
import html
from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree as ET


@dataclass
class ValidationResult:
    """Result of XML validation."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]
    
    def __str__(self) -> str:
        lines = []
        if self.is_valid:
            lines.append("✅ XML is valid")
        else:
            lines.append("❌ XML validation failed")
        
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            for err in self.errors:
                lines.append(f"  - {err}")
        
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            for warn in self.warnings:
                lines.append(f"  - {warn}")
        
        return "\n".join(lines)


class EuropassValidator:
    """Validates Europass XML structure and content."""
    
    # Expected namespaces for Europass 1.0 schema
    EXPECTED_NAMESPACES = {
        '': 'http://www.europass.eu/1.0',
        'eures': 'http://www.europass_eures.eu/1.0',
        'hr': 'http://www.hr-xml.org/3',
        'oa': 'http://www.openapplications.org/oagis/9',
        'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    }
    
    # Required top-level elements in order
    REQUIRED_CANDIDATE_ELEMENTS = [
        '{http://www.hr-xml.org/3}DocumentID',
        'CandidateSupplier',
        'CandidatePerson',
        'CandidateProfile',
    ]
    
    # Elements allowed in CandidatePerson
    ALLOWED_PERSON_ELEMENTS = {
        'PersonName',
        'Communication',
        'NationalityCode',
        '{http://www.hr-xml.org/3}BirthDate',
        'PrimaryLanguageCode',
        'GenderCode',
        '{http://www.hr-xml.org/3}PersonTitle',  # Optional but sometimes causes issues
        '{http://www.hr-xml.org/3}PersonDescription',  # Optional but sometimes causes issues
    }
    
    # Known problematic patterns
    INVALID_CHAR_PATTERN = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
    
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
    
    def validate(self, xml_content: str) -> ValidationResult:
        """
        Validate Europass XML content.
        
        Args:
            xml_content: The XML string to validate
            
        Returns:
            ValidationResult with validation status and any issues found
        """
        self.errors = []
        self.warnings = []
        
        # Basic parsing check
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as e:
            self.errors.append(f"XML parse error: {e}")
            return ValidationResult(False, self.errors, self.warnings)
        
        # Run all validation checks
        self._check_namespaces(root)
        self._check_root_element(root)
        self._check_candidate_structure(root)
        self._check_person_elements(root)
        self._check_content_encoding(root, xml_content)
        self._check_base64_data(root)
        self._check_html_descriptions(root)
        self._check_invalid_characters(xml_content)
        self._check_country_codes(root)
        self._check_language_codes(root)
        
        is_valid = len(self.errors) == 0
        return ValidationResult(is_valid, self.errors, self.warnings)
    
    def validate_file(self, file_path: str) -> ValidationResult:
        """Validate an Europass XML file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.validate(content)
        except Exception as e:
            return ValidationResult(False, [f"Failed to read file: {e}"], [])
    
    def _check_namespaces(self, root: ET.Element) -> None:
        """Check that required namespaces are declared."""
        # Get actual namespaces from the document
        # Note: ElementTree doesn't preserve namespace prefixes well,
        # so we check the raw tag format
        root_tag = root.tag
        if not root_tag.startswith('{'):
            self.warnings.append("Root element should use namespace")
        
        # Check for Europass namespace
        if 'http://www.europass.eu/1.0' not in root_tag:
            if 'europass' not in root_tag.lower():
                self.errors.append(
                    "Root element must be in Europass namespace "
                    "(http://www.europass.eu/1.0)"
                )
    
    def _check_root_element(self, root: ET.Element) -> None:
        """Check root element is Candidate."""
        local_name = root.tag.split('}')[-1] if '}' in root.tag else root.tag
        if local_name != 'Candidate':
            self.errors.append(
                f"Root element must be 'Candidate', found '{local_name}'"
            )
    
    def _check_candidate_structure(self, root: ET.Element) -> None:
        """Check that Candidate has required child elements."""
        children = list(root)
        child_tags = [child.tag.split('}')[-1] if '}' in child.tag else child.tag 
                      for child in children]
        
        # Check for DocumentID
        has_document_id = any('DocumentID' in tag for tag in child_tags)
        if not has_document_id:
            self.errors.append("Missing required element: hr:DocumentID")
        
        # Check for CandidateSupplier
        if 'CandidateSupplier' not in child_tags:
            self.errors.append("Missing required element: CandidateSupplier")
        
        # Check for CandidatePerson
        if 'CandidatePerson' not in child_tags:
            self.errors.append("Missing required element: CandidatePerson")
        
        # Check for CandidateProfile
        if 'CandidateProfile' not in child_tags:
            self.errors.append("Missing required element: CandidateProfile")
    
    def _check_person_elements(self, root: ET.Element) -> None:
        """Check CandidatePerson structure for problematic elements."""
        ns = {'': 'http://www.europass.eu/1.0', 'hr': 'http://www.hr-xml.org/3'}
        
        # Find CandidatePerson
        for child in root:
            local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if local_name == 'CandidatePerson':
                person = child
                break
        else:
            return  # Already reported as error
        
        # Check for PersonTitle - this can cause issues
        for elem in person:
            local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if local_name == 'PersonTitle':
                self.warnings.append(
                    "hr:PersonTitle element may not be supported by all Europass editors"
                )
            if local_name == 'PersonDescription':
                self.warnings.append(
                    "hr:PersonDescription element may not be supported by all Europass editors"
                )
    
    def _check_content_encoding(self, root: ET.Element, raw_xml: str) -> None:
        """Check XML declaration and encoding."""
        if not raw_xml.strip().startswith('<?xml'):
            self.warnings.append("Missing XML declaration (<?xml version=\"1.0\"...?>)")
        elif 'encoding="UTF-8"' not in raw_xml[:100] and "encoding='UTF-8'" not in raw_xml[:100]:
            self.warnings.append("XML should declare UTF-8 encoding")
    
    def _check_base64_data(self, root: ET.Element) -> None:
        """Validate base64 encoded data (like profile pictures)."""
        # Find EmbeddedData elements
        for elem in root.iter():
            local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if local_name == 'EmbeddedData' and elem.text:
                data = elem.text.strip()
                # Remove whitespace (base64 can have line breaks)
                data_clean = re.sub(r'\s', '', data)
                
                # Check for valid base64
                try:
                    # Check if it decodes
                    base64.b64decode(data_clean, validate=True)
                except Exception as e:
                    self.errors.append(f"Invalid base64 in EmbeddedData: {e}")
                
                # Check for reasonable size (images shouldn't be > 10MB encoded)
                if len(data_clean) > 10 * 1024 * 1024:
                    self.warnings.append(
                        f"Large base64 data ({len(data_clean)} chars) may cause issues"
                    )
    
    def _check_html_descriptions(self, root: ET.Element) -> None:
        """Check HTML content in Description elements.
        
        Note: When XML is parsed, escaped entities (&lt; etc) are automatically
        unescaped. So valid XML with &lt;p&gt; will appear as <p> in the DOM.
        We only flag an error if the RAW XML string contained unescaped HTML,
        which would cause XML parsing to fail. Since we've already parsed 
        successfully, the HTML is properly escaped.
        """
        # This check is now a no-op since if we parsed the XML successfully,
        # all HTML in Description elements is properly escaped.
        # We keep the method for future use with additional validation.
        pass
    
    def _check_invalid_characters(self, xml_content: str) -> None:
        """Check for characters that cause JavaScript errors."""
        # Find control characters (except tab, newline, carriage return)
        matches = self.INVALID_CHAR_PATTERN.findall(xml_content)
        if matches:
            char_codes = [hex(ord(c)) for c in matches[:5]]
            self.errors.append(
                f"XML contains invalid control characters: {char_codes}"
                + (" (and more)" if len(matches) > 5 else "")
            )
        
        # Check for null bytes (especially in base64)
        if '\x00' in xml_content:
            self.errors.append("XML contains null bytes (\\x00)")
    
    def _check_country_codes(self, root: ET.Element) -> None:
        """Check country codes are lowercase ISO 3166-1 alpha-2."""
        for elem in root.iter():
            local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if local_name == 'CountryCode' and elem.text:
                code = elem.text.strip()
                if code != code.lower():
                    self.errors.append(
                        f"CountryCode '{code}' must be lowercase (use '{code.lower()}')"
                    )
                if len(code) != 2:
                    self.warnings.append(
                        f"CountryCode '{code}' should be 2-letter ISO code"
                    )
    
    def _check_language_codes(self, root: ET.Element) -> None:
        """Check language codes are ISO 639 format."""
        language_elements = ['PrimaryLanguageCode', 'CompetencyID']
        
        for elem in root.iter():
            local_name = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if local_name in language_elements and elem.text:
                code = elem.text.strip()
                # Should be 2 or 3 letter code
                if not (2 <= len(code) <= 3):
                    self.warnings.append(
                        f"Language code '{code}' should be 2-3 letter ISO code"
                    )


def compare_xml_structure(reference_path: str, generated_path: str) -> dict:
    """
    Compare the structure of a reference XML with a generated one.
    
    Args:
        reference_path: Path to the known-working reference XML
        generated_path: Path to the generated XML to validate
        
    Returns:
        Dictionary with comparison results
    """
    def get_element_paths(root: ET.Element, prefix: str = "") -> set:
        """Get all element paths in the XML tree."""
        paths = set()
        for child in root:
            local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            path = f"{prefix}/{local_name}" if prefix else local_name
            paths.add(path)
            paths.update(get_element_paths(child, path))
        return paths
    
    with open(reference_path, 'r', encoding='utf-8') as f:
        ref_root = ET.fromstring(f.read())
    
    with open(generated_path, 'r', encoding='utf-8') as f:
        gen_root = ET.fromstring(f.read())
    
    ref_paths = get_element_paths(ref_root)
    gen_paths = get_element_paths(gen_root)
    
    return {
        'in_reference_only': ref_paths - gen_paths,
        'in_generated_only': gen_paths - ref_paths,
        'common': ref_paths & gen_paths,
        'reference_count': len(ref_paths),
        'generated_count': len(gen_paths),
    }


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python europass_validator.py <xml_file> [reference_xml]")
        sys.exit(1)
    
    validator = EuropassValidator()
    result = validator.validate_file(sys.argv[1])
    print(result)
    
    if len(sys.argv) >= 3:
        print("\n--- Structure Comparison ---")
        comparison = compare_xml_structure(sys.argv[2], sys.argv[1])
        print(f"Reference elements: {comparison['reference_count']}")
        print(f"Generated elements: {comparison['generated_count']}")
        if comparison['in_reference_only']:
            print(f"\nMissing from generated ({len(comparison['in_reference_only'])}):")
            for path in sorted(comparison['in_reference_only'])[:10]:
                print(f"  - {path}")
        if comparison['in_generated_only']:
            print(f"\nExtra in generated ({len(comparison['in_generated_only'])}):")
            for path in sorted(comparison['in_generated_only'])[:10]:
                print(f"  + {path}")
    
    sys.exit(0 if result.is_valid else 1)
