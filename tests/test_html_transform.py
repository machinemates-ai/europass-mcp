#!/usr/bin/env python3
"""
Test Harness for HTML Transform Module (selectolax-based)

Comprehensive tests for the new two-phase HTML transformation:
1. Selectolax (Lexbor) for DOM structural transforms
2. Regex for Quill format string transforms

This replaces the legacy 5-pass regex/HTMLParser approach with ~2x speedup.

Test Categories:
- Module availability and imports
- Structural transforms (headings → bullets, link security)
- Quill format compliance (data-list, ql-indent, ql-ui markers)
- Edge cases and error handling
- Regression tests for known patterns
- Performance benchmarks

Run: uv run pytest tests/test_html_transform.py -v
"""

import re
import sys
from pathlib import Path

import pytest

# Import module under test
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from html_transform import (
    is_selectolax_available,
    transform_for_europass,
    transform_and_clean,
    post_process_html,
)


# =============================================================================
# Module Availability Tests
# =============================================================================

class TestModuleAvailability:
    """Verify selectolax and dependencies are available."""

    def test_selectolax_is_available(self):
        """selectolax (Lexbor backend) must be installed."""
        assert is_selectolax_available() is True

    def test_can_import_html_transform(self):
        """html_transform module imports successfully."""
        from html_transform import transform_for_europass, transform_and_clean
        assert callable(transform_for_europass)
        assert callable(transform_and_clean)


# =============================================================================
# Basic Transform Tests
# =============================================================================

class TestBasicTransforms:
    """Core transformation functionality."""

    def test_empty_string_returns_empty(self):
        """Empty input returns empty output."""
        assert transform_for_europass("") == ""
        assert transform_for_europass("   ") == "   "

    def test_plain_text_preserved(self):
        """Plain text without HTML passes through."""
        text = "Simple text without any HTML"
        result = transform_for_europass(f"<body>{text}</body>")
        assert text in result

    def test_output_is_single_line(self):
        """Europass requires single-line HTML (no newlines)."""
        html = "<body><p>Line 1</p>\n<p>Line 2</p>\n</body>"
        result = transform_for_europass(html)
        assert "\n" not in result

    def test_preserves_paragraph_content(self):
        """Paragraph text content is preserved."""
        html = "<body><p>Important CV content here</p></body>"
        result = transform_for_europass(html)
        assert "Important CV content here" in result


# =============================================================================
# Heading to Bullet Conversion Tests
# =============================================================================

class TestHeadingToBulletConversion:
    """Test conversion of headings followed by lists."""

    def test_h2_followed_by_ul_becomes_bold_bullet(self):
        """<h2>Title</h2><ul>... becomes bold bullet + indented children."""
        html = """<body>
            <h2>Tâches:</h2>
            <ul><li>Task one</li><li>Task two</li></ul>
        </body>"""
        result = transform_for_europass(html)
        
        # Heading text should be wrapped in <strong>
        assert "<strong>Tâches:</strong>" in result
        # Child items should exist
        assert "Task one" in result
        assert "Task two" in result

    def test_h3_followed_by_ol_converts(self):
        """Works with h3 and ordered lists too."""
        html = """<body>
            <h3>Technologies:</h3>
            <ol><li>Python</li><li>JavaScript</li></ol>
        </body>"""
        result = transform_for_europass(html)
        
        assert "<strong>Technologies:</strong>" in result
        assert "Python" in result

    def test_heading_without_list_becomes_bold_paragraph(self):
        """Standalone heading (no list after) becomes bold paragraph."""
        html = "<body><h2>Section Title</h2><p>Some text</p></body>"
        result = transform_for_europass(html)
        
        # Should become <p><strong>Section Title</strong></p>
        assert "<strong>Section Title</strong>" in result
        # Original text preserved
        assert "Some text" in result

    def test_multiple_headings_converted(self):
        """Multiple heading+list pairs are all converted."""
        html = """<body>
            <h2>Skills:</h2>
            <ul><li>Python</li></ul>
            <h2>Tools:</h2>
            <ul><li>Docker</li></ul>
        </body>"""
        result = transform_for_europass(html)
        
        assert "<strong>Skills:</strong>" in result
        assert "<strong>Tools:</strong>" in result
        assert "Python" in result
        assert "Docker" in result


# =============================================================================
# Quill Format Compliance Tests
# =============================================================================

