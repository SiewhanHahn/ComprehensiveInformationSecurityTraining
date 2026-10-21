-- MySQL 初始化参考模板（MVP）。
-- 库和账号由官方镜像的 entrypoint 通过 MYSQL_DATABASE / MYSQL_USER / MYSQL_PASSWORD 自动创建；
-- 本文件仅用于核对字符集与权限基线，不创建 localhost 专用账号，也不写死密码。
--
-- MVP 账号策略：
--   root           仅用于容器初始化/管理，不暴露给应用；
--   weather_app    应用与迁移共用的库级账号（官方镜像授予目标库 ALL 权限）；
--   迁移账号/运行账号的进一步分离、审计表只读等是后续加固项，不在 MVP 首版实现。

SELECT 'weather_warning' AS db_name, @@version AS mysql_version,
       @@character_set_server AS charset, @@time_zone AS time_zone;
