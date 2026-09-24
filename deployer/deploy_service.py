from flask import Flask, jsonify, request

from deploy import (
    build_image,
    check_build_status,
    check_database_status,
    check_deploy_status,
    create_namespace_if_not_exists,
    deploy_application,
    deprovision_database,
    provision_database,
    rotate_database_credentials,
)

app = Flask(__name__)


def _extract_user_config(payload):
    if payload is None:
        raise ValueError("Request body is required.")
    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object.")

    if "user_config" in payload and isinstance(payload["user_config"], dict):
        return payload["user_config"]

    if any(key in payload for key in ("app_name", "git_url", "namespace", "image")):
        return payload

    raise ValueError("Request body must contain a 'user_config' object or application config fields.")


@app.route("/api/build", methods=["POST"])
def api_build():
    try:
        user_config = _extract_user_config(request.get_json(silent=True))
        result = build_image(user_config)
        return jsonify({
            "status": "success",
            "message": "Build job submitted.",
            "app_name": user_config.get("app_name"),
            "namespace": user_config.get("namespace", "default"),
            "image": user_config.get("image"),
            "job": result,
        }), 202
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/deploy", methods=["POST"])
def api_deploy():
    try:
        user_config = _extract_user_config(request.get_json(silent=True))
        result = deploy_application(user_config)
        return jsonify({
            "status": "success",
            "message": "Deployment manifest applied.",
            "app_name": user_config.get("app_name"),
            "namespace": user_config.get("namespace", "default"),
            "manifest": result,
        }), 202
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/api/build/status", methods=["POST"])
def api_build_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = payload.get("namespace", "default")

        if not name:
            raise ValueError("'name' is required.")

        result = check_build_status(name=name, namespace=namespace)
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


@app.route("/api/deploy/status", methods=["POST"])
def api_deploy_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = payload.get("namespace", "default")

        if not name:
            raise ValueError("'name' is required.")

        result = check_deploy_status(name=name, namespace=namespace)
        response = {
            "status": "success",
            "name": name,
            "namespace": namespace,
            "result": result["status"],
            "summary": result["summary"],
            "reason": result["reason"],
            "details": result["details"],
        }
        if result["status"] == "Running" and result.get("url"):
            response["url"] = result["url"]
        return jsonify(response)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


# add a namespace create endpoint
@app.route("/api/namespace", methods=["POST"])
def api_create_namespace():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        namespace = payload.get("namespace")
        if not namespace:
            raise ValueError("'namespace' is required.")

        create_namespace_if_not_exists(namespace)
        return jsonify({
            "status": "success",
            "message": f"Namespace '{namespace}' created successfully.",
            "namespace": namespace,
        }), 201
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
