import json

from flask import Flask, Response, request

from python.api import tunnel as tunnel_api
from python.helpers import dotenv, process, runtime
from python.helpers.print_style import PrintStyle
from python.helpers.tunnel_manager import TunnelManager

# initialize the internal Flask server
app = Flask("app")
app.json.sort_keys = False  # Disable key sorting in jsonify


def run():
    # Suppress only request logs but keep the startup messages
    from werkzeug.serving import WSGIRequestHandler, make_server

    PrintStyle().print("Starting tunnel server...")

    class NoRequestLoggingWSGIRequestHandler(WSGIRequestHandler):
        def log_request(self, code="-", size="-"):
            pass  # Override to suppress request logging

    # Get configuration from environment
    tunnel_api_port = runtime.get_tunnel_api_port()
    host = (
        runtime.get_arg("host") or dotenv.get_dotenv_value("WEB_UI_HOST") or "localhost"
    )
    server = None

    # handle api request — call tunnel logic directly and return safe JSON
    @app.route("/", methods=["POST"])
    async def handle_request():
        try:
            body = request.get_json(silent=True) or {}
            result = await tunnel_api.process(body)
            # tunnel_api.process() always returns dict — serialize fresh
            return Response(
                response=json.dumps(result),
                status=200,
                mimetype="application/json",
            )
        except Exception as e:
            PrintStyle.error(f"Tunnel error: {str(e)}")
            return Response(
                response=json.dumps({"error": "Internal server error"}),
                status=500,
                mimetype="application/json",
            )

    try:
        server = make_server(
            host=host,
            port=tunnel_api_port,
            app=app,
            request_handler=NoRequestLoggingWSGIRequestHandler,
            threaded=True,
        )

        process.set_server(server)
        # server.log_startup()
        server.serve_forever()
    finally:
        # Clean up tunnel if it was started
        try:
            TunnelManager.get_instance().stop_tunnel()
        except Exception:
            pass


# run the internal server
if __name__ == "__main__":
    runtime.initialize()
    dotenv.load_dotenv()
    run()
