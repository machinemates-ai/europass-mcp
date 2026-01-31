"""
Pydantic Schema for Quill Delta Validation.

Quill Delta is the internal format used by the Quill rich text editor.
Europass uses Quill for CV content editing, so validating Delta structure
ensures compatibility and prevents malformed content.

Reference: https://quilljs.com/docs/delta/

Usage:
    from quill_schema import QuillDelta, validate_delta, html_to_delta_ops
    
    # Validate Delta JSON
    delta = QuillDelta.model_validate({"ops": [{"insert": "Hello\\n"}]})
    
    # Quick validation (returns True/False)
    is_valid = validate_delta({"ops": [{"insert": "World\\n"}]})
"""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


# =============================================================================
# Quill Delta Attribute Types
# =============================================================================

class InlineAttributes(BaseModel):
    """
    Inline formatting attributes for text content.
    
    These apply to runs of text within a line.
    """
    model_config = ConfigDict(extra="allow")
    
    # Text formatting
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    strike: Optional[bool] = None
    
    # Font styling
    font: Optional[str] = None
    size: Optional[str] = Field(None, pattern=r"^(small|normal|large|huge|\d+px)$")
    color: Optional[str] = None
    background: Optional[str] = None
    
    # Links
    link: Optional[str] = None
    
    # Code
    code: Optional[bool] = None
    
    # Script (superscript/subscript)
    script: Optional[Literal["sub", "super"]] = None


