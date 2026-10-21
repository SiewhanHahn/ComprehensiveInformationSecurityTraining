# 数据库设计说明书 V1

## 1. 数据库约束

- 数据库：MySQL 8.4（运行于 Docker 容器；目标补丁版本 8.4.x）。
- 默认字符集：`utf8mb4`。
- 默认排序规则：`utf8mb4_0900_ai_ci`。
- 时间：应用层统一使用 UTC，数据库使用 `DATETIME(6)` 保存业务时间。
- 降水、阈值、权重和指标：使用 `DECIMAL`，避免业务结果使用二进制浮点存储。
- 主键：使用 `BIGINT UNSIGNED AUTO_INCREMENT`，对外 API 不暴露可猜测的内部 ID 时应另设公开标识。
- 表引擎：InnoDB，启用外键和事务。
- 结构变更：Alembic 管理，不在应用启动时自动 `create_all`。

## 2. 枚举与状态

### 2.1 角色

- `ADMIN`：系统管理员
- `ANALYST`：气象分析员
- `REVIEWER`：预警审核员
- `VIEWER`：普通查看用户

### 2.2 预警状态

- `DRAFT`
- `PENDING_REVIEW`
- `REJECTED`
- `APPROVED`
- `PUBLISHED`
- `WITHDRAWN`

允许转换：

```text
DRAFT -> PENDING_REVIEW
PENDING_REVIEW -> APPROVED | REJECTED
REJECTED -> DRAFT
APPROVED -> PUBLISHED
PUBLISHED -> WITHDRAWN
```

数据库不单独依赖 `CHECK` 实现全部业务状态控制；状态转换必须在服务层查询当前行并在事务中校验。MySQL 8.4 的 `CHECK` 约束只用于字段值域的基础限制。

## 3. 表设计

以下 15 张表为 MVP 目标结构，覆盖暴雨端到端闭环；当前 ORM/迁移尚未通过真实 MySQL 验证，不表示已建表。其余七类灾种复用用户、角色、预警状态机、审批和审计结构，灾种专属指标字段通过后续迁移扩展，不把未实现字段写成已完成。

### 3.1 users

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 内部主键 |
| username | VARCHAR(64) | UNIQUE, NOT NULL | 登录名 |
| password_hash | VARCHAR(255) | NOT NULL | 密码摘要 |
| display_name | VARCHAR(100) | NOT NULL | 显示名 |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE | 账号状态 |
| failed_login_count | SMALLINT UNSIGNED | NOT NULL DEFAULT 0 | 连续失败次数 |
| locked_until | DATETIME(6) | NULL | 临时锁定到期 |
| created_at / updated_at | DATETIME(6) | NOT NULL | UTC 时间 |

索引：`uq_users_username`，`idx_users_active`。

### 3.2 roles

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| code | VARCHAR(32) | UNIQUE, NOT NULL | 角色代码 |
| name | VARCHAR(64) | NOT NULL | 中文名称 |
| created_at | DATETIME(6) | NOT NULL | 创建时间 |

### 3.3 user_roles

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| user_id | BIGINT UNSIGNED | PK/FK | 用户 |
| role_id | BIGINT UNSIGNED | PK/FK | 角色 |
| granted_by | BIGINT UNSIGNED | NULL/FK | 授权人 |
| granted_at | DATETIME(6) | NOT NULL | 授权时间 |

删除策略：用户或角色有业务记录时不物理删除，采用停用或撤销关联。

### 3.4 data_sources

记录 Open-Meteo、ERA5、NOAA GHCN-Daily 等来源。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| code | VARCHAR(64) | UNIQUE, NOT NULL | 来源代码 |
| name | VARCHAR(128) | NOT NULL | 来源名称 |
| data_type | VARCHAR(32) | NOT NULL | FORECAST/REANALYSIS/OBSERVATION |
| endpoint | VARCHAR(512) | NULL | 接口地址，不存密钥 |
| license_note | VARCHAR(500) | NULL | 许可说明 |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE | 是否启用 |
| created_at | DATETIME(6) | NOT NULL | 创建时间 |

### 3.5 datasets

记录一次导入或实验快照。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| source_id | BIGINT UNSIGNED | FK, NOT NULL | 数据源 |
| dataset_type | VARCHAR(32) | NOT NULL | FORECAST/ERA5_LABEL/GHCN_OBSERVATION |
| version | VARCHAR(100) | NOT NULL | 数据或实验版本 |
| period_start / period_end | DATE | NOT NULL | 覆盖日期 |
| row_count | INT UNSIGNED | NOT NULL DEFAULT 0 | 行数 |
| quality_status | VARCHAR(32) | NOT NULL | READY/PARTIAL/FAILED |
| imported_at | DATETIME(6) | NOT NULL | 导入时间 |
| checksum | CHAR(64) | NULL | 内容校验摘要 |

唯一建议：`source_id, dataset_type, version`。

