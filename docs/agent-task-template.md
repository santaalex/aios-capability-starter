# 给其他电脑或 AI 工具的统一任务指令

能力负责人先复制 `task-template/`，填写 `TASK.md` 和 `task.json`。然后只需把任务目录
和下面这段话交给 Codex、Grok、Cursor 或其他能够访问仓库和终端的本机工具。

```text
请在 AIOS Capability Starter 仓库中执行随附的 CapabilityDevelopment Task Bundle。

1. 先阅读仓库根目录 AGENTS.md、任务目录 TASK.md 和 task.json。
2. 运行 task-validate；合同无效时停止并报告具体字段，不要猜测缺失值。
3. 如果能力目录尚不存在，运行 init --task。
4. 只实现 task.json 的 objective；遵守 non_goals、acceptance 和 secrets_policy。
5. 客户差异不得写进 Capability Pack；需要本机软件时只声明固定 Adapter 接口。
6. 真实执行一个最小脱敏 Golden，并如实记录结果。
7. 运行 build --task，生成候选 ZIP 和 result.json。
8. 运行 result-validate --task。

Pack 构建成功不代表功能 Golden、签名、发布、Windows HIL 或客户验收已经通过。
最终交回 ZIP、result.json、最小功能测试报告和已知限制；不要操作 Control Plane 或客户设备。
```

Task Bundle 才是本次任务的权威输入。聊天内容与 Task Bundle 冲突时，应停止并指出冲突，
不得擅自选择聊天中的旧版本。
