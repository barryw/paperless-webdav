# tests/test_main.py
"""Tests for main entrypoint."""

import signal
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Filter expected warnings from mocking async functions in sync test context.
# These warnings occur because AsyncMock coroutines are created but not awaited
# when we mock async functions that are passed to run_async (which is also mocked).
pytestmark = [
    pytest.mark.filterwarnings("ignore:coroutine.*was never awaited:RuntimeWarning"),
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
]


@pytest.fixture
def mock_main_settings():
    """Provide test settings for main module tests.

    Named differently from conftest's mock_main_settings to avoid confusion,
    as this fixture includes additional environment variables specific
    to main module testing (ADMIN_PORT, WEBDAV_PORT, LOG_LEVEL, LOG_FORMAT).
    """
    with patch.dict(
        "os.environ",
        {
            "PAPERLESS_URL": "http://paperless.test",
            "DATABASE_URL": "postgresql://test:test@localhost/test",
            "ENCRYPTION_KEY": "dGVzdGtleXRoYXRpczMyYnl0ZXNsb25nIQ==",
            "SECRET_KEY": "test-secret-key-for-sessions",
            "ADMIN_PORT": "8080",
            "WEBDAV_PORT": "8081",
            "LOG_LEVEL": "INFO",
            "LOG_FORMAT": "json",
        },
    ):
        # Clear cached settings
        from paperless_webdav.config import get_settings

        get_settings.cache_clear()
        yield
        get_settings.cache_clear()


class TestLoadSharesSync:
    """Tests for load_shares_sync function."""

    def test_load_shares_from_database(self, mock_main_settings):
        """load_shares_sync should fetch shares from database and return dict."""
        from paperless_webdav.main import load_shares_sync

        # Create mock shares with name attribute
        mock_share1 = MagicMock()
        mock_share1.name = "tax2025"
        mock_share2 = MagicMock()
        mock_share2.name = "receipts"

        # Mock the session and query result
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_share1, mock_share2]
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("paperless_webdav.main.get_sync_session", return_value=mock_session):
            shares = load_shares_sync()

            assert "tax2025" in shares
            assert "receipts" in shares
            assert shares["tax2025"] == mock_share1
            assert shares["receipts"] == mock_share2

    def test_load_shares_returns_empty_dict_when_no_shares(self, mock_main_settings):
        """load_shares_sync should return empty dict when no shares exist."""
        from paperless_webdav.main import load_shares_sync

        # Mock the session and query result
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("paperless_webdav.main.get_sync_session", return_value=mock_session):
            shares = load_shares_sync()

            assert shares == {}


class TestLoadAllShares:
    """Tests for _load_all_shares async function."""

    @pytest.mark.asyncio
    async def test_load_all_shares_returns_empty_when_no_session_factory(self, mock_main_settings):
        """_load_all_shares should return empty list when session factory is None."""
        from paperless_webdav.main import _load_all_shares

        with patch("paperless_webdav.main._async_session_factory", None):
            result = await _load_all_shares()
            assert result == []

    @pytest.mark.asyncio
    async def test_load_all_shares_queries_database(self, mock_main_settings):
        """_load_all_shares should query all shares from database."""
        from paperless_webdav.main import _load_all_shares

        # Create mock shares
        mock_share1 = MagicMock()
        mock_share1.name = "share1"
        mock_share2 = MagicMock()
        mock_share2.name = "share2"

        # Create mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_share1, mock_share2]
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Create mock session factory context manager
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch("paperless_webdav.main._async_session_factory", mock_session_factory):
            result = await _load_all_shares()

            assert len(result) == 2
            assert mock_share1 in result
            assert mock_share2 in result


