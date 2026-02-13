import run_ui


def test_socketio_engine_configuration_defaults():
    server = run_ui.socketio_server.eio

    assert server.ping_interval == 25
    assert server.ping_timeout == 20
    assert server.max_http_buffer_size == 50 * 1024 * 1024
