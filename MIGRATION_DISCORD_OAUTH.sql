-- MySQL 数据库迁移脚本
-- 执行方式: mysql -u root -p dbname < MIGRATION_DISCORD_OAUTH.sql
--
-- 注意：discord_id 不设 UNIQUE 约束，MySQL 8.0.16+ 才支持多 NULL 唯一索引。
--       项目已启用启动时 auto_migrate，首次部署会自动完成此迁移，无需手动执行。
-- 如需手动迁移，请在已有数据前备份数据库。

-- 为 users 表添加 Discord OAuth 字段
ALTER TABLE users ADD COLUMN discord_id VARCHAR(30) NULL;
ALTER TABLE users ADD COLUMN discord_username VARCHAR(100) NULL;
-- 如需唯一约束（MySQL 8.0.16+）：
-- ALTER TABLE users ADD UNIQUE INDEX uk_discord_id (discord_id);
