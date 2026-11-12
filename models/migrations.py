import logging
from sqlalchemy import text
from models.database import engine, Base

logger = logging.getLogger(__name__)


def _column_type_to_mysql(col) -> str:
    """将 SQLAlchemy Column 转换为 MySQL DDL 类型字符串。"""
    t = col.type
    typ_name = type(t).__name__
    length = getattr(t, "length", None)

    # Boolean -> TINYINT(1)
    if typ_name == "Boolean":
        return "TINYINT(1)"

    # String(n) -> VARCHAR(n)
    if typ_name == "String" and length:
        return f"VARCHAR({length})"

    # Text -> TEXT
    if typ_name == "Text":
        return "TEXT"

    # Integer -> INTEGER
    if typ_name == "Integer":
        return "INTEGER"

    # Float -> DOUBLE PRECISION
    if typ_name == "Float":
        return "DOUBLE PRECISION"

    # Fallback: TypeName(length) or TypeName
    if length:
        return f"{typ_name}({length})"
    return typ_name


def _build_add_column_sql(table_name: str, col) -> str:
    """生成 ALTER TABLE ... ADD COLUMN ... DDL。"""
    nullable = "NULL" if col.nullable else "NOT NULL"
    default = ""
    if col.default is not None:
        dval = col.default.arg
        if dval is not None:
            if isinstance(dval, str):
                default = f" DEFAULT '{dval}'"
            elif isinstance(dval, bool):
                default = f" DEFAULT {1 if dval else 0}"
            else:
                default = f" DEFAULT {dval}"
    # nullable=True 时不加 UNIQUE（MySQL 的 UNIQUE+NULL 只允许一个 NULL 值）
    unique = " UNIQUE" if col.unique and not col.nullable else ""
    col_type = _column_type_to_mysql(col)
    return f"ALTER TABLE `{table_name}` ADD COLUMN `{col.name}` {col_type} {nullable}{default}{unique}"


async def auto_migrate():
    """启动时自动检测表结构差异并执行增量迁移。

    - 新建缺失表：由 init_db 中的 create_all 处理，本函数跳过。
    - 新增列：检测缺失列并执行 ALTER TABLE ADD COLUMN（支持 UNIQUE）。
    - 新增索引：检测缺失索引并执行 ALTER TABLE ADD INDEX。
    幂等安全，重复执行无副作用。
    """
    dialect_name = engine.dialect.name
    table_names = list(Base.metadata.tables.keys())
    migrations = []

    # 通过 information_schema / PRAGMA 读取数据库实际结构
    if dialect_name == "mysql":
        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT TABLE_NAME, COLUMN_NAME "
                "FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE()"
            ))
            col_rows = result.fetchall()

        db_columns: dict = {}   # table -> {col_name}
        for tbl, col in col_rows:
            db_columns.setdefault(tbl, set()).add(col)

        # MySQL 索引名从 information_schema.STATISTICS 读取，避免误判已存在索引为缺失
        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT TABLE_NAME, INDEX_NAME "
                "FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = DATABASE()"
            ))
            idx_rows = result.fetchall()

        db_indexes: dict = {}   # table -> {index_name}
        for tbl, idx_name in idx_rows:
            db_indexes.setdefault(tbl, set()).add(idx_name)
    else:
        # SQLite 兼容路径（PRAGMA 需在 sync 上下文中执行）
        db_columns = {}
        db_indexes = {}

        async with engine.begin() as conn:
            def _collect(pragma_conn):
                for tbl in table_names:
                    try:
                        cols = pragma_conn.execute(text(f"PRAGMA table_info(`{tbl}`)")).fetchall()
                        db_columns[tbl] = {c[1] for c in cols}

                        # 只取索引名（用于判断 ORM 定义的索引是否已存在）
                        indexes = pragma_conn.execute(text(f"PRAGMA index_list(`{tbl}`)")).fetchall()
                        db_indexes[tbl] = {idx[1] for idx in indexes}
                    except Exception:
                        pass
            await conn.run_sync(_collect)

    for table_name in table_names:
        if table_name not in db_columns:
            continue  # create_all 负责新建表，跳过

        orm_table = Base.metadata.tables[table_name]
        existing_cols = db_columns[table_name]
        existing_idx_names = db_indexes.get(table_name, set())

        # 检测缺失列
        for col in orm_table.columns:
            col_name = col.name
            if col_name not in existing_cols:
                sql = _build_add_column_sql(table_name, col)
                migrations.append(sql)
                logger.info(f"[migration] {table_name}: ADD COLUMN `{col_name}`")

        # 检测缺失索引：ORM 定义了但该索引名在数据库中不存在
        for idx in orm_table.indexes:
            idx_name = idx.name
            if idx_name not in existing_idx_names:
                # 注意必须用 c.name：Column.__str__() 返回 "表名.列名"，
                # MySQL 索引列清单不允许表限定名（会报 1072）
                cols_str = ",".join(f"`{c.name}`" for c in idx.columns)
                mig_sql = f"ALTER TABLE `{table_name}` ADD INDEX `{idx_name}` ({cols_str})"
                migrations.append(mig_sql)
                logger.info(f"[migration] {table_name}: ADD INDEX `{idx_name}`")

    if migrations:
        logger.info(f"Applying {len(migrations)} schema migration(s)...")
        applied = 0
        skipped = 0
        async with engine.begin() as conn:
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                    applied += 1
                except Exception as e:
                    err_code = None
                    orig = getattr(e, "orig", None)
                    if orig is not None:
                        err_code = orig.args[0] if orig.args else None
                    # 幂等容错：对象已存在时跳过，其余错误中断
                    if err_code in (1060, 1061, 1091):
                        logger.warning(f"[migration] skipped (already exists): {sql}")
                        skipped += 1
                        continue
                    logger.error(f"Schema migration failed: {e}")
                    raise
        logger.info(
            f"Schema migration completed ({applied} applied, {skipped} skipped)"
        )
    else:
        logger.info("Schema migration: no changes needed")