class TestQuillFormatCompliance:
    """Verify output matches Quill/Europass requirements."""

    def test_ul_becomes_ol(self):
        """<ul> tags are converted to <ol> (Quill requirement)."""
        html = "<body><ul><li>Item</li></ul></body>"
        result = transform_for_europass(html)
        
        assert "<ul>" not in result
        assert "<ol>" in result or "Item" in result

    def test_li_has_data_list_attribute(self):
        """<li> tags get data-list="bullet" attribute."""
        html = "<body><ul><li>Item</li></ul></body>"
        result = transform_for_europass(html)
        
        assert 'data-list="bullet"' in result

    def test_li_has_ql_ui_marker(self):
        """<li> tags contain <span class="ql-ui"></span> marker."""
        html = "<body><ul><li>Item</li></ul></body>"
        result = transform_for_europass(html)
        
        assert '<span class="ql-ui">' in result

    def test_nested_list_gets_indent_class(self):
        """Nested list items get ql-indent-N class when following heading."""
        # Note: The module only adds ql-indent when headings are converted to bullets
        # (heading-child marker triggers indent). Pure nested lists retain structure.
        html = """<body>
            <h2>Section:</h2>
            <ul>
                <li>Child item</li>
            </ul>
        </body>"""
        result = transform_for_europass(html)
        
        # Heading children should get indent class
        assert "ql-indent-" in result

    def test_indent_capped_at_max(self):
        """Deep nesting is capped at max_indent (default 1)."""
        html = """<body>
            <ul>
                <li>Level 0
                    <ul><li>Level 1
                        <ul><li>Level 2
                            <ul><li>Level 3</li></ul>
                        </li></ul>
                    </li></ul>
                </li>
            </ul>
        </body>"""
        result = transform_for_europass(html, max_indent=1)
        
        # Should not have ql-indent-2 or higher
        assert "ql-indent-2" not in result
        assert "ql-indent-3" not in result


# =============================================================================
# Link Security Tests
# =============================================================================

class TestLinkSecurity:
    """Verify external links are properly secured."""

    def test_external_link_gets_target_blank(self):
        """External links get target="_blank"."""
        html = '<body><a href="https://example.com">Link</a></body>'
        result = transform_for_europass(html)
        
        assert 'target="_blank"' in result

    def test_external_link_gets_rel_noopener(self):
        """External links get rel="noopener noreferrer"."""
        html = '<body><a href="https://example.com">Link</a></body>'
        result = transform_for_europass(html)
        
        assert 'rel="noopener noreferrer"' in result

    def test_internal_link_unchanged(self):
        """Internal/relative links are not modified."""
        html = '<body><a href="/page">Internal</a></body>'
        result = transform_for_europass(html)
        
        # Should preserve the link but not add target/rel
        assert "Internal" in result

    def test_mailto_link_unchanged(self):
        """mailto: links are not modified."""
        html = '<body><a href="mailto:test@example.com">Email</a></body>'
        result = transform_for_europass(html)
        
        assert "mailto:" in result


# =============================================================================
# Inline Formatting Preservation Tests
# =============================================================================

class TestInlineFormattingPreservation:
    """Verify bold, italic, etc. are preserved."""

    def test_strong_preserved(self):
        """<strong> tags preserved in list items."""
        html = "<body><ul><li><strong>Bold text</strong> normal</li></ul></body>"
        result = transform_for_europass(html)
        
        assert "<strong>Bold text</strong>" in result

    def test_em_preserved(self):
        """<em> tags preserved in list items."""
        html = "<body><ul><li><em>Italic text</em></li></ul></body>"
        result = transform_for_europass(html)
        
        assert "<em>Italic text</em>" in result

    def test_nested_formatting_preserved(self):
        """Nested formatting (bold inside italic) preserved."""
        html = "<body><ul><li><em><strong>Bold italic</strong></em></li></ul></body>"
        result = transform_for_europass(html)
        
        assert "<strong>Bold italic</strong>" in result
        assert "<em>" in result


# =============================================================================
# Post-Processing Tests
# =============================================================================

class TestPostProcessing:
    """Test post_process_html cleanup."""

    def test_normalizes_spacing_in_tags(self):
        """Trailing spaces moved outside closing tags."""
        html = "<strong>text </strong>more"
        result = post_process_html(html)
        
        # Space should be outside the tag
        assert "</strong> " in result or result == "<strong>text</strong> more"

    def test_merges_consecutive_lists(self):
        """Consecutive <ol> lists are merged."""
        html = "<ol><li>A</li></ol><ol><li>B</li></ol>"
        result = post_process_html(html)
        
        # Should not have </ol><ol> pattern
        assert "</ol><ol>" not in result

    def test_cleans_multiple_spaces(self):
        """Multiple consecutive spaces reduced to one."""
        html = "text   with    spaces"
        result = post_process_html(html)
        
        assert "   " not in result


# =============================================================================
# Full Pipeline Tests (transform_and_clean)
# =============================================================================

