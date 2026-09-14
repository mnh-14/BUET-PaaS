from flask import Blueprint, jsonify, request

from deploy_utils import (
    build_image,
    check_build_status,
    extract_required_namespace,
    extract_user_config,
    get_build_logs,
)


build_routes = Blueprint("build_routes", __name__)


@build_routes.route("/api/build", methods=["POST"])
def api_build():
    try:
        user_config = extract_user_config(request.get_json(silent=True))
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


@build_routes.route("/api/build/status", methods=["POST"])
def api_build_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = extract_required_namespace(payload)
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


@build_routes.route("/api/build/logs", methods=["GET"])
def api_build_logs():
    try:
        name = request.args.get("name") or request.args.get("app_name")
        namespace = request.args.get("namespace")
        if not namespace:
            raise ValueError("'namespace' query parameter is required.")
        if not name:
            raise ValueError("'name' or 'app_name' query parameter is required.")

        result = get_build_logs(name=name, namespace=namespace)
        return jsonify({
            "status": "success",
            "name": name,
            "namespace": namespace,
            **result,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400