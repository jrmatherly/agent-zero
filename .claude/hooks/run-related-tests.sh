#!/usr/bin/env bash
# PostToolUse hook: Auto-run related test file after editing Python source files
# Maps python/{area}/{name}.py → tests/test_{name}.py and runs it if it exists

set -euo pipefail

INPUT=$(cat)

FILE_PATH=$(python3 -c "
import json, sys
data = json.loads(sys.argv[1])
print(data.get('tool_input', {}).get('file_path', ''))
" "$INPUT" 2>/dev/null) || exit 0

# Only process Python files (skip tests themselves, prompts, configs)
if [[ "$FILE_PATH" != *.py ]]; then
    exit 0
fi

# Skip if the file IS a test file
if [[ "$FILE_PATH" == */tests/* || "$FILE_PATH" == */test_* ]]; then
    exit 0
fi

# Extract the base module name from the file path
BASENAME=$(basename "$FILE_PATH" .py)

# Find the project root (traverse up to find pyproject.toml)
DIR=$(dirname "$FILE_PATH")
PROJECT_ROOT=""
while [[ "$DIR" != "/" ]]; do
    if [[ -f "$DIR/pyproject.toml" ]]; then
        PROJECT_ROOT="$DIR"
        break
    fi
    DIR=$(dirname "$DIR")
done

if [[ -z "$PROJECT_ROOT" ]]; then
    exit 0
fi

TEST_FILE="$PROJECT_ROOT/tests/test_${BASENAME}.py"

if [[ -f "$TEST_FILE" ]]; then
    cd "$PROJECT_ROOT"
    # Run quietly: only show failures, stop on first failure
    uv run pytest "$TEST_FILE" -x -q 2>&1 | tail -5 || true
fi

exit 0
