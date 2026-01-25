# tests/test_webdav_server.py
"""Tests for WebDAV server setup."""

from unittest.mock import MagicMock, patch

from paperless_webdav.webdav_auth import PaperlessBasicAuthenticator
from paperless_webdav.webdav_server import create_webdav_app, WebDAVServer


class TestCreateWebdavApp:
    """Tests for create_webdav_app factory function."""

    def test_returns_wsgi_callable(self, mock_settings):
        """create_webdav_app should return a WSGI-callable application."""
        with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
            with patch("paperless_webdav.webdav_server.PaperlessProvider"):
                with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_wsgi:
                    mock_wsgi.return_value = MagicMock()
                    app = create_webdav_app(
                        paperless_url="http://paperless.test",
                        share_loader=lambda: {},
                    )

        # WSGI apps are callable (our mock is callable)
        assert callable(app)

    def test_creates_paperless_provider(self, mock_settings):
        """Should create a PaperlessProvider with paperless_url."""
        with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
            with patch("paperless_webdav.webdav_server.PaperlessProvider") as mock_provider:
                with patch("paperless_webdav.webdav_server.WsgiDAVApp"):
                    create_webdav_app(
                        paperless_url="http://paperless.test",
                        share_loader=lambda: {},
                    )

                    mock_provider.assert_called_once()
                    call_kwargs = mock_provider.call_args[1]
                    assert call_kwargs["paperless_url"] == "http://paperless.test"

    def test_creates_basic_authenticator(self, mock_settings):
        """Should create a PaperlessBasicAuthenticator subclass with paperless_url."""
        with patch("paperless_webdav.webdav_server.PaperlessProvider"):
            with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_app:
                create_webdav_app(
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                # Check the config passed to WsgiDAVApp
                config = mock_app.call_args[0][0]
                auth_class = config["http_authenticator"]["domain_controller"]

                # Should be a subclass of PaperlessBasicAuthenticator
                assert issubclass(auth_class, PaperlessBasicAuthenticator)

                # When instantiated, should pass correct params to parent
                instance = auth_class(None, {})
                assert instance._paperless_url == "http://paperless.test"
                assert instance._auth_mode == "paperless"
                assert instance._encryption_key is None

    def test_creates_authenticator_with_oidc_mode(self, mock_settings):
        """Should pass auth_mode and encryption_key to authenticator for OIDC."""
        with patch("paperless_webdav.webdav_server.PaperlessProvider"):
            with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_app:
                create_webdav_app(
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                    auth_mode="oidc",
                    encryption_key="test-encryption-key",
                )

                # Check the config passed to WsgiDAVApp
                config = mock_app.call_args[0][0]
                auth_class = config["http_authenticator"]["domain_controller"]

                # When instantiated, should pass correct params to parent
                instance = auth_class(None, {})
                assert instance._paperless_url == "http://paperless.test"
                assert instance._auth_mode == "oidc"
                assert instance._encryption_key == "test-encryption-key"

    def test_stores_share_loader_in_config(self, mock_settings):
        """Should store share_loader in config for request handlers."""
        share_loader = MagicMock(return_value={})

        with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
            with patch("paperless_webdav.webdav_server.PaperlessProvider"):
                with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_wsgi_app:
                    create_webdav_app(
                        paperless_url="http://paperless.test",
                        share_loader=share_loader,
                    )

                    # Check config was passed to WsgiDAVApp
                    mock_wsgi_app.assert_called_once()
                    config = mock_wsgi_app.call_args[0][0]
                    assert config["share_loader"] is share_loader

    def test_configures_basic_auth_only(self, mock_settings):
        """Should configure HTTP Basic auth and disable digest auth."""
        with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
            with patch("paperless_webdav.webdav_server.PaperlessProvider"):
                with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_wsgi_app:
                    create_webdav_app(
                        paperless_url="http://paperless.test",
                        share_loader=lambda: {},
                    )

                    config = mock_wsgi_app.call_args[0][0]
                    auth_config = config["http_authenticator"]
                    assert auth_config["accept_basic"] is True
                    assert auth_config["accept_digest"] is False
                    assert auth_config["default_to_digest"] is False

    def test_has_provider_mapping_at_root(self, mock_settings):
        """Should map root path to PaperlessProvider."""
        with patch("paperless_webdav.webdav_server.PaperlessBasicAuthenticator"):
            with patch("paperless_webdav.webdav_server.PaperlessProvider") as mock_provider:
                mock_provider_instance = MagicMock()
                mock_provider.return_value = mock_provider_instance

                with patch("paperless_webdav.webdav_server.WsgiDAVApp") as mock_wsgi_app:
                    create_webdav_app(
                        paperless_url="http://paperless.test",
                        share_loader=lambda: {},
                    )

                    config = mock_wsgi_app.call_args[0][0]
                    assert "/" in config["provider_mapping"]
                    assert config["provider_mapping"]["/"] is mock_provider_instance


class TestWebDAVServer:
    """Tests for WebDAVServer class."""

    def test_creates_cheroot_server_with_host_and_port(self, mock_settings):
        """Should create cheroot server bound to configured host and port."""
        with patch("paperless_webdav.webdav_server.create_webdav_app") as mock_create_app:
            mock_create_app.return_value = MagicMock()

            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
                mock_server_instance = MagicMock()
                mock_server.return_value = mock_server_instance

                WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                mock_server.assert_called_once()
                call_args = mock_server.call_args
                assert call_args[0][0] == ("0.0.0.0", 8081)

    def test_creates_app_with_paperless_url(self, mock_settings):
        """Should create app with correct paperless_url."""
        with patch("paperless_webdav.webdav_server.create_webdav_app") as mock_create_app:
            mock_create_app.return_value = MagicMock()

            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server"):
                WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://custom.paperless",
                    share_loader=lambda: {},
                )

                mock_create_app.assert_called_once()
                call_kwargs = mock_create_app.call_args[1]
                assert call_kwargs["paperless_url"] == "http://custom.paperless"

    def test_creates_app_with_share_loader(self, mock_settings):
        """Should pass share_loader to create_webdav_app."""
        share_loader = MagicMock(return_value={"share1": {}})

        with patch("paperless_webdav.webdav_server.create_webdav_app") as mock_create_app:
            mock_create_app.return_value = MagicMock()

            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server"):
                WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=share_loader,
                )

                call_kwargs = mock_create_app.call_args[1]
                assert call_kwargs["share_loader"] is share_loader

    def test_passes_app_to_cheroot_server(self, mock_settings):
        """Should pass created WSGI app to cheroot server."""
        mock_app = MagicMock()

        with patch("paperless_webdav.webdav_server.create_webdav_app") as mock_create_app:
            mock_create_app.return_value = mock_app

            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
                WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                call_args = mock_server.call_args
                # Second positional arg should be the app
                assert call_args[0][1] is mock_app


