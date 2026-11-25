"""Run from the repo root: python -m tests.manual_warning_version_migration.

Set DATABASE_URL to a newly created, empty MySQL 8 schema named
warning_version_migration_<12 lowercase hex digits>. Use a dedicated QA account
with DDL/DML rights only on that schema and keep all other writers stopped.
The rehearsal leaves fixtures and the database at 0009 for inspection.
"""
import os
import re

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError

PREVIOUS = "0008_hazard_assessment"
TARGET = "0009_warning_text_versions"
TABLE = "warning_text_versions"
BODY_COLUMNS = ("title", "area_text", "impact_text", "reasoning_text")
INSERT_SNAPSHOT = text("""
    INSERT INTO warning_text_versions (warning_id, version_no, title, area_text, impact_text, reasoning_text)
    VALUES (:warning_id, :version_no, 'Prior title', 'Prior area', NULL, 'Prior reasoning')
""")


def seed_legacy_warnings(engine):
    with engine.begin() as conn:
        user_id = conn.execute(text("""
            INSERT INTO users (username, display_name, password_hash)
            VALUES ('migration_qa', 'Migration QA', 'unused')
        """)).lastrowid
        run_id = conn.execute(text("""
            INSERT INTO fusion_runs (algorithm_version, method, lead_hours, weights_json,
                                     input_count, status, executed_at)
            VALUES ('qa', 'EQUAL_AVERAGE', 24, '{}', 4, 'SUCCESS', UTC_TIMESTAMP(6))
        """)).lastrowid
        threshold_id = conn.execute(text("""
            INSERT INTO warning_thresholds (hazard_type, code, threshold_mm, level)
            VALUES ('RAINSTORM', 'HEAVY', 25, 'YELLOW')
        """)).lastrowid
        result_id = conn.execute(text("""
            INSERT INTO warning_results (fusion_run_id, threshold_id, city_code, valid_date,
                                         fused_mm, risk_level, data_status)
            VALUES (:run, :threshold, 'CHANGSHA', '2024-03-27', 29.625, 'YELLOW', 'COMPLETE')
        """), {"run": run_id, "threshold": threshold_id}).lastrowid
        insert_warning = text("""
            INSERT INTO warnings (public_id, warning_result_id, created_by, status, version_no,
                                  title, area_text, impact_text, reasoning_text)
            VALUES (:public_id, :result, :user, 'DRAFT', 7,
                    'Current title', 'Current area', 'Current impact', 'Current reasoning')
        """)
        return tuple(conn.execute(insert_warning, {
            "public_id": public_id, "result": result_id, "user": user_id,
        }).lastrowid for public_id in ("qa-legacy-one", "qa-legacy-two"))


def warning_rows(conn):
    return conn.execute(text("SELECT * FROM warnings ORDER BY id")).all()


def snapshot_rows(conn):
    return conn.execute(text("""
        SELECT warning_id, version_no, title, area_text, impact_text, reasoning_text
        FROM warning_text_versions ORDER BY warning_id, version_no
    """)).all()


def assert_schema(engine):
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns(TABLE)}
    warning = {column["name"]: column for column in inspector.get_columns("warnings")}
    assert set(columns) == {"warning_id", "version_no", *BODY_COLUMNS}
    for name in columns:
        expected = warning["id" if name == "warning_id" else name]
        reflected_type = columns[name]["type"].compile(dialect=engine.dialect)
        assert reflected_type == expected["type"].compile(dialect=engine.dialect)
        assert columns[name]["nullable"] == expected["nullable"]
        assert columns[name]["default"] is None
    assert inspector.get_pk_constraint(TABLE)["constrained_columns"] == ["warning_id", "version_no"]
    foreign_key, = inspector.get_foreign_keys(TABLE)
    assert foreign_key["constrained_columns"] == ["warning_id"]
    assert foreign_key["referred_table"] == "warnings" and foreign_key["referred_columns"] == ["id"]
    assert foreign_key["options"]["ondelete"] == "CASCADE"


