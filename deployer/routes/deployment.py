from flask import Blueprint, jsonify, request

from deploy_utils import (
    check_deploy_status,
    deploy_application,
    extract_required_namespace,
    extract_user_config,
    get_deploy_logs,
)


deployment_routes = Blueprint("deployment_routes", __name__)


@deployment_routes.route("/api/deploy", methods=["POST"])
def api_deploy():
    try:
        user_config = extract_user_config(request.get_json(silent=True))
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


@deployment_routes.route("/api/deploy/status", methods=["POST"])
def api_deploy_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = extract_required_namespace(payload)
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


@deployment_routes.route("/api/deploy/logs", methods=["GET"])
def api_deploy_logs():
    try:
        name = request.args.get("name") or request.args.get("app_name")
        namespace = request.args.get("namespace")
        if not namespace:
            raise ValueError("'namespace' query parameter is required.")
        if not name:
            raise ValueError("'name' or 'app_name' query parameter is required.")

        result = get_deploy_logs(name=name, namespace=namespace)
        return jsonify({
            "status": "success",
            "name": name,
            "namespace": namespace,
            **result,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400