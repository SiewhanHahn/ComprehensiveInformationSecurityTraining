#!/bin/bash
# 第二轮 code review 低危项（L1-L8）回归
cd ~/Projects/ComprehensiveInformationSecurityTraining
set -a; . ./.env; set +a
BASE=http://127.0.0.1:8080
PASS=0; FAIL=0
ck() { if [ "$2" = "$3" ]; then echo "PASS $1 ($2)"; PASS=$((PASS+1)); else echo "FAIL $1 want=$3 got=$2"; FAIL=$((FAIL+1)); fi; }
code() { curl -s -o /dev/null -w "%{http_code}" "$@"; }
jget() { python3 -c "import json,sys;print(json.load(open('$1')).get('$2',''))" 2>/dev/null; }
sql() { docker compose exec -T mysql mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -e "$1" </dev/null 2>/dev/null; }

echo "== L3. /health/db 不泄露版本 =="
has_version=$(curl -s $BASE/health/db | python3 -c "import json,sys;d=json.load(sys.stdin);print('yes' if 'version' in d else 'no')")
ck "health_db_no_version" "$has_version" no

echo "== L6. ADMIN 全业务权限 =="
curl -s -c /tmp/l6_adm.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"admin_demo\",\"password\":\"$DEMO_ADMIN_PASSWORD\"}" > /tmp/l6_adm.json
ADM=$(jget /tmp/l6_adm.json csrf_token)
curl -s -b /tmp/l6_adm.txt -X POST $BASE/api/v1/warnings -H 'Content-Type: application/json' -H "X-CSRF-Token: $ADM" -d '{"city_code":"CHANGSHA","valid_date":"2024-03-27","threshold_code":"HEAVY","title":"admin权限测试","area_text":"长沙","reasoning_text":"x"}' > /tmp/l6_w.json
WID=$(jget /tmp/l6_w.json public_id)
ck "admin_create_200" "$(jget /tmp/l6_w.json status)" DRAFT
ck "admin_submit_200" "$(code -b /tmp/l6_adm.txt -X POST $BASE/api/v1/warnings/$WID/submit -H "X-CSRF-Token: $ADM")" 200
curl -s -c /tmp/l6_rev.txt -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"reviewer_demo\",\"password\":\"$DEMO_REVIEWER_PASSWORD\"}" > /tmp/l6_rev.json
REV=$(jget /tmp/l6_rev.json csrf_token)
ck "reviewer_approve_200" "$(code -b /tmp/l6_rev.txt -X POST $BASE/api/v1/warnings/$WID/review -H 'Content-Type: application/json' -H "X-CSRF-Token: $REV" -d '{"decision":"APPROVE","comment":"ok"}')" 200
ck "admin_publish_200" "$(code -b /tmp/l6_adm.txt -X POST $BASE/api/v1/warnings/$WID/publish -H "X-CSRF-Token: $ADM")" 200

echo "== L2/L4. 审计 IP 取自 X-Forwarded-For + request_id =="
docker compose exec -T api python -c "
import urllib.request, json
req = urllib.request.Request('http://127.0.0.1:8000/api/v1/auth/login',
    data=json.dumps({'username':'nobody_l2_probe','password':'x'}).encode(),
    headers={'Content-Type':'application/json','X-Forwarded-For':'203.0.113.99'})
try:
    urllib.request.urlopen(req, timeout=5)
except Exception:
    pass
" </dev/null
read ip rid < <(sql "SELECT ip_address, IFNULL(request_id,'NULL') FROM weather_warning.audit_logs WHERE action='LOGIN_FAILED' AND reason='unknown user' ORDER BY created_at DESC, id DESC LIMIT 1;")
ck "audit_ip_xff" "$ip" 203.0.113.99
ck "audit_request_id" "$([ -n "$rid" ] && [ "$rid" != "NULL" ] && echo nonempty)" nonempty

echo "== L5. Redis 宕机返回 503 =="
docker compose stop redis >/dev/null 2>&1
ck "redis_down_login_503" "$(curl -s -m 20 -o /dev/null -w "%{http_code}" -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"analyst_demo\",\"password\":\"$DEMO_ANALYST_PASSWORD\"}")" 503
docker compose start redis >/dev/null 2>&1
sleep 6
ck "redis_up_login_200" "$(curl -s -m 20 -o /dev/null -w "%{http_code}" -X POST $BASE/api/v1/auth/login -H 'Content-Type: application/json' -d "{\"username\":\"analyst_demo\",\"password\":\"$DEMO_ANALYST_PASSWORD\"}")" 200

# 清理测试预警
sql "SET @w=(SELECT id FROM weather_warning.warnings WHERE public_id='$WID'); SET @r=(SELECT warning_result_id FROM weather_warning.warnings WHERE id=@w); SET @f=(SELECT fusion_run_id FROM weather_warning.warning_results WHERE id=@r); DELETE FROM weather_warning.warning_reviews WHERE warning_id=@w; DELETE FROM weather_warning.warnings WHERE id=@w; DELETE FROM weather_warning.warning_results WHERE id=@r; DELETE FROM weather_warning.fusion_runs WHERE id=@f;"

echo "=============================="
echo "RESULT: PASS=$PASS FAIL=$FAIL"
[ "$FAIL" -eq 0 ]
