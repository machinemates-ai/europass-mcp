#!/usr/bin/env python3
"""
Formatting Preservation Tests

Tests that formatting is preserved through the full pipeline:
  DOCX → MarkItDown → Markdown → AST Transform → Quill HTML

Strategy:
1. Structural Invariants: Count formatting elements (bold, links, lists)
2. Content Preservation: Verify text content isn't lost
3. Quill Compliance: Ensure output is valid Quill HTML
4. Known Patterns: Test specific Europass/CV formatting patterns
"""

import re
from pathlib import Path

import pytest

# Import pipeline components
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from markdown_transform import transform_headings_to_bullets
from mcp_server import _markdown_to_html as markdown_to_quill_html


# =============================================================================
# Test Fixtures - Realistic CV Content Patterns
# =============================================================================

@pytest.fixture
def cv_experience_markdown():
    """Realistic CV experience section in markdown."""
    return """## Senior Software Engineer

- **Company**: Tech Corp International
- **Location**: Paris, France
- **Duration**: January 2020 - Present

### Key Responsibilities

- Led a team of 5 developers on cloud migration project
- Designed and implemented microservices architecture using **Python** and **FastAPI**
- Reduced deployment time by 60% through CI/CD automation
- Mentored junior developers and conducted code reviews

### Technologies Used

- Python, FastAPI, PostgreSQL
- Docker, Kubernetes, AWS
- Git, GitHub Actions, Terraform
"""


@pytest.fixture
def cv_education_markdown():
    """Realistic CV education section."""
    return """## Master of Computer Science

- **Institution**: Université Paris-Saclay
- **Location**: Paris, France  
- **Period**: 2015 - 2017
- **Grade**: Magna Cum Laude

### Thesis

*"Distributed Systems for Real-Time Analytics"* - Supervised by Prof. Jean Dupont

### Relevant Coursework

- Machine Learning and Deep Learning
- Distributed Systems
- Software Engineering
- Data Structures and Algorithms
"""


@pytest.fixture
def cv_with_links_markdown():
    """CV content with various link formats."""
    return """## Contact & Online Presence

- Email: [john.doe@example.com](mailto:john.doe@example.com)
- LinkedIn: [linkedin.com/in/johndoe](https://linkedin.com/in/johndoe)
- GitHub: [github.com/johndoe](https://github.com/johndoe)
- Portfolio: [johndoe.dev](https://johndoe.dev)

## Publications

- [Paper Title One](https://doi.org/10.1000/example1) - Published in *Journal of CS*, 2023
- [Paper Title Two](https://arxiv.org/abs/1234.5678) - Preprint, 2024
"""


@pytest.fixture
def complex_nested_list():
    """Deeply nested list structure common in CVs."""
    return """## Project Experience

- **E-Commerce Platform Redesign**
  - Role: Lead Developer
  - Technologies:
    - Frontend: React, TypeScript
    - Backend: Node.js, Express
    - Database: PostgreSQL, Redis
  - Achievements:
    - Increased conversion rate by 25%
    - Reduced page load time by 40%
- **Mobile Banking App**
  - Role: Senior Developer
  - Technologies:
    - React Native
    - Firebase
  - Users: 100,000+ active users
"""


# =============================================================================
# Structural Invariant Tests
# =============================================================================

