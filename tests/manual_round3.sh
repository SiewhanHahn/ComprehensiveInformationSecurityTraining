#!/bin/bash
# 第二轮 code review 回归：验证 H1/H2/M1 三项修复
cd ~/Projects/ComprehensiveInformationSecurityTraining
set -a; . ./.env; set +a
BASE=http://127.0.0.1:8080
PASS=0; FAIL=0
ck() { if [ "$2" = "$3" ]; then echo "PASS $1 ($2)"; PASS=$((PASS+1)); else echo "FAIL $1 want=$3 got=$2"; FAIL=$((FAIL+1)); fi; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
jget() { python3 -c "import json,sys;print(json.load(open('$1')).get('$2',''))" 2>/dev/null; }
sql() { docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "$1" </dev/null 2>/dev/null; }

echo "== 1. is_active 停用账号登录 =="
sql "UPDATE weather_warning.users SET is_active=0 WHERE username='viewer_demo';"
ck "disabled_login_401" "$(curl -s -o /dev/null -w "%{http_code}" -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"viewer_demo\",\"password\":\"$DEMO_VIEWER_PASSWORD\"}")" 401
sql "UPDATE weather_warning.users SET is_active=1 WHERE username='viewer_demo';"

echo "== 2. viewer 读取未发布预警反馈 =="
curl -s -c /tmp/fb_a.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"analyst_demo\",\"password\":\"$DEMO_ANALYST_PASSWORD\"}" > /tmp/fb_a.json
AT=$(jget /tmp/fb_a.json csrf_token)
curl -s -c /tmp/fb_v.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"viewer_demo\",\"password\":\"$DEMO_VIEWER_PASSWORD\"}" > /tmp/fb_v.json
curl -s -b /tmp/fb_a.txt -X POST $BASE/api/v1/warnings -H 'Content-Type: application/json' -H "X-CSRF-Token: $AT" -d '{"city_code":"CHANGSHA","valid_date":"2024-03-27","threshold_code":"HEAVY","title":"反馈越权测试","area_text":"长沙","reasoning_text":"x"}' > /tmp/fb_w.json
WID=$(jget /tmp/fb_w.json public_id)
ck "created_draft" "$(jget /tmp/fb_w.json status)" DRAFT
ck "viewer_feedback_draft_404" "$(code -b /tmp/fb_v.txt $BASE/api/v1/warnings/$WID/feedback)" 404

echo "== 3. 会话滑动过期 touch_session =="
curl -s -c /tmp/fb_s.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"analyst_demo\",\"password\":\"$DEMO_ANALYST_PASSWORD\"}" > /tmp/fb_s.json
SID=$(grep ww_session /tmp/fb_s.txt | awk '{print $7}')
docker compose exec -T redis redis-cli EXPIRE "session:$SID" 60 >/dev/null 2>&1
ttl_before=$(docker compose exec -T redis redis-cli TTL "session:$SID" | tr -d '\r')
code -b /tmp/fb_s.txt $BASE/api/v1/cities >/dev/null
ttl_after=$(docker compose exec -T redis redis-cli TTL "session:$SID" | tr -d '\r')
if [ "$ttl_after" -gt "$ttl_before" ] 2>/dev/null; then echo "PASS session_ttl_refreshed ($ttl_before -> $ttl_after)"; PASS=$((PASS+1)); else echo "FAIL session_ttl_refreshed before=$ttl_before after=$ttl_after"; FAIL=$((FAIL+1)); fi

# 清理测试预警
sql "SET @w=(SELECT id FROM weather_warning.warnings WHERE public_id='$WID'); SET @r=(SELECT warning_result_id FROM weather_warning.warnings WHERE id=@w); SET @f=(SELECT fusion_run_id FROM weather_warning.warning_results WHERE id=@r); DELETE FROM weather_warning.warnings WHERE id=@w; DELETE FROM weather_warning.warning_results WHERE id=@r; DELETE FROM weather_warning.fusion_runs WHERE id=@f;"

echo "=============================="
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
