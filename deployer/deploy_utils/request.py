"""Request payload validation shared by route handlers."""


def extract_user_config(payload):
    if payload is None:
        raise ValueError("Request body is required.")
    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object.")

    if "user_config" in payload and isinstance(payload["user_config"], dict):
        payload = payload["user_config"]

    if not any(key in payload for key in ("app_name", "git_url", "namespace", "image")):
        raise ValueError("Request body must contain a 'user_config' object or application config fields.")

    if not payload.get("namespace"):
        raise ValueError("'namespace' is required.")

    return payload


def extract_required_namespace(payload):
    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object.")

    namespace = payload.get("namespace")
    if not namespace:
        raise ValueError("'namespace' is required.")

    return namespace