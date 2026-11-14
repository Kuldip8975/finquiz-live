import os
import sys
import tempfile

# Use a throwaway database for unit tests, set before the app modules load.
# CI sets PYTEST_DATABASE_URL to run the same tests against PostgreSQL.
os.environ["DATABASE_URL"] = os.environ.get("PYTEST_DATABASE_URL") or ("sqlite:///" + os.path.join(tempfile.mkdtemp(), "unit.db"))
os.environ.setdefault("QUESTION_SECONDS", "20")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
