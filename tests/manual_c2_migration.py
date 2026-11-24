"""Migration rehearsal: run ONLY against an empty disposable c2_migration_* schema."""
import os
import re
from decimal import Decimal

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.models import WarningResult
from backend.app.services import typhoon

B7, C8 = "0007_warning_lifecycle_audit", "0008_hazard_assessment"


def main():
    url = make_url(os.environ["DATABASE_URL"])
    if url.host != "mysql" or not re.fullmatch(r"c2_migration_[a-f0-9]{12}", url.database or ""):
        raise SystemExit("Refusing: require c2_migration_<12 hex> at mysql")
    engine = create_engine(url)
    if inspect(engine).get_table_names():
        raise SystemExit("Refusing: C2 migration rehearsal needs an empty database")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, B7)
    with engine.begin() as conn:
        run_id = conn.execute(text("""INSERT INTO fusion_runs
            (algorithm_version, method, lead_hours, weights_json, input_count, status, executed_at)
            VALUES ('qa', 'EQUAL_AVERAGE', 24, '{}', 4, 'SUCCESS', UTC_TIMESTAMP(6))""")).lastrowid
        threshold_id = conn.execute(text("""INSERT INTO warning_thresholds
            (hazard_type,code,threshold_mm,level) VALUES ('RAINSTORM','HEAVY',25,'YELLOW')""")).lastrowid
        conn.execute(text("""INSERT INTO warning_results
            (fusion_run_id,threshold_id,city_code,valid_date,fused_mm,risk_level,data_status)
            VALUES (:run,:th,'CHANGSHA','2024-03-27',29.625,'YELLOW','COMPLETE')"""), {"run": run_id, "th": threshold_id})
    for target in (C8, B7, C8):
        (command.upgrade if target == C8 else command.downgrade)(cfg, target)
        columns = {column['name']: column for column in inspect(engine).get_columns('warning_results')}
        assert ('assessment_json' in columns) == (target == C8)
        assert all(columns[name]['nullable'] == (target == C8) for name in ('fused_mm', 'fusion_run_id', 'threshold_id'))
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == target
            assert conn.execute(text("SELECT fusion_run_id, threshold_id, fused_mm FROM warning_results")).one() == (
                run_id, threshold_id, Decimal("29.625"),
            )
    insert = text("""INSERT INTO warning_results
        (fusion_run_id,threshold_id,fused_mm,assessment_json,city_code,valid_date,risk_level,data_status)
        VALUES (:run,:th,:mm,:assessment,'CHANGSHA','2024-03-27','YELLOW','COMPLETE')""")
    pairs = [
        (None, threshold_id, 1, None, 3819), (run_id, None, 1, None, 3819),
        (run_id, None, None, '{}', 3819), (None, threshold_id, None, '{}', 3819),
        (run_id + 1000, threshold_id, 1, None, 1452), (run_id, threshold_id + 1000, 1, None, 1452),
    ]
    for run, threshold, mm, assessment, expected in pairs:
        try:
            with engine.begin() as conn:
                conn.execute(insert, {"run": run, "th": threshold, "mm": mm, "assessment": assessment})
        except DBAPIError as error:
            # PyMySQL maps 3819 CHECK failures to OperationalError, unlike 1452 FK failures.
            assert error.orig.args[0] == expected, (error.orig, expected)
        else:
            raise AssertionError(f'expected MySQL integrity error {expected}: {run, threshold, mm, assessment}')
    f = typhoon.replay('hato-20170822', 'GUANGZHOU').forecast
    with Session(engine) as db:
        db.add(WarningResult(city_code='GUANGZHOU', valid_date=f.closest_point.valid_at.date(),
                             risk_level=typhoon.NEAR_RISK_LEVEL, data_status='COMPLETE', assessment_json=f.model_dump(mode='json')))
        db.commit()
    try:
        command.downgrade(cfg, B7)
    except RuntimeError as error:
        assert '0008 contains non-rainfall evidence' in str(error)
    else:
        raise AssertionError('downgrade must stop before DDL when published evidence could be lost')
    with engine.connect() as conn:
        assert conn.scalar(text('SELECT version_num FROM alembic_version')) == C8
        assert conn.scalar(text('SELECT COUNT(*) FROM warning_results WHERE assessment_json IS NOT NULL')) == 1
    print('PASS: 0007→0008→0007→0008 kept the rain result; mixed evidence and missing foreign rows rejected; typhoon evidence prevents downgrade')


if __name__ == '__main__':
    main()
