"""Markdown-to-Jira wiki markup converter.

Converts the agent's Markdown output to Jira wiki markup format.
Jira Cloud uses its own wiki syntax that differs from standard Markdown.

Conversions:
- Headers: `# H1` → `h1. H1`
- Bold: `**text**` → `*text*`
- Italic: `*text*` → `_text_`
- Inline code: `` `code` `` → `{{code}}`
- Strikethrough: `~~text~~` → `-text-`
- Links: `[text](url)` → `[text|url]`
- Code blocks: ``` → {code} / {code:lang}
- Unordered lists: `- item` → `* item`
- Ordered lists: `1. item` → `# item`
- Blockquotes: `> text` → `{quote}text{quote}`
- Horizontal rules: `---` → `----`
"""

from __future__ import annotations

import re


def markdown_to_jira(text: str) -> str:
    """Convert Markdown text to Jira wiki markup.

    Args:
        text: Markdown-formatted string.

    Returns:
        Jira wiki markup string.
    """
    if not text:
        return ""

    # Process code blocks first (before any inline processing)
    text = _convert_code_blocks(text)

    lines = text.split("\n")
    result: list[str] = []
    in_quote = False

    for line in lines:
        # Skip lines inside code blocks (already processed)
        if line.startswith("{code") or line == "{code}":
            if in_quote:
                result.append("{quote}")
                in_quote = False
            result.append(line)
            continue

        # Blockquotes
        if line.startswith("> "):
            if not in_quote:
                result.append("{quote}")
                in_quote = True
            result.append(line[2:])
            continue
        elif in_quote:
            result.append("{quote}")
            in_quote = False

        # Horizontal rules
        if re.match(r"^-{3,}$", line.strip()):
            result.append("----")
            continue

        # Headers
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            level = len(header_match.group(1))
            result.append(f"h{level}. {header_match.group(2)}")
            continue

        # Unordered lists
        list_match = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
        if list_match:
            result.append(f"* {list_match.group(2)}")
            continue

        # Ordered lists
        ol_match = re.match(r"^(\s*)\d+\.\s+(.+)$", line)
        if ol_match:
            result.append(f"# {ol_match.group(2)}")
            continue

        result.append(line)

    # Close any open blockquote
    if in_quote:
        result.append("{quote}")

    # Apply inline formatting to the joined result
    output = "\n".join(result)
    output = _convert_inline_formatting(output)
    return output


def _convert_code_blocks(text: str) -> str:
    """Convert fenced code blocks to Jira {code} blocks."""

    def _replace_code_block(match: re.Match) -> str:
        lang = match.group(1) or ""
        code = match.group(2)
        if lang:
            return f"{{code:{lang}}}\n{code}\n{{code}}"
        return f"{{code}}\n{code}\n{{code}}"

    return re.sub(
        r"```(\w*)\n(.*?)```",
        _replace_code_block,
        text,
        flags=re.DOTALL,
    )


def _convert_inline_formatting(text: str) -> str:
    """Convert inline Markdown formatting to Jira equivalents.

    Order matters: process longer/more-specific patterns first.
    """
    # Protect code blocks from inline processing
    code_blocks: list[str] = []

    def _save_code_block(match: re.Match) -> str:
        code_blocks.append(match.group(0))
        return f"\x00CODE{len(code_blocks) - 1}\x00"

    text = re.sub(
        r"\{code(?::\w+)?\}.*?\{code\}", _save_code_block, text, flags=re.DOTALL
    )

    # Inline code: `code` → {{code}} (must be before bold/italic)
    text = re.sub(r"`([^`]+)`", r"{{\1}}", text)

    # Strikethrough: ~~text~~ → -text-
    text = re.sub(r"~~(.+?)~~", r"-\1-", text)

    # Italic first: *text* → _text_ (single asterisk, not part of **)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)

    # Bold: **text** → *text*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Links: [text](url) → [text|url]
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"[\1|\2]", text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODE{i}\x00", block)

    return text
