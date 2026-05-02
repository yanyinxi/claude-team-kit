---
name: data-engineer
description: >
  数据工程 Skill。提供 Spark ETL 模板、Airflow DAG 编排、数据质量检查规范、
  数据仓库建模（星型/雪花模型、SCD Type 2）、CDC 实时同步方案。
  内置 SparkETL、DataQualityCheck 类模板和 Debezium + Kafka 配置，适用数据管道开发和数仓建设场景。
---

# data-engineer — 数据工程 Skill

## 核心能力

1. **Spark ETL**：分布式数据处理、JOIN 优化、分区管理
2. **Airflow DAG**：任务编排、依赖管理、失败重试
3. **数据质量**：Schema 校验、空值处理、异常检测
4. **数仓建模**：星型/雪花模型、维度表、事实表
5. **CDC 同步**：Debezium + Kafka 实时同步方案

## Spark ETL 模板

### 读写操作

```python
from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, lit, when, coalesce, to_date
from pyspark.sql.types import StructType
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class SparkETL:
    def __init__(self, app_name: str = "etl-job"):
        self.spark = (
            SparkSession.builder
            .appName(app_name)
            .config("spark.sql.adaptive.enabled", "true")
            .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("WARN")

    def read_from_s3(
        self,
        path: str,
        format: str = "delta",
        schema: Optional[StructType] = None,
        partition_cols: Optional[list[str]] = None
    ) -> DataFrame:
        reader = self.spark.read.format(format).options(header="true", inferSchema="false")

        if schema:
            reader = reader.schema(schema)

        df = reader.load(path)

        if partition_cols:
            for col_name in partition_cols:
                df = df.withColumn(col_name, to_date(col(col_name)))

        logger.info(f"Read {df.count()} rows from {path}")
        return df

    def write_to_s3(
        self,
        df: DataFrame,
        path: str,
        format: str = "delta",
        partition_cols: Optional[list[str]] = None,
        mode: str = "overwrite"
    ):
        writer = df.write.format(format).mode(mode).options(header="true")

        if partition_cols:
            writer = writer.partitionBy(*partition_cols)

        writer.save(path)
        logger.info(f"Written to {path}")

    def upsert(
        self,
        df: DataFrame,
        target_path: str,
        merge_key: list[str]
    ):
        """Delta Lake MERGE INTO 实现 SCD Type 2"""
        df.createOrReplaceTempView("source")

        self.spark.sql(f"""
            MERGE INTO delta.`{target_path}` AS target
            USING source AS src
            ON {" AND ".join([f"target.{k} = src.{k}" for k in merge_key])}
            WHEN MATCHED AND src.is_deleted = true THEN
                DELETE
            WHEN MATCHED AND src.active = false THEN
                UPDATE SET
                    end_date = current_date(),
                    active = false
            WHEN NOT MATCHED THEN
                INSERT *
        """)
```

### 数据质量检查

```python
from great_expectations import GreatExpectations
from great_expectations.dataset import SparkDFDataset

class DataQualityCheck:
    def __init__(self, context_path: str = ".ge/"):
        self.context = GreatExpectations.get_context(context_root_dir=context_path)
        self.gx_logger = self.context.get_or_create_data_context()

    def validate(
        self,
        df: DataFrame,
        expectations_file: Optional[str] = None
    ) -> dict:
        gx_df = SparkDFDataset(df)

        if expectations_file and self.context.file_exists(expectations_file):
            batch_kwargs = {"dataset": df}
            batch = self.context.get_batch(
                batch_kwargs=batch_kwargs,
                batch_request={"datasource_name": "ds", "data_asset_name": "validation"}
            )
            results = self.context.run_validation_operator(
                "action_list_operator",
                assets_to_validate=[batch],
                run_name="etl_validation"
            )
        else:
            # 内联期望
            results = gx_df.validate(
                expectations=[
                    {"expectation_type": "expect_column_to_not_be_null", "kwargs": {"column": "id"}},
                    {"expectation_type": "expect_column_values_to_be_unique", "kwargs": {"column": "id"}},
                    {"expectation_type": "expect_column_value_lengths_to_be_between",
                     "kwargs": {"column": "email", "min_value": 5, "max_value": 100}},
                    {"expectation_type": "expect_column_derivative_to_be_within_threshold",
                     "kwargs": {"column": "amount", "max_abs_threshold": 1000}}
                ]
            )

        if not results["success"]:
            raise ValueError(f"Data quality check failed: {results['results']}")

        return results
```

## Airflow DAG 模板

