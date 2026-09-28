from flask import Blueprint, jsonify, request

from deploy_utils import create_namespace_if_not_exists


namespace_routes = Blueprint("namespace_routes", __name__)


@namespace_routes.route("/api/namespace", methods=["POST"])
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