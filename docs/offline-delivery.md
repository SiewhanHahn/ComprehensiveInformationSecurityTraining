# 终验与离线启动

**这是教学项目。** 四个重点灾种支持受控的研判与正式演练流程；四个基础试算不入库、不制单。以下现场路线不需要现取天气数据，但须在有网时预先取得镜像、源码和样本，且环境已安装兼容的 Docker。实测平台为 **Docker Engine 29.7.2（Linux/amd64）和 Docker Compose 5.5.0**。出发前先运行 `docker version`、`docker compose version` 和下方 `config -q`；`!override`、`!reset` 或 `gw_priority` 不兼容时先更新并重验，勿等断网后修复。

## 1. 核对交付文件

- 同一验收 SHA 的 `weather-course-source-<SHA10>.tar.gz` 与 Linux 镜像包 `weather-course-images-<SHA10>.tar.gz`；核对同目录 `SHA256SUMS.txt`。Win PowerShell 可用 `Get-FileHash <文件>`，GNU 工具可用 `sha256sum -c SHA256SUMS.txt`。
- 解包到**新目录**，不复制其他环境的 `.env` 或数据库卷。测试用镜像是 `linux/amd64`。在解包目录使用 Docker Linux 容器运行；别覆盖原有 B/C 演示。
- 从 `.env.example` 建 `.env`，为各变量生成独立随机值；为验收现场记录 `DEFENSE_PORT`（空闲回环端口）、`DELIVERY_REVISION`（验收完整 SHA）。不要把真实密码录入 PPT、截图或交付包。

## 2. 从已准备的镜像启动

```bash
docker load -i /path/to/weather-course-images-<SHA10>.tar.gz
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml config -q
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml up -d --no-build --pull never
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml ps
```

镜像包包含同 SHA 的应用/Nginx 构建、MySQL 和 Redis；种子与迁移复用应用镜像。缺镜像时应报错，不会联网拉取或就地重建。上述 `weather-course-demo` 只供演示；做写入验收必须按下一节新建 QA 项目和 MySQL 卷，不能复用演示库。浏览器打开 `http://127.0.0.1:<DEFENSE_PORT>`，检查 `/build-revision.txt` 等于完整 SHA，检查 `/health`、`/health/db`、`/health/redis` 后再进入。若版本不符，停止写入。对既有演示不要运行 `down -v`。

<a id="qa-preflight"></a>
## 3. 写入验收的 QA 前置检查

先准备空闲的回环端口（填入 `.env` 的 `DEFENSE_PORT`），选择全新的 QA 项目名并确认它未关联任何现有容器或卷。`image-identities.json` 随匹配的镜像包交付，记录保存时的 API 与前端镜像 ID。示例在 Docker 主机内执行；`REV` 为完整交付 SHA，按实际情况替换文件路径：

```bash
QA=weather-course-qa-run1
PORT=18589
REV='替换成完整验收SHA'
python tests/verify_offline_qa_target.py preflight --project "$QA" --port "$PORT" --revision "$REV" > "$QA-fresh.json" &&
  docker compose -p "$QA" -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml up -d --no-build --pull never &&
  curl -fsS --retry 5 --retry-all-errors "http://127.0.0.1:$PORT/health" > /dev/null &&
  python tests/verify_offline_qa_target.py verify --project "$QA" --port "$PORT" --revision "$REV" \
    --fresh-proof "$QA-fresh.json" --image-manifest /path/to/image-identities.json > "$QA-target.json"
```

这一命令链只有前置检查通过才允许启动，并在健康检查通过后运行 `verify`。失败时不要分开重跑 Compose。它核对回环映射、运行镜像 ID、当前 QA 专属 MySQL 卷和页面 SHA。给 `tests/browser_b_acceptance.py` 传 `--qa-proof "$QA-target.json" --expect-revision "$REV"`，并仅为该 QA 注入账号密码与 `BCHECK_ALLOW_WRITE=1`。若使用 SSH 回环转发，由验收启动器核对实际映射后在证明中补充测试用的 `test_url`。

## 4. 演示与验收

1. [九城同样本指标与数据年份](data-and-method.md)：解释 2024/2025/2026 分期、逐小时提前一天（非整日同次起报）、ERA5 代理，10 mm/24 h 的 F1 不是严重暴雨准确率。用回放样本讲清改善及反例（数值为 mm/24 h，不混入 2026 测试）：
   - 南宁 2024-02-04：ECMWF **10.5**、融合 **5.025**、ERA5 **2.5**，融合消除 10 mm 档误报。
   - 南昌 2024-02-05：ECMWF **9.7**、融合 **12.35**、ERA5 **8.3**，融合新增 10 mm 档误报。
2. 按[操作指南](user-guide-v1.md)手算长沙、更换南京样例、跑坏文件，再展示台风、雪灾、雷电历史案例及事后核对。
3. [基础试算](user-guide-v1.md#basic-forecast)逐项改输入：干旱第 5 天 1.00 mm，高温 34.9→35.0，低温 0.1→0.0，风雹分别试算真实布尔值与缺测。证明结论可变，基础路径不会生成预警。
4. 仅在一次性 QA 库，按 B 流程用不同身份驳回、改稿重提、审批发布、响应反馈和查看审计；演示实例与集成测试的写入权限不能混用。

**安全与许可**：分发源码与镜像时剔除 `.env`、私钥、缓存、数据库卷；第三方资料不自动受项目代码许可证约束。项目负责人确认开源许可之前，不执行最终推送。

## 正文版本迁移（0009）

升级前停写并备份，按新候选构建匹配的应用及迁移镜像，核对迁移头 `0009_warning_text_versions`。旧版 0008 验收包不包含历史正文入口。0009 不回填旧稿，仅在后续实际编辑时保存被替换的正文。

如需降级，**先停止全部写入并备份**，再通过在线 Alembic 连接检查；检查和删表不是一个原子操作。有快照会拒绝降级，不能清空历史绕过保护。需要回到旧版本时，在独立环境演练从升级前备份恢复，并明确恢复点之后的数据影响。
