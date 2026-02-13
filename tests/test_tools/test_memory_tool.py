"""Tests for memory tools (memory_save, memory_load, memory_delete, memory_forget)."""

from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.documents import Document


def _make_mock_agent():
    """Create a minimal mock Agent for tool instantiation."""
    agent = MagicMock()
    agent.agent_name = "A0"
    agent.context = MagicMock()
    agent.context.log = MagicMock()
    agent.context.log.log = MagicMock(return_value=MagicMock())
    agent.read_prompt = MagicMock(return_value="prompt_result")
    return agent


def _make_loop_data():
    """Create a minimal mock LoopData."""
    ld = MagicMock()
    ld.params_temporary = {}
    return ld


def _make_mock_memory_db():
    """Create a mock Memory instance with async methods."""
    db = MagicMock()
    db.insert_text = AsyncMock(return_value="mem-id-123")
    db.search_similarity_threshold = AsyncMock(return_value=[])
    db.delete_documents_by_ids = AsyncMock(return_value=[])
    db.delete_documents_by_query = AsyncMock(return_value=[])
    return db


class TestMemorySave:
    """Test MemorySave tool."""

    @patch("python.tools.memory_save.Memory")
    async def test_save_stores_data_correctly(self, mock_memory_cls):
        """Test that memory_save calls insert_text with the provided text and metadata."""
        from python.helpers.tool import Response
        from python.tools.memory_save import MemorySave

        mock_db = _make_mock_memory_db()
        mock_memory_cls.get = AsyncMock(return_value=mock_db)
        mock_memory_cls.Area.MAIN.value = "main"

        agent = _make_mock_agent()
        tool = MemorySave(
            agent=agent,
            name="memory_save",
            method=None,
            args={"text": "important fact", "area": "main"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(text="important fact", area="main")

        assert isinstance(result, Response)
        assert result.break_loop is False
        mock_memory_cls.get.assert_awaited_once_with(agent)
        mock_db.insert_text.assert_awaited_once_with("important fact", {"area": "main"})
        agent.read_prompt.assert_called_once_with(
            "fw.memory_saved.md", memory_id="mem-id-123"
        )

    @patch("python.tools.memory_save.Memory")
    async def test_save_defaults_to_main_area(self, mock_memory_cls):
        """Test that when no area is provided, it defaults to the MAIN area."""
        from python.tools.memory_save import MemorySave

        mock_db = _make_mock_memory_db()
        mock_memory_cls.get = AsyncMock(return_value=mock_db)
        mock_memory_cls.Area.MAIN.value = "main"

        agent = _make_mock_agent()
        tool = MemorySave(
            agent=agent,
            name="memory_save",
            method=None,
            args={"text": "data"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(text="data", area="")

        # When area is empty, it should default to "main"
        call_args = mock_db.insert_text.call_args
        assert call_args[0][1]["area"] == "main"

    @patch("python.tools.memory_save.Memory")
    async def test_save_with_empty_text(self, mock_memory_cls):
        """Test that memory_save handles empty text without error."""
        from python.helpers.tool import Response
        from python.tools.memory_save import MemorySave

        mock_db = _make_mock_memory_db()
        mock_memory_cls.get = AsyncMock(return_value=mock_db)
        mock_memory_cls.Area.MAIN.value = "main"

        agent = _make_mock_agent()
        tool = MemorySave(
            agent=agent,
            name="memory_save",
            method=None,
            args={"text": ""},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(text="", area="")

        assert isinstance(result, Response)
        assert result.break_loop is False
        mock_db.insert_text.assert_awaited_once()

    @patch("python.tools.memory_save.Memory")
    async def test_save_passes_extra_kwargs_as_metadata(self, mock_memory_cls):
        """Test that extra kwargs are included in the metadata dict."""
        from python.tools.memory_save import MemorySave

        mock_db = _make_mock_memory_db()
        mock_memory_cls.get = AsyncMock(return_value=mock_db)
        mock_memory_cls.Area.MAIN.value = "main"

        agent = _make_mock_agent()
        tool = MemorySave(
            agent=agent,
            name="memory_save",
            method=None,
            args={"text": "data", "area": "solutions", "custom_key": "custom_val"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(text="data", area="solutions", custom_key="custom_val")

        call_args = mock_db.insert_text.call_args
        metadata = call_args[0][1]
        assert metadata["area"] == "solutions"
        assert metadata["custom_key"] == "custom_val"


class TestMemoryLoad:
    """Test MemoryLoad tool."""

    @patch("python.tools.memory_load.Memory")
    async def test_load_returns_formatted_results(self, mock_memory_cls):
        """Test that memory_load returns formatted documents when results are found."""
        from python.helpers.tool import Response
        from python.tools.memory_load import MemoryLoad

        docs = [
            Document(
                page_content="fact one",
                metadata={"id": "1", "area": "main"},
            ),
            Document(
                page_content="fact two",
                metadata={"id": "2", "area": "main"},
            ),
        ]
        mock_db = _make_mock_memory_db()
        mock_db.search_similarity_threshold = AsyncMock(return_value=docs)
        mock_memory_cls.get = AsyncMock(return_value=mock_db)
        mock_memory_cls.format_docs_plain = MagicMock(
            return_value=["id: 1\nContent: fact one", "id: 2\nContent: fact two"]
        )

        agent = _make_mock_agent()
        tool = MemoryLoad(
            agent=agent,
            name="memory_load",
            method=None,
            args={"query": "facts"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(query="facts")

        assert isinstance(result, Response)
        assert result.break_loop is False
        assert "fact one" in result.message
        assert "fact two" in result.message
        mock_db.search_similarity_threshold.assert_awaited_once()

    @patch("python.tools.memory_load.Memory")
    async def test_load_no_results_returns_not_found(self, mock_memory_cls):
        """Test that memory_load returns a not-found prompt when no documents match."""
        from python.helpers.tool import Response
        from python.tools.memory_load import MemoryLoad

        mock_db = _make_mock_memory_db()
        mock_db.search_similarity_threshold = AsyncMock(return_value=[])
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        agent.read_prompt = MagicMock(return_value="No memories found for: test query")
        tool = MemoryLoad(
            agent=agent,
            name="memory_load",
            method=None,
            args={"query": "test query"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(query="test query")

        assert isinstance(result, Response)
        assert result.break_loop is False
        assert result.message == "No memories found for: test query"
        agent.read_prompt.assert_called_once_with(
            "fw.memories_not_found.md", query="test query"
        )

    @patch("python.tools.memory_load.Memory")
    async def test_load_with_empty_query(self, mock_memory_cls):
        """Test that memory_load handles an empty query string."""
        from python.helpers.tool import Response
        from python.tools.memory_load import MemoryLoad

        mock_db = _make_mock_memory_db()
        mock_db.search_similarity_threshold = AsyncMock(return_value=[])
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        tool = MemoryLoad(
            agent=agent,
            name="memory_load",
            method=None,
            args={"query": ""},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(query="")

        assert isinstance(result, Response)
        assert result.break_loop is False
        # search should still be called even with empty query
        mock_db.search_similarity_threshold.assert_awaited_once()

    @patch("python.tools.memory_load.Memory")
    async def test_load_passes_threshold_and_limit(self, mock_memory_cls):
        """Test that custom threshold and limit values are forwarded to the DB search."""
        from python.tools.memory_load import MemoryLoad

        mock_db = _make_mock_memory_db()
        mock_db.search_similarity_threshold = AsyncMock(return_value=[])
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        tool = MemoryLoad(
            agent=agent,
            name="memory_load",
            method=None,
            args={"query": "search term"},
            message="",
            loop_data=_make_loop_data(),
        )

        await tool.execute(
            query="search term", threshold=0.8, limit=5, filter="area == 'main'"
        )

        mock_db.search_similarity_threshold.assert_awaited_once_with(
            query="search term",
            limit=5,
            threshold=0.8,
            filter="area == 'main'",
        )


class TestMemoryDelete:
    """Test MemoryDelete tool."""

    @patch("python.tools.memory_delete.Memory")
    async def test_delete_by_ids(self, mock_memory_cls):
        """Test that memory_delete correctly parses comma-separated IDs and deletes them."""
        from python.helpers.tool import Response
        from python.tools.memory_delete import MemoryDelete

        deleted_docs = [
            Document(page_content="old", metadata={"id": "id1"}),
            Document(page_content="old2", metadata={"id": "id2"}),
        ]
        mock_db = _make_mock_memory_db()
        mock_db.delete_documents_by_ids = AsyncMock(return_value=deleted_docs)
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        agent.read_prompt = MagicMock(return_value="Deleted 2 memories.")
        tool = MemoryDelete(
            agent=agent,
            name="memory_delete",
            method=None,
            args={"ids": "id1, id2"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(ids="id1, id2")

        assert isinstance(result, Response)
        assert result.break_loop is False
        mock_db.delete_documents_by_ids.assert_awaited_once_with(ids=["id1", "id2"])
        agent.read_prompt.assert_called_once_with(
            "fw.memories_deleted.md", memory_count=2
        )

    @patch("python.tools.memory_delete.Memory")
    async def test_delete_with_empty_ids(self, mock_memory_cls):
        """Test that memory_delete handles an empty ids string (deletes nothing)."""
        from python.helpers.tool import Response
        from python.tools.memory_delete import MemoryDelete

        mock_db = _make_mock_memory_db()
        mock_db.delete_documents_by_ids = AsyncMock(return_value=[])
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        tool = MemoryDelete(
            agent=agent,
            name="memory_delete",
            method=None,
            args={"ids": ""},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(ids="")

        assert isinstance(result, Response)
        assert result.break_loop is False
        mock_db.delete_documents_by_ids.assert_awaited_once_with(ids=[])


class TestMemoryForget:
    """Test MemoryForget tool (delete by query)."""

    @patch("python.tools.memory_forget.Memory")
    async def test_forget_by_query(self, mock_memory_cls):
        """Test that memory_forget delegates to delete_documents_by_query."""
        from python.helpers.tool import Response
        from python.tools.memory_forget import MemoryForget

        deleted_docs = [Document(page_content="forgotten", metadata={"id": "x1"})]
        mock_db = _make_mock_memory_db()
        mock_db.delete_documents_by_query = AsyncMock(return_value=deleted_docs)
        mock_memory_cls.get = AsyncMock(return_value=mock_db)

        agent = _make_mock_agent()
        agent.read_prompt = MagicMock(return_value="Deleted 1 memories.")
        tool = MemoryForget(
            agent=agent,
            name="memory_forget",
            method=None,
            args={"query": "old stuff"},
            message="",
            loop_data=_make_loop_data(),
        )

        result = await tool.execute(query="old stuff")

        assert isinstance(result, Response)
        assert result.break_loop is False
        mock_db.delete_documents_by_query.assert_awaited_once()
        agent.read_prompt.assert_called_once_with(
            "fw.memories_deleted.md", memory_count=1
        )
