# Ubuntu Docker Compose 部署规划 V2

## 1. 目标与当前状态

本规划目标是在 Ubuntu 26.04 LTS 虚拟机上使用 Docker CE 与 Docker Compose 插件，并通过仓库根目录的 Dockerfile 和 Compose 配置，一键构建、初始化并启动前端、后端、MySQL 与 Redis。VM 项目目录规划为 `~/Projects/ComprehensiveInformationSecurityTraining`，通过 SSH 管理。

环境检查已确认目标 VM 为 Ubuntu 26.04 LTS、x86_64，`python3 --version` 报告 Python 3.14.4，Docker CE 29.7.2 与 Docker Compose 插件 5.5.0 已安装，`docker.service` 已启用。宿主机无需安装 MySQL；官方 `mysql:8.4.11` 容器镜像可用。MySQL、Redis 及项目容器尚未启动或验证。当前仓库尚无 Dockerfile、Compose 配置及前端工程；后端也仅为 FastAPI 骨架和研究脚本。Compose 服务设计与运行验收均待实现。`shawn` 已加入 `docker` 组，重新登录后可直接执行 Docker 命令；该组权限基本等价于 root，仅应限于本机开发 VM。

| 项目 | 当前状态 | 下一步 |
| --- | --- | --- |
| Docker CE | 29.7.2，已安装并运行 | 无需重复安装 |
| Docker Compose | 插件 5.5.0 | 用 `docker compose config` 校验配置 |
| docker 组 | `shawn` 已加入并验证 | 保持仅限本机开发 |
| MySQL 容器 | 未启动 | 编写 Compose 后首次启动 |
| Redis 容器 | 未启动 | 编写 Compose 并接入 Session/缓存 |
| 前端/后端容器 | 无 Dockerfile、无业务 API | 按 M1~M4 实现 |
| 测试与交付 | 测试报告模板已创建，尚无实测结果；无压缩包 | 按 `docs/test-report-v1.md` 留证 |

## 2. 目标环境与技术选型

- 主机：Ubuntu 26.04 LTS，x86_64；日常管理通过 SSH。
- 容器运行时：Docker CE（当前安装 29.7.2）；编排使用 Docker Compose 插件，命令统一为 `docker compose`（当前 v5.5.0）。
- 后端基础镜像：目标运行时为 Python 3.14.4。截至 2026-10-20，Docker 官方 `python:3.14.4` 标签不可用（官方镜像提供 3.14.8），因此默认使用 `ubuntu:26.04` 基础镜像安装发行版 Python 3.14.4；构建后运行 `python3 --version` 核对实际版本。若改用官方 Python 镜像，只能使用 3.14.8，需明确记录该补丁版本差异。
- 版本核对注意：检查时 VM 的 `python3 --version` 报告 3.14.4，但 apt 包元数据中的 `python3` 为 `3.14.3-0ubuntu2`；容器构建和文档记录必须区分“解释器版本”与“发行版包版本”，以实际执行结果为准。
- 数据库：MySQL 8.4，固定官方 `mysql:8.4.11` 镜像（已确认该标签提供 amd64）；不依赖宿主机安装 MySQL。
- 缓存：Redis 8.10.2，使用官方 `redis:8.10.2` 镜像；实施构建时核实标签可拉取并固定镜像摘要。Redis 服务始终随 Compose 启动，用于服务端 Session 和可重建缓存，不作为权威数据存储。API 的 Session/Redis 集成尚未实现，集成前不得声称应用已在读写 Redis。
- 前端：独立前端 Dockerfile 构建静态资源，并由轻量 Web 服务容器提供；具体框架/工程目录确定后再定实现细节。
- 后端：根目录 `Dockerfile` 构建 FastAPI/Uvicorn 服务。容器以非 root 用户运行。
- 数据库迁移：独立的一次性 Compose 服务执行 Alembic；迁移成功后才启动 API。seed 为演示必需，幂等创建角色、数据源、教学阈值和演示账号，不写死通用默认密码。

## 3. 服务拓扑与一键启动

目标 Compose 服务：

