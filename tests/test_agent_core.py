"""Tests for core Agent, AgentContext, and AgentConfig classes.

Covers context creation/ID uniqueness, thread-safe counter, eviction,
serialization (output), config defaults, and monologue loop behavior.
"""

import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent import (
    Agent,
    AgentConfig,
    AgentContext,
    HandledException,
    LoopData,
)
from models import ModelConfig, ModelType
from python.helpers.tool import Response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_config(**overrides) -> ModelConfig:
    """Create a minimal ModelConfig for testing."""
    defaults = dict(
        type=ModelType.CHAT,
        provider="test",
        name="test-model",
    )
    defaults.update(overrides)
    return ModelConfig(**defaults)


def _make_agent_config(**overrides) -> AgentConfig:
    """Create a minimal AgentConfig with mock model configs."""
    mc = _make_model_config()
    defaults = dict(
        chat_model=mc,
        utility_model=mc,
        embeddings_model=mc,
        browser_model=mc,
        mcp_servers="",
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


@pytest.fixture(autouse=True)
def _clean_contexts():
    """Ensure AgentContext class-level state is clean before and after each test."""
    with AgentContext._contexts_lock:
        AgentContext._contexts.clear()
        AgentContext._context_timestamps.clear()
    yield
    with AgentContext._contexts_lock:
        AgentContext._contexts.clear()
        AgentContext._context_timestamps.clear()


@pytest.fixture
def agent_config():
    return _make_agent_config()


def _make_context(config=None, **kwargs):
    """Create an AgentContext while mocking Agent.__init__ to avoid heavy side effects."""
    cfg = config or _make_agent_config()
    with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
        ctx = AgentContext(config=cfg, **kwargs)
        # AgentContext.__init__ calls Agent(0, config, self) which we patched,
        # so ctx.apollos is an Agent with no attributes. Provide a minimal mock.
        ctx.apollos = MagicMock(spec=Agent)
    return ctx


# ---------------------------------------------------------------------------
# 1. AgentContext creation and ID uniqueness
# ---------------------------------------------------------------------------


class TestAgentContextCreation:
    def test_contexts_get_unique_ids(self):
        """Multiple contexts created sequentially have unique IDs."""
        contexts = [_make_context() for _ in range(20)]
        ids = [c.id for c in contexts]
        assert len(ids) == len(set(ids)), "Context IDs must be unique"

    def test_context_registered_in_class_dict(self):
        """A newly created context is stored in AgentContext._contexts."""
        ctx = _make_context()
        assert AgentContext.get(ctx.id) is ctx

    def test_context_id_can_be_specified(self):
        """When id is passed explicitly it is used."""
        ctx = _make_context(id="my-custom-id")
        assert ctx.id == "my-custom-id"
        assert AgentContext.get("my-custom-id") is ctx


# ---------------------------------------------------------------------------
# 2. AgentContext counter thread safety
# ---------------------------------------------------------------------------


class TestAgentContextCounterThreadSafety:
    def test_concurrent_counter_increments_produce_unique_values(self):
        """Concurrent AgentContext creations produce unique .no values."""
        num_threads = 50  # 50 threads is sufficient; keeps CI runners stable
        results: list[int] = []
        errors: list[Exception] = []
        barrier = threading.Barrier(num_threads)

        def create_context(idx):
            try:
                barrier.wait(timeout=10)
                ctx = _make_context(id=f"thread-{idx}")
                results.append(ctx.no)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=create_context, args=(i,))
            for i in range(num_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Threads raised errors: {errors}"
        assert len(results) == num_threads
        assert len(set(results)) == num_threads, "All .no values must be unique"


# ---------------------------------------------------------------------------
# 3. AgentContext eviction
# ---------------------------------------------------------------------------


class TestAgentContextEviction:
    def test_stale_contexts_are_evicted(self):
        """Contexts with timestamps older than CONTEXT_TTL are evicted when new ones are created."""
        # Create a context and artificially age its timestamp
        ctx_old = _make_context(id="old-ctx")
        with AgentContext._contexts_lock:
            # Set timestamp to well beyond TTL
            AgentContext._context_timestamps["old-ctx"] = (
                time.monotonic() - AgentContext.CONTEXT_TTL - 100
            )

        # Mark it as not running so it can be evicted
        ctx_old.task = None

        # Creating a new context triggers eviction
        _make_context(id="new-ctx")

        assert AgentContext.get("old-ctx") is None, (
            "Stale context should have been evicted"
        )
        assert AgentContext.get("new-ctx") is not None

    def test_running_contexts_are_not_evicted(self):
        """Contexts that are 'running' (task.is_alive()) are not evicted even if stale."""
        ctx_running = _make_context(id="running-ctx")
        mock_task = MagicMock()
        mock_task.is_alive.return_value = True
        ctx_running.task = mock_task

        with AgentContext._contexts_lock:
            AgentContext._context_timestamps["running-ctx"] = (
                time.monotonic() - AgentContext.CONTEXT_TTL - 100
            )

        # Trigger eviction
        _make_context(id="trigger-ctx")

        assert AgentContext.get("running-ctx") is not None, (
            "Running context must not be evicted"
        )

    def test_max_contexts_eviction(self):
        """When MAX_CONTEXTS is exceeded, oldest non-running contexts are evicted."""
        original_max = AgentContext.MAX_CONTEXTS
        try:
            AgentContext.MAX_CONTEXTS = 5
            # Create 5 contexts
            for i in range(5):
                ctx = _make_context(id=f"ctx-{i}")
                ctx.task = None
                with AgentContext._contexts_lock:
                    # Stagger timestamps so oldest are evicted first
                    AgentContext._context_timestamps[f"ctx-{i}"] = time.monotonic() - (
                        5 - i
                    )

            # Creating one more should trigger overflow eviction
            _make_context(id="overflow-ctx")

            with AgentContext._contexts_lock:
                remaining = len(AgentContext._contexts)
            # Should be at most MAX_CONTEXTS (some older ones evicted)
            assert (
                remaining <= AgentContext.MAX_CONTEXTS + 1
            )  # +1 for the new one triggering eviction
        finally:
            AgentContext.MAX_CONTEXTS = original_max


# ---------------------------------------------------------------------------
# 4. AgentContext serialization (output method)
# ---------------------------------------------------------------------------


class TestAgentContextOutput:
    def test_output_contains_required_keys(self):
        """output() returns a dict with expected keys."""
        ctx = _make_context(id="out-test", name="test-context")
        result = ctx.output()
        required_keys = {
            "id",
            "name",
            "user_id",
            "created_at",
            "no",
            "log_guid",
            "log_version",
            "log_length",
            "paused",
            "last_message",
            "type",
            "running",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_output_values_match_context(self):
        """output() values correspond to context attributes."""
        ctx = _make_context(id="val-test", name="my-ctx")
        ctx.paused = True
        result = ctx.output()
        assert result["id"] == "val-test"
        assert result["name"] == "my-ctx"
        assert result["paused"] is True
        assert result["type"] == "user"
        assert result["running"] is False


# ---------------------------------------------------------------------------
# 5. AgentConfig defaults
# ---------------------------------------------------------------------------


class TestAgentConfigDefaults:
    def test_default_values(self):
        """AgentConfig fields have expected defaults."""
        cfg = _make_agent_config()
        assert cfg.profile == ""
        assert cfg.memory_subdir == ""
        assert cfg.knowledge_subdirs == ["default", "custom"]
        assert cfg.code_exec_ssh_enabled is True
        assert cfg.code_exec_ssh_addr == "localhost"
        assert cfg.code_exec_ssh_port == 55022
        assert cfg.code_exec_ssh_user == "root"
        assert cfg.code_exec_ssh_pass == ""
        assert cfg.additional == {}
        assert cfg.browser_http_headers == {}

    def test_config_overrides(self):
        """Explicit values override defaults."""
        cfg = _make_agent_config(profile="custom-profile", memory_subdir="sub")
        assert cfg.profile == "custom-profile"
        assert cfg.memory_subdir == "sub"


# ---------------------------------------------------------------------------
# 6. Agent.monologue() terminates on response tool
# ---------------------------------------------------------------------------


class TestMonologueResponseTermination:
    @pytest.mark.asyncio
    async def test_monologue_returns_on_response_tool(self):
        """When the LLM returns a response tool call, monologue terminates and returns the message."""
        cfg = _make_agent_config()

        # Build a mock context with minimal plumbing
        with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
            agent = Agent.__new__(Agent)

        # Wire up agent internals manually
        agent.config = cfg
        agent.number = 0
        agent.agent_name = "A0"
        agent.intervention = None
        agent.data = {}

        mock_ctx = MagicMock()
        mock_ctx.paused = False
        mock_ctx.task = MagicMock()
        mock_ctx.task.is_alive.return_value = True
        mock_ctx.streaming_agent = None
        mock_ctx.log = MagicMock()
        agent.context = mock_ctx

        # Provide a minimal history
        mock_history = MagicMock()
        mock_history.output.return_value = []
        mock_history.add_message.return_value = MagicMock()
        mock_history.new_topic = MagicMock()
        agent.history = mock_history
        agent.last_user_message = None

        # The LLM response is a JSON tool call for "response"
        llm_response = (
            '{"tool_name": "response", "tool_args": {"text": "Hello, world!"}}'
        )

        # Mock call_extensions to be a no-op
        agent.call_extensions = AsyncMock(return_value=None)

        # Mock prepare_prompt to return empty list
        agent.prepare_prompt = AsyncMock(return_value=[])

        # Mock call_chat_model to return the response tool JSON
        agent.call_chat_model = AsyncMock(return_value=(llm_response, ""))

        # Mock hist_add_ai_response
        agent.hist_add_ai_response = AsyncMock()

        # Mock handle_intervention to do nothing
        agent.handle_intervention = AsyncMock()

        # Mock read_prompt for repeat detection
        agent.read_prompt = MagicMock(return_value="")

        # Mock get_tool to return a mock tool that returns a break_loop Response
        mock_tool = MagicMock()
        mock_tool.name = "response"
        mock_tool.progress = ""
        mock_tool.before_execution = AsyncMock()
        mock_tool.execute = AsyncMock(
            return_value=Response(message="Hello, world!", break_loop=True)
        )
        mock_tool.after_execution = AsyncMock()
        agent.get_tool = MagicMock(return_value=mock_tool)

        result = await agent.monologue()
        assert result == "Hello, world!"


# ---------------------------------------------------------------------------
# 7. Agent.monologue() handles tool dispatch
# ---------------------------------------------------------------------------


class TestMonologueToolDispatch:
    @pytest.mark.asyncio
    async def test_tool_is_dispatched_and_result_incorporated(self):
        """When LLM returns a non-response tool, it is executed and the loop continues
        until the response tool is called."""
        cfg = _make_agent_config()

        with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
            agent = Agent.__new__(Agent)

        agent.config = cfg
        agent.number = 0
        agent.agent_name = "A0"
        agent.intervention = None
        agent.data = {}

        mock_ctx = MagicMock()
        mock_ctx.paused = False
        mock_ctx.task = MagicMock()
        mock_ctx.task.is_alive.return_value = True
        mock_ctx.streaming_agent = None
        mock_ctx.log = MagicMock()
        agent.context = mock_ctx

        mock_history = MagicMock()
        mock_history.output.return_value = []
        mock_history.add_message.return_value = MagicMock()
        mock_history.new_topic = MagicMock()
        agent.history = mock_history
        agent.last_user_message = None

        # First call: LLM requests a "knowledge_tool", second call: LLM requests "response"
        call_count = 0

        async def fake_call_chat_model(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (
                    '{"tool_name": "knowledge_tool", "tool_args": {"query": "test"}}',
                    "",
                )
            return ('{"tool_name": "response", "tool_args": {"text": "Done"}}', "")

        agent.call_extensions = AsyncMock(return_value=None)
        agent.prepare_prompt = AsyncMock(return_value=[])
        agent.call_chat_model = AsyncMock(side_effect=fake_call_chat_model)
        agent.hist_add_ai_response = AsyncMock()
        agent.handle_intervention = AsyncMock()
        agent.read_prompt = MagicMock(return_value="")

        # Track tools that were dispatched
        dispatched_tools = []

        def fake_get_tool(name, method, args, message, loop_data, **kw):
            dispatched_tools.append(name)
            mock_tool = MagicMock()
            mock_tool.name = name
            mock_tool.progress = ""
            mock_tool.before_execution = AsyncMock()
            mock_tool.after_execution = AsyncMock()
            if name == "response":
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="Done", break_loop=True)
                )
            else:
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="tool result", break_loop=False)
                )
            return mock_tool

        agent.get_tool = MagicMock(side_effect=fake_get_tool)

        result = await agent.monologue()
        assert result == "Done"
        assert "knowledge_tool" in dispatched_tools
        assert "response" in dispatched_tools
        assert call_count == 2


