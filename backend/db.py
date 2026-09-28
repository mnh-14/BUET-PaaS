"""""
Collections:
  - projects          one document per student project
  - deployments       one document per build attempt (many per project)
  - project_polling   one document per project, owned by poller.py 

Connection:
  Reads MONGO_URI and MONGO_DB from the .env file.
"""

import os
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv() 

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB",  "buetpaas")


_client: MongoClient = None


def get_client() -> MongoClient:
    """Returns the shared MongoClient, creating it on first call."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    """Returns the buetpaas database handle."""
    return get_client()[MONGO_DB]


def projects_col() -> Collection:
    return get_db()["projects"]

def deployments_col() -> Collection:
    return get_db()["deployments"]

def polling_col() -> Collection:
    return get_db()["project_polling"]

def users_col() -> Collection:
    return get_db()["users"]

def tunnels_col() -> Collection:
    """
    Maps host port → Cloudflare tunnel public URL.
    Document structure:
    {
        "port":        9003,
        "tunnel_url":  "https://xxxx.trycloudflare.com",
        "project_id":  "proj-a1b2c3d4",
        "created_at":  ISODate(...)
    }
    """
    return get_db()["tunnels"]

def github_installations_col() -> Collection:
    return get_db()["github_installations"]

def github_connections_col() -> Collection:
    return get_db()["github_connections"]

def github_oauth_states_col() -> Collection:
    return get_db()["github_oauth_states"]

def github_webhook_deliveries_col() -> Collection:
    return get_db()["github_webhook_deliveries"]

def user_databases_col() -> Collection:
    """
    One document per per-user provisioned database.
    Document structure:
    {
        "database_id":         "db-a1b2c3d4",
        "project_id":          "proj-x1y2z3",
        "user_id":             "2105085",
        "engine":              "postgres",               # postgres | mongodb | redis
        "status":              "ready",                  # creating | ready | failed | deprovisioned
        "size_gb":             1,
        "idem_key":            "proj-x1y2z3:postgres",   # unique idempotency key
        "app_name":            "proj-x1y2z3-postgres",   # k8s resource name base
        "namespace":           "db-proj-x1y2z3",
        "credentials":         {"user": "...", "password": "...", "database": "appdb"},
        "connection_internal": "postgresql://u:p@svc.ns.svc.cluster.local:5432/appdb",
        "connection_external": "postgresql://u:p@192.168.68.121:31234/appdb",
        "node_port":           31234,                    # None when ClusterIP only
        "created_at":          ISODate(...),
        "updated_at":          ISODate(...),
        "deprovisioned_at":    ISODate(...) | None
    }
    """
    return get_db()["user_databases"]


def init_indexes():
    users_col().create_index("user_id", unique=True)
    users_col().create_index("email",   unique=True)

    projects_col().create_index("project_id", unique=True)
    projects_col().create_index("user_id")
    projects_col().create_index([("created_at", DESCENDING)])

    
    deployments_col().create_index("deployment_id", unique=True)
    deployments_col().create_index("project_id")                      
    deployments_col().create_index([("project_id", ASCENDING),
                                    ("deployed_at", DESCENDING)])     
    deployments_col().create_index(
        "automatic_key",
        unique=True,
        partialFilterExpression={"automatic_key": {"$type": "string"}},
    )

    polling_col().create_index("project_id", unique=True)

    tunnels_col().create_index("port", unique=True)
    tunnels_col().create_index("project_id")

    github_installations_col().create_index("installation_id", unique=True)
    github_connections_col().create_index(
        [("user_id", ASCENDING), ("installation_id", ASCENDING)], unique=True
    )
    github_connections_col().create_index("installation_id")
    github_oauth_states_col().create_index("state_hash", unique=True)
    github_oauth_states_col().create_index("expires_at", expireAfterSeconds=0)
    github_webhook_deliveries_col().create_index("delivery_id", unique=True)
    github_webhook_deliveries_col().create_index(
        "expires_at", expireAfterSeconds=0
    )
    projects_col().create_index(
        [
            ("github_installation_id", ASCENDING),
            ("github_repo_id", ASCENDING),
            ("deploy_branch", ASCENDING),
        ]
    )

    user_databases_col().create_index("database_id", unique=True)
    user_databases_col().create_index(
        "idem_key",
        unique=True,
        partialFilterExpression={"idem_key": {"$type": "string"}},
    )
    user_databases_col().create_index("project_id")
    user_databases_col().create_index("user_id")
    user_databases_col().create_index(
        [("project_id", ASCENDING), ("engine", ASCENDING)]
    )
    user_databases_col().create_index([("created_at", DESCENDING)])

    print("MongoDB indexes initialized.")


def ping():
    """
    Checks that MongoDB is reachable.
    Called at startup — raises an exception if the DB is down.
    """
    get_client().admin.command("ping")
