# Planner Prompt

读取 Master Brief、Project State、Roadmap 和现有产物，输出一份短计划：

1. 当前阶段与目标差距。
2. 已验证、部分完成、待办、阻塞、需验证事项。
3. 只选择一个最高优先级且依赖满足的下一任务。
4. 写明 Objective、Priority、Dependencies、Inputs、Actions、Deliverable、Validation Criteria。
5. 如果下一任务被用户输入阻塞，给出可逆 fallback，但明确不能将 fallback 当真实验收。

不要重复已验证工作，不把 README 宣传、模拟数据或测试通过当成业务成功证明。
