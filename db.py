import os
import psycopg2
import psycopg2.extras
from typing import Optional, Dict, Any

DB_URL = os.getenv("DATABASE_URL")


def get_conn():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set")
    conn = psycopg2.connect(DB_URL)
    return conn


def fetchone_dict(cur) -> Optional[Dict[str, Any]]:
    row = cur.fetchone()
    if row is None:
        return None
    return dict(row)


def fetchall_dict(cur):
    rows = cur.fetchall()
    return [dict(r) for r in rows]


