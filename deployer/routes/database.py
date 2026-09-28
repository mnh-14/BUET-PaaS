"""Database lifecycle endpoints for the deployer service."""

from flask import Blueprint, jsonify, request

from deploy_utils import (
    check_database_status,
    deprovision_database,
    extract_required_namespace,
    extract_user_config,
    get_database_logs,
    provision_database,
)


database_routes = Blueprint("database_routes", __name__)


@database_routes.route("/api/database", methods=["POST"])
def api_provision_database():
    try:
        user_config = extract_user_config(request.get_json(silent=True))
        result = provision_database(user_config)
        return jsonify({
            "status": "success",
            "message": "Database resources applied.",
            "app_name": user_config.get("app_name"),
            "namespace": user_config.get("namespace"),
            "engine": user_config.get("engine"),
            "manifest": result,
        }), 202
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@database_routes.route("/api/database/status", methods=["POST"])
def api_database_status():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = extract_required_namespace(payload)
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


@database_routes.route("/api/database/logs", methods=["GET"])
def api_database_logs():
    try:
        name = request.args.get("name") or request.args.get("app_name")
        namespace = request.args.get("namespace")
        if not namespace:
            raise ValueError("'namespace' query parameter is required.")
        if not name:
            raise ValueError("'name' or 'app_name' query parameter is required.")

        result = get_database_logs(name=name, namespace=namespace)
        return jsonify({
            "status": "success",
            "name": name,
            "namespace": namespace,
            **result,
        })
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400


@database_routes.route("/api/database", methods=["DELETE"])
def api_deprovision_database():
    try:
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")

        name = payload.get("name") or payload.get("app_name")
        namespace = extract_required_namespace(payload)
        if not name:
            raise ValueError("'name' is required.")

        result = deprovision_database(name=name, namespace=namespace)
        return jsonify(result)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400