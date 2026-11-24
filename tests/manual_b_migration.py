"""Destructive migration rehearsal ONLY in a newly-created, empty QA database."""
import os
import re

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def main():
    url = make_url(os.environ['DATABASE_URL'])
    if not re.fullmatch(r'bcheck_migration_[0-9a-f]{12}', url.database or '') or url.host != 'mysql':
        raise SystemExit('Refusing: require a dedicated empty bcheck_migration_<12 hex> database at mysql')
    engine = create_engine(url)
    if inspect(engine).get_table_names():
        raise SystemExit('Refusing: QA database is not empty')
    cfg = Config('alembic.ini')
    b6, b7 = '0006_idx_users_active', '0007_warning_lifecycle_audit'
    command.upgrade(cfg, b6)
    with engine.begin() as con:
        con.execute(text("INSERT INTO audit_logs(action,resource_type,result,reason) VALUES('QA_LEGACY','qa','SUCCESS','keep')"))
    for direction in [b7, b6, b7]:
        (command.downgrade if direction == b6 else command.upgrade)(cfg, direction)
        inspector = inspect(engine)
        for table, columns in [('warnings', ('cancelled_at', 'cancelled_by')), ('audit_logs', ('resource_version',))]:
            actual = {c['name'] for c in inspector.get_columns(table)}
            assert all((c in actual) == (direction == b7) for c in columns)
        assert ('fk_warnings_cancelled_by_users' in {f['name'] for f in inspector.get_foreign_keys('warnings')}) == (direction == b7)
        with engine.connect() as con:
            assert con.scalar(text('SELECT version_num FROM alembic_version')) == direction
            assert con.scalar(text("SELECT COUNT(*) FROM audit_logs WHERE action='QA_LEGACY' AND reason='keep'")) == 1
    case = os.environ.get('B_QA_GUARD_CASE', 'audit')
    if case == 'audit':
        with engine.begin() as con:
            con.execute(text("INSERT INTO audit_logs(action,resource_type,result,resource_version) VALUES('QA_VERSIONED','qa','SUCCESS',2)"))
        check_sql = "SELECT COUNT(*) FROM audit_logs WHERE action='QA_VERSIONED' AND resource_version=2"
    elif case == 'cancelled':
        # Isolate the warnings-side condition: create a valid FK graph and only an unversioned legacy audit.
        from pathlib import Path
        from sqlalchemy.orm import Session
        from backend.app import seed
        from backend.app.deps import CurrentUser
        from backend.app.models import User
        from backend.app.schemas import WarningCreate
        from backend.app.services.audit import AuditContext
        from backend.app.services.warnings import create_warning
        with Session(engine) as db:
            seed.seed_reference_data(db)
            seed.import_sample(db, Path('data/sample/replay_sample.json'))
            user = User(username='qa_fixture', display_name='QA', password_hash='unused', is_active=False)
            db.add(user); db.flush()
            actor = CurrentUser(user.id, user.username, ['ANALYST'])
            w = create_warning(db, WarningCreate(city_code='CHANGSHA', valid_date='2024-03-27', threshold_code='HEAVY',
                               title='QA', area_text='QA', impact_text='QA', reasoning_text='QA'), actor,
                               AuditContext(db, actor, None, None))
            w.status = 'CANCELLED'; w.cancelled_by = user.id
            db.commit()
            assert not db.scalar(text('SELECT COUNT(*) FROM audit_logs WHERE resource_version IS NOT NULL'))
        check_sql = "SELECT COUNT(*) FROM warnings WHERE status='CANCELLED' AND cancelled_by IS NOT NULL"
    else:
        raise SystemExit('unexpected QA guard case')
    try:
        command.downgrade(cfg, b6)
    except RuntimeError as err:
        assert '0007 contains lifecycle/audit history' in str(err)
    else:
        raise AssertionError('downgrade should have stopped before DDL')
    with engine.connect() as con:
        assert con.scalar(text('SELECT version_num FROM alembic_version')) == b7
        assert con.scalar(text(check_sql)) == 1
    print(f'PASS 0006 -> 0007 -> 0006 -> 0007; legacy row retained; {case}-only downgrade safely refused')


if __name__ == '__main__':
    main()
