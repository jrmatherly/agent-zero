# Code Execution System - Comprehensive Architecture Analysis

## Core Entry Point
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/tools/code_execution_tool.py` (22046 bytes)

### Main Tool Class
- **Class**: `CodeExecution(Tool)` (line 45)
  - Async method: `execute(**kwargs) -> Response` (line 63-100)
  - Supports 5 runtime types: `python`, `nodejs`, `terminal`, `output`, `reset`
  - Handles code execution across multiple sessions with state management

### State Management
- **State Dataclass** (line 40-42):
  ```python
  @dataclass
  class State:
      ssh_enabled: bool
      shells: dict[int, ShellWrap]
  ```
- **ShellWrap Dataclass** (line 32-36):
  ```python
  @dataclass
  class ShellWrap:
      id: int
      session: LocalInteractiveSession | SSHInteractiveSession
      running: bool
  ```
- State stored in agent context via `self.agent.set_data("_cet_state", self.state)` (line 182)
- Retrieved via `self.agent.get_data("_cet_state")` (line 124)

### Timeout Configuration
- **CODE_EXEC_TIMEOUTS** (line 16-21): First output=30s, between=15s, max=180s, dialog=5s
- **OUTPUT_TIMEOUTS** (line 24-29): First output=90s, between=45s, max=300s, dialog=5s

### Key Methods

1. **execute_python_code(session, code, reset)** (line 185-189)
   - Uses `ipython -c {escaped_code}`
   - Calls terminal_session() with python> prefix

2. **execute_nodejs_code(session, code, reset)** (line 191-195)
   - Uses `node /exe/node_eval.js {escaped_code}`
   - Calls terminal_session() with node> prefix

3. **execute_terminal_command(session, command, reset)** (line 197-209)
   - Executes bash or PowerShell based on platform/SSH mode
   - Calls terminal_session() with bash>/PS> prefix

4. **terminal_session(session, command, reset, prefix, timeouts)** (line 211-267)
   - Core execution handler with retry logic (2 attempts on connection loss)
   - Sends command via `self.state.shells[session].session.send_command(command)` (line 234)
   - Returns output via `get_terminal_output()` (line 253)
   - Detects session type (local vs remote) (line 236-248)

5. **get_terminal_output(session, timeouts)** (line 279-419)
   - **Main output collection loop** with complex timeout logic:
     - `first_output_timeout`: Waits for first output
     - `between_output_timeout`: Waits between outputs
     - `dialog_timeout`: Detects user prompts
     - `max_exec_timeout`: Hard cap on total runtime
   - Pattern detection:
     - **Shell prompts** (line 47-54): Detects `(venv)...# $`, `root@container:~#`, PowerShell prompts
     - **Dialog patterns** (line 56-61): Y/N, yes/no, `:`, `?` at end of lines
   - Output cleanup via `fix_full_output()` (line 507-515)
   - Truncates very large outputs (~1MB threshold)

6. **prepare_state(reset, session)** (line 123-183)
   - Initializes LocalInteractiveSession or SSHInteractiveSession
   - Checks SSH enablement via `self.agent.config.code_exec_ssh_enabled` (line 128)
   - Determines CWD via `ensure_cwd()` (line 147)
   - Falls back to create LocalInteractiveSession on development mode (line 174)

### SSH Configuration (from Agent Config)
- **code_exec_ssh_enabled**: Boolean, set based on `shell_interface == "ssh"`
- **code_exec_ssh_addr**: Hostname/IP (default: "localhost" in Docker, custom in non-Docker)
- **code_exec_ssh_port**: Port number (default: 22 in Docker, `rfc_port_ssh` in non-Docker)
- **code_exec_ssh_user**: Username (default: "root")
- **code_exec_ssh_pass**: Password from config (can be `None`)