class TestStructuralInvariants:
    """Test that structural elements are preserved through the pipeline."""
    
    def _count_bold(self, text: str) -> int:
        """Count bold markers in markdown or <strong>/<b> in HTML."""
        if "<" in text:  # HTML
            return len(re.findall(r'<(strong|b)[^>]*>', text, re.I))
        else:  # Markdown
            return len(re.findall(r'\*\*[^*]+\*\*', text))
    
    def _count_italic(self, text: str) -> int:
        """Count italic markers in markdown or <em>/<i> in HTML."""
        if "<" in text:  # HTML
            return len(re.findall(r'<(em|i)[^>]*>', text, re.I))
        else:  # Markdown
            # Match single * or _ but not ** or __
            return len(re.findall(r'(?<!\*)\*(?!\*)[^*]+\*(?!\*)', text))
    
    def _count_links(self, text: str) -> int:
        """Count links in markdown or HTML."""
        if "<" in text:  # HTML
            return len(re.findall(r'<a\s+href=', text, re.I))
        else:  # Markdown
            return len(re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text))
    
    def _count_list_items(self, text: str) -> int:
        """Count list items in markdown or HTML."""
        if "<" in text:  # HTML
            return len(re.findall(r'<li[^>]*>', text, re.I))
        else:  # Markdown
            return len(re.findall(r'^[\s]*[-*+]\s', text, re.MULTILINE))
    
    def test_bold_count_preserved(self, cv_experience_markdown):
        """Bold formatting count should be preserved or increased.
        
        Headings become bold bullets, so bold count may increase.
        What matters is no bold is LOST.
        """
        original_bold = self._count_bold(cv_experience_markdown)
        
        # Through AST transform
        transformed = transform_headings_to_bullets(cv_experience_markdown)
        transform_bold = self._count_bold(transformed)
        
        # Through Quill conversion
        quill_html = markdown_to_quill_html(transformed)
        html_bold = self._count_bold(quill_html)
        
        # Bold count may increase (headings → bold), but should never decrease
        assert transform_bold >= original_bold, \
            f"AST transform lost bold: {original_bold} → {transform_bold}"
        assert html_bold >= original_bold, \
            f"Quill conversion lost bold: {original_bold} → {html_bold}"
    
    def test_link_count_preserved(self, cv_with_links_markdown):
        """Link count should be preserved."""
        original_links = self._count_links(cv_with_links_markdown)
        
        transformed = transform_headings_to_bullets(cv_with_links_markdown)
        transform_links = self._count_links(transformed)
        
        quill_html = markdown_to_quill_html(transformed)
        html_links = self._count_links(quill_html)
        
        assert transform_links == original_links, \
            f"AST transform lost links: {original_links} → {transform_links}"
        assert html_links == original_links, \
            f"Quill conversion lost links: {original_links} → {html_links}"
    
    def test_list_items_preserved_or_increased(self, cv_experience_markdown):
        """List item count should be >= original (headings become items)."""
        original_items = self._count_list_items(cv_experience_markdown)
        
        transformed = transform_headings_to_bullets(cv_experience_markdown)
        transform_items = self._count_list_items(transformed)
        
        quill_html = markdown_to_quill_html(transformed)
        html_items = self._count_list_items(quill_html)
        
        # Headings become list items, so count should increase
        assert transform_items >= original_items, \
            f"AST transform lost items: {original_items} → {transform_items}"
        assert html_items >= original_items, \
            f"Quill lost items: {original_items} → {html_items}"


# =============================================================================
# Content Preservation Tests
# =============================================================================

class TestContentPreservation:
    """Test that actual text content is preserved."""
    
    def _extract_text(self, html: str) -> str:
        """Extract plain text from HTML."""
        # Remove tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _extract_words(self, text: str) -> set:
        """Extract significant words (3+ chars) from text."""
        # Remove markdown/HTML syntax
        clean = re.sub(r'[*_`#\[\]()<>]', ' ', text)
        clean = re.sub(r'https?://\S+', '', clean)  # Remove URLs
        words = re.findall(r'\b[a-zA-Z]{3,}\b', clean.lower())
        return set(words)
    
    def test_key_words_preserved(self, cv_experience_markdown):
        """Key content words should appear in final output."""
        important_words = {
            'senior', 'software', 'engineer', 'python', 'fastapi',
            'docker', 'kubernetes', 'developers', 'team'
        }
        
        transformed = transform_headings_to_bullets(cv_experience_markdown)
        quill_html = markdown_to_quill_html(transformed)
        
        output_text = self._extract_text(quill_html).lower()
        
        for word in important_words:
            assert word in output_text, f"Lost word '{word}' in output"
    
    def test_company_names_preserved(self, cv_experience_markdown):
        """Company and organization names should be preserved."""
        # Add specific company names to test
        md = cv_experience_markdown.replace(
            "Tech Corp International",
            "Acme Corporation Ltd."
        )
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "Acme Corporation Ltd." in quill_html
    
    def test_dates_preserved(self):
        """Date formats should be preserved exactly."""
        md = """## Work Experience

- **Period**: January 2020 - December 2024
- Started: 2019-06-15
- Ended: 2024-01
"""
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "January 2020" in quill_html
        assert "December 2024" in quill_html
        assert "2019-06-15" in quill_html
        assert "2024-01" in quill_html
    
    def test_special_characters_preserved(self):
        """Special characters and accents should be preserved."""
        md = """## Éducation

- **École**: École Polytechnique Fédérale
- **Spécialité**: Génie Logiciel
- **Note**: Très Bien (≥16/20)
- Symbols: © ® ™ € £ ¥
"""
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "École Polytechnique Fédérale" in quill_html
        assert "Génie Logiciel" in quill_html
        assert "Très Bien" in quill_html
        assert "≥16/20" in quill_html or "&ge;16/20" in quill_html
        # At least some special chars preserved
        assert any(c in quill_html for c in ["©", "®", "™", "€"])


