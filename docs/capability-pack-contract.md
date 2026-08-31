# Capability Pack 最小合同

每个候选包必须包含：

- `manifest.json`：制品身份、兼容范围、组件清单、大小和 SHA-256；
- `capability.json`：能力身份、执行入口、输入输出合同、UI 和 Skill 引用；
- `runtime/`：客户无关的候选逻辑或固定 Adapter 的调用入口；
- `schemas/`：输入、工程师确认、结果 JSON Schema；
- `ui/`：Workbench 能力卡、表单和结果展示描述；
- `skills/`：工程师/Agent 使用说明；
- `golden/`：最小案例；
- `docs/`：边界和限制。

固定约束：

- `capability_id` 使用小写 kebab-case；
- `version` 使用 MAJOR.MINOR.PATCH；
- 同一 `capability_id + version` 不覆盖；
- ZIP 只包含 manifest 声明的文件；
- 文本为 UTF-8 无 BOM，换行统一为 LF；
- 组件内容、大小和 SHA-256 必须匹配；
- 激活仍要求内部发布环境生成的 Ed25519 detached signature。

本仓库保留与 AIOS Capability Pack v1 相同的 pack/source/contract schemas，但不包含
签名私钥或发布命令。