# ---------------------------------------------------------------------------
# 8. Agent.monologue() handles intervention (paused/killed)
# ---------------------------------------------------------------------------


class TestMonologueIntervention:
    @pytest.mark.asyncio
    async def test_killed_context_stops_monologue(self):
        """When the context task is killed (HandledException), monologue raises."""
        cfg = _make_agent_config()

        with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
            agent = Agent.__new__(Agent)

        agent.config = cfg
        agent.number = 0
        agent.agent_name = "A0"
        agent.intervention = None
        agent.data = {}

        mock_ctx = MagicMock()
        mock_ctx.paused = False
        mock_ctx.task = MagicMock()
        mock_ctx.task.is_alive.return_value = True
        mock_ctx.streaming_agent = None
        mock_ctx.log = MagicMock()
        agent.context = mock_ctx

        mock_history = MagicMock()
        mock_history.output.return_value = []
        mock_history.add_message.return_value = MagicMock()
        agent.history = mock_history
        agent.last_user_message = None

        agent.call_extensions = AsyncMock(return_value=None)

        # Simulate the LLM call raising a fatal error that exhausts retries
        agent.prepare_prompt = AsyncMock(side_effect=HandledException("killed"))
        agent.handle_intervention = AsyncMock()
        agent.read_prompt = MagicMock(return_value="")

        with pytest.raises(HandledException):
            await agent.monologue()