### 3.6 forecast_records

每行表示某城市、某有效时间、某模式和提前量的预报值。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| dataset_id | BIGINT UNSIGNED | FK, NOT NULL | 所属数据集 |
| city_code | VARCHAR(32) | NOT NULL | 城市代码 |
| model_code | VARCHAR(32) | NOT NULL | ECMWF/GFS/ICON/GEM |
| valid_at | DATETIME(6) | NOT NULL | 预报有效时间 UTC |
| lead_hours | SMALLINT UNSIGNED | NOT NULL | 提前量，MVP 为 24 |
| precipitation_mm | DECIMAL(10,3) | NULL | 预报降水 |
| is_complete | BOOLEAN | NOT NULL DEFAULT TRUE | 数据完整性 |
| created_at | DATETIME(6) | NOT NULL | 入库时间 |

唯一键：`dataset_id, city_code, model_code, valid_at, lead_hours`。
索引：`city_code, valid_at, lead_hours`。

### 3.7 observation_records

支持 ERA5 代理标签和 GHCN 独立观测，但通过 `observation_type` 严格区分。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| dataset_id | BIGINT UNSIGNED | FK, NOT NULL | 数据集 |
| city_code | VARCHAR(32) | NULL | 匹配城市 |
| station_code | VARCHAR(64) | NULL | 观测站 |
| observation_type | VARCHAR(32) | NOT NULL | ERA5_PROXY/GHCN_DAILY |
| observed_date | DATE | NOT NULL | 观测日期 |
| precipitation_mm | DECIMAL(10,3) | NULL | 日累计降水 |
| quality_flag | VARCHAR(32) | NULL | 质量标记 |
| created_at | DATETIME(6) | NOT NULL | 入库时间 |

唯一键：`dataset_id, city_code, observed_date, observation_type`（命名 `uq_obs_city_date_type`）。ERA5 代理标签按城市去重；GHCN 站点观测因多站共城，接入时需另建 `station_code` 维度的去重键，不能复用本键。

### 3.8 fusion_runs

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| algorithm_version | VARCHAR(64) | NOT NULL | 算法版本 |
| method | VARCHAR(32) | NOT NULL | EQUAL_MEAN 等 |
| lead_hours | SMALLINT UNSIGNED | NOT NULL | 提前量 |
| weights_json | JSON | NOT NULL | 模式权重 |
| input_count | SMALLINT UNSIGNED | NOT NULL | 输入模式数 |
| status | VARCHAR(32) | NOT NULL | SUCCESS/PARTIAL/FAILED |
| executed_at | DATETIME(6) | NOT NULL | 执行时间 |
| created_by | BIGINT UNSIGNED | NULL/FK | 操作者 |

### 3.9 fusion_inputs

追溯一次融合使用的原始预报。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| fusion_run_id | BIGINT UNSIGNED | PK/FK | 融合批次 |
| forecast_record_id | BIGINT UNSIGNED | PK/FK | 原始输入 |
| model_code | VARCHAR(32) | NOT NULL | 冗余便于查询 |
| value_mm | DECIMAL(10,3) | NOT NULL | 输入值 |

### 3.10 warning_thresholds

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| hazard_type | VARCHAR(32) | NOT NULL DEFAULT 'RAINSTORM' | 灾种代码；MVP 为 RAINSTORM |
| code | VARCHAR(32) | NOT NULL | LIGHT/MODERATE/HEAVY |
| threshold_mm | DECIMAL(10,3) | NOT NULL | 24 小时阈值 |
| level | VARCHAR(16) | NOT NULL | 教学风险等级（BLUE/YELLOW/ORANGE/RED，仅界面可视化分级，不代表官方预警信号） |
| is_active | BOOLEAN | NOT NULL DEFAULT TRUE | 是否启用 |

> 注意：`level` 的色码仅是教学演示用的风险分级标识，对应 10/25/50mm 的日累计阈值，**不代表国家气象台官方蓝/黄/橙/红预警发布标准**。MVP 的 `threshold_mm` 是暴雨专用字段；扩展到其他灾种时需增加指标代码/单位等字段，不能直接复用毫米阈值。唯一键为 `hazard_type, code`。

### 3.11 warning_results

保存一次回放或计算结果，不等于已发布预警。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| fusion_run_id | BIGINT UNSIGNED | FK, NOT NULL | 融合运行 |
| threshold_id | BIGINT UNSIGNED | FK, NOT NULL | 阈值 |
| city_code | VARCHAR(32) | NOT NULL | 城市 |
| valid_date | DATE | NOT NULL | 有效日期 |
| fused_mm | DECIMAL(10,3) | NOT NULL | 融合累计 |
| baseline_mm | DECIMAL(10,3) | NULL | 基线值 |
| proxy_label_mm | DECIMAL(10,3) | NULL | ERA5 标签，可空 |
| risk_level | VARCHAR(16) | NULL | 达到所选教学阈值时的等级；未达阈值为 NULL |
| data_status | VARCHAR(32) | NOT NULL | COMPLETE/PARTIAL |
| created_at | DATETIME(6) | NOT NULL | 创建时间 |

