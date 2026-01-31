"""
Single-Pass HTML Transformation for Europass/Quill Compatibility.

Replaces the previous 5 separate regex/HTMLParser transforms with a
cleaner two-phase approach:
1. Selectolax (Lexbor) for DOM structural transforms
2. Regex for Quill format string transforms

Architecture:
    Mammoth HTML → transform_for_europass() → Quill-compatible HTML → nh3 sanitize

Quill Format Requirements:
    - <ol> instead of <ul> (even for bullets)
    - data-list="bullet" attribute on <li>
    - <span class="ql-ui"></span> marker inside each <li>
    - ql-indent-N classes for nesting (max N=1 for ATS optimization)

Why selectolax/Lexbor:
    - 30x faster than BeautifulSoup, 5-10x faster than lxml
    - Modern HTML5-compliant parser
    - No external dependencies (Lexbor is bundled)
    - Clean DOM manipulation API
"""

import logging
import re

logger = logging.getLogger(__name__)

# Lazy import for optional dependency
_LexborHTMLParser = None


def _get_parser():
    """Lazy import selectolax."""
    global _LexborHTMLParser
    if _LexborHTMLParser is None:
        try:
            from selectolax.lexbor import LexborHTMLParser
            _LexborHTMLParser = LexborHTMLParser
        except ImportError:
            raise ImportError(
                "selectolax not installed. Run: pip install selectolax"
            )
    return _LexborHTMLParser


def is_selectolax_available() -> bool:
    """Check if selectolax is installed."""
    try:
        _get_parser()
        return True
    except ImportError:
        return False


def transform_for_europass(html: str, max_indent: int = 1) -> str:
    """
    Transform HTML to Europass/Quill-compatible format.
    
    Two-phase approach:
    1. Selectolax for structural DOM transforms (headings, links)
    2. Regex for Quill format string transforms (lists)
    
    Args:
        html: Input HTML (typically from Mammoth DOCX conversion)
        max_indent: Maximum indent level for ATS optimization (default: 1)
        
    Returns:
        Quill-compatible HTML string
    """
    if not html or not html.strip():
        return html
    
    LexborHTMLParser = _get_parser()
    
    # === PHASE 1: Structural transforms with selectolax ===
    tree = LexborHTMLParser(html)
    body = tree.css_first('body')
    if not body:
        return html
    
    # Convert headings followed by lists into bold list items
    _convert_headings_to_bullets(body)
    
    # Secure links (add target/rel attributes)
    _secure_links(body)
    
    # Extract HTML from body
    result = body.html
    result = re.sub(r'^<body[^>]*>', '', result)
    result = re.sub(r'</body>$', '', result)
    
    # === PHASE 2: String-based transforms for Quill format ===
    result = _convert_lists_to_quill_format(result, max_indent)
    
    # Single-line output (Europass requirement)
    result = result.replace('\n', '').strip()
    
    logger.debug(f"Transformed HTML: {len(html)} → {len(result)} chars")
    return result


def _convert_headings_to_bullets(body) -> None:
    """
    Convert headings followed by lists into bold bullet items.
    
    Europass uses flat bullet lists where section headers are bold items
    at indent level 0, followed by child items at indent level 1.
    
    Before: <h2>Tâches:</h2><ul><li>item</li></ul>
    After:  <ol><li data-list="bullet"><strong>Tâches:</strong></li>
                <li data-list="bullet" class="ql-indent-1">item</li></ol>
    """
    LexborHTMLParser = _get_parser()
    headings = body.css('h1, h2, h3, h4, h5, h6')
    
    for heading in headings:
        # Get the heading text content
        heading_text = heading.text(strip=True)
        if not heading_text:
            continue
        
        # Check if next sibling is a list
        next_elem = heading.next
        while next_elem and (next_elem.tag is None or next_elem.tag == '-text'):
            next_elem = next_elem.next
        
        if next_elem and next_elem.tag in ('ul', 'ol'):
            # Mark the list items as "heading children" (need extra indent)
            for li in next_elem.css('li'):
                existing_class = li.attrs.get('class', '')
                if existing_class:
                    li.attrs['class'] = f"{existing_class} heading-child"
                else:
                    li.attrs['class'] = 'heading-child'
            
            # Create new node by parsing HTML, then insert and remove old
            new_html = (
                f'<ol><li data-list="bullet" class="heading-parent">'
                f'<span class="ql-ui"></span><strong>{heading_text}</strong></li></ol>'
            )
            new_tree = LexborHTMLParser(new_html)
            new_node = new_tree.css_first('ol')
            heading.insert_before(new_node)
            heading.decompose()
        else:
            # No list follows - convert to bold paragraph
            new_html = f'<p><strong>{heading_text}</strong></p>'
            new_tree = LexborHTMLParser(new_html)
            new_node = new_tree.css_first('p')
            heading.insert_before(new_node)
            heading.decompose()


