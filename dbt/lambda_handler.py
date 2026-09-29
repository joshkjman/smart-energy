"""Run dbt build inside Lambda. The project ships in this zip at /var/task."""
from dbt.cli.main import dbtRunner

PROJECT_DIR = "/var/task"

def handler(event, context):
    res = dbtRunner().invoke([
        "build",
        "--project-dir", PROJECT_DIR,
        "--profiles-dir", PROJECT_DIR,
    ])
    if not res.success:
        raise RuntimeError(f"dbt build failed: {res.exception}")
    return {"success": True}