`warning_results` 当前字段是暴雨专用（`fused_mm`、`baseline_mm`、`proxy_label_mm`）。扩展其他灾种时应新增通用指标代码/单位/结果字段或按灾种拆分结果表，不能把毫米字段解释为所有灾种的通用结果。

### 3.12 warnings

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| public_id | CHAR(26) | UNIQUE, NOT NULL | 对外不可猜测标识 |
| warning_result_id | BIGINT UNSIGNED | FK, NOT NULL | 计算结果 |
| hazard_type | VARCHAR(32) | NOT NULL DEFAULT 'RAINSTORM' | 灾种代码；MVP 为 RAINSTORM |
| created_by | BIGINT UNSIGNED | FK, NOT NULL | 分析员 |
| status | VARCHAR(32) | NOT NULL | 状态机状态 |
| title | VARCHAR(200) | NOT NULL | 标题 |
| area_text | VARCHAR(500) | NOT NULL | 影响区域 |
| impact_text | TEXT | NULL | 影响说明 |
| reasoning_text | TEXT | NOT NULL | 研判依据 |
| version_no | INT UNSIGNED | NOT NULL DEFAULT 1 | 版本 |
| submitted_at / approved_at / published_at / withdrawn_at | DATETIME(6) | NULL | 状态时间 |
| published_by / withdrawn_by | BIGINT UNSIGNED | NULL/FK | 发布人/撤回人，与状态时间戳配套追溯 |
| created_at / updated_at | DATETIME(6) | NOT NULL | 时间 |

### 3.13 warning_reviews

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| warning_id | BIGINT UNSIGNED | FK, NOT NULL | 预警 |
| reviewer_id | BIGINT UNSIGNED | FK, NOT NULL | 审核人 |
| decision | VARCHAR(16) | NOT NULL | APPROVE/REJECT |
| comment | VARCHAR(1000) | NOT NULL | 审核意见 |
| created_at | DATETIME(6) | NOT NULL | 时间 |

### 3.14 warning_feedback

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| warning_id | BIGINT UNSIGNED | FK, NOT NULL | 预警 |
| created_by | BIGINT UNSIGNED | FK, NOT NULL | 操作者 |
| response_status | VARCHAR(32) | NOT NULL | RECEIVED/PROCESSING/COMPLETED |
| content | TEXT | NOT NULL | 反馈 |
| created_at | DATETIME(6) | NOT NULL | 时间 |

MVP 中反馈只做追加记录、展示和审计，不自动回流训练模型或修改阈值。若后续要形成模型反馈闭环，必须新增反馈批次、样本版本和审核状态，不能直接用反馈文本覆盖或重训生产结果。

### 3.15 audit_logs

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED | PK | 主键 |
| actor_id | BIGINT UNSIGNED | NULL/FK | 操作者，系统动作可为空 |
| actor_role | VARCHAR(32) | NULL | 动作时角色快照 |
| action | VARCHAR(64) | NOT NULL | 动作代码 |
| resource_type | VARCHAR(64) | NOT NULL | 资源类型 |
| resource_id | VARCHAR(64) | NULL | 资源标识 |
| result | VARCHAR(16) | NOT NULL | SUCCESS/DENIED/FAILED |
| reason | VARCHAR(500) | NULL | 原因 |
| request_id | CHAR(36) | NULL | 请求关联 |
| ip_address | VARCHAR(45) | NULL | IPv4/IPv6 |
| created_at | DATETIME(6) | NOT NULL | UTC 时间 |

索引：`created_at`、`actor_id, created_at`、`resource_type, resource_id`。

## 4. 事务与约束

- 预警状态变更使用 `SELECT ... FOR UPDATE` 锁定预警行，校验状态后更新。
- 审批必须检查审核员不是 `created_by`。
- 预警状态更新、审核记录和成功审计日志同一事务提交。
- 任何异常回滚业务更新和审计成功记录。
- 审计日志不提供删除和更新接口。
- 数据导入使用批次 ID；失败批次标记 `FAILED`，不把部分数据标记为 `READY`。
- 外键使用 `RESTRICT` 保护原始数据和审计关联；账号采用停用而非物理删除。

## 5. 初始化角色与数据源

角色：`ADMIN`、`ANALYST`、`REVIEWER`、`VIEWER`。

数据源：

- `OPEN_METEO_PREVIOUS_RUNS`：FORECAST
- `OPEN_METEO_ERA5`：REANALYSIS
- `NOAA_GHCN_DAILY`：OBSERVATION

不在初始化脚本中写入真实账号密码；演示账号由 seed 命令使用环境变量或交互方式创建。
