from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Alembic Autogenerate 配置 ---
# 1. 导入项目的 Base
from core.models.base import Base
# 2. 导入所有模型模块，以便 Base.metadata 知道它们
#    假设 alembic.ini 中设置了 prepend_sys_path = .
from core.models import user, subscription, task, billing, node, admin, log, notification

# 3. 设置 target_metadata
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata
# --- 添加调试打印 --- 
print(f"[Alembic env.py DEBUG] Target metadata tables: {list(target_metadata.tables.keys())}")
# -------------------
# ------------------------------------

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # --- 确保 engine_from_config 可以工作 ---
    # engine_from_config 从 alembic.ini 读取配置并创建引擎
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool, # 对于迁移通常不需要连接池
    )

    with connectable.connect() as connection:
        # 4. 确保 context.configure 包含 target_metadata
        context.configure(
            connection=connection, 
            target_metadata=target_metadata # 需要这个才能自动生成
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
