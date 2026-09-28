<<<<<<< HEAD
from flask import Flask, jsonify

from routes.build import build_routes
from routes.database import database_routes
from routes.deployment import deployment_routes
from routes.namespace import namespace_routes
from routes.security import security_routes

app = Flask(__name__)
app.register_blueprint(build_routes)
app.register_blueprint(database_routes)
app.register_blueprint(deployment_routes)
app.register_blueprint(namespace_routes)
app.register_blueprint(security_routes)


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})