# ---------------------------------------------------------------------------
# 9. Agent.monologue() iteration counting
# ---------------------------------------------------------------------------


class TestMonologueIterationCounting:
    @pytest.mark.asyncio
    async def test_loop_data_iteration_increments(self):
        """Each iteration through the inner loop increments loop_data.iteration."""
        cfg = _make_agent_config()

        with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
            agent = Agent.__new__(Agent)

        agent.config = cfg
        agent.number = 0
        agent.agent_name = "A0"
        agent.intervention = None
        agent.data = {}

        mock_ctx = MagicMock()
        mock_ctx.paused = False
        mock_ctx.task = MagicMock()
        mock_ctx.task.is_alive.return_value = True
        mock_ctx.streaming_agent = None
        mock_ctx.log = MagicMock()
        agent.context = mock_ctx

        mock_history = MagicMock()
        mock_history.output.return_value = []
        mock_history.add_message.return_value = MagicMock()
        agent.history = mock_history
        agent.last_user_message = None

        iterations_seen = []
        call_count = 0

        async def tracking_call_chat_model(**kwargs):
            nonlocal call_count
            call_count += 1
            iterations_seen.append(agent.loop_data.iteration)
            if call_count >= 3:
                return ('{"tool_name": "response", "tool_args": {"text": "done"}}', "")
            return ('{"tool_name": "code_execution", "tool_args": {"code": "x=1"}}', "")

        agent.call_extensions = AsyncMock(return_value=None)
        agent.prepare_prompt = AsyncMock(return_value=[])
        agent.call_chat_model = AsyncMock(side_effect=tracking_call_chat_model)
        agent.hist_add_ai_response = AsyncMock()
        agent.handle_intervention = AsyncMock()
        agent.read_prompt = MagicMock(return_value="")

        def fake_get_tool(name, method, args, message, loop_data, **kw):
            mock_tool = MagicMock()
            mock_tool.name = name
            mock_tool.progress = ""
            mock_tool.before_execution = AsyncMock()
            mock_tool.after_execution = AsyncMock()
            if name == "response":
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="done", break_loop=True)
                )
            else:
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="ok", break_loop=False)
                )
            return mock_tool

        agent.get_tool = MagicMock(side_effect=fake_get_tool)

        await agent.monologue()

        assert iterations_seen == [0, 1, 2], (
            f"Expected [0, 1, 2] but got {iterations_seen}"
        )


