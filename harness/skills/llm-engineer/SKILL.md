---
name: llm-engineer
description: >
  大模型工程 Skill。提供 Prompt 工程模板（Few-shot、CoT、结构化 JSON 输出）、
  RAG 实现规范（Embedding + 向量检索 + 重排序）、LangChain 链式调用模式。
  内置 RAGPipeline、PromptTemplate 类和 LoRA 微调模板，适用 LLM 应用开发和生产化部署场景。
---

# llm-engineer — 大模型工程 Skill

## 核心能力

1. **Prompt 工程**：Few-shot、CoT、角色设定、结构化输出
2. **RAG 实现**：Embedding、向量检索、混合搜索、重排序
3. **模型微调**：SFT、RLHF、DPO、LoRA 微调流程
4. **LangChain**：Chain 组合、Tool 调用、Memory 管理
5. **安全与合规**：Prompt 注入防护、内容审核、幻觉检测

## Prompt 工程模板

### Few-shot Prompt

```python
from typing import Optional

class PromptTemplate:
    SYSTEM_TEMPLATE = """你是一个专业的数据分析师。
请根据用户的请求，分析数据并给出专业的回答。
回答格式：
- 分析结论
- 关键数据点
- 建议行动"""

    USER_TEMPLATE = """
## 用户请求
{query}

## 上下文
{context}

## Few-shot 示例
示例 1：
输入：分析 2024 年 Q3 用户增长
输出：
- 分析结论：Q3 用户增长率为 15%，主要来自自然搜索
- 关键数据点：新用户 10,000，自然搜索贡献 60%
- 建议行动：加大 SEO 投入，测试付费渠道 ROI

示例 2：
输入：对比 2024 年 1 月和 2 月的转化率
输出：
- 分析结论：2 月转化率较 1 月下降 3%
- 关键数据点：1 月 5.2%，2 月 5.0%
- 建议行动：排查 2 月页面加载速度变化

## 请按上述格式分析
输入：{query}
输出："""

    @classmethod
    def build(cls, query: str, context: str = "") -> dict:
        return {
            "system": cls.SYSTEM_TEMPLATE,
            "user": cls.USER_TEMPLATE.format(query=query, context=context)
        }

# 使用
prompt = PromptTemplate.build(
    query="分析 2024 年用户留存率",
    context="DAU 30日均值为 5,000，次日留存 40%，7日留存 20%"
)
```

### Chain of Thought (CoT)

```python
COT_TEMPLATE = """请逐步推理以下问题：

问题：{question}

步骤 1：理解问题
- 识别问题类型：（分类/回归/推理/生成）
- 识别关键约束条件：

步骤 2：分解问题
- 子问题 1：
- 子问题 2：
- 子问题 3：

步骤 3：逐步推理
推理 1：基于 [前提 X]
推理 2：基于 [推理 1 的结果]
推理 3：因此 [结论]

步骤 4：验证
- 检查逻辑是否自洽
- 检查是否满足所有约束

步骤 5：最终答案
{question}

答案："""
```

### 结构化输出（JSON Mode）

```python
STRUCTURED_PROMPT = """请将用户输入分类并提取实体。

要求：
1. 分类只能是以下类别：support | billing | technical | sales | other
2. 实体提取：email, phone, order_id（如存在）
3. 如有情绪识别，标注：positive | neutral | negative

输出 JSON 格式：
{{
  "category": "support|billing|technical|sales|other",
  "entities": {{
    "email": "string|null",
    "phone": "string|null",
    "order_id": "string|null"
  }},
  "sentiment": "positive|neutral|negative",
  "summary": "一句话总结用户请求"
}}

输入：{user_input}
输出："""
```

## RAG 实现

### 向量检索模板