| 服务 | 生命周期 | 职责 | 启动条件 |
| --- | --- | --- | --- |
| `mysql` | 长期运行 | MySQL 8.4 持久化业务数据 | 初始化配置齐全且健康检查通过 |
| `redis` | 长期运行 | 服务端 Session 与可重建缓存 | 健康检查通过；API 集成 Session 后作为强依赖 |
| `migrate` | 一次性 | 执行 `alembic upgrade head` | `mysql` healthy；失败非零退出 |
| `seed` | 一次性 | 幂等创建角色、数据源、阈值和演示账号（密码由本地配置提供） | 迁移成功；失败阻止 API 启动 |
| `api` | 长期运行 | FastAPI HTTP API | 数据库健康、迁移及必要 seed 成功 |
| `frontend` | 长期运行 | 提供前端页面并调用 API | 前端镜像构建成功；API 地址配置正确 |

根目录规划文件：

- `Dockerfile`：基于 `ubuntu:26.04` 安装 `python3`、`python3-venv`、`python3-pip`（目标 Python 3.14.4），安装锁定依赖并配置非 root 运行。
- `frontend/Dockerfile`（或前端工程对应位置）：构建并提供前端静态资源。
- `compose.yaml`：声明上述服务、私有网络、依赖健康状态、卷、环境变量和端口。
- `.dockerignore`：排除 `.env`、`.venv`、缓存数据、结果、字节码和版本控制目录。
- `.env.example`：仅列变量名和说明，不放真实凭据。

完成实现后的统一入口为：

```bash
docker compose up --build -d
```

首次启动的迁移/seed 应由 Compose 依赖关系保证先于 API 完成；任一初始化任务失败时 API 不应进入可服务状态。重复启动不得清空 MySQL 卷或重跑破坏性初始化。常用检查与停止：

```bash
docker compose ps
docker compose logs --tail=100 api frontend mysql redis migrate seed
docker compose down
```

以上命令是目标用法，当前尚不能执行验收，因为配置文件和镜像构建定义尚不存在。

## 4. 安装与准备流程

1. 通过 SSH 登录 Ubuntu VM，核对系统版本、磁盘空间及项目目录；已有目录或数据不得覆盖。
2. 由具有 sudo 权限的操作者交互安装 Docker CE（Docker Engine 官方仓库版，不使用 Ubuntu 的 `docker.io` 包）。国内网络优先使用阿里云 Docker CE 镜像；经核对，该镜像包含 Ubuntu 26.04 对应的 `resolute` suite，并提供 `docker-ce` 29.7.x。若镜像不可用，再回退 Docker 官方源。安装 `docker-ce`、`docker-ce-cli`、`containerd.io`、`docker-buildx-plugin`、`docker-compose-plugin`，然后验证 `docker version`、`docker compose version`。当前实际安装版本为 Docker CE 29.7.2、Compose 插件 5.5.0。

   ```bash
   sudo apt update
   sudo apt install -y ca-certificates curl
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
     -o /etc/apt/keyrings/docker.asc
   sudo chmod a+r /etc/apt/keyrings/docker.asc
   # 建议核对密钥指纹与 Docker 官方文档一致
   gpg --show-keys --with-fingerprint /etc/apt/keyrings/docker.asc

   sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
   Types: deb
   URIs: https://mirrors.aliyun.com/docker-ce/linux/ubuntu
   Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
   Components: stable
   Architectures: $(dpkg --print-architecture)
   Signed-By: /etc/apt/keyrings/docker.asc
   EOF

   sudo apt update
   sudo apt install -y docker-ce docker-ce-cli containerd.io \
     docker-buildx-plugin docker-compose-plugin
   sudo systemctl enable --now docker
   sudo docker run hello-world
   ```

   阿里云 Docker CE 镜像只解决 apt 软件包下载，不代理 Docker Hub 镜像。若拉取基础镜像失败，可配置阿里云容器镜像加速器（通常需要阿里云账号）或其他可信镜像源，并固定镜像摘要；不要使用来源不明的公共镜像。
