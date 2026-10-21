#!/bin/bash
# 第二轮回归/边界测试（在 VM 项目根执行）
set -u
BASE=http://127.0.0.1:8080
cd "$(dirname "$0")/.." || exit 1
set -a; . ./.env; set +a

PASS=0; FAIL=0
check() {
  local name="$1" got="$2" want="$3"
  if [ "$got" = "$want" ]; then echo "PASS  $name ($got)"; PASS=$((PASS+1));
  else echo "FAIL  $name expected=$want got=$got"; FAIL=$((FAIL+1)); fi
}
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
jget() { python3 -c "import json,sys;print(json.load(open('$1')).get('$2',''))" 2>/dev/null; }
sql() { docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "$1" 2>/dev/null; }

echo "== A. 服务健康 =="
check "health" "$(code $BASE/health)" 200
check "health_db" "$(code $BASE/health/db)" 200
check "health_redis" "$(code $BASE/health/redis)" 200

echo "== B. 认证 =="
check "noauth_cities" "$(code $BASE/api/v1/cities)" 401
curl -s -c /tmp/r2_a.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"analyst_demo\",\"password\":\"$DEMO_ANALYST_PASSWORD\"}" > /tmp/r2_a.json
ATOKEN=$(jget /tmp/r2_a.json csrf_token)
check "login_analyst" "$(python3 -c "import json;print(json.load(open('/tmp/r2_a.json'))['user']['username'])")" analyst_demo
check "bad_password" "$(code -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"analyst_demo","password":"wrong"}')" 401
check "unknown_user" "$(code -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d '{"username":"nobody_xyz","password":"wrong"}')" 401
check "me" "$(code -b /tmp/r2_a.txt $BASE/api/v1/auth/me)" 200

echo "== C. CSRF =="
check "write_no_csrf" "$(code -b /tmp/r2_a.txt -X POST $BASE/api/v1/auth/logout)" 403
check "write_bad_csrf" "$(code -b /tmp/r2_a.txt -X POST $BASE/api/v1/auth/logout -H 'X-CSRF-Token: wrong')" 403
CSRF_COOKIE=$(grep ww_csrf /tmp/r2_a.txt | awk '{print $7}')
check "csrf_cookie_len" "$([ ${#CSRF_COOKIE} -eq 43 ] && echo 43)" 43

echo "== D. RBAC =="
curl -s -c /tmp/r2_v.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"viewer_demo\",\"password\":\"$DEMO_VIEWER_PASSWORD\"}" > /tmp/r2_v.json
VTOKEN=$(jget /tmp/r2_v.json csrf_token)
check "viewer_create" "$(code -b /tmp/r2_v.txt -X POST $BASE/api/v1/warnings -H 'Content-Type: application/json' -H "X-CSRF-Token: $VTOKEN" -d '{"city_code":"CHANGSHA","valid_date":"2024-03-27","threshold_code":"HEAVY","title":"x","area_text":"x","reasoning_text":"x"}')" 403
check "analyst_audit" "$(code -b /tmp/r2_a.txt $BASE/api/v1/audit-logs)" 403
curl -s -c /tmp/r2_r.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"reviewer_demo\",\"password\":\"$DEMO_REVIEWER_PASSWORD\"}" > /tmp/r2_r.json
RTOKEN=$(jget /tmp/r2_r.json csrf_token)
check "analyst_review_forbidden" "$(code -b /tmp/r2_a.txt -X POST $BASE/api/v1/warnings/nonexistent/review -H 'Content-Type: application/json' -H "X-CSRF-Token: $ATOKEN" -d '{"decision":"APPROVE","comment":"x"}')" 403

