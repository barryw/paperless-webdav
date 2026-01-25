#!/usr/bin/env python3
"""Container entrypoint that runs migrations before starting the app.

Uses PostgreSQL advisory locks to ensure only one pod runs migrations
when multiple replicas start simultaneously.
"""

import os
import subprocess
import sys
import time

import psycopg2


# Advisory lock ID - arbitrary but unique number for this app's migrations
MIGRATION_LOCK_ID = 839274651


def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL environment variable is required")
        sys.exit(1)
    return url


def run_migrations_with_lock(database_url: str) -> bool:
    """Run alembic migrations with PostgreSQL advisory lock.

    Uses pg_try_advisory_lock to attempt non-blocking lock acquisition.
    If another pod has the lock, we wait for it to complete.

    Args:
        database_url: PostgreSQL connection URL

    Returns:
        True if migrations ran successfully, False otherwise
    """
    # Convert asyncpg URL to psycopg2 format if needed
    sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    max_attempts = 30
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        try:
            conn = psycopg2.connect(sync_url)
            conn.autocommit = True
            cursor = conn.cursor()

            # Try to acquire advisory lock (non-blocking)
            cursor.execute("SELECT pg_try_advisory_lock(%s)", (MIGRATION_LOCK_ID,))
            lock_acquired = cursor.fetchone()[0]

            if lock_acquired:
                print("Acquired migration lock, running alembic upgrade...")
                try:
                    result = subprocess.run(
                        ["uv", "run", "alembic", "upgrade", "head"],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    print(result.stdout)
                    if result.stderr:
                        print(result.stderr, file=sys.stderr)
                    print("Migrations completed successfully")
                    return True
                except subprocess.CalledProcessError as e:
                    print(f"Migration failed: {e}", file=sys.stderr)
                    print(e.stdout)
                    print(e.stderr, file=sys.stderr)
                    return False
                finally:
                    # Release the lock
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_ID,))
                    cursor.close()
                    conn.close()
            else:
                # Another pod has the lock, wait for it
                print(f"Migration lock held by another pod, waiting... (attempt {attempt}/{max_attempts})")
                cursor.close()
                conn.close()
                time.sleep(2)

        except psycopg2.OperationalError as e:
            print(f"Database connection error: {e}, retrying... (attempt {attempt}/{max_attempts})")
            time.sleep(2)

    print("ERROR: Timed out waiting for migration lock")
    return False


def main():
    """Main entrypoint."""
    print("Starting paperless-webdav...")

    database_url = get_database_url()

    # Run migrations with lock
    if not run_migrations_with_lock(database_url):
        print("ERROR: Failed to run migrations")
        sys.exit(1)

    # Start the application
    print("Starting application...")
    os.execvp("uv", ["uv", "run", "python", "-m", "paperless_webdav.main"])


if __name__ == "__main__":
    main()
