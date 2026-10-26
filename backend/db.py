import os
import uuid
import copy
import logging
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import pymongo
from pymongo.errors import PyMongoError

# Load environment variables
load_dotenv()
backend_env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(backend_env_path):
    load_dotenv(backend_env_path)

logger = logging.getLogger("cleancompute.db")

DATABASE_NAME = os.getenv("DATABASE_NAME", "cleancompute")
MONGODB_URI = os.getenv("MONGODB_URI", "").strip()


class MockInsertOneResult:
    def __init__(self, inserted_id: str):
        self.inserted_id = inserted_id


class MockDeleteResult:
    def __init__(self, deleted_count: int):
        self.deleted_count = deleted_count


class InMemoryCollection:
    """In-memory collection fallback mimicking PyMongo collection methods."""

    def __init__(self, name: str):
        self.name = name
        self._docs: List[Dict[str, Any]] = []

    def insert_one(self, document: Dict[str, Any]) -> MockInsertOneResult:
        doc = copy.deepcopy(document)
        if "_id" not in doc:
            doc["_id"] = str(uuid.uuid4())
        else:
            doc["_id"] = str(doc["_id"])
        self._docs.append(doc)
        return MockInsertOneResult(doc["_id"])

    def insert_many(self, documents: List[Dict[str, Any]]) -> List[str]:
        ids = []
        for d in documents:
            res = self.insert_one(d)
            ids.append(res.inserted_id)
        return ids

    def _matches(self, doc: Dict[str, Any], query: Dict[str, Any]) -> bool:
        if not query:
            return True
        for k, v in query.items():
            doc_val = doc.get(k)
            # Support matching string id if query has _id
            if k == "_id":
                if str(doc_val) != str(v):
                    return False
            elif doc_val != v:
                return False
        return True

    def find_one(self, filter: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        query = filter or {}
        for doc in self._docs:
            if self._matches(doc, query):
                return copy.deepcopy(doc)
        return None

    def find(
        self,
        filter: Optional[Dict[str, Any]] = None,
        sort: Optional[List[tuple]] = None,
        limit: Optional[int] = None,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        query = filter or {}
        matched = [copy.deepcopy(doc) for doc in self._docs if self._matches(doc, query)]

        if sort:
            for field, direction in reversed(sort):
                reverse = direction in (-1, pymongo.DESCENDING)
                matched.sort(
                    key=lambda item: (item.get(field) is None, item.get(field)),
                    reverse=reverse
                )

        if skip:
            matched = matched[skip:]
        if limit is not None:
            matched = matched[:limit]
        return matched

    def update_one(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False):
        query = filter or {}
        for doc in self._docs:
            if self._matches(doc, query):
                if "$set" in update:
                    for k, v in update["$set"].items():
                        doc[k] = copy.deepcopy(v)
                return
        if upsert:
            new_doc = copy.deepcopy(query)
            if "$set" in update:
                new_doc.update(copy.deepcopy(update["$set"]))
            self.insert_one(new_doc)

    def delete_many(self, filter: Optional[Dict[str, Any]] = None) -> MockDeleteResult:
        query = filter or {}
        if not query:
            count = len(self._docs)
            self._docs.clear()
            return MockDeleteResult(count)

        initial_len = len(self._docs)
        self._docs = [doc for doc in self._docs if not self._matches(doc, query)]
        return MockDeleteResult(initial_len - len(self._docs))

    def count_documents(self, filter: Optional[Dict[str, Any]] = None) -> int:
        query = filter or {}
        return sum(1 for doc in self._docs if self._matches(doc, query))

    def create_index(self, keys, **kwargs):
        # In-memory no-op
        return str(keys)


class InMemoryDatabase:
    """In-memory database fallback providing collections."""

    def __init__(self, name: str = "cleancompute"):
        self.name = name
        self.jobs = InMemoryCollection("jobs")
        self.schedules = InMemoryCollection("schedules")
        self.carbon_cache = InMemoryCollection("carbon_cache")

    def __getitem__(self, name: str) -> InMemoryCollection:
        if not hasattr(self, name):
            setattr(self, name, InMemoryCollection(name))
        return getattr(self, name)


class DatabaseManager:
    """Manages connection to MongoDB Atlas with seamless in-memory fallback."""

    def __init__(self):
        self.db = None
        self.client = None
        self.db_type = "memory"
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return

        if not MONGODB_URI:
            logger.warning("MONGODB_URI not set. Falling back to in-memory database.")
            self._use_memory_fallback()
            self._initialized = True
            return

        try:
            logger.info("Connecting to MongoDB Atlas...")
            # Short timeout to allow quick fallback if unreachable/offline
            self.client = pymongo.MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000
            )
            # Verify connection
            self.client.admin.command("ping")
            self.db = self.client[DATABASE_NAME]
            self.db_type = "mongodb"
            logger.info("Successfully connected to MongoDB Atlas database '%s'.", DATABASE_NAME)

            # Ensure required indexes
            self._create_indexes()

        except Exception as exc:
            logger.warning(
                "MongoDB connection failed: %s. Falling back to in-memory database.",
                exc
            )
            self._use_memory_fallback()

        self._initialized = True

    def _use_memory_fallback(self):
        self.db_type = "memory"
        self.db = InMemoryDatabase(DATABASE_NAME)
        logger.info("Using in-memory database fallback for CleanCompute.")

    def _create_indexes(self):
        try:
            if self.db_type == "mongodb":
                self.db.schedules.create_index("job_id")
                self.db.jobs.create_index("created_at")
                logger.info("Created MongoDB indexes on schedules.job_id and jobs.created_at.")
        except Exception as exc:
            logger.warning("Failed to create MongoDB indexes: %s", exc)

    def get_db(self):
        if not self._initialized:
            self.initialize()
        return self.db

    def get_db_type(self) -> str:
        if not self._initialized:
            self.initialize()
        return self.db_type


db_manager = DatabaseManager()


def get_db():
    return db_manager.get_db()


def get_db_type() -> str:
    return db_manager.get_db_type()