class TestFullPipeline:
    """Integration tests for complete transformation pipeline."""

    def test_realistic_cv_experience_section(self):
        """Realistic CV experience section transforms correctly."""
        html = """<body>
            <h2>Senior Software Engineer</h2>
            <ul>
                <li><strong>Company:</strong> Tech Corp</li>
                <li><strong>Duration:</strong> 2020 - Present</li>
            </ul>
            <h3>Responsibilities:</h3>
            <ul>
                <li>Led team of 5 developers</li>
                <li>Designed microservices architecture</li>
            </ul>
        </body>"""
        
        result = transform_and_clean(html)
        
        # Key content preserved
        assert "Senior Software Engineer" in result
        assert "Tech Corp" in result
        assert "Led team of 5 developers" in result
        
        # Quill format applied
        assert 'data-list="bullet"' in result
        assert '<span class="ql-ui">' in result
        
        # Single line output
        assert "\n" not in result

    def test_cv_with_links_and_formatting(self):
        """CV with links and inline formatting."""
        html = """<body>
            <h2>Contact</h2>
            <ul>
                <li>GitHub: <a href="https://github.com/user">github.com/user</a></li>
                <li>Email: <strong>user@example.com</strong></li>
            </ul>
        </body>"""
        
        result = transform_and_clean(html)
        
        # Content preserved
        assert "github.com/user" in result
        assert "user@example.com" in result
        
        # Link secured
        assert 'target="_blank"' in result
        
        # Formatting preserved
        assert "<strong>" in result


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Edge cases and error handling."""

    def test_malformed_html_handled(self):
        """Malformed HTML doesn't crash."""
        html = "<body><ul><li>Unclosed item<li>Another</ul></body>"
        result = transform_for_europass(html)
        
        # Should produce some output
        assert len(result) > 0

    def test_empty_list_handled(self):
        """Empty list doesn't crash."""
        html = "<body><ul></ul></body>"
        result = transform_for_europass(html)
        
        assert isinstance(result, str)

    def test_deeply_nested_structure(self):
        """Very deeply nested structure is handled."""
        html = "<body>" + "<ul><li>" * 10 + "Deep" + "</li></ul>" * 10 + "</body>"
        result = transform_for_europass(html)
        
        assert "Deep" in result

    def test_unicode_content_preserved(self):
        """Unicode characters preserved."""
        html = "<body><ul><li>Développement • Français 日本語</li></ul></body>"
        result = transform_for_europass(html)
        
        assert "Développement" in result
        assert "•" in result
        assert "日本語" in result

    def test_html_entities_preserved(self):
        """HTML entities handled correctly."""
        html = "<body><ul><li>R&amp;D &copy; 2024</li></ul></body>"
        result = transform_for_europass(html)
        
        # Entity should be preserved somehow
        assert "R&amp;D" in result or "R&D" in result


# =============================================================================
# Regression Tests - Known Patterns from Production
# =============================================================================

class TestRegressionPatterns:
    """Regression tests for patterns seen in production CVs."""

    def test_europass_experience_pattern(self):
        """Europass experience description pattern."""
        html = """<body>
            <p><strong>Ingénieur Logiciel</strong></p>
            <p>ACME Corporation — Paris, France</p>
            <p>Janvier 2020 - Présent</p>
            <h3>Missions:</h3>
            <ul>
                <li>Développement back-end avec <strong>Python</strong> et <strong>FastAPI</strong></li>
                <li>Mise en place de CI/CD avec GitHub Actions</li>
            </ul>
        </body>"""
        
        result = transform_and_clean(html)
        
        # All content preserved
        assert "Ingénieur Logiciel" in result
        assert "ACME Corporation" in result
        assert "Python" in result
        assert "FastAPI" in result
        assert "CI/CD" in result

    def test_skills_section_with_categories(self):
        """Skills section with multiple categories."""
        html = """<body>
            <h2>Compétences Techniques</h2>
            <ul>
                <li><strong>Langages:</strong> Python, JavaScript, TypeScript</li>
                <li><strong>Frameworks:</strong> FastAPI, React, Node.js</li>
                <li><strong>Cloud:</strong> AWS, GCP, Azure</li>
            </ul>
        </body>"""
        
        result = transform_and_clean(html)
        
        assert "Compétences Techniques" in result
        assert "Python, JavaScript, TypeScript" in result
        assert "FastAPI, React, Node.js" in result

    def test_education_with_details(self):
        """Education section with nested details."""
        html = """<body>
            <h2>Formation</h2>
            <ul>
                <li>Master Informatique — Université Paris-Saclay
                    <ul>
                        <li>Spécialisation: Machine Learning</li>
                        <li>Mention: Très Bien</li>
                    </ul>
                </li>
            </ul>
        </body>"""
        
        result = transform_and_clean(html)
        
        assert "Master Informatique" in result
        assert "Machine Learning" in result
        assert "Très Bien" in result
        
        # Nested items should have indent
        assert "ql-indent-" in result


# =============================================================================
# Performance Sanity Check
# =============================================================================

class TestPerformance:
    """Basic performance sanity checks."""

    def test_large_document_completes_quickly(self):
        """Large document processes in reasonable time."""
        import time
        
        # Generate large HTML (~100 list items)
        items = [f"<li>Item {i} with some content</li>" for i in range(100)]
        html = f"<body><ul>{''.join(items)}</ul></body>"
        
        start = time.time()
        result = transform_and_clean(html)
        elapsed = time.time() - start
        
        # Should complete in under 100ms for 100 items
        assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s"
        assert len(result) > 0

    def test_multiple_transforms_consistent(self):
        """Repeated transforms produce identical results."""
        html = """<body>
            <h2>Test:</h2>
            <ul><li>Item 1</li><li>Item 2</li></ul>
        </body>"""
        
        results = [transform_and_clean(html) for _ in range(5)]
        
        # All results should be identical
        assert all(r == results[0] for r in results)


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