def _convert_lists_to_quill_format(html: str, max_indent: int = 1) -> str:
    """
    Convert lists to Quill's flat format with proper indentation.
    
    String-based processing (simpler than fighting selectolax's 
    limited child selector support):
    - Replace <ul> with <ol>
    - Add data-list="bullet" to <li>
    - Add ql-ui marker
    - Process heading markers for indent
    """
    # Replace <ul> with <ol>
    html = html.replace('<ul>', '<ol>').replace('</ul>', '</ol>')
    
    def process_li(match):
        """Process a single <li> tag."""
        attrs = match.group(1) or ''
        
        # Parse existing classes
        class_match = re.search(r'class="([^"]*)"', attrs)
        existing_classes = class_match.group(1) if class_match else ''
        
        # Check for heading markers
        is_heading_child = 'heading-child' in existing_classes
        
        # Determine indent level
        indent_match = re.search(r'ql-indent-(\d+)', existing_classes)
        indent = int(indent_match.group(1)) if indent_match else 0
        
        if is_heading_child and indent == 0:
            indent = 1
        
        # Cap indent at max_indent
        indent = min(indent, max_indent)
        
        # Build class attribute
        class_attr = f' class="ql-indent-{indent}"' if indent > 0 else ''
        
        return f'<li data-list="bullet"{class_attr}>'
    
    # Replace all <li> tags
    html = re.sub(r'<li([^>]*)>', process_li, html)
    
    # Add ql-ui marker to li items that don't have it
    html = re.sub(
        r'(<li[^>]*>)(?!<span class="ql-ui">)',
        r'\1<span class="ql-ui"></span>',
        html
    )
    
    # Clean up heading marker classes
    html = re.sub(r'\s*heading-child\s*', '', html)
    html = re.sub(r'\s*heading-parent\s*', '', html)
    html = re.sub(r'class="\s*"', '', html)
    
    return html


def _secure_links(body) -> None:
    """
    Ensure all links have proper security attributes.
    
    Adds target="_blank" and rel="noopener noreferrer" to external links.
    """
    for link in body.css('a'):
        href = link.attrs.get('href', '')
        
        # Only process external links
        if href.startswith(('http://', 'https://')):
            link.attrs['target'] = '_blank'
            link.attrs['rel'] = 'noopener noreferrer'


def post_process_html(html: str) -> str:
    """
    Post-process HTML for final cleanup.
    
    Handles text-level fixes that are easier with regex:
    - Normalize spacing around inline tags
    - Clean up multiple spaces
    - Merge consecutive lists
    """
    # Normalize spacing around inline tags
    # Move trailing spaces from inside closing tags to outside
    html = re.sub(r'\s+(</(?:strong|em|b|i|u)>)', r'\1 ', html)
    
    # Move leading spaces from inside opening tags to outside
    html = re.sub(r'(<(?:strong|em|b|i|u)>)\s+', r' \1', html)
    
    # Clean up multiple spaces
    html = re.sub(r'  +', ' ', html)
    
    # Merge consecutive <ol> lists (from heading conversion)
    html = re.sub(r'</ol>\s*<ol>', '', html)
    
    return html


def transform_and_clean(html: str, max_indent: int = 1) -> str:
    """
    Full transformation pipeline: transform + post-process.
    
    This is the main entry point for docx_to_quill.py
    """
    html = transform_for_europass(html, max_indent)
    html = post_process_html(html)
    return html


if __name__ == "__main__":
    # Quick test
    import sys
    
    print(f"selectolax available: {is_selectolax_available()}")
    
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            html = f.read()
        result = transform_and_clean(html)
        print(result)
    else:
        # Simple test case
        test_html = """
        <h2>Tâches:</h2>
        <ul>
            <li>Back-end development</li>
            <li>Front-end development
                <ul>
                    <li>React components</li>
                    <li>TypeScript</li>
                </ul>
            </li>
        </ul>
        """
        result = transform_and_clean(test_html)
        print("Input:")
        print(test_html)
        print("\nOutput:")
        print(result)
