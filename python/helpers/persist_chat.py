import json
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any

from agent import Agent, AgentConfig, AgentContext, AgentContextType
from initialize import initialize_agent
from python.helpers import files, history
from python.helpers.log import Log, LogItem
from python.helpers.tenant import TenantContext

CHATS_FOLDER = "usr/chats"  # legacy fallback
LOG_SIZE = 1000
CHAT_FILE_NAME = "chat.json"


def _get_chats_folder(context: AgentContext) -> str:
    """Resolve chats folder from context's tenant_ctx, falling back to legacy."""
    if context.tenant_ctx and not context.tenant_ctx.is_system:
        return context.tenant_ctx.chats_dir
    return CHATS_FOLDER


def get_chat_folder_path(ctxid: str, context: AgentContext | None = None):
    """
    Get the folder path for any context (chat or task).

    Args:
        ctxid: The context ID
        context: Optional AgentContext for user-scoped resolution

    Returns:
        The absolute path to the context folder
    """
    if context and context.tenant_ctx and not context.tenant_ctx.is_system:
        return files.get_abs_path(context.tenant_ctx.chats_dir, ctxid)
    return files.get_abs_path(CHATS_FOLDER, ctxid)


def get_chat_msg_files_folder(ctxid: str, context: AgentContext | None = None):
    return files.get_abs_path(get_chat_folder_path(ctxid, context), "messages")


def save_tmp_chat(context: AgentContext):
    """Save context to the chats folder (user-scoped when tenant_ctx is present)"""
    # Skip saving BACKGROUND contexts as they should be ephemeral
    if context.type == AgentContextType.BACKGROUND:
        return

    path = _get_chat_file_path(context.id, context)
    files.make_dirs(path)
    data = _serialize_context(context)
    js = _safe_json_serialize(data, ensure_ascii=False)
    files.write_file(path, js)


def save_tmp_chats():
    """Save all contexts to the chats folder"""
    for context in AgentContext.all():
        # Skip BACKGROUND contexts as they should be ephemeral
        if context.type == AgentContextType.BACKGROUND:
            continue
        save_tmp_chat(context)


def load_tmp_chats():
    """Load all contexts from legacy chats folder + user-scoped directories."""
    _convert_v080_chats()

    json_files = []

    # Legacy: usr/chats/{ctxid}/chat.json
    if files.exists(CHATS_FOLDER):
        for folder_name in files.list_files(CHATS_FOLDER, "*"):
            json_files.append(_get_chat_file_path(folder_name))

    # Multi-user: usr/orgs/*/teams/*/members/*/chats/{ctxid}/chat.json
    json_files.extend(_discover_user_chat_files())

    ctxids = []
    seen_files: set[str] = set()
    for file in json_files:
        abs_file = files.get_abs_path(file) if not file.startswith("/") else file
        if abs_file in seen_files:
            continue
        seen_files.add(abs_file)
        try:
            js = files.read_file(abs_file)
            data = json.loads(js)
            ctx = _deserialize_context(data)
            ctxids.append(ctx.id)
        except Exception as e:
            print(f"Error loading chat {file}: {e}")
    return ctxids


def _discover_user_chat_files() -> list[str]:
    """Walk usr/orgs/*/teams/*/members/*/chats/ to find chat.json files."""
    import os

    result = []
    orgs_dir = files.get_abs_path("usr/orgs")
    if not os.path.isdir(orgs_dir):
        return result

    for org in os.listdir(orgs_dir):
        teams_dir = os.path.join(orgs_dir, org, "teams")
        if not os.path.isdir(teams_dir):
            continue
        for team in os.listdir(teams_dir):
            members_dir = os.path.join(teams_dir, team, "members")
            if not os.path.isdir(members_dir):
                continue
            for member in os.listdir(members_dir):
                chats_dir = os.path.join(members_dir, member, "chats")
                if not os.path.isdir(chats_dir):
                    continue
                for ctx_folder in os.listdir(chats_dir):
                    chat_file = os.path.join(chats_dir, ctx_folder, CHAT_FILE_NAME)
                    if os.path.isfile(chat_file):
                        result.append(chat_file)
    return result


def _get_chat_file_path(ctxid: str, context: AgentContext | None = None):
    if context and context.tenant_ctx and not context.tenant_ctx.is_system:
        return files.get_abs_path(context.tenant_ctx.chats_dir, ctxid, CHAT_FILE_NAME)
    return files.get_abs_path(CHATS_FOLDER, ctxid, CHAT_FILE_NAME)


def _convert_v080_chats():
    json_files = files.list_files(CHATS_FOLDER, "*.json")
    for file in json_files:
        path = files.get_abs_path(CHATS_FOLDER, file)
        name = file.rstrip(".json")
        new = _get_chat_file_path(name)
        files.move_file(path, new)


def load_json_chats(
    jsons: list[str],
    user_id: str | None = None,
    tenant_ctx: "TenantContext | None" = None,
):
    """Load contexts from JSON strings, optionally assigning to importing user."""
    ctxids = []
    for js in jsons:
        data = json.loads(js)
        if "id" in data:
            del data["id"]  # remove id to get new
        # Override user_id so imported chats belong to the importing user
        if user_id is not None:
            data["user_id"] = user_id
        ctx = _deserialize_context(data)
        if tenant_ctx is not None:
            ctx.tenant_ctx = tenant_ctx
        ctxids.append(ctx.id)
        save_tmp_chat(ctx)
    return ctxids


def export_json_chat(context: AgentContext):
    """Export context as JSON string"""
    data = _serialize_context(context)
    js = _safe_json_serialize(data, ensure_ascii=False)
    return js