class TestWebDAVServerLifecycle:
    """Tests for WebDAVServer start/stop lifecycle methods."""

    def test_start_calls_server_start(self, mock_settings):
        """start() should call server.start()."""
        with patch("paperless_webdav.webdav_server.create_webdav_app"):
            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
                mock_server_instance = MagicMock()
                mock_server.return_value = mock_server_instance

                server = WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                server.start()

                mock_server_instance.start.assert_called_once()

    def test_stop_calls_server_stop(self, mock_settings):
        """stop() should call server.stop()."""
        with patch("paperless_webdav.webdav_server.create_webdav_app"):
            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
                mock_server_instance = MagicMock()
                mock_server.return_value = mock_server_instance

                server = WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                server.stop()

                mock_server_instance.stop.assert_called_once()


class TestWebDAVServerProperties:
    """Tests for WebDAVServer property access."""

    def test_stores_host(self, mock_settings):
        """Should store configured host."""
        with patch("paperless_webdav.webdav_server.create_webdav_app"):
            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server"):
                server = WebDAVServer(
                    host="127.0.0.1",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                assert server._host == "127.0.0.1"

    def test_stores_port(self, mock_settings):
        """Should store configured port."""
        with patch("paperless_webdav.webdav_server.create_webdav_app"):
            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server"):
                server = WebDAVServer(
                    host="0.0.0.0",
                    port=9000,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                assert server._port == 9000

    def test_stores_app_reference(self, mock_settings):
        """Should store reference to created WSGI app."""
        mock_app = MagicMock()

        with patch("paperless_webdav.webdav_server.create_webdav_app") as mock_create_app:
            mock_create_app.return_value = mock_app

            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server"):
                server = WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                assert server._app is mock_app

    def test_stores_server_reference(self, mock_settings):
        """Should store reference to cheroot server."""
        mock_server_instance = MagicMock()

        with patch("paperless_webdav.webdav_server.create_webdav_app"):
            with patch("paperless_webdav.webdav_server.cheroot.wsgi.Server") as mock_server:
                mock_server.return_value = mock_server_instance

                server = WebDAVServer(
                    host="0.0.0.0",
                    port=8081,
                    paperless_url="http://paperless.test",
                    share_loader=lambda: {},
                )

                assert server._server is mock_server_instance