# ---------------------------------------------------------------------------
# 10. Agent message history accumulation
# ---------------------------------------------------------------------------


class TestAgentMessageHistory:
    @pytest.mark.asyncio
    async def test_ai_responses_are_added_to_history(self):
        """Each LLM response is passed to hist_add_ai_response during the monologue."""
        cfg = _make_agent_config()

        with patch.object(Agent, "__init__", lambda self, *a, **kw: None):
            agent = Agent.__new__(Agent)

        agent.config = cfg
        agent.number = 0
        agent.agent_name = "A0"
        agent.intervention = None
        agent.data = {}

        mock_ctx = MagicMock()
        mock_ctx.paused = False
        mock_ctx.task = MagicMock()
        mock_ctx.task.is_alive.return_value = True
        mock_ctx.streaming_agent = None
        mock_ctx.log = MagicMock()
        agent.context = mock_ctx

        mock_history = MagicMock()
        mock_history.output.return_value = []
        mock_history.add_message.return_value = MagicMock()
        agent.history = mock_history
        agent.last_user_message = None

        ai_responses_recorded = []

        async def tracking_hist_add(message):
            ai_responses_recorded.append(message)

        call_count = 0

        async def fake_call_chat_model(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return (
                    '{"tool_name": "memory_save", "tool_args": {"key": "a", "value": "b"}}',
                    "",
                )
            return ('{"tool_name": "response", "tool_args": {"text": "final"}}', "")

        agent.call_extensions = AsyncMock(return_value=None)
        agent.prepare_prompt = AsyncMock(return_value=[])
        agent.call_chat_model = AsyncMock(side_effect=fake_call_chat_model)
        agent.hist_add_ai_response = AsyncMock(side_effect=tracking_hist_add)
        agent.handle_intervention = AsyncMock()
        agent.read_prompt = MagicMock(return_value="")

        def fake_get_tool(name, method, args, message, loop_data, **kw):
            mock_tool = MagicMock()
            mock_tool.name = name
            mock_tool.progress = ""
            mock_tool.before_execution = AsyncMock()
            mock_tool.after_execution = AsyncMock()
            if name == "response":
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="final", break_loop=True)
                )
            else:
                mock_tool.execute = AsyncMock(
                    return_value=Response(message="saved", break_loop=False)
                )
            return mock_tool

        agent.get_tool = MagicMock(side_effect=fake_get_tool)

        await agent.monologue()

        # Both LLM responses should have been recorded
        assert len(ai_responses_recorded) == 2
        assert "memory_save" in ai_responses_recorded[0]
        assert "response" in ai_responses_recorded[1]


