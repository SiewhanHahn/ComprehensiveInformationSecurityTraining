"""正文版本是内容版本，不是审批轮次。只在隔离 QA 中创建测试预警。"""
import pytest
from sqlalchemy import select

from backend.app.db import SessionLocal
from backend.app.models import Warning
from conftest import csrf_headers, review_body

pytestmark = pytest.mark.integration


def test_review_reads_exact_draft_text_across_rejection_and_resubmission(login, make_warning, new_client):
    author, ac = login("analyst_demo")
    reviewer, rc = login("reviewer_demo")
    admin, _ = login("admin_demo")
    viewer, _ = login("viewer_demo")
    original = dict(title="初稿", area_text="河东", impact_text="涵洞积水", reasoning_text="第一版\n依据")
    current = dict(title="改稿", area_text="河西", impact_text="道路封闭", reasoning_text="第二版\n依据")
    pid = make_warning(author, ac, **original)
    url = f"/api/v1/warnings/{pid}"
    ah, rh = csrf_headers(ac), csrf_headers(rc)
    assert author.post(url + "/submit", headers=ah).status_code == 200
    reject = review_body(reviewer, pid, "REJECT", "请修改研判区域")
    assert reviewer.post(url + "/review", headers=rh, json=reject).status_code == 200
    assert author.patch(url, headers=ah, json=current).json()["version_no"] == 2
    assert author.patch(url, headers=ah, json=current).json()["version_no"] == 2
    assert author.post(url + "/submit", headers=ah).status_code == 200
    for reader in (reviewer, admin):
        for version, text in [(1, original), (2, current)]:
            res = reader.get(f"{url}/versions/{version}")
            assert res.status_code == 200, res.text
            assert res.json() == {"version_no": version, **text}
            assert res.headers["cache-control"] == "no-store"
    approve = review_body(reviewer, pid, "APPROVE", "已核对两个版本")
    assert reviewer.post(url + "/review", headers=rh, json=approve).status_code == 200
    assert reviewer.post(url + "/publish", headers=rh).status_code == 200
    assert viewer.get(url).status_code == 200
    unauth = new_client().get(url + "/versions/1")
    assert (unauth.status_code, unauth.json()["error"]["code"]) == (401, "UNAUTHENTICATED")
    assert unauth.headers.get("cache-control") == "no-store"
    for reader in (viewer, author):
        denied = reader.get(url + "/versions/1")
        assert (denied.status_code, denied.json()["error"]["code"]) == (403, "FORBIDDEN")
        assert denied.headers.get("cache-control") == "no-store"


def test_pre_migration_gap_is_not_filled_with_current_text(login, make_warning):
    author, csrf = login("analyst_demo")
    reviewer, _ = login("reviewer_demo")
    pid = make_warning(author, csrf, reasoning_text="已有第三版")
    url = f"/api/v1/warnings/{pid}"
    with SessionLocal() as db:
        # Simulate a pre-0009 warning: only the latest row survived old edits.
        w = db.scalar(select(Warning).where(Warning.public_id == pid))
        w.version_no = 3
        db.commit()
    assert author.patch(url, headers=csrf_headers(csrf), json={"reasoning_text": "第四版"}).status_code == 200
    for missing in (1, 2):
        resp = reviewer.get(f"{url}/versions/{missing}")
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "VERSION_NOT_RETAINED"
        assert resp.headers.get("cache-control") == "no-store"
    assert reviewer.get(url + "/versions/3").json()["reasoning_text"] == "已有第三版"
    assert reviewer.get(url + "/versions/4").json()["reasoning_text"] == "第四版"
    for path in (url + "/versions/5", "/api/v1/warnings/not-a-real-warning/versions/1"):
        res = reviewer.get(path)
        assert (res.status_code, res.json()["error"]["code"]) == (404, "NOT_FOUND")
    assert reviewer.get(url + "/versions/0").status_code == 422
    assert author.post(url + "/cancel", headers=csrf_headers(csrf)).status_code == 200
    assert reviewer.get(url + "/versions/3").json()["error"]["code"] == "NOT_FOUND"


def test_aborted_edit_commits_neither_text_nor_snapshot(login, make_warning):
    from backend.app.deps import CurrentUser
    from backend.app.models import AuditLog, WarningTextVersion
    from backend.app.schemas import WarningUpdate
    from backend.app.services.audit import AuditContext
    from backend.app.services.warnings import update_warning

    author, csrf = login("analyst_demo")
    pid = make_warning(author, csrf, reasoning_text="原文")
    with SessionLocal() as db:
        w = db.scalar(select(Warning).where(Warning.public_id == pid))
        wid = w.id
        actor = CurrentUser(w.created_by, "analyst_demo", ["ANALYST"])
        audit = AuditContext(db, actor, None, None)
        update_warning(db, pid, WarningUpdate(reasoning_text="不应落库"), actor, audit)
        assert db.get(WarningTextVersion, (wid, 1)).reasoning_text == "原文"
        db.rollback()
    with SessionLocal() as db:
        assert db.get(WarningTextVersion, (wid, 1)) is None
        w = db.get(Warning, wid)
        assert (w.version_no, w.reasoning_text) == (1, "原文")
        assert db.scalar(select(AuditLog.id).where(
            AuditLog.resource_id == pid, AuditLog.action == "WARNING_UPDATE"
        )) is None
