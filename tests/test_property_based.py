#!/usr/bin/env python3
"""
Property-based tests using Hypothesis.

Generate random markdown structures and verify invariants hold.
"""

import pytest
from hypothesis import given, strategies as st, settings, assume
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from markdown_transform import transform_headings_to_bullets


# Custom strategies for markdown content
@st.composite
def markdown_list_item(draw, max_depth=3, current_depth=0):
    """Generate a markdown list item with optional nesting."""
    text = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S')),
        min_size=5,
        max_size=50
    ).filter(lambda x: x.strip()))
    
    indent = "    " * current_depth
    item = f"{indent}- {text}"
    
    # Maybe add nested items
    if current_depth < max_depth and draw(st.booleans()):
        num_nested = draw(st.integers(min_value=1, max_value=3))
        nested = []
        for _ in range(num_nested):
            nested.append(draw(markdown_list_item(max_depth, current_depth + 1)))
        return item + "\n" + "\n".join(nested)
    
    return item


@st.composite
def markdown_section(draw):
    """Generate a markdown section with heading and list."""
    heading_text = draw(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P')),
        min_size=3,
        max_size=30
    ).filter(lambda x: x.strip() and '\n' not in x))
    
    num_items = draw(st.integers(min_value=1, max_value=5))
    items = [draw(markdown_list_item(max_depth=2)) for _ in range(num_items)]
    
    return f"## {heading_text}\n" + "\n".join(items)


class TestPropertyBased:
    """Property-based tests for markdown transform."""

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=100)
    def test_never_crashes(self, text):
        """Transform should never crash on any input."""
        try:
            result = transform_headings_to_bullets(text)
            assert isinstance(result, str)
        except Exception as e:
            pytest.fail(f"Crashed on input: {text[:100]}... Error: {e}")

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=50)
    def test_idempotent(self, text):
        """Applying transform twice should be same as once."""
        result1 = transform_headings_to_bullets(text)
        result2 = transform_headings_to_bullets(result1)
        assert result1 == result2

    @given(markdown_section())
    @settings(max_examples=50)
    def test_heading_becomes_bullet(self, section):
        """H2 headings with lists should become bullet parents."""
        assume(section.startswith("## "))
        result = transform_headings_to_bullets(section)
        
        # Should have converted H2 to bullet
        # Either "- **Heading**" format or pass-through
        assert "## " not in result or "- **" in result

    @given(st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5))
    @settings(max_examples=30)
    def test_list_items_preserved(self, items):
        """All list item content should be preserved."""
        # Filter out problematic items (null bytes, control chars, empty, HTML special chars)
        html_special = '<>&"\'`'
        items = [i for i in items if i.strip() and '\n' not in i and '\x00' not in i 
                 and i.isprintable() and not any(c in i for c in html_special)]
        assume(len(items) > 0)
        
        md = "## Test Section\n" + "\n".join(f"- {item}" for item in items)
        result = transform_headings_to_bullets(md)
        
        for item in items:
            assert item in result, f"Lost content: {item}"


class TestBoundaryConditions:
    """Test boundary conditions."""

    @given(st.integers(min_value=1, max_value=8))
    def test_deep_nesting(self, depth):
        """Should handle nesting up to 8 levels (markdown parser limit)."""
        md = "## Deep\n"
        for i in range(depth):
            md += "    " * i + f"- Level {i}\n"
        
        result = transform_headings_to_bullets(md)
        
        # All levels should be present
        for i in range(depth):
            assert f"Level {i}" in result

    @given(st.integers(min_value=1, max_value=20))
    def test_many_headings(self, count):
        """Should handle many H2 headings."""
        md = "\n\n".join(f"## Section {i}\n- Item {i}" for i in range(count))
        result = transform_headings_to_bullets(md)
        
        # All items should be present
        for i in range(count):
            assert f"Item {i}" in result

    @given(st.text(alphabet="- *+", min_size=10, max_size=100))
    @settings(max_examples=20)
    def test_marker_soup(self, markers):
        """Should handle mixed list markers without crashing."""
        md = "## Test\n" + "\n".join(f"{m} item" for m in markers if m in "-*+")
        result = transform_headings_to_bullets(md)
        assert isinstance(result, str)


class TestUnicode:
    """Test Unicode handling."""

    @given(st.text(
        alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'S', 'M')),
        min_size=5,
        max_size=100
    ))
    @settings(max_examples=50)
    def test_unicode_preserved(self, text):
        """Unicode characters should be preserved."""
        assume(text.strip() and '\n' not in text[:50])
        clean_text = text.replace('\n', ' ')[:50]
        
        md = f"## {clean_text}\n- {clean_text}"
        result = transform_headings_to_bullets(md)
        
        # Content should be preserved
        assert clean_text in result

    def test_specific_unicode(self):
        """Test specific Unicode patterns from real CVs."""
        patterns = [
            "Réalisations et Contributions",
            "Développeur Full Stack",
            "Implémentation système",
            "日本語テスト",
            "🚀 Achievements 🎯",
            "Tâches & Responsabilités",
        ]
        
        for pattern in patterns:
            md = f"## {pattern}\n- Item"
            result = transform_headings_to_bullets(md)
            assert pattern in result, f"Lost Unicode: {pattern}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--hypothesis-show-statistics"])
