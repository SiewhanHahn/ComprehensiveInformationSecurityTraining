# C2 台风子项：版本与验收入口

本项只新增台风历史案例，C1 暴雨指标和回放源样本不变。**本地标签 `checkpoint/c2-typhoon` 仅在同一干净归档通过测试、迁移和浏览器验收后创建**，不可用 C1 或 `main` 替代。

```bash
git rev-parse 'checkpoint/c2-typhoon^{commit}'
git notes --ref=c2-acceptance show 'checkpoint/c2-typhoon^{commit}'
```

- 启动方法沿用[独立演示归档](user-guide-v1.md#defense)，将复查标签改为 `checkpoint/c2-typhoon`、项目改为 `rain-c2-demo`、`DEFENSE_PORT` 和版本检查地址改为 `18380`；保留 C1 的 18280 和历史环境。检查前端本身返回的 `/build-revision.txt`，不能只看健康检查。
- 写入测试只在独立 QA 环境（本项指定 `18381`），不同 Compose 项目、Redis/MySQL 卷和随机凭据。容器全量 pytest 启用 `RUN_INTEGRATION=1`；`tests/manual_c2_migration.py` 只接受空的 `c2_migration_<12位十六进制>` 数据库（主机 `mysql`）。切勿在 B/C1 演示库降级。
- 前端运行锁定依赖的 Node 回归与 Vite 构建。浏览器使用 `tests/browser_typhoon_acceptance.py --qa-url <QA回环地址> --expect-revision <同一完整SHA>`（需要设置 `BCHECK_ALLOW_WRITE=1` 和三个 QA 密码）。同一 QA 再回归 `tests/browser_defense.py` 与 `tests/browser_b_acceptance.py`。
- `0008` 可从 `0007` 升级并保留旧暴雨记录；非降水证据写入后不能直接往回退。首次构建镜像可联网，实例运行地与浏览器无需外网即可回放。案例是定点判断和一次对照，不是台风精度统计。