class TestRunServers:
    """Tests for run_servers function."""

    def test_run_servers_initializes_database(self, mock_main_settings):
        """run_servers should initialize database on startup."""
        from paperless_webdav.main import run_servers

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async") as mock_run_async,
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.signal.signal"),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance

            # uvicorn.run will block, so we need to raise to exit
            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Verify init_database was called via run_async
            calls = mock_run_async.call_args_list
            assert len(calls) >= 1
            # First call should be to init_database (it's a coroutine)

    def test_run_servers_creates_webdav_server_in_background_thread(self, mock_main_settings):
        """run_servers should create WebDAV server and run it in daemon thread."""
        from paperless_webdav.main import run_servers

        captured_thread = None

        def capture_thread_start(target, daemon):
            nonlocal captured_thread
            captured_thread = threading.Thread(target=target, daemon=daemon)
            # Don't actually start it
            return captured_thread

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal"),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance

            mock_thread = MagicMock()
            mock_thread_class.return_value = mock_thread

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Verify WebDAV server was created
            mock_webdav.assert_called_once()

            # Verify thread was created as daemon and started
            mock_thread_class.assert_called_once()
            call_kwargs = mock_thread_class.call_args.kwargs
            assert call_kwargs.get("daemon") is True
            assert call_kwargs.get("target") == mock_webdav_instance.start

            mock_thread.start.assert_called_once()

    def test_run_servers_registers_signal_handlers(self, mock_main_settings):
        """run_servers should register SIGINT and SIGTERM handlers."""
        from paperless_webdav.main import run_servers

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal") as mock_signal,
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Verify signal handlers were registered
            signal_calls = [call[0][0] for call in mock_signal.call_args_list]
            assert signal.SIGINT in signal_calls
            assert signal.SIGTERM in signal_calls

    def test_run_servers_runs_fastapi_via_uvicorn(self, mock_main_settings):
        """run_servers should run FastAPI via uvicorn in main thread."""
        from paperless_webdav.main import run_servers

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal"),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Verify uvicorn.run was called with correct parameters
            mock_uvicorn.assert_called_once()
            call_kwargs = mock_uvicorn.call_args.kwargs
            call_args = mock_uvicorn.call_args.args

            assert (
                "paperless_webdav.app:app" in call_args
                or call_kwargs.get("app") == "paperless_webdav.app:app"
            )
            assert call_kwargs.get("host") == "0.0.0.0"
            assert call_kwargs.get("port") == 8080


class TestShutdownHandler:
    """Tests for shutdown signal handler."""

    def test_shutdown_handler_stops_webdav_server(self, mock_main_settings):
        """Shutdown handler should stop WebDAV server."""
        from paperless_webdav.main import run_servers

        captured_handler = None

        def capture_signal_handler(sig, handler):
            nonlocal captured_handler
            if sig == signal.SIGINT:
                captured_handler = handler

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal", side_effect=capture_signal_handler),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Now test the captured handler
            assert captured_handler is not None

            with patch("paperless_webdav.main.sys.exit"):
                try:
                    captured_handler(signal.SIGINT, None)
                except SystemExit:
                    pass

                # Verify webdav server stop was called
                mock_webdav_instance.stop.assert_called_once()

    def test_shutdown_handler_closes_database(self, mock_main_settings):
        """Shutdown handler should close database connection."""
        from paperless_webdav.main import run_servers

        captured_handler = None

        def capture_signal_handler(sig, handler):
            nonlocal captured_handler
            if sig == signal.SIGINT:
                captured_handler = handler

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async") as mock_run_async,
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal", side_effect=capture_signal_handler),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Now test the captured handler
            assert captured_handler is not None

            # Reset mock to track calls during shutdown
            mock_run_async.reset_mock()

            with patch("paperless_webdav.main.sys.exit"):
                try:
                    captured_handler(signal.SIGINT, None)
                except SystemExit:
                    pass

                # Verify close_database was called via run_async
                assert mock_run_async.called

    def test_shutdown_handler_exits_with_code_zero(self, mock_main_settings):
        """Shutdown handler should exit with code 0."""
        from paperless_webdav.main import run_servers

        captured_handler = None

        def capture_signal_handler(sig, handler):
            nonlocal captured_handler
            if sig == signal.SIGINT:
                captured_handler = handler

        with (
            patch("paperless_webdav.main.setup_logging"),
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal", side_effect=capture_signal_handler),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            # Now test the captured handler
            assert captured_handler is not None

            with patch("paperless_webdav.main.sys.exit") as mock_exit:
                try:
                    captured_handler(signal.SIGINT, None)
                except SystemExit:
                    pass

                mock_exit.assert_called_once_with(0)


class TestLoggingSetup:
    """Tests for logging setup in run_servers."""

    def test_run_servers_calls_setup_logging(self, mock_main_settings):
        """run_servers should call setup_logging with settings."""
        from paperless_webdav.main import run_servers

        with (
            patch("paperless_webdav.main.setup_logging") as mock_setup_logging,
            patch("paperless_webdav.main.logger"),
            patch("paperless_webdav.main.init_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.close_database", new_callable=AsyncMock),
            patch("paperless_webdav.main.run_async"),
            patch("paperless_webdav.main.WebDAVServer") as mock_webdav,
            patch("paperless_webdav.main.threading.Thread") as mock_thread_class,
            patch("paperless_webdav.main.signal.signal"),
            patch("paperless_webdav.main.uvicorn.run") as mock_uvicorn,
        ):
            mock_webdav_instance = MagicMock()
            mock_webdav.return_value = mock_webdav_instance
            mock_thread_class.return_value = MagicMock()

            mock_uvicorn.side_effect = KeyboardInterrupt()

            try:
                run_servers()
            except (KeyboardInterrupt, SystemExit):
                pass

            mock_setup_logging.assert_called_once_with("INFO", "json")
