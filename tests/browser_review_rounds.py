"""Run against Vite production assets with isolated API fixtures, no live accounts or DB.

    python tests/browser_review_rounds.py --dist frontend/dist
Set CHROMIUM_PATH to an installed Chromium/Edge, or install Playwright Chromium.
"""
import argparse
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


ORIGIN = "http://127.0.0.1:18791"


def scenario(browser, dist, changed, decision):
    def row(key, token, version=1):
        return dict(public_id=key, title=key, created_by="analyst", city_name="长沙", valid_date="2024-03-27",
                    status="PENDING_REVIEW", review_token=token, version_no=version)

    rows = [row("A", "1:first"), row("B", "1:first")]
    sent = []
    unexpected = []

    def serve(route):
        url = urlsplit(route.request.url)
        path = url.path
        if (url.scheme + "://" + url.netloc) != ORIGIN:
            unexpected.append(route.request.url)
        elif path == "/api/v1/auth/me":
            return route.fulfill(json={"user": {"id": 2, "username": "reviewer", "roles": ["REVIEWER"]}})
        elif path == "/api/v1/cities":
            return route.fulfill(json=[])
        elif path == "/api/v1/notifications/unread-count":
            return route.fulfill(json={"unread_count": 0})
        elif path == "/api/v1/warnings" and route.request.method == "GET":
            return route.fulfill(json=rows)
        elif path == "/api/v1/warnings/A/review" and route.request.method == "POST":
            sent.append(route.request.post_data_json)
            return route.fulfill(json={"decision": decision})
        elif path == "/review" or path.startswith("/assets/") or path == "/favicon.ico":
            file = (dist / ("index.html" if path == "/review" else path.lstrip("/"))).resolve()
            if file.is_relative_to(dist) and file.is_file():
                mime = "text/javascript" if file.suffix == ".js" else mimetypes.guess_type(file.name)[0]
                return route.fulfill(body=file.read_bytes(), content_type=mime or "application/octet-stream")
            return route.fulfill(status=404, body="")
        else:
            unexpected.append(path)
        return route.abort()

    with browser.new_context(service_workers="block", reduced_motion="reduce") as ctx:
        ctx.route("**/*", serve)
        page = ctx.new_page()
        page.goto(ORIGIN + "/review")
        a, b = (page.get_by_label("审核意见：" + key, exact=True) for key in ("A", "B"))
        act = page.get_by_role("row").filter(has=a).get_by_role("button", name="驳回" if decision == "REJECT" else "批准", exact=True)

        def refresh():
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/v1/warnings"):
                page.get_by_role("button", name="刷新", exact=True).click()
            expect(a).to_be_visible()

        a.fill("上一轮意见")
        b.fill("另一张单的草稿")
        refresh()
        expect(a).to_have_value("上一轮意见")
        version = 2 if changed else 1
        token = f"{version}:resubmitted"
        rows[0] = row("A", token, version)
        refresh()
        expect(a).to_have_value("")
        expect(b).to_have_value("另一张单的草稿")
        if decision == "REJECT":
            act.click()
            expect(page.get_by_role("alert")).to_contain_text("驳回时必须填写审核意见")
            assert not sent
            a.fill("本轮新意见")
        with page.expect_response(lambda r: urlsplit(r.url).path.endswith("/A/review")):
            act.click()
        assert sent == [{"decision": decision, "comment": "本轮新意见" if decision == "REJECT" else "", "review_token": token}]
        assert not unexpected, unexpected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or None)
        try:
            for changed in (False, True):
                for decision in ("REJECT", "APPROVE"):
                    scenario(browser, args.dist.resolve(), changed, decision)
                    print(f"PASS: changed={changed}, decision={decision}")
        finally:
            browser.close()