echo "== E. 回放/指标 =="
curl -s -b /tmp/r2_a.txt "$BASE/api/v1/replay?city_code=CHANGSHA&date=2024-03-27&threshold_code=HEAVY" > /tmp/r2_c.json
check "replay_complete_status" "$(jget /tmp/r2_c.json data_status)" COMPLETE
check "replay_complete_fused" "$(python3 -c "import json;print(round(json.load(open('/tmp/r2_c.json'))['fused_mm'],3))")" 29.625
curl -s -b /tmp/r2_a.txt "$BASE/api/v1/replay?city_code=CHANGSHA&date=2024-02-06&threshold_code=HEAVY" > /tmp/r2_p.json
check "replay_partial_status" "$(jget /tmp/r2_p.json data_status)" PARTIAL
check "replay_partial_fused_none" "$(python3 -c "import json;print(json.load(open('/tmp/r2_p.json'))['fused_mm'])")" None
check "replay_missing" "$(code -b /tmp/r2_a.txt "$BASE/api/v1/replay?city_code=NOPE&date=2024-03-27&threshold_code=HEAVY")" 404
check "replay_bad_threshold" "$(code -b /tmp/r2_a.txt "$BASE/api/v1/replay?city_code=CHANGSHA&date=2024-03-27&threshold_code=NOPE")" 404
curl -s -b /tmp/r2_a.txt $BASE/api/v1/metrics/experiments/10mm > /tmp/r2_m.json
check "metrics_10_delta" "$(python3 -c "import json;print(json.load(open('/tmp/r2_m.json'))['delta_f1'])")" 4.38

echo "== F. 状态机 + 自审 =="
curl -s -b /tmp/r2_a.txt -X POST $BASE/api/v1/warnings -H 'Content-Type: application/json' -H "X-CSRF-Token: $ATOKEN" \
  -d '{"city_code":"CHANGSHA","valid_date":"2024-03-27","threshold_code":"HEAVY","title":"第二轮状态机测试","area_text":"长沙市","reasoning_text":"融合29.6mm"}' > /tmp/r2_w.json
WID=$(jget /tmp/r2_w.json public_id)
check "created_draft" "$(jget /tmp/r2_w.json status)" DRAFT
check "publish_from_draft_invalid" "$(code -b /tmp/r2_r.txt -X POST $BASE/api/v1/warnings/$WID/publish -H "X-CSRF-Token: $RTOKEN")" 409
check "submit" "$(code -b /tmp/r2_a.txt -X POST $BASE/api/v1/warnings/$WID/submit -H "X-CSRF-Token: $ATOKEN")" 200
check "reviewer_approve" "$(code -b /tmp/r2_r.txt -X POST $BASE/api/v1/warnings/$WID/review -H 'Content-Type: application/json' -H "X-CSRF-Token: $RTOKEN" -d '{"decision":"APPROVE","comment":"ok"}')" 200
check "publish" "$(code -b /tmp/r2_r.txt -X POST $BASE/api/v1/warnings/$WID/publish -H "X-CSRF-Token: $RTOKEN")" 200
check "viewer_sees_published" "$(code -b /tmp/r2_v.txt $BASE/api/v1/warnings/$WID)" 200
check "withdraw" "$(code -b /tmp/r2_r.txt -X POST $BASE/api/v1/warnings/$WID/withdraw -H "X-CSRF-Token: $RTOKEN")" 200
check "viewer_after_withdraw" "$(code -b /tmp/r2_v.txt $BASE/api/v1/warnings/$WID)" 404

# 自审：临时给 reviewer 加 ANALYST 角色，创建并提交后自己审批
sql "INSERT IGNORE INTO weather_warning.user_roles(user_id,role_id) SELECT u.id,r.id FROM weather_warning.users u, weather_warning.roles r WHERE u.username='reviewer_demo' AND r.code='ANALYST';"
rm -f /tmp/r2_r2.txt
curl -s -c /tmp/r2_r2.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"reviewer_demo\",\"password\":\"$DEMO_REVIEWER_PASSWORD\"}" > /tmp/r2_r2.json
R2TOKEN=$(jget /tmp/r2_r2.json csrf_token)
curl -s -b /tmp/r2_r2.txt -X POST $BASE/api/v1/warnings -H 'Content-Type: application/json' -H "X-CSRF-Token: $R2TOKEN" \
  -d '{"city_code":"CHANGSHA","valid_date":"2024-03-27","threshold_code":"HEAVY","title":"自审测试","area_text":"长沙市","reasoning_text":"自审测试"}' > /tmp/r2_s.json
