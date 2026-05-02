---
name: ml-engineer
description: >
  机器学习工程 Skill。提供 ML 训练流程（PyTorch/TensorFlow）、特征工程规范、
  模型评估指标（accuracy/F1/ROC-AUC）、FastAPI 部署模板。
  内置 FeaturePipeline、Trainer 类模板和 MLflow 监控配置，适用 ML 模型开发和生产化部署场景。
---

# ml-engineer — 机器学习工程 Skill

## 核心能力

1. **数据管道**：特征工程、训练/验证/测试集划分
2. **模型训练**：PyTorch/TensorFlow、分布式训练、AutoML
3. **模型评估**：离线指标、在线 A/B 测试
4. **模型部署**：REST API、batch prediction、edge inference
5. **MLOps**：监控、漂移检测、模型回滚

## 数据管道

### 特征工程模板

```python
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from typing import Tuple

class FeaturePipeline:
    def __init__(self, numeric_cols: list[str], categorical_cols: list[str]):
        self.numeric_cols = numeric_cols
        self.categorical_cols = categorical_cols
        self.scalers: dict = {}
        self.encoders: dict = {}

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 数值特征：标准化
        for col in self.numeric_cols:
            scaler = StandardScaler()
            df[col] = scaler.fit_transform(df[[col]])
            self.scalers[col] = scaler

        # 类别特征：Label Encoding
        for col in self.categorical_cols:
            encoder = LabelEncoder()
            df[col] = encoder.fit_transform(df[col].astype(str))
            self.encoders[col] = encoder

        return df

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # 数值特征：标准化
        for col in self.numeric_cols:
            df[col] = self.scalers[col].transform(df[[col]])

        # 类别特征：Label Encoding
        for col in self.categorical_cols:
            # 处理未见过的类别
            known = set(self.encoders[col].classes_)
            df[col] = df[col].apply(
                lambda x: x if x in known else self.encoders[col].classes_[0]
            )
            df[col] = self.encoders[col].transform(df[col].astype(str))

        return df

def split_data(
    df: pd.DataFrame,
    target_col: str,
    test_size: float = 0.2,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    X = df.drop(columns=[target_col])
    y = df[target_col]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )

    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.1, random_state=random_state, stratify=y_train
    )

    return X_train, X_val, X_test, y_train, y_val, y_test
```

## 模型训练

### PyTorch 训练模板

```python
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from typing import Optional

class Trainer:
    def __init__(
        self,
        model: nn.Module,
        optimizer: torch.optim.Optimizer,
        criterion: nn.Module,
        device: Optional[torch.device] = None
    ):
        self.model = model.to(device or torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        self.optimizer = optimizer
        self.criterion = criterion
        self.device = self.model.device

    def train_epoch(self, dataloader: DataLoader) -> float:
        self.model.train()
        total_loss = 0
        for batch_x, batch_y in dataloader:
            batch_x = batch_x.to(self.device)
            batch_y = batch_y.to(self.device)

            self.optimizer.zero_grad()
            output = self.model(batch_x)
            loss = self.criterion(output, batch_y)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()
        return total_loss / len(dataloader)

    def evaluate(self, dataloader: DataLoader) -> dict:
        self.model.eval()
        total_loss = 0
        correct = 0
        total = 0

        with torch.no_grad():
            for batch_x, batch_y in dataloader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)

                output = self.model(batch_x)
                loss = self.criterion(output, batch_y)
                total_loss += loss.item()

                predictions = output.argmax(dim=1)
                correct += (predictions == batch_y).sum().item()
                total += batch_y.size(0)

        return {
            "loss": total_loss / len(dataloader),
            "accuracy": correct / total
        }

    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
        epochs: int,
        early_stopping_patience: int = 5
    ):
        best_val_loss = float("inf")
        patience_counter = 0

        for epoch in range(epochs):
            train_loss = self.train_epoch(train_loader)
            val_metrics = self.evaluate(val_loader)

            print(f"Epoch {epoch+1}/{epochs}")
            print(f"  Train Loss: {train_loss:.4f}")
            print(f"  Val Loss: {val_metrics['loss']:.4f}, Acc: {val_metrics['accuracy']:.4f}")

            # Early stopping
            if val_metrics["loss"] < best_val_loss:
                best_val_loss = val_metrics["loss"]
                patience_counter = 0
                self.save_checkpoint("best_model.pt")
            else:
                patience_counter += 1
                if patience_counter >= early_stopping_patience:
                    print(f"Early stopping at epoch {epoch+1}")
                    break

    def save_checkpoint(self, path: str):
        torch.save({
            "model_state": self.model.state_dict(),
            "optimizer_state": self.optimizer.state_dict()
        }, path)
```

