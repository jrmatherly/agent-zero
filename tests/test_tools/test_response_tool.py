"""Tests for the Response tool (python/tools/response.py)."""

from unittest.mock import MagicMock


def _make_mock_agent():
    """Create a minimal mock Agent for tool instantiation."""
    agent = MagicMock()
    agent.agent_name = "A0"
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock())
    return agent


def _make_loop_data():
    """Create a minimal mock LoopData."""
    ld = MagicMock()
    ld.params_temporary = {}
    return ld


class TestResponseToolExecute:
    """Test ResponseTool.execute() returns correct Response objects."""

    async def test_execute_returns_response_with_text_arg(self):
        """Test that execute() returns a Response with the correct message when 'text' key is used."""
        from python.helpers.tool import Response
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "Hello, world!"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute()

        assert isinstance(result, Response)
        assert result.message == "Hello, world!"
        assert result.break_loop is True

    async def test_execute_returns_response_with_message_arg(self):
        """Test that execute() falls back to 'message' key when 'text' is absent."""
        from python.helpers.tool import Response
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"message": "Fallback message"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute()

        assert isinstance(result, Response)
        assert result.message == "Fallback message"
        assert result.break_loop is True

    async def test_execute_break_loop_is_true(self):
        """Test that the response tool always sets break_loop=True to end the agent loop."""
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "done"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute()

        assert result.break_loop is True


class TestResponseToolEmptyMessage:
    """Test ResponseTool behavior with empty or edge-case messages."""

    async def test_execute_with_empty_text(self):
        """Test that execute() handles an empty 'text' arg gracefully."""
        from python.helpers.tool import Response
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": ""},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute()

        assert isinstance(result, Response)
        assert result.message == ""
        assert result.break_loop is True

    async def test_execute_prefers_text_over_message(self):
        """When both 'text' and 'message' keys are present, 'text' takes priority."""
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "from_text", "message": "from_message"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute()

        assert result.message == "from_text"


class TestResponseToolLifecycleHooks:
    """Test before_execution and after_execution overrides."""

    async def test_before_execution_is_noop(self):
        """ResponseTool.before_execution() should do nothing (overrides base)."""
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "test"},
            message="",
            loop_data=_make_loop_data(),
        )

        # Should not raise and should not call any agent methods
        await tool.before_execution()

    async def test_after_execution_marks_log_finished(self):
        """ResponseTool.after_execution() marks log_item_response as finished when present."""
        from python.helpers.tool import Response
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        loop_data = _make_loop_data()
        mock_log = MagicMock()
        loop_data.params_temporary = {"log_item_response": mock_log}

        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "test"},
            message="",
            loop_data=loop_data,
        )

        response = Response(message="test", break_loop=True)
        await tool.after_execution(response)

        mock_log.update.assert_called_once_with(finished=True)

    async def test_after_execution_no_log_item(self):
        """ResponseTool.after_execution() handles missing log_item_response gracefully."""
        from python.helpers.tool import Response
        from python.tools.response import ResponseTool

        agent = _make_mock_agent()
        loop_data = _make_loop_data()
        loop_data.params_temporary = {}

        tool = ResponseTool(
            agent=agent,
            name="response",
            method=None,
            args={"text": "test"},
            message="",
            loop_data=loop_data,
        )

        response = Response(message="test", break_loop=True)
        # Should not raise
        await tool.after_execution(response)