### Development Mode Behavior
**Lines 163-173**:
```python
if not runtime.is_development():
    raise Exception(
        "Code execution requires SSH sandboxing in production. "
        "Set code_exec_ssh_enabled=true and configure Docker SSH, "
        "or set DEVELOPMENT_MODE=true to run unsandboxed locally."
    )
else:
    PrintStyle.warning(
        "Code execution running UNSANDBOXED on host. "
        "This is allowed in development mode only."
    )
shell = LocalInteractiveSession(cwd=cwd)
```

---

## Shell Session Implementations

### 1. LocalInteractiveSession
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/shell_local.py` (56 lines)

- **Purpose**: Local unsandboxed execution for development
- **Constructor**: `__init__(cwd: str | None = None)` (line 9-12)
  - Uses TTYSession internally
  - Workspace: `self.cwd`
  
- **Key Methods**:
  - `connect()` (line 14-21): Initializes TTYSession with terminal executable
  - `send_command(command: str)` (line 28-32): Resets full_output, sends command
  - `read_output(timeout, reset_full_output)` (line 34-55): Returns (full_output, partial_output) tuple
  - `close()` (line 23-25): Kills session

- **Output Cleaning**: Uses `clean_string()` from shell_ssh (line 50)

### 2. SSHInteractiveSession
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/shell_ssh.py` (271 lines)

- **Purpose**: Remote sandboxed execution via SSH (Docker container)
- **Constructor**: `__init__(logger, hostname, port, username, password, cwd)` (line 31-55)
  - Uses Paramiko for SSH
  - Security: Validates hostname (localhost/private IPs allow AutoAddPolicy; public IPs enforce strict key checking) (line 13-50)
  - Tracks full/partial output as bytes
  
- **Key Methods**:
  - `connect(keepalive_interval)` (line 57-114): 
    - Establishes SSH connection with retry logic (3 attempts, 5s between)
    - Disables systemd prompt metadata: `unset PROMPT_COMMAND PS0; stty -echo` (line 91)
    - Sets keepalive to prevent connection drop
    - Waits for initial prompt
  - `send_command(command: str)` (line 122-132): Appends newline, sends via paramiko shell
  - `read_output(timeout, reset_full_output)` (line 134-189):
    - Polls `shell.recv_ready()` with timeout
    - Handles multi-byte UTF-8 sequences properly (line 208-236)
    - Returns (full_output, partial_output) decoded tuples
  - `receive_bytes(num_bytes)` (line 191-237): Low-level byte reception with UTF-8 handling
  - `close()` (line 116-120): Closes shell and SSH client

- **Output Cleaning**: `clean_string()` (line 240-271)
  - Removes ANSI escape codes
  - Removes null bytes
  - Normalizes line endings (\r\n → \n)
  - Handles carriage returns

---

## TTY Session Layer (POSIX/Windows)
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/tty_session.py` (343 lines)

### TTYSession Class
- **Constructor**: `__init__(cmd, cwd=None, env=None, encoding="utf-8", echo=False)` (line 21-28)
  - Cross-platform (POSIX vs Windows via `pywinpty`)
  - Command can be string or list
  - Echo control for input suppression
  
- **Key Methods**:
  - `start()` (line 42-50): Spawns PTY (POSIX) or WinPTY (Windows)
  - `sendline(line)` (line 76-77): Sends line with newline
  - `read_full_until_idle(idle_timeout, total_timeout)` (line 115-124): Collects all output until idle
  - `read_chunks_until_idle(idle_timeout, total_timeout)` (line 126-137): Async generator for streaming
  - `kill()` (line 84-103): Force-kills process with error handling
  - `close()` (line 53-65): Cancels pump task, terminates process

### POSIX Implementation
**_spawn_posix_pty()** (line 154-206):
- Uses `pty.openpty()` to create pseudo-terminal
- Disables ECHO via `termios` if requested (line 163-166)
- Uses `asyncio.create_subprocess_shell()` (line 168-176)
- Implements non-blocking I/O via loop's `add_reader()` (line 195)

### Windows Implementation
**_spawn_winpty()** (line 212-282):
- Uses `winpty.PtyProcess.spawn()` from pywinpty
- Cleans PowerShell startup flags (line 213-220)
- Handles UTF-8 encoding/decoding (line 237-238)
- Adds `\r\n` for Windows line endings (line 254-255)

---

## Docker Container Management

### DockerContainerManager
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/docker.py` (154 lines)

