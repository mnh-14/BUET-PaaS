from flask import Flask, jsonify, request

from deploy import (
    check_database_status,
    deprovision_database,
    get_database_logs,
    provision_database,
    rotate_database_credentials,
)
from routes.build import build_routes
from routes.deployment import deployment_routes
from routes.namespace import namespace_routes
from routes.security import security_routes

app = Flask(__name__)
app.register_blueprint(build_routes)
app.register_blueprint(deployment_routes)
app.register_blueprint(namespace_routes)
app.register_blueprint(security_routes)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


@app.route("/api/database/engines", methods=["GET"])
def api_database_engines():
    """Advertise supported engine metadata (used for validation without a cluster)."""
    try:
        from k3s_conf import DATABASE_ENGINES
        payload = {
            engine: {
                "image": spec["image"],
                "port": spec["port"],
                "credential_keys": list(spec["credentials"]),
            }
            for engine, spec in DATABASE_ENGINES.items()
        }
        return jsonify({"status": "success", "engines": payload})
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


def _extract_database_config(payload):
    if payload is None:
        raise ValueError("Request body is required.")
    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object.")

    if "database_config" in payload and isinstance(payload["database_config"], dict):
        config = payload["database_config"]
    elif any(key in payload for key in ("app_name", "namespace", "engine")):
        config = payload
    else:
        raise ValueError(
            "Request body must contain a 'database_config' object or app_name/namespace/engine fields."
        )

    if not config.get("app_name"):
        raise ValueError("'app_name' is required.")
    if not config.get("namespace"):
        raise ValueError("'namespace' is required.")
    if not config.get("engine"):
        raise ValueError("'engine' is required.")
    if config.get("credentials") is None:
        config["credentials"] = {}
    return config


@app.route("/api/database/provision", methods=["POST"])
def api_database_provision():
    try:
        config = _extract_database_config(request.get_json(silent=True))
        result = provision_database(config)
        response = {key: value for key, value in result.items() if key != "manifest"}
        response["status"] = "success"
        return jsonify(response), 202
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/database/rotate", methods=["POST"])
def api_database_rotate():
    try:
        config = _extract_database_config(request.get_json(silent=True))
        result = rotate_database_credentials(config)
        result["status"] = "success"
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/database/deprovision", methods=["POST"])
def api_database_deprovision():
    try:
        payload = request.get_json(silent=True) or {}
        config = _extract_database_config(payload)
        result = deprovision_database(config)
        result["status"] = "success"
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/database/status", methods=["POST"])
def api_database_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = payload.get("namespace", "default")
        if not name:
            raise ValueError("'name' is required.")

        result = check_database_status(name=name, namespace=namespace)
        return jsonify({
            "status": "success",
            "name": name,
            "namespace": namespace,
            "result": result["status"],
            "summary": result["summary"],
            "reason": result["reason"],
            "details": result["details"],
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/database/logs", methods=["GET"])
def api_database_logs():
    try:
        name = request.args.get("name") or request.args.get("app_name")
        namespace = request.args.get("namespace", "default")
        if not name:
            raise ValueError("'name' query parameter is required.")

        result = get_database_logs(name=name, namespace=namespace)
        result["status"] = "success"
        return jsonify(result)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)