# ---------------------------------------------------------------------------
# 11. LoopData initialization
# ---------------------------------------------------------------------------


class TestLoopData:
    def test_default_values(self):
        """LoopData initializes with expected defaults."""
        ld = LoopData()
        assert ld.iteration == -1
        assert ld.system == []
        assert ld.user_message is None
        assert ld.history_output == []
        assert ld.last_response == ""
        assert ld.current_tool is None
        assert ld.params_temporary == {}
        assert ld.params_persistent == {}

    def test_kwargs_override(self):
        """LoopData accepts kwargs that override defaults."""
        ld = LoopData(iteration=5, last_response="hello")
        assert ld.iteration == 5
        assert ld.last_response == "hello"


# ---------------------------------------------------------------------------
# 12. AgentContext.remove
# ---------------------------------------------------------------------------


class TestAgentContextRemove:
    def test_remove_deletes_context(self):
        """AgentContext.remove() removes the context from the class dict."""
        ctx = _make_context(id="rm-test")
        assert AgentContext.get("rm-test") is ctx
        removed = AgentContext.remove("rm-test")
        assert removed is ctx
        assert AgentContext.get("rm-test") is None

    def test_remove_nonexistent_returns_none(self):
        """Removing a non-existent context returns None."""
        result = AgentContext.remove("does-not-exist")
        assert result is None