- **Purpose**: Lifecycle management for Docker containers (used for SSH sandbox)
- **Constructor**: `__init__(image, name, ports=None, volumes=None, logger=None)` (line 11-24)
  - Initializes docker.from_env() client (line 26-51)
  - Retry loop on connection errors (line 28-51)
  
- **Key Methods**:
  - `start_container()` (line 102-153):
    - Checks for existing container by name
    - Starts if stopped; reuses if running
    - Creates new container with `client.containers.run()` if needed (line 139-145)
    - Ports and volumes passed at creation
    - Waits 5s for SSH to be ready (line 153)
  - `cleanup_container()` (line 54-73): Stops and removes container
  - `get_image_containers()` (line 75-100): Lists containers for a given image

### McpContainerManager
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/mcp_container_manager.py` (124 lines)

- **Purpose**: Manages Docker containers for MCP servers (separate from code execution)
- **Container Naming**: Prefix `"apollos-mcp-"` + server name (line 20)
- **Key Methods**:
  - `start_server(resource)` (line 40-78): Creates or reuses container with labels
  - `stop_server(server_name)` (line 80-88): Stops and removes
  - `get_status(server_name)` (line 90-99): Returns running/status info
  - `list_servers()` (line 108-123): Lists all MCP containers with labels

---

## Runtime Configuration

### get_runtime_config() in settings.py
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/settings.py` (lines 951-972)

**Returns dict based on deployment mode**:

**In Dockerized Mode** (lines 952-958):
```python
{
    "code_exec_ssh_enabled": shell_interface == "ssh",
    "code_exec_ssh_addr": "localhost",
    "code_exec_ssh_port": 22,
    "code_exec_ssh_user": "root",
}
```

**In Non-Dockerized Mode** (lines 959-972):
```python
{
    "code_exec_ssh_enabled": shell_interface == "ssh",
    "code_exec_ssh_addr": rfc_url (parsed),
    "code_exec_ssh_port": rfc_port_ssh,
    "code_exec_ssh_user": "root",
}
```

### Runtime Detection
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/runtime.py` (lines 57-62)

```python
def is_dockerized() -> bool:
    return bool(get_arg("dockerized"))

def is_development() -> bool:
    return not is_dockerized()