## 模型评估

### 离线评估指标

```python
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score,
    f1_score, roc_auc_score, confusion_matrix
)
import numpy as np

def evaluate_model(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray = None) -> dict:
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average="weighted"),
        "recall": recall_score(y_true, y_pred, average="weighted"),
        "f1": f1_score(y_true, y_pred, average="weighted"),
    }

    if y_prob is not None:
        metrics["roc_auc"] = roc_auc_score(y_true, y_prob, multi_class="ovr")

    # Confusion Matrix
    cm = confusion_matrix(y_true, y_pred)
    metrics["confusion_matrix"] = cm.tolist()

    return metrics
```

## 模型部署

### FastAPI 部署模板

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import torch
from typing import List
import numpy as np

app = FastAPI(title="ML Model API", version="1.0")

# 模型加载（启动时）
model = None

class PredictionInput(BaseModel):
    features: List[List[float]]

class PredictionOutput(BaseModel):
    predictions: List[int]
    probabilities: List[List[float]]

@app.on_event("startup")
async def load_model():
    global model
    model = torch.jit.load("model.pt")
    model.eval()

@app.post("/predict", response_model=PredictionOutput)
async def predict(input_data: PredictionInput):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    features = torch.tensor(input_data.features, dtype=torch.float32)

    with torch.no_grad():
        output = model(features)
        probs = torch.softmax(output, dim=1)
        predictions = output.argmax(dim=1)

    return PredictionOutput(
        predictions=predictions.tolist(),
        probabilities=probs.tolist()
    )
```

## MLOps 监控

```yaml
# mlflow/config.yaml
mlflow:
  tracking_uri: http://localhost:5000
  experiment_name: production-models

monitoring:
  # 数据漂移检测
  drift_detection:
    enabled: true
    interval: hourly
    threshold:
      psi: 0.2    # Population Stability Index
      kl_div: 0.1

  # 模型性能监控
  performance:
    enabled: true
    interval: daily
    metrics:
      - accuracy
      - precision
      - recall
      - f1
      - latency_p95

  # 告警
  alerts:
    - metric: accuracy
      condition: "< 0.85"
      severity: high
      notify:
        - email: ml-team@company.com
        - slack: "#ml-alerts"
```

## 验证方法

```bash
[[ -f skills/ml-engineer/SKILL.md ]] && echo "✅"

grep -q "PyTorch\|TensorFlow\|sklearn" skills/ml-engineer/SKILL.md && echo "✅ ML 框架"
grep -q "feature.*pipeline\|fit_transform" skills/ml-engineer/SKILL.md && echo "✅ 特征工程"
grep -q "FastAPI\|REST.*API\|deploy" skills/ml-engineer/SKILL.md && echo "✅ 部署"
grep -q "drift\|monitoring\|mlflow" skills/ml-engineer/SKILL.md && echo "✅ MLOps"
```

## Red Flags

- 无 validation set 评估
- 过拟合（train acc 远高于 val acc）
- 特征未做标准化上线
- 无数据漂移检测
- 模型无版本管理
- 无 A/B 测试直接全量上线