def assert_invalid_snapshot(engine, warning_id, version_no, mysql_error):
    try:
        with engine.begin() as conn:
            conn.execute(INSERT_SNAPSHOT, {"warning_id": warning_id, "version_no": version_no})
    except IntegrityError as error:
        assert error.orig.args[0] == mysql_error, error.orig
    else:
        raise AssertionError(f"expected MySQL integrity error {mysql_error}")


def assert_downgrade_refused(cfg):
    # Alembic uses its own engine. Observe statements there as well as our QA connection.
    def reject_ddl(conn, cursor, statement, parameters, context, executemany):
        assert not re.match(r"\s*(CREATE|ALTER|DROP|TRUNCATE|RENAME)\b", statement, re.IGNORECASE), statement

    event.listen(Engine, "before_cursor_execute", reject_ddl)
    try:
        command.downgrade(cfg, PREVIOUS)
    except RuntimeError as error:
        message = str(error).lower()
        assert TABLE in message and "stop writers" in message and "backup" in message, message
    else:
        raise AssertionError("downgrade accepted a non-empty snapshot table")
    finally:
        event.remove(Engine, "before_cursor_execute", reject_ddl)


def main():
    database_url = os.environ.get("DATABASE_URL")
    url = make_url(database_url) if database_url else None
    if (url is None or url.drivername != "mysql+pymysql" or not url.host
            or not re.fullmatch(r"warning_version_migration_[0-9a-f]{12}", url.database or "")
            or set(url.query) - {"charset"}):
        raise SystemExit("Refusing: set DATABASE_URL to a dedicated mysql+pymysql QA schema "
                         "warning_version_migration_<12 hex> (only charset allowed in query)")

    cfg = Config("alembic.ini")
    assert ScriptDirectory.from_config(cfg).get_revision(TARGET).down_revision == PREVIOUS
    engine = create_engine(url)
    inspector = inspect(engine)
    if inspector.get_table_names() or inspector.get_view_names():
        raise SystemExit("Refusing: migration rehearsal needs an empty QA schema")

    command.upgrade(cfg, PREVIOUS)
    first, second = seed_legacy_warnings(engine)
    with engine.connect() as conn:
        legacy_rows = warning_rows(conn)
        assert len(legacy_rows) == 2
        assert all(row.version_no == 7 for row in legacy_rows)

    for apply, target in ((command.upgrade, TARGET), (command.downgrade, PREVIOUS), (command.upgrade, TARGET)):
        apply(cfg, target)
        assert inspect(engine).has_table(TABLE) == (target == TARGET)
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == target
            assert warning_rows(conn) == legacy_rows
            if target == TARGET:
                assert snapshot_rows(conn) == []  # No backfill, even for existing version 7.
        if target == TARGET:
            assert_schema(engine)

    # Same warning/different versions and same version/different warnings are both valid.
    with engine.begin() as conn:
        conn.execute(INSERT_SNAPSHOT, [
            {"warning_id": warning_id, "version_no": version_no}
            for warning_id, version_no in ((first, 5), (first, 6), (second, 5))
        ])
        snapshots = snapshot_rows(conn)
        assert snapshots == [
            (warning_id, version_no, "Prior title", "Prior area", None, "Prior reasoning")
            for warning_id, version_no in ((first, 5), (first, 6), (second, 5))
        ]
    assert_invalid_snapshot(engine, first, 5, 1062)
    assert_invalid_snapshot(engine, max(first, second) + 1, 5, 1452)

    assert_downgrade_refused(cfg)
    with engine.connect() as conn:
        assert conn.scalar(text("SELECT version_num FROM alembic_version")) == TARGET
        assert warning_rows(conn) == legacy_rows
        assert snapshot_rows(conn) == snapshots
    assert_schema(engine)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM warnings WHERE id = :id"), {"id": second})
        assert snapshot_rows(conn) == snapshots[:2]
        assert warning_rows(conn) == legacy_rows[:1]

    engine.dispose()
    print("PASS: legacy warnings preserved without backfill; empty downgrade/re-upgrade, "
          "composite key, FK cascade, and downgrade refusal before DDL verified")


if __name__ == "__main__":
    main()