```

---

## Docker Images

### Base Image
**File**: `/Users/jason/dev/apollos-ai/agent-zero/docker/base/Dockerfile` (52 lines)

- **Base**: `kalilinux/kali-rolling`
- **Locale/TZ**: en_US.UTF-8, UTC
- **Installation Layers**:
  1. `install_base_packages[1-4].sh` - System packages
  2. `install_python.sh` - Python 3.12
  3. `install_searxng.sh` - Search engine
  4. `configure_ssh.sh` - SSH server setup
- **AppUser**: Created at line 48 (uid=1000, bash shell)
- **Exposed Ports**: 22 (SSH), 80 (HTTP), 9000-9009
- **Keep-alive**: `tail -f /dev/null`

### App Image (docker/run/Dockerfile)
**File**: `/Users/jason/dev/apollos-ai/agent-zero/docker/run/Dockerfile` (44 lines)

- **Base**: `ghcr.io/jrmatherly/apollos-ai-base:latest`
- **Requires BRANCH arg** - Specifies branch to clone
- **Installation Steps**:
  1. Copy filesystem files from `./fs/` (scripts, configs)
  2. `pre_install.sh` - Setup
  3. `install_A0.sh` - Clone repo, install Python deps, Playwright, preload models
  4. `post_install.sh` - Cleanup
- **AppUser Permissions**: Owns `/git/apollos-ai`, `/opt/venv-a0`, `/a0`
- **CMD**: Runs `/exe/initialize.sh` (supervisord with appuser/root processes)

### Local Dev Image (DockerfileLocal)
**File**: `/Users/jason/dev/apollos-ai/agent-zero/DockerfileLocal` (52 lines)

- **Base**: Same as app image
- **Optimization**: Layer-cached dependency install (copies `requirements.txt` separately)
- **No BRANCH requirement** - Uses local working tree
- **Source Code**: Copied fresh from `./` (line 30)
- **AppUser Permissions**: Same as app image

---

## Settings Configuration

### Settings TypedDict
**File**: `/Users/jason/dev/apollos-ai/agent-zero/python/helpers/settings.py` (lines 65-172)

Relevant shell/code execution fields:
- `shell_interface`: Literal["local", "ssh"] (line 145)
- `rfc_url`, `rfc_password`, `rfc_port_http`, `rfc_port_ssh` (lines 140-143)
- Derived (via `get_runtime_config()`):
  - `code_exec_ssh_enabled`
  - `code_exec_ssh_addr`
  - `code_exec_ssh_port`
  - `code_exec_ssh_user`
  - `code_exec_ssh_pass`

### Shell Interface Options
**Line 269-271**:
```python
{"value": "local", "label": "Local Python TTY"},
{"value": "ssh", "label": "SSH"},
```

### Default Settings
**get_default_settings()** (lines 651-775):
- `shell_interface`: "local" if dockerized, else "ssh" (line 750-751)
- `rfc_auto_docker`: True (line 745)
- `rfc_url`: "localhost" (line 746)
- `rfc_port_http`: 55080 (line 748)
- `rfc_port_ssh`: 55022 (line 749)

---

## Sandboxing Strategy

### Production (Dockerized)
1. **SSH is primary sandbox mechanism**
2. Code runs in Docker container via SSH connection
3. SSH user: `root` (in container), separate from host
4. Container filesystem isolation
5. Network namespace isolation (if configured)
6. Resource limits via Docker (CPU, memory)

### Development (Local)
1. **No sandboxing** - runs on host
2. LocalInteractiveSession spawns shells directly
3. Warning printed: "Code execution running UNSANDBOXED on host"
4. Exception if SSH disabled in production: "Code execution requires SSH sandboxing in production"

### Error Handling
- Connection retry logic (2 attempts in terminal_session, 3 in SSH connect)
- Output timeout detection with fallback messages
- Dialog detection to prevent interactive prompts hanging
- Shell prompt detection for early termination

---

## File Locations Summary

| Component | File Path |
|-----------|-----------|
| Code Execution Tool | `/python/tools/code_execution_tool.py` |
| Local Shell | `/python/helpers/shell_local.py` |
| SSH Shell | `/python/helpers/shell_ssh.py` |
| TTY Session (POSIX/Windows) | `/python/helpers/tty_session.py` |
| Docker Manager | `/python/helpers/docker.py` |
| MCP Container Manager | `/python/helpers/mcp_container_manager.py` |
| Settings | `/python/helpers/settings.py` |
| Runtime Utils | `/python/helpers/runtime.py` |
| Base Dockerfile | `/docker/base/Dockerfile` |
| App Dockerfile | `/docker/run/Dockerfile` |
| Local Dockerfile | `/DockerfileLocal` |
| Installation Scripts | `/docker/run/fs/ins/` |

---

## Key Insights

1. **Two-tier abstraction**: Tool layer (code_execution_tool) → Session layer (Local/SSH) → Transport layer (TTY/Paramiko)
2. **Production requires SSH**: Enforced at line 164-167 of code_execution_tool.py
3. **Session multiplexing**: Multiple shells supported via session ID (0, 1, 2, ...)
4. **Smart output parsing**: Detects shell prompts and dialogs to prevent timeout false positives
5. **Cross-platform**: POSIX (Linux/Mac) and Windows (PowerShell via WinPTY)
6. **Resource isolation via Docker**: Container provides process, filesystem, and network isolation
7. **Graceful degradation**: Falls back from SSH to local when development mode enabled
