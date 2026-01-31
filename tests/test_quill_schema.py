#!/usr/bin/env python3
"""
Tests for Pydantic Quill Delta Schema.

Tests the quill_schema.py module which provides:
- QuillDelta, DeltaOp, DeltaAttributes models
- Validation helpers
- Europass-specific patterns
- HTML to Delta conversion
"""

from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quill_schema import (
    QuillDelta,
    DeltaInsertOp,
    DeltaRetainOp,
    DeltaDeleteOp,
    DeltaAttributes,
    InlineAttributes,
    BlockAttributes,
    ImageEmbed,
    VideoEmbed,
    EuropassListItem,
    EuropassSection,
    validate_delta,
    validate_delta_strict,
    create_simple_delta,
    html_to_delta_ops,
)


# =============================================================================
# Basic Delta Structure Tests
# =============================================================================

class TestQuillDeltaBasic:
    """Test basic QuillDelta validation."""
    
    def test_simple_text_delta(self):
        """Simple text should validate."""
        delta = QuillDelta.model_validate({
            "ops": [{"insert": "Hello World\n"}]
        })
        assert len(delta.ops) == 1
        assert delta.ops[0].insert == "Hello World\n"
    
    def test_empty_ops_fails(self):
        """Empty ops list should fail validation."""
        with pytest.raises(Exception):
            QuillDelta.model_validate({"ops": []})
    
    def test_missing_ops_fails(self):
        """Missing ops key should fail validation."""
        with pytest.raises(Exception):
            QuillDelta.model_validate({})
    
    def test_multiple_ops(self):
        """Multiple operations should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Hello "},
                {"insert": "World"},
                {"insert": "\n"}
            ]
        })
        assert len(delta.ops) == 3
    
    def test_to_plain_text(self):
        """Should extract plain text from delta."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Hello "},
                {"insert": "World", "attributes": {"bold": True}},
                {"insert": "\n"}
            ]
        })
        assert delta.to_plain_text() == "Hello World\n"


# =============================================================================
# Inline Attributes Tests
# =============================================================================

class TestInlineAttributes:
    """Test inline formatting attributes."""
    
    def test_bold_attribute(self):
        """Bold attribute should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Bold text", "attributes": {"bold": True}},
                {"insert": "\n"}
            ]
        })
        assert delta.ops[0].attributes.bold is True
    
    def test_italic_attribute(self):
        """Italic attribute should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Italic", "attributes": {"italic": True}},
                {"insert": "\n"}
            ]
        })
        assert delta.ops[0].attributes.italic is True
    
    def test_link_attribute(self):
        """Link attribute should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Click here", "attributes": {"link": "https://example.com"}},
                {"insert": "\n"}
            ]
        })
        assert delta.ops[0].attributes.link == "https://example.com"
    
    def test_combined_attributes(self):
        """Multiple inline attributes should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Bold italic link", "attributes": {
                    "bold": True,
                    "italic": True,
                    "link": "https://example.com"
                }},
                {"insert": "\n"}
            ]
        })
        attrs = delta.ops[0].attributes
        assert attrs.bold is True
        assert attrs.italic is True
        assert attrs.link == "https://example.com"
    
    def test_script_superscript(self):
        """Superscript should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "x", "attributes": {"script": "super"}},
                {"insert": "2\n"}
            ]
        })
        assert delta.ops[0].attributes.script == "super"
    
    def test_script_subscript(self):
        """Subscript should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "H"},
                {"insert": "2", "attributes": {"script": "sub"}},
                {"insert": "O\n"}
            ]
        })
        assert delta.ops[1].attributes.script == "sub"


# =============================================================================
# Block Attributes Tests
# =============================================================================

