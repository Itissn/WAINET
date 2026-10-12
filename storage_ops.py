"""Private SQLite backup, verification and restore-to-new-file operations.

Never overwrite the live database. Stop the server before switching a restored DB.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from contextlib import closing

ROOT = Path(__file__).resolve().parent


def verify(path):
    path = Path(path).resolve(strict=True)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Database foreign key check failed")
        required = {"observations", "users", "reviews", "points_ledger"}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            raise ValueError("Not a complete WAINET database")
        return {"integrity": "ok", "observations": db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]}


def copy_database(source, destination):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.suffix != ".sqlite3":
        raise ValueError("Use a private .sqlite3 destination")
    if destination == source:
        raise ValueError("Source and destination must differ")
    if destination.is_relative_to(ROOT):
        relative = destination.relative_to(ROOT)
        if relative.parts[0] in {"docs", ".git"} or relative.parts[0].startswith("presentation"):
            raise ValueError("Do not put private databases in a published directory")
    verify(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation: refuse overwrite even if another process just created it.
    with destination.open("xb"):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as target:
                original.backup(target)
        result = verify(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore", "verify"])
    parser.add_argument("source")
    parser.add_argument("destination", nargs="?")
    args = parser.parse_args()
    if args.operation != "verify" and not args.destination:
        parser.error("backup/restore require a NEW destination file")
    result = verify(args.source) if args.operation == "verify" else copy_database(args.source, args.destination)
    print(json.dumps({"operation": args.operation, **result}))


if __name__ == "__main__":
    main()
