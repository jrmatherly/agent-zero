# Apollos AI - Architecture Deep Dive

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Web UI (webui/)                       │
│  Alpine.js + vanilla JS/HTML/CSS                             │
│  WebSocket (Socket.IO) + REST API                            │
└───────────┬──────────────────┬───────────────────────────────┘
            │ REST (Flask)     │ WebSocket (python-socketio)
┌───────────▼──────────────────▼───────────────────────────────┐
│                    run_ui.py (Entry Point)                    │
│  Flask + uvicorn + Starlette (ASGI) + python-socketio        │
│  Auto-discovers: API handlers, WebSocket handlers            │
│  Mounts: /mcp (MCP Server), /a2a (A2A Server), / (Flask)    │
└───────────┬──────────────────┬───────────────────────────────┘
            │                  │
┌───────────▼──────┐ ┌────────▼────────────────────────────────┐
│ python/api/      │ │ python/websocket_handlers/               │
│ ~75 REST         │ │ Namespace-based: /, /state_sync, etc.    │
│ endpoints        │ │ StateSyncHandler, HelloHandler, etc.     │
└──────────────────┘ └─────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────┐
│                    agent.py (Core Agent)                      │
│  AgentContext: session management, multi-context threading    │
│  Agent: monologue loop, tool execution, LLM interaction      │
│  Extension hooks at every lifecycle stage                     │
└───────────┬──────────┬──────────┬────────────────────────────┘
            │          │          │
┌───────────▼──┐ ┌─────▼─────┐ ┌─▼──────────────────────┐
│ python/tools/│ │ models.py │ │ python/extensions/     │
│ 19 tools     │ │ LiteLLM   │ │ 24 lifecycle hooks     │
│ (auto-disc.) │ │ LangChain │ │ (auto-discovered)      │
└──────────────┘ └───────────┘ └────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────┐
│                   python/helpers/ (89 modules)                │
│  Memory (FAISS) | Shell (local/SSH/Docker) | MCP (client/srv)│
│  Auth (OIDC+local) | Settings | Skills | History | Tokens    │
│  Search | Browser | vault_crypto | user_store | auth_db      │
└──────────────────────────────────────────────────────────────┘
```

## Core Loop (agent.py)

The agent operates in a **monologue loop**:
1. Build system prompt (via extensions)
2. Collect message history (compressed)
3. Call LLM with streaming
4. Parse JSON response → extract tool call
5. Execute tool → get result
6. Append result to history
7. Repeat until `response` tool (break_loop=True) or error

## Key Lifecycle Extension Points

| Event | When | Example Extensions |
|-------|------|-------------------|
| `agent_init` | Agent created | Init plugins |
| `system_prompt` | Building system prompt | Add tools, skills, secrets, projects |
| `message_loop_start` | Before loop iteration | Setup context |
| `before_main_llm_call` | Before LLM call | Modify messages |
| `response_stream` | During streaming | Log, mask secrets |
| `response_stream_chunk` | Each chunk | Mask secrets in stream |
| `reasoning_stream` | During reasoning | Log reasoning |
| `tool_execute_before` | Before tool runs | Validate, log |
| `tool_execute_after` | After tool runs | Log results |
| `message_loop_end` | After loop iteration | Cleanup |
| `monologue_start/end` | Full monologue lifecycle | Timing |
| `hist_add_before` | Before adding to history | Filter |

## Communication Protocol

Agent communicates via **JSON responses**:
```json
{
    "thoughts": ["reasoning step 1", "step 2"],
    "headline": "Short summary",
    "tool_name": "tool_name",
    "tool_args": {"arg1": "val1"}
}
```

## Multi-Agent Hierarchy

- Apollos's superior = human user
- Each agent can spawn subordinates via `call_subordinate` tool
- Subordinates report back to their superior
- Profiles specialize subordinates for specific tasks

## Authentication Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Login Flow                                 │
│  /login (GET) → login.html (dual: SSO + local form)         │
│  /login (POST) → AuthManager.login_local() or legacy HMAC   │
│  /login/entra → MSAL auth-code flow → /auth/callback        │
│  /auth/callback → process_callback() → establish_session()   │
└───────────┬─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│  AuthManager (python/helpers/auth.py)                        │
│  - EntraID OIDC (MSAL ConfidentialClientApplication)         │
│  - PersistentTokenCache (AES-256-GCM encrypted at rest)      │
│  - Local login via user_store (Argon2id password hashing)    │
│  - Session fixation prevention (session.clear on login)      │
│  - Backward compat: legacy AUTH_LOGIN/AUTH_PASSWORD           │
└───────────┬─────────────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────────────┐
│  Auth Database (auth_db.py + user_store.py + Alembic)        │
│  8 tables: users, organizations, teams, memberships, vault   │
│  JIT user provisioning from OIDC claims on first login       │
│  Entra group → team sync (including >200 group overage)      │
└─────────────────────────────────────────────────────────────┘
```
