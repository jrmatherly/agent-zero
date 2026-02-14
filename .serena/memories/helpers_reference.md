# Apollos AI - Helpers Reference (103 modules)

## Grouped by Functional Area

### Memory & Knowledge (7)
| Module | Purpose |
|--------|---------|
| `memory.py` | Vector-backed memory system with FAISS |
| `vector_db.py` | FAISS wrapper with LocalFileStore cache |
| `vector_store.py` | Vector store abstraction layer |
| `faiss_wrapper.py` | FAISS index management utilities |
| `memory_consolidation.py` | Memory compression and summarization |
| `knowledge_import.py` | Bulk knowledge base import/indexing |
| `document_query.py` | Query documents using vector similarity |

### LLM Integration (6)
| Module | Purpose |
|--------|---------|
| `call_llm.py` | High-level LLM invocation helpers |
| `tokens.py` | Token counting (tiktoken cl100k_base) with 1.1x buffer |
| `rate_limiter.py` | Sliding window rate limiting per provider/model |
| `providers.py` | Provider configuration registry |
| `browser_use_monkeypatch.py` | Compatibility patches for browser-use |
| `dotenv.py` | .env loading with validation (see `docs/reference/environment-variables.md`) |

### Shell & Execution (5)
| Module | Purpose |
|--------|---------|
| `shell_local.py` | Local shell via TTY session |
| `shell_ssh.py` | Remote SSH via Paramiko |
| `docker.py` | Docker container lifecycle management |
| `tty_session.py` | Terminal emulation (pty-based) |
| `runtime.py` | Runtime utilities (terminal detection, bin lookup, port config) |

### Chat Persistence (3)
| Module | Purpose |
|--------|---------|
| `persist_chat.py` | Chat serialization to `usr/chats/{id}/` |
| `history.py` | Message history with topic-based compression |
| `message_queue.py` | Async message queue for inter-agent communication |

### Browser Automation (3)
| Module | Purpose |
|--------|---------|
| `browser_use.py` | browser-use library wrapper |
| `playwright.py` | Direct Playwright integration |
| `browser.py` | Generic browser interface |

### MCP Integration & Gateway (7)
| Module | Purpose |
|--------|---------|
| `mcp_handler.py` | MCP client (connect to external MCP servers) |
| `mcp_server.py` | MCP server (expose Apollos AI as MCP, FastMCP 3.0 + SSE) + DynamicMcpProxy |
| `mcp_connection_pool.py` | Persistent MCP sessions, async-safe with health checking |
| `mcp_resource_store.py` | Pluggable backend (InMemory), creator+admin+role permissions |
| `mcp_identity.py` | X-Mcp-UserId/UserName/Roles header injection, auth stripping |
| `mcp_container_manager.py` | Docker lifecycle management for MCP server containers |
| `mcp_oauth.py` | OAuth flow support for MCP servers |

### Configuration (6)
| Module | Purpose |
|--------|---------|
| `settings.py` | Global settings (env override via A0_SET_* prefix) |
| `projects.py` | Multi-project management |
| `secrets.py` | Secrets manager with streaming filter |
| `security.py` | Filename sanitization, security helpers |
| `branding.py` | Centralized brand config (BRAND_NAME, BRAND_SLUG, BRAND_URL, BRAND_GITHUB_URL, BRAND_UPDATE_CHECK_URL) |
| `workspace.py` | Workspace path resolution and isolation |

### Skills (3)
| Module | Purpose |
|--------|---------|
| `skills.py` | Skill discovery, loading, YAML metadata parsing |
| `skills_import.py` | Skill import/installation |
| `skills_cli.py` | CLI interface for skills |

### Logging & Monitoring (6)
| Module | Purpose |
|--------|---------|
| `log.py` | Structured logging (types: log/success/warning/error/hint/progress) |
| `state_monitor.py` | State change monitoring |
| `state_monitor_integration.py` | Integration hooks for state monitor |
| `state_snapshot.py` | Snapshot capture for debugging |
| `print_style.py` | Terminal output styling (colors, padding) + structured startup output (`banner`, `phase`, `step`, `ready`) |
| `print_catch.py` | Print output interception |

