import os

DB_TYPE = "fuseki"  # options: "fuseki" | "graphdb"
DB_BASE_URI = os.environ.get("DB_BASE_URI", "")
DB_USERNAME = os.environ.get("DB_USERNAME", "")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
TIMEOUT = float(os.environ.get("TIMEOUT", "20.0"))
SHOW_WARNINGS = True
WARNINGS_INVALID = False  # Allows warnings to flag as invalid when true
DROP_ON_START = False  # Drops all graphs when updating vocabs
