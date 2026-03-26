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

    polling_col().create_index("project_id", unique=True)

    tunnels_col().create_index("port", unique=True)
    tunnels_col().create_index("project_id")

    print("MongoDB indexes initialized.")


def ping():
    """
    Checks that MongoDB is reachable.
    Called at startup — raises an exception if the DB is down.
    """
    get_client().admin.command("ping")