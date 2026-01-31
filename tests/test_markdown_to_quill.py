"""
Tests for Markdown to Quill HTML conversion.

Validates that markdown is correctly converted to Europass-compatible
Quill Editor HTML format with proper nesting via ql-indent-N classes.
"""

import re
from collections import Counter

import pytest

from src.mcp_server import _markdown_to_html


class TestFlatLists:
    """Test flat list conversion."""

    def test_simple_flat_list(self):
        """Simple bullet list should produce flat ol with li tags."""
        md = """- Item 1
- Item 2
- Item 3"""
        html = _markdown_to_html(md)
        
        assert "<ol>" in html
        assert html.count('<li data-list="bullet">') == 3
        assert '<span class="ql-ui"></span>' in html
        assert "ql-indent" not in html  # No nesting

    def test_flat_list_with_bold(self):
        """Bold text should be preserved in list items."""
        md = """- **Bold item**
- Normal item"""
        html = _markdown_to_html(md)
        
        assert "<strong>Bold item</strong>" in html
        assert html.count('<li data-list="bullet">') == 2

    def test_flat_list_with_link(self):
        """Links should be properly formatted."""
        md = "- Check [this link](https://example.com)"
        html = _markdown_to_html(md)
        
        assert 'href="https://example.com"' in html
        assert 'rel="noopener noreferrer"' in html
        assert 'target="_blank"' in html


class TestNestedLists:
    """Test nested list conversion to Quill indent classes."""

    def test_two_level_nesting(self):
        """Two-level nested list should use ql-indent-1."""
        md = """- Top level
  - Nested item 1
  - Nested item 2
- Another top level"""
        html = _markdown_to_html(md)
        
        # Should have both top-level and indented items
        assert '<li data-list="bullet"><span class="ql-ui">' in html
        assert 'class="ql-indent-1"' in html
        
        # Count items
        assert html.count('data-list="bullet"') == 4
        assert html.count('ql-indent-1') == 2

    def test_three_level_nesting(self):
        """Three-level nested list should use ql-indent-1 and ql-indent-2."""
        md = """- Level 0
  - Level 1
    - Level 2a
    - Level 2b
  - Level 1 again"""
        html = _markdown_to_html(md)
        
        assert 'class="ql-indent-1"' in html
        assert 'class="ql-indent-2"' in html
        
        # Count indent levels
        indent_1 = html.count('ql-indent-1')
        indent_2 = html.count('ql-indent-2')
        assert indent_1 == 2  # Two level-1 items
        assert indent_2 == 2  # Two level-2 items

    def test_europass_style_structure(self):
        """Test structure matching Europass CV format."""
        md = """- **Contexte :** Description du contexte.

- **Réalisations :**
  - **Agent E-commerce :** Création d'un agent.
  - **Pipelines RAG :** Implémentation.
- **Tâches :**
  - **Back-end :**
    - Codage LLM.
    - API RESTful.
  - **DevOps :**
    - CI/CD."""
        html = _markdown_to_html(md)
        
        # Should have proper Quill structure
        assert '<ol>' in html
        assert 'data-list="bullet"' in html
        
        # Count nesting levels
        indents = re.findall(r'ql-indent-(\d+)', html)
        counts = Counter(indents)
        
        # Should have nested items
        assert len(counts) > 0, "Should have nested items with ql-indent classes"


class TestFormatPreservation:
    """Test that formatting is preserved correctly."""

    def test_bold_preserved(self):
        """Bold text should be preserved."""
        md = "**Bold text**"
        html = _markdown_to_html(md)
        assert "<strong>Bold text</strong>" in html

    def test_italic_preserved(self):
        """Italic text should be preserved."""
        md = "*Italic text*"
        html = _markdown_to_html(md)
        assert "<em>Italic text</em>" in html

    def test_code_preserved(self):
        """Inline code should be preserved."""
        md = "`code`"
        html = _markdown_to_html(md)
        assert "<code>code</code>" in html

    def test_paragraph_preserved(self):
        """Paragraphs should be wrapped in <p> tags."""
        md = "First paragraph.\n\nSecond paragraph."
        html = _markdown_to_html(md)
        assert html.count("<p>") == 2

    def test_single_line_output(self):
        """Output should be single-line (Europass XML requirement)."""
        md = """- Item 1
- Item 2

Paragraph."""
        html = _markdown_to_html(md)
        assert "\n" not in html


class TestEdgeCases:
    """Test edge cases and malformed input."""

    def test_empty_input(self):
        """Empty input should return empty string."""
        assert _markdown_to_html("") == ""
        assert _markdown_to_html(None) == ""

    def test_mixed_content(self):
        """Mix of paragraphs and lists."""
        md = """Introduction paragraph.

- List item 1
- List item 2

Conclusion paragraph."""
        html = _markdown_to_html(md)
        
        assert "<p>Introduction paragraph.</p>" in html
        assert "<p>Conclusion paragraph.</p>" in html
        assert '<li data-list="bullet">' in html


class TestQuillFormatCompliance:
    """Test compliance with Quill Editor format used by Europass."""

    def test_ol_instead_of_ul(self):
        """Europass uses <ol> for all lists, not <ul>."""
        md = "- Bullet item"
        html = _markdown_to_html(md)
        
        assert "<ol>" in html
        assert "<ul>" not in html

    def test_data_list_attribute(self):
        """All li elements should have data-list='bullet'."""
        md = """- Item 1
  - Nested"""
        html = _markdown_to_html(md)
        
        li_count = html.count("<li")
        data_list_count = html.count('data-list="bullet"')
        assert li_count == data_list_count

    def test_ql_ui_span(self):
        """All li elements should have <span class='ql-ui'></span>."""
        md = """- Item 1
- Item 2"""
        html = _markdown_to_html(md)
        
        li_count = html.count("<li")
        ql_ui_count = html.count('<span class="ql-ui"></span>')
        assert li_count == ql_ui_count


def compare_with_original(original_xml_path: str, generated_xml_path: str) -> dict:
    """
    Compare formatting metrics between original and generated XML.
    
    Returns dict with comparison metrics for validation.
    """
    import re
    from pathlib import Path
    
    def extract_metrics(xml_content: str) -> dict:
        indents = re.findall(r'ql-indent-(\d+)', xml_content)
        return {
            "total_li": len(re.findall(r'data-list', xml_content)),
            "indent_1": indents.count("1"),
            "indent_2": indents.count("2"),
            "total_indented": len(indents),
        }
    
    original = Path(original_xml_path).read_text() if Path(original_xml_path).exists() else ""
    generated = Path(generated_xml_path).read_text() if Path(generated_xml_path).exists() else ""
    
    return {
        "original": extract_metrics(original),
        "generated": extract_metrics(generated),
    }


if __name__ == "__main__":
    # Quick test run
    pytest.main([__file__, "-v"])