3. 决定是否将 `shawn` 加入 `docker` 组。该组通常等价于主机 root 权限；若授权则需明确告知风险并重新登录生效，不应将其描述为低权限组。
4. 将代码放入 `~/Projects/ComprehensiveInformationSecurityTraining`，确认 `.env`、缓存、结果文件的同步范围；`.env` 不能传入镜像或提交仓库。
5. 实现并审查 Dockerfile、Compose、健康检查、迁移与前端构建，然后设置本机秘密配置。
6. 先运行 Compose 配置校验与构建，再首次启动；在测试环境验证迁移和数据持久化后再用于演示。

VM sudo 需要交互认证；不得将密码嵌入 SSH 命令、脚本、仓库或容器配置。未完成安装前，不声称 Docker Engine 或 Compose 已可用。

## 5. 网络、配置与凭据

- Compose 私有网络内通过服务名解析：后端连接 MySQL 主机 `mysql:3306`、Redis 主机 `redis:6379`，不得在容器内用 `localhost` 连接其他服务。
- MySQL 和 Redis 默认不发布宿主机端口。确需本机 GUI 调试时，仅临时绑定 `127.0.0.1` 并在使用后撤销。
- 演示环境对外仅发布必需入口，默认绑定 `127.0.0.1`；若需局域网访问，应先明确访问范围并配置防火墙与传输保护，不默认开放公网。
- `.env` 仅保留在 VM 并加入 `.gitignore`；真实密码和密钥不写入 Dockerfile、镜像层、SQL 示例、日志或文档。生产级秘密可改用 Docker secrets。
- MySQL root 凭据仅用于管理/初始化；API 不使用 root。MVP 采用单个库级账号 `weather_app`（官方镜像 grant ALL on 目标库），迁移与运行共用；迁移/运行账号分离、运行账号去除 DDL 权限、审计表只读是后续加固项，已在 `sql/init.sql` 注明。
- Redis 设置认证策略和网络隔离；只接受 Compose 内可信服务访问。缓存应设置容量上限与淘汰策略，不可把敏感数据无期限存入缓存。
- 环境变量不是专用秘密管理系统；不得分享含凭据的 `docker inspect`、Compose 展开配置或日志。

## 6. 数据持久化、备份与日志

- MySQL 使用命名卷（如 `mysql_data`）挂载 `/var/lib/mysql`，使用 InnoDB、utf8mb4 和 UTC。普通 `docker compose down` 保留数据；`down -v` 会删除卷，必须作为明确的破坏性操作，不用于日常重启。
- Redis 保存可过期的服务端 Session 和可重建缓存，不保存唯一业务事实；Redis 数据丢失会使用户重新登录，但不应丢失 MySQL 中的业务记录。若未来确需持久任务状态，再单独设计 AOF/RDB、卷和恢复要求。
- 研究数据 `data/cache`、`data/results` 不打入生产服务镜像。需要运行实验时通过受控只读挂载或单独实验环境提供，不与 MySQL 持久化卷混用。离线答辩应提供经许可检查的最小预报/标签样本和导入脚本；单靠 `data/results/pooled.json` 无法完成历史回放。
- MySQL 备份使用 `mysqldump` 逻辑导出到 VM 受限目录，按保留策略复制到独立备份位置；定期在隔离测试数据库验证恢复。恢复不得默认覆盖已有数据。
- 配置容器日志轮转/大小限制，禁止输出 DSN、密码、令牌或敏感请求内容。

## 7. 实现前需处理的项目问题

1. `backend/app/models.py`：复核 MySQL `DATETIME(6)`、主键无符号类型与 ORM 映射。
2. `User.roles`：显式指定 `user_roles` 多用户外键关联条件。
3. 初始 Alembic revision 应使用明确、可审查的迁移操作，不从未来变化的 ORM 模型调用 `create_all/drop_all`。
4. 完善 Alembic 模板和运行路径，验证在线迁移与必要的离线 SQL。
5. `seed.py` 提供幂等入口；不写入通用演示密码。
6. 教学风险等级与官方预警信号分开表达，避免把教学阈值描述为官方预警标准。
7. 检查 `requirements.txt` 与研究脚本依赖完整性（研究脚本使用 NumPy，但当前清单未列出），区分 API 镜像和实验运行依赖。
8. 配置加载应在应用/迁移运行时校验；健康检查仅捕获预期错误，不泄露凭据和堆栈。
9. 前端工程与 Redis 客户端/缓存用途尚未在仓库实现；添加 Compose 服务前先实现或明确最小可运行健康端点，不能用空壳服务伪装业务功能。

