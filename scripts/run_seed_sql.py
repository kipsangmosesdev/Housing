"""Run the amenity seed SQL with the project's psycopg environment."""

import os
from pathlib import Path

import psycopg
from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parent.parent
SQL_FILE = Path(__file__).with_name("seed_amenities.sql")


def main():
    database_url = os.environ.get("DATABASE_URL") or dotenv_values(
        PROJECT_DIR / ".env"
    ).get("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is not set in the environment or project .env file."
        )

    sql_statements = [
        statement.strip()
        for statement in SQL_FILE.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            inserted = 0
            for statement in sql_statements:
                cursor.execute(statement)
                if statement.lstrip().upper().startswith("INSERT INTO"):
                    inserted = cursor.rowcount
                elif statement.lstrip().upper().startswith("SELECT COUNT"):
                    total = cursor.fetchone()[0]

    print(f"Inserted {inserted} missing amenities. Total amenities: {total}.")


if __name__ == "__main__":
    main()
