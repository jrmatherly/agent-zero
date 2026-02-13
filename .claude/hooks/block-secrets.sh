#!/usr/bin/env bash
# PreToolUse hook: Block edits to secrets and environment files
# Prevents accidental modification of usr/.env, usr/secrets.env, and similar

set -euo pipefail

INPUT=$(cat)

FILE_PATH=$(python3 -c "
import json, sys
data = json.loads(sys.argv[1])
print(data.get('tool_input', {}).get('file_path', ''))
" "$INPUT" 2>/dev/null) || exit 0

# Block edits to secrets/env files in usr/
case "$FILE_PATH" in
    */usr/.env|*/usr/secrets.env)
        echo '{"decision":"block","reason":"This file contains secrets/API keys. Edit it manually outside Claude Code."}'
        exit 2
        ;;
esac

exit 0
