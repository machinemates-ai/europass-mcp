"""
Markdown post-processor using markdown-it-py AST.

Transforms LLM output with ## headings into Europass-compatible nested bullet structure.

Before:
    ## Réalisations :
    - Item 1
    - Item 2

After:
    - **Réalisations :**
      - Item 1
      - Item 2
"""

from markdown_it import MarkdownIt
from markdown_it.token import Token


def transform_headings_to_bullets(text: str) -> str:
    """
    Transform markdown headings followed by lists into nested bullet structure.
    
    Uses markdown-it-py AST parsing (no regex).
    """
    md = MarkdownIt()
    tokens = md.parse(text)
    
    output_lines: list[str] = []
    heading_pending = False  # True if we just saw a heading
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        # Heading → bold bullet parent
        if token.type == "heading_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and inline.type == "inline":
                output_lines.append(f"- **{inline.content}**")
                heading_pending = True
            i += 3
            continue
        
        # Standalone paragraph (outside lists)
        if token.type == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and inline.type == "inline" and inline.content:
                output_lines.append(inline.content)
                heading_pending = False
            i += 3
            continue
        
        # Bullet list → process recursively
        if token.type == "bullet_list_open":
            # If list follows a heading, it becomes children of that heading
            # Add +2 indent for proper nesting
            base_indent = 2 if heading_pending else 0
            heading_pending = False
            
            # Find matching close
            close_idx = find_matching_close(tokens, i, "bullet_list_open", "bullet_list_close")
            
            # Process the list
            process_bullet_list(tokens[i+1:close_idx], base_indent, output_lines)
            
            i = close_idx + 1
            continue
        
        i += 1
    
    return "\n".join(output_lines)


def find_matching_close(tokens: list[Token], start: int, open_type: str, close_type: str) -> int:
    """Find the index of the matching close token."""
    depth = 1
    i = start + 1
    while i < len(tokens) and depth > 0:
        if tokens[i].type == open_type:
            depth += 1
        elif tokens[i].type == close_type:
            depth -= 1
        i += 1
    return i - 1


def process_bullet_list(tokens: list[Token], base_indent: int, output: list[str]) -> None:
    """Process a bullet list's inner tokens."""
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        if token.type == "list_item_open":
            # Find the matching close
            close_idx = i + 1
            depth = 1
            while close_idx < len(tokens):
                if tokens[close_idx].type == "list_item_open":
                    depth += 1
                elif tokens[close_idx].type == "list_item_close":
                    depth -= 1
                    if depth == 0:
                        break
                close_idx += 1
            
            # Process this list item
            process_list_item(tokens[i+1:close_idx], base_indent, output)
            
            i = close_idx + 1
            continue
        
        i += 1


def process_list_item(tokens: list[Token], indent: int, output: list[str]) -> None:
    """Process a single list item's content."""
    item_text = None
    i = 0
    
    while i < len(tokens):
        token = tokens[i]
        
        # Get the item's text from paragraph
        if token.type == "paragraph_open":
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            if inline and inline.type == "inline" and item_text is None:
                item_text = inline.content
            i += 3
            continue
        
        # Nested bullet list
        if token.type == "bullet_list_open":
            # First output the current item text
            if item_text:
                indent_str = " " * indent
                output.append(f"{indent_str}- {item_text}")
                item_text = None  # Already output
            
            # Find matching close
            close_idx = find_matching_close(tokens, i, "bullet_list_open", "bullet_list_close")
            
            # Process nested list with +2 indent
            process_bullet_list(tokens[i+1:close_idx], indent + 2, output)
            
            i = close_idx + 1
            continue
        
        i += 1
    
    # Output item text if not yet output (no nested list)
    if item_text:
        indent_str = " " * indent
        output.append(f"{indent_str}- {item_text}")


def test_transform():
    """Test the transformation."""
    text = """**Contexte :** Some intro text.

## Réalisations et Contributions :
- Agent Conversationnel E-commerce
- Pipelines RAG Avancés
  - Sous-item 1
  - Sous-item 2

## Tâches :
- Développement Back-end
  - Codage de pipelines
"""
    
    print("=== ORIGINAL ===")
    print(text)
    print()
    print("=== TRANSFORMED ===")
    result = transform_headings_to_bullets(text)
    print(result)
    print()
    
    lines = result.split("\n")
    print("=== STRUCTURE CHECK ===")
    for line in lines:
        if line.startswith("- **"):
            print(f"L0 (heading): {line}")
        elif line.startswith("  - "):
            print(f"L1 (child):   {line}")
        elif line.startswith("    - "):
            print(f"L2 (nested):  {line}")
        elif line.strip():
            print(f"TEXT:         {line}")


if __name__ == "__main__":
    test_transform()