```python
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Chroma, FAISS
from langchain.document_loaders import WebLoader, DirectoryLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Optional
import openai

class RAGPipeline:
    def __init__(
        self,
        embedding_model: str = "text-embedding-ada-002",
        vector_store: str = "chroma",
        persist_dir: Optional[str] = ".vector_store"
    ):
        self.embeddings = OpenAIEmbeddings(model=embedding_model)
        self.vector_store_type = vector_store
        self.persist_dir = persist_dir
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", " ", ""]
        )
        self.vectorstore: Optional[Chroma] = None

    def load_documents(
        self,
        source: str,
        source_type: str = "directory"  # "directory", "web", "file"
    ):
        if source_type == "directory":
            from langchain.document_loaders import DirectoryLoader
            loader = DirectoryLoader(source, glob="**/*.md")
        elif source_type == "web":
            loader = WebLoader(source)
        else:
            from langchain.document_loaders import TextLoader
            loader = TextLoader(source)

        docs = loader.load()
        chunks = self.text_splitter.split_documents(docs)

        if self.vector_store_type == "chroma":
            self.vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.persist_dir
            )
            self.vectorstore.persist()
        else:
            self.vectorstore = FAISS.from_documents(
                documents=chunks,
                embedding=self.embeddings
            )

        return len(chunks)

    def retrieve(self, query: str, top_k: int = 5, use_rerank: bool = True) -> List[str]:
        if not self.vectorstore:
            raise ValueError("Vector store not initialized")

        # 混合搜索（关键词 + 向量）
        docs = self.vectorstore.similarity_search(
            query, k=top_k * 2
        )

        # 重排序（如使用 Cohere）
        if use_rerank:
            from langchain.retrievers import ContextualCompressionRetriever
            from langchain.retrievers.cohere import CohereRerank

            reranker = CohereRerank(
                cohere_api_key=os.environ["COHERE_API_KEY"],
                top_n=top_k
            )
            docs = reranker.compress_documents(docs, query)

        return [doc.page_content for doc in docs[:top_k]]

    def generate_answer(
        self,
        query: str,
        context: str,
        model: str = "gpt-4"
    ) -> str:
        prompt = f"""基于以下上下文，回答用户问题。

上下文：
{context}

问题：{query}

要求：
1. 仅基于上下文回答，不要编造信息
2. 如上下文不足，说明"上下文不足以回答此问题"
3. 用中文回答

回答："""

        response = openai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个有用的助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content
```

## LangChain 链式调用

```python
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.agents import Agent, Tool, AgentExecutor
from langchain.memory import ConversationBufferMemory

# Tool 定义
search_tool = Tool(
    name="Search",
    func=search_api,
    description="搜索网络获取实时信息"
)

file_tool = Tool(
    name="ReadFile",
    func=read_file,
    description="读取本地文件内容"
)

# Chain 组合
analysis_prompt = PromptTemplate.from_template("""
作为数据分析助手，分析以下数据并给出建议：
{data}

分析维度：
1. 趋势分析
2. 异常检测
3. 建议行动
""")

analysis_chain = LLMChain(
    llm=llm,
    prompt=analysis_prompt,
    verbose=True
)

# Agent with Memory
memory = ConversationBufferMemory(memory_key="chat_history")

agent = Agent(
    llm=llm,
    tools=[search_tool, file_tool],
    prompt=AGENT_PROMPT,
    memory=memory
)

agent_executor = AgentExecutor.from_agent_and_tools(
    agent=agent,
    tools=[search_tool, file_tool],
    memory=memory,
    max_iterations=5,
    early_stopping_method="force"
)

result = agent_executor.run(input="分析第一季度销售数据")
```

## 模型微调流程

```python
# LoRA 微调模板（使用 PEFT）
from peft import LoraConfig, get_peft_model, AutoPeftModelForCausalLM
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, DataCollatorForLanguageModeling

def fine_tune_with_lora(
    base_model: str,
    train_data: str,
    output_dir: str,
    r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.05,
    epochs: int = 3,
    batch_size: int = 4
):
    # 1. 加载基础模型
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16,
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model)

    # 2. 配置 LoRA
    lora_config = LoraConfig(
        r=r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=lora_dropout,
        bias="none",
        task_type="CAUSAL_LM"
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # 3. 准备数据
    def tokenize(examples):
        return tokenizer(examples["text"], truncation=True, max_length=512)

    train_dataset = load_dataset("json", data_files=train_data)["train"]
    tokenized_dataset = train_dataset.map(tokenize, batched=True)

    # 4. 训练
    trainer = Trainer(
        model=model,
        train_dataset=tokenized_dataset,
        args=TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=4,
            warmup_steps=100,
            save_steps=500,
            logging_steps=100
        ),
        data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False)
    )
    trainer.train()

    # 5. 保存
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
```

## 验证方法

```bash
[[ -f skills/llm-engineer/SKILL.md ]] && echo "✅"

grep -q "few-shot\|CoT\|Chain.*Thought" skills/llm-engineer/SKILL.md && echo "✅ Prompt 工程"
grep -q "RAG\|vector\|embedding\|retrieval" skills/llm-engineer/SKILL.md && echo "✅ RAG"
grep -q "LangChain\|Chain\|Tool" skills/llm-engineer/SKILL.md && echo "✅ LangChain"
grep -q "LoRA\|fine.tune\|PEFT" skills/llm-engineer/SKILL.md && echo "✅ 微调"
```

## Red Flags

- Prompt 无 few-shot 示例直接上线
- RAG 无混合搜索，纯向量检索效果差
- 结构化输出无 JSON schema 约束
- 上下文窗口无限堆积导致截断
- 无 Prompt 注入防护
- 无幻觉检测机制
- LangChain Agent 无 Memory 导致无状态