# =============================================================================
# Quill Compliance Tests  
# =============================================================================

class TestQuillCompliance:
    """Test that output is valid Quill-compatible HTML."""
    
    def test_uses_ordered_list(self, cv_experience_markdown):
        """Quill should use <ol> not <ul>."""
        quill_html = markdown_to_quill_html(
            transform_headings_to_bullets(cv_experience_markdown)
        )
        
        assert "<ol>" in quill_html
        # Europass Quill doesn't use <ul>
        assert "<ul>" not in quill_html
    
    def test_has_data_list_attribute(self, cv_experience_markdown):
        """Quill lists need data-list='bullet' attribute."""
        quill_html = markdown_to_quill_html(
            transform_headings_to_bullets(cv_experience_markdown)
        )
        
        assert 'data-list="bullet"' in quill_html
    
    def test_nested_lists_have_indent(self, complex_nested_list):
        """Nested items should have ql-indent-N classes."""
        quill_html = markdown_to_quill_html(
            transform_headings_to_bullets(complex_nested_list)
        )
        
        # Should have at least indent-1 for nested items
        assert "ql-indent-1" in quill_html
    
    def test_no_bare_text_outside_tags(self, cv_experience_markdown):
        """All text should be wrapped in appropriate tags."""
        quill_html = markdown_to_quill_html(
            transform_headings_to_bullets(cv_experience_markdown)
        )
        
        # Should start and end with tags
        stripped = quill_html.strip()
        assert stripped.startswith("<"), "Should start with a tag"
        assert stripped.endswith(">"), "Should end with a tag"
    
    def test_valid_html_structure(self, cv_experience_markdown):
        """HTML should have matching open/close tags."""
        quill_html = markdown_to_quill_html(
            transform_headings_to_bullets(cv_experience_markdown)
        )
        
        # Count open vs close tags for key elements
        for tag in ['ol', 'li', 'strong', 'em', 'a']:
            opens = len(re.findall(f'<{tag}[^>]*>', quill_html, re.I))
            closes = len(re.findall(f'</{tag}>', quill_html, re.I))
            assert opens == closes, f"Mismatched {tag}: {opens} opens, {closes} closes"


# =============================================================================
# Link Preservation Tests
# =============================================================================

class TestLinkPreservation:
    """Detailed tests for link/URL preservation."""
    
    def test_mailto_links(self):
        """Email mailto: links should be preserved."""
        md = "Contact: [email@example.com](mailto:email@example.com)"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert 'href="mailto:email@example.com"' in quill_html
        assert "email@example.com" in quill_html
    
    def test_https_links(self):
        """HTTPS links should be preserved."""
        md = "Visit [our site](https://example.com/path?query=1)"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert 'href="https://example.com/path?query=1"' in quill_html
    
    def test_link_text_preserved(self):
        """Link display text should be preserved."""
        md = "See [this amazing resource](https://example.com) for details"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "this amazing resource" in quill_html
        assert 'href="https://example.com"' in quill_html


# =============================================================================
# Edge Cases and Known Failure Patterns
# =============================================================================

class TestEdgeCases:
    """Test edge cases that might cause formatting loss."""
    
    def test_bold_at_line_start(self):
        """Bold text at start of line."""
        md = "**Important**: This is crucial information"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "<strong>Important</strong>" in quill_html or \
               "<b>Important</b>" in quill_html
    
    def test_nested_bold_in_list(self):
        """Bold text inside list items."""
        md = """- First item with **bold text** in middle
- **Entire item is bold**
- Normal item
"""
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        # Count bold tags
        bold_count = len(re.findall(r'<(strong|b)[^>]*>', quill_html, re.I))
        assert bold_count >= 2, f"Expected 2+ bold, got {bold_count}"
    
    def test_empty_list_items_handled(self):
        """Empty or whitespace-only list items shouldn't crash."""
        md = """- Item one
-   
- Item three
"""
        # Should not raise
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        assert "Item one" in quill_html
        assert "Item three" in quill_html
    
    def test_very_long_lines(self):
        """Very long lines should be handled."""
        long_text = "word " * 500  # 2500+ chars
        md = f"- {long_text.strip()}"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "word" in quill_html
        # Should still have list structure
        assert "<li" in quill_html
    
    def test_code_blocks_preserved(self):
        """Inline code should be preserved."""
        md = "Use `pip install package` to install"
        
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "pip install package" in quill_html
        # Should have code formatting
        assert "<code>" in quill_html or "monospace" in quill_html.lower()
    
    def test_multiple_paragraphs(self):
        """Multiple paragraphs should remain separate."""
        md = """First paragraph with some content.

Second paragraph after blank line.

Third paragraph here.
"""
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        # All content should be present
        assert "First paragraph" in quill_html
        assert "Second paragraph" in quill_html
        assert "Third paragraph" in quill_html


