---
name: new-extension
description: Scaffold a new extension for apollos-ai. Creates the extension Python file in the correct python/extensions/<point>/ directory with proper filename prefix and Extension base class boilerplate.
argument-hint: "<extension_point>/<prefix>_<name>"
---

# New Extension — Scaffold an apollos-ai extension

Create a new extension based on `$ARGUMENTS`.

## Argument Parsing

`$ARGUMENTS` should be in the format `<extension_point>/<prefix>_<name>` (e.g., `agent_init/_15_my_setup`, `tool_execute_before/_30_log_calls`).

If only a name is given without an extension point, ask the user which extension point to use (show the list below).

## Validation

### Valid Extension Points

These are the 24 valid extension point directories under `python/extensions/`:

- `agent_init` — Agent initialization
- `banners` — UI banner generation
- `before_main_llm_call` — Before the main LLM call
- `error_format` — Error message formatting
- `hist_add_before` — Before adding to chat history
- `hist_add_tool_result` — Adding tool results to history
- `message_loop_end` — End of message processing loop
- `message_loop_prompts_after` — After prompts in message loop
- `message_loop_prompts_before` — Before prompts in message loop
- `message_loop_start` — Start of message processing loop
- `monologue_end` — End of agent monologue
- `monologue_start` — Start of agent monologue
- `process_chain_end` — End of processing chain
- `reasoning_stream` — Reasoning stream data received
- `reasoning_stream_chunk` — Each reasoning stream chunk
- `reasoning_stream_end` — Reasoning stream completes
- `response_stream` — Response stream data received
- `response_stream_chunk` — Each response stream chunk
- `response_stream_end` — Response stream completes
- `system_prompt` — System prompt processing
- `tool_execute_after` — After tool execution
- `tool_execute_before` — Before tool execution
- `user_message_ui` — User message from UI
- `util_model_call_before` — Before utility model calls

Verify the extension point is valid. If not, show the list and ask the user to choose.

### Filename Convention

- Files MUST start with a numeric prefix like `_10_`, `_20_`, `_30_` etc.
- This prefix determines execution order (lower = earlier).
- Check existing files in the target directory to choose an appropriate prefix:
  ```bash
  ls python/extensions/<extension_point>/
  ```
- If the user didn't provide a prefix, suggest one based on existing files.

### Conflict Check

Verify `python/extensions/<extension_point>/<filename>.py` does not already exist.

## Step 1: Create the extension file

Create `python/extensions/<extension_point>/<prefix>_<name>.py`:

```python
from python.helpers.extension import Extension


class ClassName(Extension):
    """TODO: Describe what this extension does."""

    async def execute(self, **kwargs):
        # TODO: Implement extension logic
        # Access the agent via self.agent
        # Access kwargs relevant to this extension point
        pass
```

Where `ClassName` is the PascalCase version of `<name>` (without the numeric prefix).

**Important conventions:**
- Import `Extension` from `python.helpers.extension`
- The class extends `Extension`
- The main method is `async execute(self, **kwargs)`
- Access the agent instance via `self.agent`
- The `kwargs` vary by extension point — check existing extensions in the same directory for the expected signature
- Return value depends on the extension point (some expect modifications, others are fire-and-forget)

## Step 2: Check existing extensions for kwargs

Read one existing extension in the same directory to show the user what `kwargs` are available:

```bash
# Show an existing extension for reference
head -30 python/extensions/<extension_point>/_*.py | head -40
```

## Step 3: Scaffold a test file

Create `tests/test_<name>.py`:

```python
"""Tests for the <name> extension."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestClassName:
    """Tests for the ClassName extension."""

    @pytest.mark.asyncio
    async def test_execute_runs(self):
        from python.extensions.<extension_point>.<prefix>_<name> import ClassName

        ext = ClassName(agent=MagicMock())
        await ext.execute()
```

## Reminders

After creating the files, remind the user:

1. **Auto-discovery**: Extensions are auto-discovered. Drop the file in the directory and it's active.
2. **Execution order**: The numeric prefix (`_10_`, `_20_`) determines execution order within the extension point. Lower numbers run first.
3. **Override path**: To override for a specific agent profile, place the same filename in `agents/<profile>/extensions/<point>/`. For user overrides, use `usr/extensions/<point>/`.
4. **Full search path** (highest priority first):
   - `usr/projects/{project}/.a0proj/agents/{profile}/extensions/{point}/`
   - `usr/projects/{project}/.a0proj/extensions/{point}/`
   - `usr/agents/{profile}/extensions/{point}/`
   - `agents/{profile}/extensions/{point}/`
   - `usr/extensions/{point}/`
   - `python/extensions/{point}/` (framework default)
5. **Test**: Run with `mise run t -- tests/test_<name>.py -v`.
