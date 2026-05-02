# Memory Index

- [所有需求必须先走 Agent，Agent 无法处理才用直接能力](feedback_use_agents_not_self.md) — 任何需求优先派发专业 Agent；仅单行 fix / 纯问答 / Agent 明确失败时才主 session 直接处理
- [声明完成前必须验证](feedback_verify_before_claiming_done.md) — 任何"已完成"声明必须有证据支持；创建文件需验证存在，发现问题需记录位置
- [代码分析必须一次穷尽](feedback_deep_analysis_first_pass.md) — 激活专家模式多轮深度思考，第一轮就穷举所有问题，不逐层发现
- [文件写入前必须确保父目录存在](feedback_file_write_parent_mkdir.md) — 任何写文件操作前加 path.parent.mkdir(parents=True, exist_ok=True)
- [Claude Code 平台特性与陷阱](reference_claude_code_lib_import.md) — lib/ 无 __init__.py 也可用 from lib.xxx；Python 三元表达式 else 不能返回 None
