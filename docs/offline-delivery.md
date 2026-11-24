# 终验与离线启动

**这是教学项目。** 四个重点灾种支持受控的研判与正式演练流程；四个基础试算不入库、不制单。以下现场路线不需要现取天气数据，但须在有网时预先取得镜像、源码和样本，且环境已安装 Docker Compose V2。

## 1. 核对交付文件

- 同一验收 SHA 的 `weather-course-source-<SHA10>.tar.gz` 与 Linux 镜像包 `weather-course-images-<SHA10>.tar.gz`；核对同目录 `SHA256SUMS.txt`。Win PowerShell 可用 `Get-FileHash <文件>`，GNU 工具可用 `sha256sum -c SHA256SUMS.txt`。
- 解包到**新目录**，不复制其他环境的 `.env` 或数据库卷。测试用镜像是 `linux/amd64`。在解包目录使用 Docker Linux 容器运行；别覆盖原有 B/C 演示。
- 从 `.env.example` 建 `.env`，为各变量生成独立随机值；为验收现场记录 `DEFENSE_PORT`（空闲回环端口）、`DELIVERY_REVISION`（验收完整 SHA）。不要把真实密码录入 PPT、截图或交付包。

## 2. 从已准备的镜像启动

```bash
docker load -i weather-course-images-<SHA10>.tar.gz
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml config -q
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml up -d --no-build --pull never
docker compose -p weather-course-demo -f compose.yaml -f compose.defense.yaml -f compose.offline.yaml ps
```

镜像包包含同 SHA 的应用/Nginx 构建、MySQL 和 Redis；种子与迁移复用应用镜像。缺镜像时应报错，不会联网拉取或就地重建。可换 `-p` 项目名，为每次验收新建 MySQL 卷。浏览器打开 `http://127.0.0.1:<DEFENSE_PORT>`，检查 `/build-revision.txt` 等于完整 SHA，检查 `/health`、`/health/db`、`/health/redis` 后再进入。若版本不符，停止写入。对既有演示不要运行 `down -v`。

## 3. 演示与验收

1. [九城同样本指标与数据年份](data-and-method.md)：解释 2024/2025/2026 分期、固定 24 h、ERA5 代理，10 mm/24 h 的 F1 不是严重暴雨准确率。
2. 按[操作指南](user-guide-v1.md)手算长沙、更换南京样例、跑坏文件，再展示台风、雪灾、雷电历史案例及事后核对。
3. [基础试算](user-guide-v1.md#basic-forecast)逐项改输入：干旱第 5 天 1.00 mm，高温 34.9→35.0，低温 0.1→0.0，风雹分别试算真实布尔值与缺测。证明结论可变，基础路径不会生成预警。
4. 仅在一次性 QA 库，按 B 流程用不同身份驳回、改稿重提、审批发布、响应反馈和查看审计；演示实例与集成测试的写入权限不能混用。

**安全与许可**：分发源码与镜像时剔除 `.env`、私钥、缓存、数据库卷；第三方资料不自动受项目代码许可证约束。项目负责人确认开源许可之前，不执行最终推送。