## 8. 计划新增/修改文件

| 文件 | 工作内容 |
| --- | --- |
| `Dockerfile` | 基于 `ubuntu:26.04` 的 Python 3.14.4 后端镜像、依赖安装、非 root 启动 |
| `frontend/Dockerfile` | 前端构建和静态资源服务（前端工程确定后） |
| `compose.yaml` | frontend、api、mysql、redis、migrate、seed 的编排 |
| `.dockerignore` | 排除秘密、数据缓存、虚拟环境与构建杂项 |
| `.gitignore`、`.env.example` | 忽略本机秘密并说明配置变量 |
| `requirements.txt` | 核实 API/研究依赖边界和可安装性 |
| `backend/app/config.py`、`db.py`、`models.py`、`seed.py` | 修复服务配置和启动问题 |
| `backend/migrations/` | 稳定、明确的 Alembic 迁移 |
| 前端工程配置 | 实际框架、API 地址和构建脚本确定后添加 |

本文件只规划以上工作，不表示这些文件已创建。

## 9. 验收顺序

1. 主机：确认 Ubuntu 26.04、Docker CE/Compose 插件可用；检查磁盘与服务启动状态。
2. 静态：Compose 配置校验、镜像构建、依赖安装、ORM mapper 加载、MySQL 方言编译、Alembic revision 检查。
3. 首次启动：空的测试卷启动；MySQL/Redis 健康；迁移与 seed 成功后 API 和前端 healthy。
4. 数据库：容器版本为 MySQL 8.4.x，核对 utf8mb4、UTC、表结构和最小权限账号；MySQL 不暴露不必要端口。
5. 缓存：验证 API 可连 Redis；停止/清空 Redis 后可安全重建缓存，权威业务数据不丢失。
6. 重复启动：运行同一条 Compose 命令，数据库数据保留、seed 幂等，不重复下载实验数据。
7. 故障：模拟错误凭据、数据库/Redis 不健康、迁移失败；依赖服务不得错误报告成功，日志不泄露秘密。
8. 入口与持久化：浏览器访问前端、前端调用 API；实际调用 `/health`、`/health/db`；数据库测试数据经重启仍在，备份在独立测试库恢复成功。

当前上述容器端到端验收全部待执行。Docker CE 与 Compose 已安装；前端、API、MySQL、Redis 容器和业务接口尚未实现或验证，测试报告仅为未填实测结果的模板。

## 10. 交付与压缩包

交付压缩包应能在一台装有 Docker 的 Ubuntu VM 上按 README 启动，不需要开发者手工安装 Python 依赖或 MySQL：

```text
ComprehensiveInformationSecurityTraining/
├── README.md              # 启动、停止、演示账号、常见故障
├── compose.yaml
├── Dockerfile
├── .env.example           # 仅占位符，不含真实密码
├── backend/
├── frontend/
├── docs/
├── sql/                   # 初始化/权限模板；真实密码由环境注入
└── data/results/          # 冻结的指标快照
```

若答辩要求断网回放，额外纳入经许可检查的最小预报/标签样本和导入脚本，README 写明导入步骤。仅有 `pooled.json` 指标快照不能支持单日四模式回放。

提交前检查：

- `docker compose config` 通过；`docker compose up --build -d` 后 `docker compose ps` 显示 MySQL/Redis/API/frontend 健康。
- `/health` 与 `/health/db` 可访问；前端能完成登录、回放、指标、预警流转演示。
- `docs/test-report-v1.md` 已填写 AT-01~06 的实测结果和证据位置。
- 压缩包不含 `.env`、真实密码、`.venv`、`data/cache/` 全量缓存、容器卷或本机 SSH 密钥。
- README 说明如何创建演示账号；不在文档或 seed 中写死通用密码。