class TestBlockAttributes:
    """Test block-level formatting attributes."""
    
    def test_header_levels(self):
        """Header levels 1-6 should validate."""
        for level in range(1, 7):
            delta = QuillDelta.model_validate({
                "ops": [
                    {"insert": f"Heading {level}"},
                    {"insert": "\n", "attributes": {"header": level}}
                ]
            })
            assert delta.ops[1].attributes.header == level
    
    def test_header_invalid_level(self):
        """Header level 0 or 7+ should fail."""
        with pytest.raises(Exception):
            QuillDelta.model_validate({
                "ops": [
                    {"insert": "Invalid"},
                    {"insert": "\n", "attributes": {"header": 0}}
                ]
            })
    
    def test_bullet_list(self):
        """Bullet list should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Item 1"},
                {"insert": "\n", "attributes": {"list": "bullet"}},
                {"insert": "Item 2"},
                {"insert": "\n", "attributes": {"list": "bullet"}}
            ]
        })
        assert delta.ops[1].attributes.list == "bullet"
    
    def test_ordered_list(self):
        """Ordered list should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "First"},
                {"insert": "\n", "attributes": {"list": "ordered"}}
            ]
        })
        assert delta.ops[1].attributes.list == "ordered"
    
    def test_indent_levels(self):
        """Indent levels 0-8 should validate."""
        for indent in range(0, 9):
            delta = QuillDelta.model_validate({
                "ops": [
                    {"insert": "Indented"},
                    {"insert": "\n", "attributes": {"indent": indent}}
                ]
            })
            assert delta.ops[1].attributes.indent == indent
    
    def test_indent_too_deep(self):
        """Indent level > 8 should fail."""
        with pytest.raises(Exception):
            QuillDelta.model_validate({
                "ops": [
                    {"insert": "Too deep"},
                    {"insert": "\n", "attributes": {"indent": 9}}
                ]
            })
    
    def test_text_alignment(self):
        """Text alignment options should validate."""
        for align in ["left", "center", "right", "justify"]:
            delta = QuillDelta.model_validate({
                "ops": [
                    {"insert": "Aligned text"},
                    {"insert": "\n", "attributes": {"align": align}}
                ]
            })
            assert delta.ops[1].attributes.align == align


# =============================================================================
# Embed Types Tests
# =============================================================================

