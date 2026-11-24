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
    with engine.begin() as con:
        con.execute(text("INSERT INTO audit_logs(action,resource_type,result,resource_version) VALUES('QA_VERSIONED','qa','SUCCESS',2)"))
    try:
        command.downgrade(cfg, b6)
    except RuntimeError as err:
        assert '0007 contains lifecycle/audit history' in str(err)
    else:
        raise AssertionError('downgrade should have stopped before DDL')
    with engine.connect() as con:
        assert con.scalar(text('SELECT version_num FROM alembic_version')) == b7
        assert con.scalar(text("SELECT resource_version FROM audit_logs WHERE action='QA_VERSIONED'")) == 2
    print('PASS 0006 -> 0007 -> 0006 -> 0007; legacy row retained; nonempty 0007 downgrade safely refused')


if __name__ == '__main__':
    main()