SID=$(jget /tmp/r2_s.json public_id)
curl -s -o /dev/null -b /tmp/r2_r2.txt -X POST $BASE/api/v1/warnings/$SID/submit -H "X-CSRF-Token: $R2TOKEN"
check "self_review_forbidden" "$(code -b /tmp/r2_r2.txt -X POST $BASE/api/v1/warnings/$SID/review -H 'Content-Type: application/json' -H "X-CSRF-Token: $R2TOKEN" -d '{"decision":"APPROVE","comment":"self"}')" 403
sql "DELETE FROM weather_warning.user_roles WHERE user_id=(SELECT id FROM users WHERE username='reviewer_demo') AND role_id=(SELECT id FROM roles WHERE code='ANALYST');"
sql "SET @wid=(SELECT id FROM weather_warning.warnings WHERE public_id='$SID'); SET @rid=(SELECT warning_result_id FROM weather_warning.warnings WHERE id=@wid); SET @fid=(SELECT fusion_run_id FROM weather_warning.warning_results WHERE id=@rid); DELETE FROM weather_warning.warning_reviews WHERE warning_id=@wid; DELETE FROM weather_warning.warning_feedback WHERE warning_id=@wid; DELETE FROM weather_warning.warnings WHERE id=@wid; DELETE FROM weather_warning.warning_results WHERE id=@rid; DELETE FROM weather_warning.fusion_inputs WHERE fusion_run_id=@fid; DELETE FROM weather_warning.fusion_runs WHERE id=@fid;"

echo "== G. 故障与持久化 =="
BEFORE=$(sql "SELECT COUNT(*) FROM weather_warning.warnings;")
docker compose exec -T redis redis-cli FLUSHALL >/dev/null 2>&1
check "session_after_redis_flush" "$(code -b /tmp/r2_r.txt $BASE/api/v1/warnings)" 401
AFTER=$(sql "SELECT COUNT(*) FROM weather_warning.warnings;")
check "mysql_data_intact" "$([ "$BEFORE" = "$AFTER" ] && echo same)" same
docker compose stop mysql >/dev/null 2>&1
check "db_down_503" "$(code $BASE/health/db)" 503
docker compose start mysql >/dev/null 2>&1
sleep 12
check "db_back_200" "$(code $BASE/health/db)" 200
docker compose restart api >/dev/null 2>&1
sleep 6
check "api_after_restart" "$(code $BASE/health)" 200
check "data_after_restart" "$([ "$(sql "SELECT COUNT(*) FROM weather_warning.warnings;")" = "$AFTER" ] && echo same)" same

echo "== H. 前端 =="
check "frontend_index" "$(code $BASE/)" 200
check "frontend_spa" "$(code $BASE/replay)" 200
ASSET=$(curl -s $BASE/ | grep -o '/assets/index-[^"]*\.js' | head -1)
check "frontend_asset" "$(code $BASE$ASSET)" 200
check "proxy_unauth" "$(code $BASE/api/v1/cities)" 401

echo "== I. 审计 =="
curl -s -c /tmp/r2_admin.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin_demo\",\"password\":\"$DEMO_ADMIN_PASSWORD\"}" > /tmp/r2_admin.json
check "admin_audit" "$(code -b /tmp/r2_admin.txt $BASE/api/v1/audit-logs)" 200
check "audit_has_publish" "$(curl -s -b /tmp/r2_admin.txt "$BASE/api/v1/audit-logs?page_size=100" | python3 -c "import sys,json;d=json.load(sys.stdin);print('yes' if any(x['action']=='WARNING_PUBLISH' for x in d) else 'no')")" yes

echo "=============================="
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
