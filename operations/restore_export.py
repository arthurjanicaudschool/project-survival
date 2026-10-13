import os
import json
import argparse
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict
from survival.store import Store
from survival.restore import restore

load_dotenv(".env")
p = argparse.ArgumentParser(
    description="Restore to a separate empty migrated database only"
)
p.add_argument("--directory", required=True)
args = p.parse_args()
target = os.environ["RESTORE_DATABASE_URL"]
source = conninfo_to_dict(os.environ["DATABASE_URL"])
dest = conninfo_to_dict(target)
if all(source.get(k) == dest.get(k) for k in ("host", "port", "dbname")):
    raise ValueError("Restore must target a separate database")
s = Store(target)
try:
    print(json.dumps(restore(s, args.directory)))
finally:
    s.close()