```python
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.dummy import DummyOperator
from airflow.providers.amazon.aws.operators.emr import EMROperatorCreateJobFlow
from airflow.providers.amazon.aws.sensors.emr import EMRJobFlowSensor

default_args = {
    "owner": "data-team",
    "depends_on_past": False,
    "start_date": datetime(2026, 5, 1),
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(hours=1),
    "on_failure_callback": lambda ctx: send_alert(ctx),
}

dag = DAG(
    "etl_user_events",
    default_args=default_args,
    schedule_interval="0 */6 * * *",  # 每6小时
    catchup=False,
    max_active_runs=1,
    tags=["etl", "user-events"],
)

start = DummyOperator(task_id="start", dag=dag)
end = DummyOperator(task_id="end", dag=dag)

def check_data_quality(**context):
    """数据质量检查，决定后续分支"""
    ti = context["ti"]
    result = ti.xcom_pull(task_ids="validate_data")

    if result["passed"]:
        return "run_transform"
    else:
        return "send_alert"

validate = PythonOperator(
    task_id="validate_data",
    python_callable=validate_data_quality,
    dag=dag,
)

branch = BranchPythonOperator(
    task_id="branch_decision",
    python_callable=check_data_quality,
    dag=dag,
)

transform = PythonOperator(
    task_id="run_transform",
    python_callable=run_spark_job,
    op_kwargs={"job_name": "user_events_transform"},
    dag=dag,
)

load = PythonOperator(
    task_id="load_to_warehouse",
    python_callable=load_to_redshift,
    dag=dag,
)

send_alert = PythonOperator(
    task_id="send_alert",
    python_callable=send_alert_slack,
    dag=dag,
)

start >> validate >> branch
branch >> transform >> load >> end
branch >> send_alert >> end
```

## 数仓建模

### 星型模型模板

```sql
-- 事实表：用户交易事实表
CREATE TABLE dw.fact_user_transactions (
    transaction_id    BIGINT PRIMARY KEY,
    user_id           BIGINT NOT NULL,
    product_id        BIGINT NOT NULL,
    store_id          BIGINT NOT NULL,
    date_id           INT NOT NULL,
    transaction_date  TIMESTAMP NOT NULL,
    amount            DECIMAL(12, 2) NOT NULL,
    quantity           INT NOT NULL,
    discount          DECIMAL(12, 2) DEFAULT 0,
    is_cancelled      BOOLEAN DEFAULT FALSE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Slowly Changing Dimension Type 2
    effective_date    DATE NOT NULL,
    expiry_date       DATE DEFAULT '9999-12-31',
    is_current        BOOLEAN DEFAULT TRUE,

    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES dw.dim_users(user_id),
    CONSTRAINT fk_product FOREIGN KEY (product_id) REFERENCES dw.dim_products(product_id),
    CONSTRAINT fk_store FOREIGN KEY (store_id) REFERENCES dw.dim_stores(store_id),
    CONSTRAINT fk_date FOREIGN KEY (date_id) REFERENCES dw.dim_date(date_id)
) PARTITIONED BY (transaction_date)
DISTRIBUTED BY HASH(user_id)
SORT BY (transaction_date);

-- 维度表：用户维度
CREATE TABLE dw.dim_users (
    user_id           BIGINT PRIMARY KEY,
    email             VARCHAR(255) NOT NULL,
    full_name         VARCHAR(100),
    phone             VARCHAR(20),
    date_of_birth     DATE,
    registration_date DATE NOT NULL,
    tier              VARCHAR(20) DEFAULT 'standard',

    -- SCD Type 2
    effective_date    DATE NOT NULL,
    expiry_date       DATE DEFAULT '9999-12-31',
    is_current        BOOLEAN DEFAULT TRUE
);
```

## CDC 同步（Debezium + Kafka）

```yaml
# debezium-connector.json
{
  "name": "orders-cdc-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "database.hostname": "postgres-prod",
    "database.port": "5432",
    "database.user": "debezium",
    "database.password": "${secrets:debezium_password}",
    "database.dbname": "orders_db",
    "topic.prefix": "orders",
    "table.include.list": "public.orders,public.order_items",
    "plugin.name": "pgoutput",
    "transforms": "unwrap",
    "transforms.unwrap.type": "io.debezium.transforms.ExtractNewRecordState",
    "snapshot.mode": "initial",
    "tombstones.on.delete": false,
    "decimal.handling.mode": "double",
    "time.precision.mode": "adaptive"
  }
}
```

## 验证方法

```bash
[[ -f skills/data-engineer/SKILL.md ]] && echo "✅"

grep -q "Spark\|pyspark\|DataFrame" skills/data-engineer/SKILL.md && echo "✅ Spark ETL"
grep -q "Airflow\|DAG\|dag" skills/data-engineer/SKILL.md && echo "✅ 编排"
grep -q "SCD\|star.*schema\|dim.*fact" skills/data-engineer/SKILL.md && echo "✅ 数仓建模"
grep -q "Debezium\|CDC\|Kafka" skills/data-engineer/SKILL.md && echo "✅ CDC 同步"
```

## Red Flags

- Spark 任务无分区字段
- JOIN 无广播小表优化
- 无数据质量校验直接入库
- Airflow DAG 无失败重试
- 历史数据覆盖而非追加
- 数仓无 SCD Type 2 维表
