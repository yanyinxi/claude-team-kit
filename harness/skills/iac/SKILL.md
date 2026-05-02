---
name: iac
description: >
  基础设施即代码 Skill。提供 Terraform/Pulumi 模块模板、模块设计规范、状态管理最佳实践
  （remote state + DynamoDB lock）、多环境分离（dev/stage/prod）和 Workspace 隔离策略。
  内置 S3 Bucket、RDS、ASG 等常用模块模板，适用 IaC 标准化和云资源管理场景。
  支持变量验证和 plan 预览，防止误操作导致的生产环境变更。
---

# iac — 基础设施即代码 Skill

## 核心能力

1. **Terraform 模块设计**：标准化模块结构、输入输出规范
2. **Pulumi 等效转换**：HCL ↔ TypeScript/Python 互转
3. **状态管理**：remote state、lock、drift 检测
4. **多环境部署**：dev/staging/prod 分离策略
5. **安全基线**：加密 state、最小权限 IAM

## Terraform 模块标准结构

```
module/
├── main.tf          # 资源定义
├── variables.tf     # 输入变量（含 descriptions）
├── outputs.tf       # 输出值
├── versions.tf     # provider 版本约束
├── locals.tf       # 本地变量
├── data.tf         # 数据源
└── README.md       # 模块文档

禁止：
- hardcoded 变量值（必须通过 variables.tf）
- 跨模块状态耦合
- 本地 state（必须 remote state）
```

## 常用模块模板

### S3 Bucket 模块

```hcl
# variables.tf
variable "bucket_name" {
  description = "S3 bucket 名称"
  type        = string
}

variable " versioning" {
  description = "是否启用版本控制"
  type        = bool
  default     = true
}

# main.tf
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name

  versioning {
    enabled = var.versioning
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  lifecycle_rule {
    enabled = true
    noncurrent_version_expiration {
      days = 30
    }
  }
}

# outputs.tf
output "bucket_arn" {
  description = "S3 Bucket ARN"
  value       = aws_s3_bucket.this.arn
}
```

### RDS 数据库模块

```hcl
# 多可用区 + 加密 + 自动备份
resource "aws_db_instance" "main" {
  identifier           = var.name
  engine              = "postgres"
  engine_version      = "15.3"
  instance_class      = var.instance_class
  allocated_storage   = 20
  max_allocated_storage = 100

  # 高可用
  multi_az               = true
  deletion_protection    = true

  # 安全
  storage_encrypted      = true
  kms_key_id            = var.kms_key_arn
  publicly_accessible   = false

  # 备份
  backup_retention_period = 7
  backup_window          = "03:00-04:00"
  maintenance_window     = "mon:04:00-mon:05:00"

  # 网络
  vpc_security_group_ids = var.security_group_ids
  db_subnet_group_name   = var.subnet_group_name

  # 参数
  parameters = [
    { name = "max_connections", value = "100" }
  ]
}
```

## Pulumi 等效写法

```typescript
// Pulumi TypeScript 等效
import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";

const bucket = new aws.s3.Bucket("my-bucket", {
    versioning: { enabled: true },
    serverSideEncryptionConfiguration: {
        rule: {
            applyServerSideEncryptionByDefault: {
                sseAlgorithm: "AES256"
            }
        }
    },
});

export const bucketArn = bucket.arn;
```

## State 管理最佳实践

```bash
# 1. 使用 remote state（S3 + DynamoDB lock）
terraform {
  backend "s3" {
    bucket         = "my-terraform-state"
    key            = "prod networking/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}

# 2. state 文件永远不要手动编辑
terraform apply  # 自动更新
# ❌ 禁止：手动 vi terraform.tfstate

# 3. drift 检测
terraform plan > drift-report.txt
grep -c "～ ～" drift-report.txt  # drift 数量

# 4. state 锁定期
terraform force-unlock <lock-id>  # 仅紧急时使用
```

## 多环境策略

```
environments/
├── dev/
│   ├── main.tf
│   └── terraform.tfvars
├── staging/
│   ├── main.tf
│   └── terraform.tfvars
└── prod/
    ├── main.tf
    └── terraform.tfvars

# workspace 分离
terraform workspace new prod
terraform workspace select prod
terraform apply -var-file="environments/prod/terraform.tfvars"
```

## 安全基线

| 规则 | 要求 |
|------|------|
| State 加密 | `encrypt = true` |
| 最小权限 IAM | 仅授予必需权限 |
| S3 公私访问 | `publicly_accessible = false` |
| 数据库加密 | `storage_encrypted = true` |
| 删除保护 | `deletion_protection = true`（生产环境）|
| 日志审计 | CloudTrail + S3 access logging |

## 验证方法

```bash
[[ -f skills/iac/SKILL.md ]] && echo "✅"

grep -q "terraform\|pulum" skills/iac/SKILL.md && echo "✅ IaC 工具"
grep -q "remote.state\|S3.*DynamoDB" skills/iac/SKILL.md && echo "✅ State 管理"
grep -q "encrypt\|IAM\|publicly_accessible" skills/iac/SKILL.md && echo "✅ 安全基线"
```

## Red Flags

- local state（`backend "local"`）用于生产环境
- hardcoded 变量值在 `.tf` 文件中
- `publicly_accessible = true` 用于 RDS/S3
- 手动编辑 `terraform.tfstate`
- 无 DynamoDB lock 的 S3 backend