def remove_chat(ctxid, context: AgentContext | None = None):
    """Remove a chat or task context"""
    path = get_chat_folder_path(ctxid, context)
    files.delete_dir(path)


def remove_msg_files(ctxid, context: AgentContext | None = None):
    """Remove all message files for a chat or task context"""
    path = get_chat_msg_files_folder(ctxid, context)
    files.delete_dir(path)


def _serialize_context(context: AgentContext):
    # serialize agents
    agents = []
    agent = context.apollos
    while agent:
        agents.append(_serialize_agent(agent))
        agent = agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)

    data = {k: v for k, v in context.data.items() if not k.startswith("_")}
    output_data = {
        k: v for k, v in context.output_data.items() if not k.startswith("_")
    }

    return {
        "id": context.id,
        "name": context.name,
        "user_id": context.user_id,
        "created_at": (
            context.created_at.isoformat()
            if context.created_at
            else datetime.fromtimestamp(0).isoformat()
        ),
        "type": context.type.value,
        "last_message": (
            context.last_message.isoformat()
            if context.last_message
            else datetime.fromtimestamp(0).isoformat()
        ),
        "agents": agents,
        "streaming_agent": (
            context.streaming_agent.number if context.streaming_agent else 0
        ),
        "log": _serialize_log(context.log),
        "data": data,
        "output_data": output_data,
    }


def _serialize_agent(agent: Agent):
    data = {k: v for k, v in agent.data.items() if not k.startswith("_")}

    history = agent.history.serialize()

    return {
        "number": agent.number,
        "data": data,
        "history": history,
    }


def _serialize_log(log: Log):
    # Guard against concurrent log mutations while serializing.
    with log._lock:
        logs = [
            item.output() for item in log.logs[-LOG_SIZE:]
        ]  # serialize LogItem objects
        guid = log.guid
        progress = log.progress
        progress_no = log.progress_no
    return {
        "guid": guid,
        "logs": logs,
        "progress": progress,
        "progress_no": progress_no,
    }


def _deserialize_context(data):
    config = initialize_agent()
    log = _deserialize_log(data.get("log", None))

    # Restore user_id and reconstruct TenantContext
    user_id = data.get("user_id", None)
    tenant_ctx = None
    if user_id:
        tenant_ctx = TenantContext(user_id=user_id)
    else:
        tenant_ctx = TenantContext.system()

    context = AgentContext(
        config=config,
        id=data.get("id", None),  # get new id
        name=data.get("name", None),
        created_at=(
            datetime.fromisoformat(
                # older chats may not have created_at - backcompat
                data.get("created_at", datetime.fromtimestamp(0).isoformat())
            )
        ),
        type=AgentContextType(data.get("type", AgentContextType.USER.value)),
        last_message=(
            datetime.fromisoformat(
                data.get("last_message", datetime.fromtimestamp(0).isoformat())
            )
        ),
        log=log,
        paused=False,
        data=data.get("data", {}),
        output_data=data.get("output_data", {}),
        user_id=user_id,
        tenant_ctx=tenant_ctx,
    )

    agents = data.get("agents", [])
    apollos = _deserialize_agents(agents, config, context)
    streaming_agent = apollos
    while streaming_agent and streaming_agent.number != data.get("streaming_agent", 0):
        streaming_agent = streaming_agent.data.get(Agent.DATA_NAME_SUBORDINATE, None)

    context.apollos = apollos
    context.streaming_agent = streaming_agent

    return context


def _deserialize_agents(
    agents: list[dict[str, Any]], config: AgentConfig, context: AgentContext
) -> Agent:
    prev: Agent | None = None
    zero: Agent | None = None

    for ag in agents:
        current = Agent(
            number=ag["number"],
            config=config,
            context=context,
        )
        current.data = ag.get("data", {})
        current.history = history.deserialize_history(
            ag.get("history", ""), agent=current
        )
        if not zero:
            zero = current

        if prev:
            prev.set_data(Agent.DATA_NAME_SUBORDINATE, current)
            current.set_data(Agent.DATA_NAME_SUPERIOR, prev)
        prev = current

    return zero or Agent(0, config, context)


# def _deserialize_history(history: list[dict[str, Any]]):
#     result = []
#     for hist in history:
#         content = hist.get("content", "")
#         msg = (
#             HumanMessage(content=content)
#             if hist.get("type") == "human"
#             else AIMessage(content=content)
#         )
#         result.append(msg)
#     return result


def _deserialize_log(data: dict[str, Any]) -> "Log":
    log = Log()
    log.guid = data.get("guid", str(uuid.uuid4()))
    log.set_initial_progress()

    # Deserialize the list of LogItem objects
    i = 0
    for item_data in data.get("logs", []):
        agentno = item_data.get("agentno")
        if agentno is None:
            agentno = item_data.get("agent_number", 0)
        log.logs.append(
            LogItem(
                log=log,  # restore the log reference
                no=i,  # item_data["no"],
                type=item_data["type"],
                heading=item_data.get("heading", ""),
                content=item_data.get("content", ""),
                kvps=OrderedDict(item_data["kvps"]) if item_data["kvps"] else None,
                timestamp=item_data.get("timestamp", 0.0),
                agentno=agentno,
                id=item_data.get("id"),
            )
        )
        log.updates.append(i)
        i += 1

    return log


class _SafeEncoder(json.JSONEncoder):
    """Single-pass JSON encoder that converts non-serializable objects to str."""

    def default(self, o):
        try:
            return str(o)
        except Exception:
            return None


def _safe_json_serialize(obj, **kwargs):
    return json.dumps(obj, cls=_SafeEncoder, **kwargs)