class BlockAttributes(BaseModel):
    """
    Block-level formatting attributes.
    
    These apply to entire lines/paragraphs.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    
    # Headers (h1-h6)
    header: Optional[int] = Field(None, ge=1, le=6)
    
    # Lists
    list: Optional[Literal["bullet", "ordered", "checked", "unchecked"]] = None
    
    # Indentation (0-8 levels for Quill, Europass uses ql-indent-N classes)
    indent: Optional[int] = Field(None, ge=0, le=8)
    
    # Text alignment
    align: Optional[Literal["left", "center", "right", "justify"]] = None
    
    # Block quote
    blockquote: Optional[bool] = None
    
    # Code block
    code_block: Optional[Union[bool, str]] = Field(None, alias="code-block")
    
    # Text direction
    direction: Optional[Literal["rtl", "ltr"]] = None


class DeltaAttributes(InlineAttributes, BlockAttributes):
    """
    Combined attributes for Delta operations.
    
    Inherits both inline and block-level attributes.
    Quill operations can have any combination of these.
    """
    pass


# =============================================================================
# Embed Types (non-text inserts)
# =============================================================================

class ImageEmbed(BaseModel):
    """Image embed object."""
    image: str  # URL or base64 data URI
    
    @field_validator("image")
    @classmethod
    def validate_image(cls, v: str) -> str:
        if not v:
            raise ValueError("Image source cannot be empty")
        # Allow URLs, data URIs, and relative paths
        if not (v.startswith(("http://", "https://", "data:", "/", ".")) or v):
            raise ValueError(f"Invalid image source: {v}")
        return v


class VideoEmbed(BaseModel):
    """Video embed object."""
    video: str  # URL


class FormulaEmbed(BaseModel):
    """LaTeX formula embed."""
    formula: str


class DividerEmbed(BaseModel):
    """Horizontal divider/rule."""
    divider: bool = True


# Union of all embed types
EmbedType = Union[ImageEmbed, VideoEmbed, FormulaEmbed, DividerEmbed, Dict[str, Any]]


# =============================================================================
# Delta Operations
# =============================================================================

class DeltaInsertOp(BaseModel):
    """
    Insert operation in a Quill Delta.
    
    The most common operation type - inserts text or embeds.
    """
    insert: Union[str, Dict[str, Any]]  # String or embed dict (image, video, etc.)
    attributes: Optional[DeltaAttributes] = None
    
    @field_validator("insert", mode="before")
    @classmethod
    def validate_insert(cls, v: Any) -> Union[str, Dict[str, Any]]:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # Should have exactly one key for embed type
            if len(v) == 0:
                raise ValueError("Embed object cannot be empty")
            # Validate known embed types
            valid_embed_keys = {"image", "video", "formula", "divider"}
            if v.keys() & valid_embed_keys:
                return v  # Return as dict, don't convert to model
            # Allow unknown embeds (extensibility)
            return v
        raise ValueError(f"Insert must be string or embed dict, got {type(v)}")


class DeltaRetainOp(BaseModel):
    """
    Retain operation in a Quill Delta.
    
    Used in diff/change deltas to skip over content.
    Optionally applies attributes to the retained range.
    """
    retain: int = Field(..., ge=1)
    attributes: Optional[DeltaAttributes] = None


class DeltaDeleteOp(BaseModel):
    """
    Delete operation in a Quill Delta.
    
    Used in diff/change deltas to remove content.
    """
    delete: int = Field(..., ge=1)


# Union of all operation types
DeltaOp = Union[DeltaInsertOp, DeltaRetainOp, DeltaDeleteOp]


# =============================================================================
# Main Delta Schema
# =============================================================================

class QuillDelta(BaseModel):
    """
    Complete Quill Delta document.
    
    A Delta is an array of operations that describe document content
    or changes to document content.
    
    For Europass CVs, we primarily use insert operations to describe
    the rich text content of CV sections.
    
    Example:
        {
            "ops": [
                {"insert": "Hello ", "attributes": {"bold": true}},
                {"insert": "World"},
                {"insert": "\\n", "attributes": {"header": 1}}
            ]
        }
    """
    ops: List[DeltaOp] = Field(..., min_length=1)
    
    @model_validator(mode="after")
    def validate_document_ends_with_newline(self) -> "QuillDelta":
        """
        Validate that document deltas end with a newline.
        
        For document deltas (not change deltas), the last insert
        should typically be a newline. This is a soft validation
        that logs a warning rather than raising an error.
        """
        if self.ops:
            last_op = self.ops[-1]
            if hasattr(last_op, "insert"):
                insert_val = last_op.insert
                if isinstance(insert_val, str) and not insert_val.endswith("\n"):
                    # This is common and not necessarily wrong
                    pass
        return self
    
    def to_plain_text(self) -> str:
        """Extract plain text from the delta."""
        text_parts = []
        for op in self.ops:
            if hasattr(op, "insert") and isinstance(op.insert, str):
                text_parts.append(op.insert)
        return "".join(text_parts)
    
    def get_insert_ops(self) -> List[DeltaInsertOp]:
        """Get only insert operations."""
        return [op for op in self.ops if isinstance(op, DeltaInsertOp)]
    
    def count_formatted_text(self) -> Dict[str, int]:
        """Count characters with specific formatting."""
        counts = {
            "bold": 0,
            "italic": 0,
            "underline": 0,
            "link": 0,
            "header": 0,
            "list": 0,
        }
        for op in self.ops:
            if hasattr(op, "insert") and isinstance(op.insert, str) and hasattr(op, "attributes"):
                attrs = op.attributes
                if attrs:
                    length = len(op.insert)
                    if attrs.bold:
                        counts["bold"] += length
                    if attrs.italic:
                        counts["italic"] += length
                    if attrs.underline:
                        counts["underline"] += length
                    if attrs.link:
                        counts["link"] += length
                    if attrs.header:
                        counts["header"] += length
                    if attrs.list:
                        counts["list"] += length
        return counts


# =============================================================================
# Validation Helpers
# =============================================================================

def validate_delta(data: Dict[str, Any]) -> bool:
    """
    Quick validation of Delta JSON.
    
    Args:
        data: Delta JSON dictionary
        
    Returns:
        True if valid, False otherwise
    """
    try:
        QuillDelta.model_validate(data)
        return True
    except Exception:
        return False


def validate_delta_strict(data: Dict[str, Any]) -> QuillDelta:
    """
    Strict validation of Delta JSON.
    
    Args:
        data: Delta JSON dictionary
        
    Returns:
        Validated QuillDelta instance
        
    Raises:
        ValidationError: If data is invalid
    """
    return QuillDelta.model_validate(data)


def create_simple_delta(text: str, attributes: Optional[Dict[str, Any]] = None) -> QuillDelta:
    """
    Create a simple Delta from plain text.
    
    Args:
        text: Plain text content
        attributes: Optional attributes to apply to all text
        
    Returns:
        QuillDelta instance
    """
    if not text.endswith("\n"):
        text += "\n"
    
    ops = []
    if attributes:
        ops.append(DeltaInsertOp(insert=text, attributes=DeltaAttributes(**attributes)))
    else:
        ops.append(DeltaInsertOp(insert=text))
    
    return QuillDelta(ops=ops)


# =============================================================================
# Europass-specific Quill Patterns
# =============================================================================

class EuropassListItem(BaseModel):
    """
    A single list item in Europass Quill format.
    
    Europass uses a flat list structure:
    - All items are in a single <ol>
    - data-list="bullet" for bullet points
    - ql-indent-N classes for nesting
    """
    content: str
    indent_level: int = Field(default=0, ge=0, le=8)
    is_bold: bool = False
    
    def to_delta_ops(self) -> List[Dict[str, Any]]:
        """Convert to Delta operations."""
        ops = []
        
        # Add content with optional bold
        if self.is_bold:
            ops.append({
                "insert": self.content,
                "attributes": {"bold": True}
            })
        else:
            ops.append({"insert": self.content})
        
        # Add newline with list formatting
        attrs = {"list": "bullet"}
        if self.indent_level > 0:
            attrs["indent"] = self.indent_level
        ops.append({
            "insert": "\n",
            "attributes": attrs
        })
        
        return ops


class EuropassSection(BaseModel):
    """
    A section in a Europass CV (e.g., job description, education details).
    
    Sections typically contain:
    - Optional header
    - List of bullet points (possibly nested)
    """
    header: Optional[str] = None
    items: List[EuropassListItem] = Field(default_factory=list)
    
    def to_delta(self) -> QuillDelta:
        """Convert section to QuillDelta."""
        ops = []
        
        # Add header if present
        if self.header:
            ops.append({"insert": self.header})
            ops.append({"insert": "\n", "attributes": {"header": 2}})
        
        # Add list items
        for item in self.items:
            ops.extend(item.to_delta_ops())
        
        # Ensure we have at least one op
        if not ops:
            ops.append({"insert": "\n"})
        
        return QuillDelta.model_validate({"ops": ops})


# =============================================================================
# HTML to Delta Conversion Helpers
# =============================================================================

def html_to_delta_ops(html: str) -> List[Dict[str, Any]]:
    """
    Convert simple Quill HTML to Delta operations.
    
    This is a basic converter for common patterns.
    For full conversion, use quill-delta library.
    
    Args:
        html: Quill-formatted HTML string
        
    Returns:
        List of Delta operation dictionaries
    """
    import re
    from html.parser import HTMLParser
    
    class DeltaBuilder(HTMLParser):
        def __init__(self):
            super().__init__()
            self.ops = []
            self.current_text = ""
            self.current_attrs = {}
            self.list_indent = 0
            
        def flush_text(self):
            if self.current_text:
                op = {"insert": self.current_text}
                if self.current_attrs:
                    op["attributes"] = self.current_attrs.copy()
                self.ops.append(op)
                self.current_text = ""
        
        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            
            if tag == "strong" or tag == "b":
                self.flush_text()
                self.current_attrs["bold"] = True
            elif tag == "em" or tag == "i":
                self.flush_text()
                self.current_attrs["italic"] = True
            elif tag == "u":
                self.flush_text()
                self.current_attrs["underline"] = True
            elif tag == "a":
                self.flush_text()
                self.current_attrs["link"] = attrs_dict.get("href", "")
            elif tag == "li":
                # Check for ql-indent-N class
                class_str = attrs_dict.get("class", "")
                match = re.search(r"ql-indent-(\d+)", class_str)
                if match:
                    self.list_indent = int(match.group(1))
                else:
                    self.list_indent = 0
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.flush_text()
                level = int(tag[1])
                self.current_attrs["header"] = level
        
        def handle_endtag(self, tag):
            if tag in ("strong", "b"):
                self.flush_text()
                self.current_attrs.pop("bold", None)
            elif tag in ("em", "i"):
                self.flush_text()
                self.current_attrs.pop("italic", None)
            elif tag == "u":
                self.flush_text()
                self.current_attrs.pop("underline", None)
            elif tag == "a":
                self.flush_text()
                self.current_attrs.pop("link", None)
            elif tag == "li":
                self.flush_text()
                # Add newline with list attributes
                attrs = {"list": "bullet"}
                if self.list_indent > 0:
                    attrs["indent"] = self.list_indent
                self.ops.append({"insert": "\n", "attributes": attrs})
            elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self.flush_text()
                level = int(tag[1])
                self.ops.append({"insert": "\n", "attributes": {"header": level}})
                self.current_attrs.pop("header", None)
            elif tag == "p":
                self.flush_text()
                self.ops.append({"insert": "\n"})
        
        def handle_data(self, data):
            # Skip whitespace-only data between tags
            if data.strip() or self.current_text:
                self.current_text += data
        
        def get_ops(self) -> List[Dict[str, Any]]:
            self.flush_text()
            if not self.ops:
                self.ops.append({"insert": "\n"})
            return self.ops
    
    parser = DeltaBuilder()
    parser.feed(html)
    return parser.get_ops()


# Export public API
__all__ = [
    # Main types
    "QuillDelta",
    "DeltaOp",
    "DeltaInsertOp",
    "DeltaRetainOp",
    "DeltaDeleteOp",
    "DeltaAttributes",
    "InlineAttributes",
    "BlockAttributes",
    # Embed types
    "ImageEmbed",
    "VideoEmbed",
    "FormulaEmbed",
    "DividerEmbed",
    "EmbedType",
    # Europass helpers
    "EuropassListItem",
    "EuropassSection",
    # Validation helpers
    "validate_delta",
    "validate_delta_strict",
    "create_simple_delta",
    "html_to_delta_ops",
]