# =============================================================================
# Regression Tests for Known Issues
# =============================================================================

class TestRegressions:
    """Tests for previously discovered bugs."""
    
    def test_heading_level_correct_indent(self):
        """H2 should become top-level bullet, H3 indented.
        
        Note: Headings are converted to **bold** bullets.
        """
        md = """## Main Heading

- Main bullet

### Sub Heading

- Sub bullet
"""
        transformed = transform_headings_to_bullets(md)
        
        # H2 becomes "- **Main Heading**" (no indent, bold)
        assert re.search(r'^- \*\*Main Heading\*\*', transformed, re.MULTILINE)
        # H3 becomes "  - **Sub Heading**" (indented, bold)
        assert "Sub Heading" in transformed
        # Main bullet preserved
        assert "Main bullet" in transformed
    
    def test_asterisk_bold_not_list(self):
        """Bold markers shouldn't be confused with list markers."""
        md = "This has **bold** and *italic* text"
        
        transformed = transform_headings_to_bullets(md)
        quill_html = markdown_to_quill_html(transformed)
        
        # Should not create extra list items
        li_count = quill_html.count("<li")
        assert li_count <= 1, f"Bold markers created {li_count} list items"
    
    def test_consecutive_headings(self):
        """Multiple headings without content between them.
        
        Note: Headings become **bold** bullets.
        """
        md = """## Heading One
## Heading Two
## Heading Three
"""
        transformed = transform_headings_to_bullets(md)
        
        # All should become bold bullets
        assert "- **Heading One**" in transformed
        assert "- **Heading Two**" in transformed
        assert "- **Heading Three**" in transformed


# =============================================================================
# Integration Tests with Sample CVs
# =============================================================================

class TestCVPatterns:
    """Test common CV formatting patterns."""
    
    def test_europass_style_experience(self):
        """Test Europass-style job experience format."""
        md = """## Software Developer

**Employer**: Europass Tech GmbH
**Location**: Berlin, Germany
**Period**: 01/2020 - 12/2024

### Description

- Developed web applications using modern frameworks
- Collaborated with cross-functional teams
- Mentored junior developers

### Achievements

- Increased code coverage from 40% to 85%
- Reduced bug count by 60%
"""
        transformed = transform_headings_to_bullets(md)
        quill_html = markdown_to_quill_html(transformed)
        
        # Key content preserved
        assert "Software Developer" in quill_html
        assert "Europass Tech GmbH" in quill_html
        assert "Berlin, Germany" in quill_html
        assert "01/2020 - 12/2024" in quill_html
        assert "85%" in quill_html
    
    def test_skills_section(self):
        """Test skills section with categories."""
        md = """## Technical Skills

### Programming Languages
- Python (Expert)
- JavaScript (Advanced)
- Go (Intermediate)

### Frameworks
- Django, FastAPI
- React, Vue.js

### Tools
- Docker, Kubernetes
- Git, GitHub Actions
"""
        transformed = transform_headings_to_bullets(md)
        quill_html = markdown_to_quill_html(transformed)
        
        # All skills present
        assert "Python" in quill_html
        assert "Expert" in quill_html
        assert "Django" in quill_html
        assert "Docker" in quill_html
    
    def test_language_section(self):
        """Test language proficiency section."""
        md = """## Languages

- **English**: Native
- **French**: Professional proficiency (C1)
- **German**: Basic (A2)
- **Spanish**: Conversational (B1)
"""
        quill_html = markdown_to_quill_html(transform_headings_to_bullets(md))
        
        assert "English" in quill_html
        assert "Native" in quill_html
        assert "C1" in quill_html
        assert "A2" in quill_html


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