### WebSocket (3)
| Module | Purpose |
|--------|---------|
| `websocket.py` | WebSocketHandler base class, origin validation |
| `websocket_manager.py` | Event routing, connection tracking, buffering |
| `websocket_namespace_discovery.py` | Auto-discover handlers from folder structure |

### Communication (5)
| Module | Purpose |
|--------|---------|
| `email_client.py` | Email client (IMAP) |
| `notification.py` | Push notification system |
| `rfc.py` / `rfc_exchange.py` / `rfc_files.py` | RFC-based data exchange |

### Search (3)
| Module | Purpose |
|--------|---------|
| `duckduckgo_search.py` | DuckDuckGo search |
| `perplexity_search.py` | Perplexity AI search |
| `searxng.py` | SearXNG meta-search |

### File Utilities (4)
| Module | Purpose |
|--------|---------|
| `files.py` | File I/O, path resolution, placeholder replacement |
| `file_tree.py` | Directory tree visualization |
| `file_browser.py` | File browsing with security |
| `attachment_manager.py` | Attachment handling |

### Data Processing (5)
| Module | Purpose |
|--------|---------|
| `dirty_json.py` | Lenient JSON parsing for LLM outputs |
| `crypto.py` | Encryption/decryption utilities |
| `guids.py` | UUID generation |
| `strings.py` | String manipulation helpers |
| `images.py` | Image processing |

### Infrastructure (12)
| Module | Purpose |
|--------|---------|
| `api.py` | ApiHandler base class |
| `tool.py` | Tool base class |
| `extension.py` | Extension base class + `call_extensions()` |
| `extract_tools.py` | Dynamic class loading from folders |
| `context.py` | ContextVar-based async context data |
| `defer.py` | DeferredTask for async execution |
| `errors.py` | Error types (RepairableException, HandledException) |
| `error_response.py` | Standardized error response formatting |
| `process.py` | Process management |
| `subagents.py` | Agent hierarchy path resolution |
| `localization.py` | Multi-language support |
| `faiss_monkey_patch.py` | FAISS compatibility patch for Python 3.12/ARM |

### Authentication & Multi-User (10)
| Module | Purpose |
|--------|---------|
| `auth.py` | AuthManager — EntraID OIDC SSO + local fallback, PersistentTokenCache, session management |
| `auth_db.py` | SQLAlchemy engine/session factory for auth database (`AUTH_DATABASE_URL`) |
| `auth_bootstrap.py` | First-launch bootstrap: run Alembic migrations, create admin account |
| `user_store.py` | ORM models (User, Org, Team, etc.) + CRUD (upsert_user, verify_password, sync_group_memberships) |
| `vault_crypto.py` | AES-256-GCM encryption/decryption with HKDF-derived keys (`VAULT_MASTER_KEY`) |
| `login.py` | Legacy HMAC-SHA256 authentication (AUTH_LOGIN/AUTH_PASSWORD) |
| `login_protection.py` | Rate limiting and brute-force protection for login |
| `tenant.py` | TenantContext for multi-user data scoping and isolation |
| `rbac.py` | Role-based access control via Casbin (`conf/rbac_model.conf`) |
| `audit.py` | Audit logging for security-relevant actions |

### Other (8)
| Module | Purpose |
|--------|---------|
| `backup.py` | BackupService for data export/import |
| `migration.py` | Data migration between versions |
| `update_check.py` | Version update checking |
| `git.py` | Git info extraction |
| `tunnel_manager.py` | Cloudflare tunnel management |
| `task_scheduler.py` | Cron-based task scheduling |
| `job_loop.py` | Background job execution loop |
| `kokoro_tts.py` | TTS via Kokoro |
| `whisper.py` | STT via Whisper |
| `fasta2a_client.py` / `fasta2a_server.py` | A2A protocol support |
| `wait.py` | Wait/sleep utilities |
