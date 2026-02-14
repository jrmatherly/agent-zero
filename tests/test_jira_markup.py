# tests/test_jira_markup.py
"""Tests for Markdown-to-Jira wiki markup converter."""


class TestJiraMarkupImport:
    def test_module_importable(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert callable(markdown_to_jira)


class TestJiraMarkupHeaders:
    def test_h1(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("# Heading 1") == "h1. Heading 1"

    def test_h2(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("## Heading 2") == "h2. Heading 2"

    def test_h3(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("### Heading 3") == "h3. Heading 3"

    def test_h6(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("###### Heading 6") == "h6. Heading 6"


class TestJiraMarkupInlineFormatting:
    def test_bold(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("**bold text**") == "*bold text*"

    def test_italic(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("*italic text*") == "_italic text_"

    def test_inline_code(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("`some code`") == "{{some code}}"

    def test_strikethrough(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("~~deleted~~") == "-deleted-"


class TestJiraMarkupLinks:
    def test_link(self):
        from python.helpers.jira_markup import markdown_to_jira

        result = markdown_to_jira("[Click here](https://example.com)")
        assert result == "[Click here|https://example.com]"

    def test_link_in_text(self):
        from python.helpers.jira_markup import markdown_to_jira

        result = markdown_to_jira("See [docs](https://docs.example.com) for info")
        assert "[docs|https://docs.example.com]" in result


class TestJiraMarkupCodeBlocks:
    def test_fenced_code_block(self):
        from python.helpers.jira_markup import markdown_to_jira

        md = "```\nprint('hello')\n```"
        result = markdown_to_jira(md)
        assert "{code}" in result
        assert "print('hello')" in result

    def test_fenced_code_block_with_language(self):
        from python.helpers.jira_markup import markdown_to_jira

        md = "```python\ndef foo():\n    pass\n```"
        result = markdown_to_jira(md)
        assert "{code:python}" in result
        assert "def foo():" in result


class TestJiraMarkupLists:
    def test_unordered_list(self):
        from python.helpers.jira_markup import markdown_to_jira

        md = "- item 1\n- item 2\n- item 3"
        result = markdown_to_jira(md)
        assert "* item 1" in result
        assert "* item 2" in result

    def test_ordered_list(self):
        from python.helpers.jira_markup import markdown_to_jira

        md = "1. first\n2. second\n3. third"
        result = markdown_to_jira(md)
        assert "# first" in result
        assert "# second" in result


class TestJiraMarkupBlockquotes:
    def test_blockquote(self):
        from python.helpers.jira_markup import markdown_to_jira

        result = markdown_to_jira("> This is a quote")
        assert "{quote}" in result
        assert "This is a quote" in result


class TestJiraMarkupHorizontalRule:
    def test_horizontal_rule(self):
        from python.helpers.jira_markup import markdown_to_jira

        result = markdown_to_jira("---")
        assert "----" in result


class TestJiraMarkupMultiline:
    def test_mixed_content(self):
        from python.helpers.jira_markup import markdown_to_jira

        md = """# Summary

The issue is caused by **incorrect configuration**.

## Steps

1. Check the `config.yaml` file
2. Update the setting
3. Restart the service

```python
config = load_config()
```

> Note: This is important.

See [the docs](https://example.com) for details."""

        result = markdown_to_jira(md)
        assert "h1. Summary" in result
        assert "*incorrect configuration*" in result
        assert "h2. Steps" in result
        assert "# Check the" in result
        assert "{{config.yaml}}" in result
        assert "{code:python}" in result
        assert "{quote}" in result
        assert "[the docs|https://example.com]" in result

    def test_empty_input(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("") == ""

    def test_plain_text_unchanged(self):
        from python.helpers.jira_markup import markdown_to_jira

        assert markdown_to_jira("Just plain text") == "Just plain text"
