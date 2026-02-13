"""Tests for the call_subordinate / Delegation tool (python/tools/call_subordinate.py)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from python.helpers.tool import Response


def _make_mock_agent(number=0):
    """Create a minimal mock Agent for tool instantiation."""
    agent = MagicMock()
    agent.number = number
    agent.agent_name = f"A{number}"
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock())
    agent.data = {}
    agent.read_prompt = MagicMock(return_value="")

    # Implement get_data / set_data with the real dict
    agent.get_data = MagicMock(side_effect=lambda key: agent.data.get(key, None))
    agent.set_data = MagicMock(
        side_effect=lambda key, value: agent.data.__setitem__(key, value)
    )

    return agent


def _make_mock_subordinate():
    """Create a mock subordinate Agent."""
    sub = MagicMock()
    sub.number = 1
    sub.agent_name = "A1"
    sub.hist_add_user_message = AsyncMock()
    sub.monologue = AsyncMock(return_value="subordinate response")
    sub.history = MagicMock()
    sub.history.new_topic = MagicMock()
    sub.set_data = MagicMock()
    return sub


def _make_loop_data():
    """Create a minimal mock LoopData."""
    ld = MagicMock()
    ld.params_temporary = {}
    return ld


class TestDelegationCreation:
    """Test subordinate agent creation and initialization."""

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_creates_subordinate_when_none_exists(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that a new subordinate is created when none exists on the agent."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500

        mock_config = MagicMock()
        mock_config.profile = "default"
        mock_init_agent.return_value = mock_config

        sub = _make_mock_subordinate()
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "do something"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(message="do something")

        assert isinstance(result, Response)
        assert result.message == "subordinate response"
        assert result.break_loop is False
        # Subordinate should have been created
        mock_init_agent.assert_called_once()
        mock_agent_cls.assert_called_once()
        # Subordinate should receive the user message
        sub.hist_add_user_message.assert_awaited_once()
        # Subordinate's monologue should run
        sub.monologue.assert_awaited_once()

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_reuses_existing_subordinate(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that an existing subordinate is reused when one is already set."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        existing_sub = _make_mock_subordinate()
        agent = _make_mock_agent(number=0)
        # Pre-set the subordinate so it already exists
        agent.data["_subordinate"] = existing_sub

        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "follow up"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(message="follow up")

        assert result.message == "subordinate response"
        # initialize_agent should NOT be called since subordinate already exists
        mock_init_agent.assert_not_called()
        # The existing sub should receive the message
        existing_sub.hist_add_user_message.assert_awaited_once()
        existing_sub.monologue.assert_awaited_once()

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_reset_creates_new_subordinate(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that passing reset='true' creates a fresh subordinate even if one exists."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_config.profile = "default"
        mock_init_agent.return_value = mock_config

        new_sub = _make_mock_subordinate()
        mock_agent_cls.return_value = new_sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        old_sub = _make_mock_subordinate()
        agent = _make_mock_agent(number=0)
        agent.data["_subordinate"] = old_sub

        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "restart task", "reset": "true"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(message="restart task", reset="true")

        assert result.message == "subordinate response"
        # A new agent should have been constructed
        mock_init_agent.assert_called_once()
        mock_agent_cls.assert_called_once()
        # The NEW sub should run (not the old one)
        new_sub.monologue.assert_awaited_once()
        old_sub.monologue.assert_not_awaited()


class TestDelegationMessagePassing:
    """Test message passing to subordinate."""

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_message_forwarded_to_subordinate(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that the message kwarg is passed to the subordinate's hist_add_user_message."""
        from agent import UserMessage
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_init_agent.return_value = mock_config

        sub = _make_mock_subordinate()
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "solve this math problem: 2+2"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(message="solve this math problem: 2+2")

        sub.hist_add_user_message.assert_awaited_once()
        call_args = sub.hist_add_user_message.call_args
        user_msg = call_args[0][0]
        assert isinstance(user_msg, UserMessage)
        assert user_msg.message == "solve this math problem: 2+2"

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_subordinate_topic_sealed_after_monologue(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that new_topic() is called on the subordinate's history after monologue."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_init_agent.return_value = mock_config

        sub = _make_mock_subordinate()
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "task"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(message="task")

        sub.history.new_topic.assert_called_once()


class TestDelegationErrorHandling:
    """Test error handling in the Delegation tool."""

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_monologue_exception_propagates(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that an exception from subordinate.monologue() propagates up."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_init_agent.return_value = mock_config

        sub = _make_mock_subordinate()
        sub.monologue = AsyncMock(side_effect=RuntimeError("LLM failed"))
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "broken task"},
            message="",
            loop_data=_make_loop_data(),
        )

        with pytest.raises(RuntimeError, match="LLM failed"):
            await tool.execute(message="broken task")

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_long_response_includes_hint(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that a long monologue result triggers the hint in additional."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_init_agent.return_value = mock_config

        long_response = "x" * 600  # > LEN_MIN of 500
        sub = _make_mock_subordinate()
        sub.monologue = AsyncMock(return_value=long_response)
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        agent.read_prompt = MagicMock(
            return_value="Use file includes for long responses."
        )
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "big task"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(message="big task")

        assert result.message == long_response
        assert result.additional is not None
        assert "hint" in result.additional
        agent.read_prompt.assert_called_with("fw.hint.call_sub.md")

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_short_response_no_hint(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that a short monologue result does NOT include a hint."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_init_agent.return_value = mock_config

        short_response = "done"
        sub = _make_mock_subordinate()
        sub.monologue = AsyncMock(return_value=short_response)
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "small task"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(message="small task")

        assert result.message == short_response
        assert result.additional is None

    @patch("python.tools.call_subordinate.save_tool_call_file")
    @patch("python.tools.call_subordinate.initialize_agent")
    @patch("python.tools.call_subordinate.Agent")
    async def test_custom_profile_passed_to_config(
        self, mock_agent_cls, mock_init_agent, mock_save_tool
    ):
        """Test that a custom agent_profile kwarg sets the config profile."""
        from python.tools.call_subordinate import Delegation

        mock_save_tool.LEN_MIN = 500
        mock_config = MagicMock()
        mock_config.profile = "default"
        mock_init_agent.return_value = mock_config

        sub = _make_mock_subordinate()
        mock_agent_cls.return_value = sub
        mock_agent_cls.DATA_NAME_SUBORDINATE = "_subordinate"
        mock_agent_cls.DATA_NAME_SUPERIOR = "_superior"

        agent = _make_mock_agent(number=0)
        tool = Delegation(
            agent=agent,
            name="call_subordinate",
            method=None,
            args={"message": "research", "agent_profile": "researcher"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(message="research", profile="researcher")

        assert mock_config.profile == "researcher"