class TestEmbedTypes:
    """Test embed (non-text) inserts."""
    
    def test_image_embed_url(self):
        """Image embed with URL should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": {"image": "https://example.com/photo.jpg"}},
                {"insert": "\n"}
            ]
        })
        assert delta.ops[0].insert["image"] == "https://example.com/photo.jpg"
    
    def test_image_embed_data_uri(self):
        """Image embed with data URI should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": {"image": "data:image/png;base64,iVBORw0KGgo="}},
                {"insert": "\n"}
            ]
        })
        assert "data:image" in delta.ops[0].insert["image"]
    
    def test_video_embed(self):
        """Video embed should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": {"video": "https://youtube.com/watch?v=123"}},
                {"insert": "\n"}
            ]
        })
        assert "youtube" in delta.ops[0].insert["video"]


# =============================================================================
# Change Delta Tests (retain/delete)
# =============================================================================

class TestChangeDelta:
    """Test retain and delete operations for change deltas."""
    
    def test_retain_operation(self):
        """Retain operation should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"retain": 5},
                {"insert": " World"}
            ]
        })
        assert delta.ops[0].retain == 5
    
    def test_retain_with_attributes(self):
        """Retain with attributes (format change) should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"retain": 5, "attributes": {"bold": True}}
            ]
        })
        assert delta.ops[0].retain == 5
        assert delta.ops[0].attributes.bold is True
    
    def test_delete_operation(self):
        """Delete operation should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"retain": 5},
                {"delete": 3}
            ]
        })
        assert delta.ops[1].delete == 3
    
    def test_complex_change_delta(self):
        """Complex change delta should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"retain": 10},
                {"delete": 5},
                {"insert": "replacement"},
                {"retain": 3, "attributes": {"bold": True}}
            ]
        })
        assert len(delta.ops) == 4


# =============================================================================
# Validation Helpers Tests
# =============================================================================

class TestValidationHelpers:
    """Test validation helper functions."""
    
    def test_validate_delta_valid(self):
        """Valid delta should return True."""
        result = validate_delta({"ops": [{"insert": "Hello\n"}]})
        assert result is True
    
    def test_validate_delta_invalid(self):
        """Invalid delta should return False."""
        result = validate_delta({"ops": []})
        assert result is False
    
    def test_validate_delta_strict_valid(self):
        """Valid delta should return QuillDelta."""
        result = validate_delta_strict({"ops": [{"insert": "Test\n"}]})
        assert isinstance(result, QuillDelta)
    
    def test_validate_delta_strict_invalid(self):
        """Invalid delta should raise exception."""
        with pytest.raises(Exception):
            validate_delta_strict({"invalid": "data"})
    
    def test_create_simple_delta(self):
        """create_simple_delta should create valid delta."""
        delta = create_simple_delta("Hello World")
        assert isinstance(delta, QuillDelta)
        assert "Hello World\n" in delta.to_plain_text()
    
    def test_create_simple_delta_with_attributes(self):
        """create_simple_delta with attributes should work."""
        delta = create_simple_delta("Bold text", {"bold": True})
        assert delta.ops[0].attributes.bold is True


# =============================================================================
# Europass-specific Tests
# =============================================================================

class TestEuropassPatterns:
    """Test Europass-specific Quill patterns."""
    
    def test_europass_list_item(self):
        """EuropassListItem should create valid ops."""
        item = EuropassListItem(content="Managed team of 5", indent_level=0)
        ops = item.to_delta_ops()
        
        assert len(ops) == 2
        assert ops[0]["insert"] == "Managed team of 5"
        assert ops[1]["attributes"]["list"] == "bullet"
    
    def test_europass_list_item_nested(self):
        """Nested EuropassListItem should have indent."""
        item = EuropassListItem(content="Sub-task", indent_level=1)
        ops = item.to_delta_ops()
        
        assert ops[1]["attributes"]["indent"] == 1
    
    def test_europass_list_item_bold(self):
        """Bold EuropassListItem should have bold attribute."""
        item = EuropassListItem(content="Important", indent_level=0, is_bold=True)
        ops = item.to_delta_ops()
        
        assert ops[0]["attributes"]["bold"] is True
    
    def test_europass_section_with_header(self):
        """EuropassSection with header should be valid."""
        section = EuropassSection(
            header="Key Achievements",
            items=[
                EuropassListItem(content="Reduced costs by 30%"),
                EuropassListItem(content="Improved efficiency"),
            ]
        )
        delta = section.to_delta()
        
        assert isinstance(delta, QuillDelta)
        assert "Key Achievements" in delta.to_plain_text()
        assert "Reduced costs" in delta.to_plain_text()
    
    def test_europass_section_nested_items(self):
        """EuropassSection with nested items should be valid."""
        section = EuropassSection(
            items=[
                EuropassListItem(content="Led development", indent_level=0),
                EuropassListItem(content="Python backend", indent_level=1),
                EuropassListItem(content="React frontend", indent_level=1),
            ]
        )
        delta = section.to_delta()
        
        # Should have 6 ops: 3 content + 3 newlines
        assert len(delta.ops) == 6


# =============================================================================
# HTML to Delta Conversion Tests
# =============================================================================

class TestHtmlToDelta:
    """Test HTML to Delta conversion."""
    
    def test_simple_paragraph(self):
        """Simple paragraph should convert."""
        ops = html_to_delta_ops("<p>Hello World</p>")
        
        assert any("Hello World" in str(op.get("insert", "")) for op in ops)
    
    def test_bold_text(self):
        """Bold text should convert with attribute."""
        ops = html_to_delta_ops("<p><strong>Bold</strong></p>")
        
        bold_ops = [op for op in ops if op.get("attributes", {}).get("bold")]
        assert len(bold_ops) >= 1
    
    def test_italic_text(self):
        """Italic text should convert with attribute."""
        ops = html_to_delta_ops("<p><em>Italic</em></p>")
        
        italic_ops = [op for op in ops if op.get("attributes", {}).get("italic")]
        assert len(italic_ops) >= 1
    
    def test_link(self):
        """Link should convert with href."""
        ops = html_to_delta_ops('<p><a href="https://example.com">Link</a></p>')
        
        link_ops = [op for op in ops if op.get("attributes", {}).get("link")]
        assert len(link_ops) >= 1
        assert "example.com" in link_ops[0]["attributes"]["link"]
    
    def test_quill_list(self):
        """Quill list format should convert."""
        html = '<ol><li data-list="bullet">Item 1</li><li data-list="bullet">Item 2</li></ol>'
        ops = html_to_delta_ops(html)
        
        list_ops = [op for op in ops if op.get("attributes", {}).get("list")]
        assert len(list_ops) >= 2
    
    def test_nested_list_with_indent(self):
        """Nested list should have indent attribute."""
        html = '''
        <ol>
            <li data-list="bullet">Parent</li>
            <li data-list="bullet" class="ql-indent-1">Child</li>
        </ol>
        '''
        ops = html_to_delta_ops(html)
        
        # Find ops with indent
        indent_ops = [op for op in ops if op.get("attributes", {}).get("indent")]
        assert len(indent_ops) >= 1
    
    def test_header(self):
        """Header should convert with header attribute."""
        ops = html_to_delta_ops("<h2>Section Title</h2>")
        
        header_ops = [op for op in ops if op.get("attributes", {}).get("header") == 2]
        assert len(header_ops) >= 1


# =============================================================================
# Count Formatted Text Tests
# =============================================================================

class TestCountFormattedText:
    """Test the count_formatted_text method."""
    
    def test_count_bold_characters(self):
        """Should count bold characters correctly."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Hello ", "attributes": {"bold": True}},  # 6 bold
                {"insert": "World\n"}  # 6 normal
            ]
        })
        counts = delta.count_formatted_text()
        assert counts["bold"] == 6
    
    def test_count_multiple_formats(self):
        """Should count multiple format types."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Bold", "attributes": {"bold": True}},  # 4 bold
                {"insert": " "},
                {"insert": "Italic", "attributes": {"italic": True}},  # 6 italic
                {"insert": "\n"}
            ]
        })
        counts = delta.count_formatted_text()
        assert counts["bold"] == 4
        assert counts["italic"] == 6


# =============================================================================
# Real-world CV Delta Tests
# =============================================================================

class TestRealWorldCVDelta:
    """Test with realistic CV content patterns."""
    
    def test_job_description_delta(self):
        """Job description with bullets should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Senior Software Engineer"},
                {"insert": "\n", "attributes": {"header": 2}},
                {"insert": "Led development of cloud-native microservices"},
                {"insert": "\n", "attributes": {"list": "bullet"}},
                {"insert": "Improved API performance by 40%"},
                {"insert": "\n", "attributes": {"list": "bullet"}},
                {"insert": "Mentored junior developers"},
                {"insert": "\n", "attributes": {"list": "bullet"}}
            ]
        })
        assert len(delta.ops) == 8
        assert "Senior Software Engineer" in delta.to_plain_text()
    
    def test_skills_section_delta(self):
        """Skills section with bold headers should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "Technical Skills:", "attributes": {"bold": True}},
                {"insert": "\n"},
                {"insert": "Python, JavaScript, TypeScript"},
                {"insert": "\n", "attributes": {"list": "bullet"}},
                {"insert": "Docker, Kubernetes, AWS"},
                {"insert": "\n", "attributes": {"list": "bullet"}}
            ]
        })
        counts = delta.count_formatted_text()
        assert counts["bold"] > 0
        assert counts["list"] > 0
    
    def test_education_with_link(self):
        """Education entry with university link should validate."""
        delta = QuillDelta.model_validate({
            "ops": [
                {"insert": "MIT", "attributes": {"link": "https://mit.edu", "bold": True}},
                {"insert": " - Master of Science"},
                {"insert": "\n", "attributes": {"header": 3}},
                {"insert": "Computer Science, 2020"},
                {"insert": "\n"}
            ]
        })
        counts = delta.count_formatted_text()
        assert counts["link"] == 3  # "MIT" = 3 chars with link
        assert counts["bold"] == 3
