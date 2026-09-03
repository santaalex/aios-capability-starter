# AIOS Task Bundle v0.1alpha1

Task Bundle 是 AIOS 在不同工程师和不同 AI 工具之间传递单次任务的公开合同。它用
`TASK.md` 解释意图，用 `task.json` 冻结机器可读事实，用 `result.json` 返回统一结果。

它不会复制历史聊天，也不是远程命令系统。

## 合同文件

- `schemas/task-bundle.v0.1alpha1.schema.json`
- `schemas/task-result.v0.1alpha1.schema.json`

`task.json` 的核心部分：

- `kind`：任务类型；
- `metadata.task_id`：单次任务身份；
- `metadata.generation`：任务修改时递增；
- `spec.objective`：业务目标；
- `spec.impact`：判断是否只改 Pack、需要插件或需要 Desktop；
- `spec.target`：开发仓库或目标设备；
- `spec.acceptance`：检查、交付物和禁止改变的对象；
- `spec.secrets_policy`：Bundle 中不得出现的秘密。

`result.json` 必须带回相同 `task_id` 和 `observed_generation`。旧 generation 的
结果不能作为新任务的完成证据。

## 当前支持的任务类型

- `CapabilityDevelopment`
- `AdapterDevelopment`
- `DeviceDeployment`
- `DesktopUpdate`

P0/P1 只执行 `CapabilityDevelopment` 的初始化、构建和结果生成；其他类型先冻结合同，
不提供客户机执行器。

## 使用现有能力任务

```bash
python tools/aios-capability task-validate path/to/task.json
python tools/aios-capability init --task path/to/task.json --repo-root .
python tools/aios-capability build --task path/to/task.json --repo-root .
python tools/aios-capability result-validate \
  dist/task-results/<task-id>.result.json --task path/to/task.json
```

`build --task` 自动生成：

```text
dist/capability-packs/<capability-id>-<version>.zip
dist/task-results/<task-id>.result.json
```

回执只证明 Task 合同、Pack 构建和 Pack 结构校验完成。如果 Task 还要求功能 Golden，
结果会是 `NEEDS_ATTENTION` 并列出未完成检查；它不会把尚未发生的签名、云端发布、
Windows HIL 或客户验收标成通过。

## 不使用 Task Bundle

原来的 `init / build / verify` 命令保持兼容。没有 `--task` 时，不生成 Task Result。

## 示例

- `examples/task-bundles/capability-development/`
- `examples/task-bundles/device-deployment-pack-only/`

第一个目录同时包含固定值的 `result.example.json`，只用于解释合同，不能代替真实执行
生成的回执。第二个示例只用于冻结未来客户机合同；当前 Starter 不会执行部署。
