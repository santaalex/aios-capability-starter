# AIOS Capability Starter

这是一个独立、最小、脱敏的 AIOS Capability Pack 开发包。它让另一台电脑上的
工程师或 Codex 在看不到 AIOS 主仓库的情况下，创建、构建和检查一个能力候选包。

本仓库只负责：

- 生成标准能力目录；
- 定义中文能力卡、输入、确认、结果、Skill 和最小 Golden；
- 构建确定性的 Capability Pack ZIP；
- 在交付前检查 ZIP 的结构、组件大小和 SHA-256。

本仓库不负责签名、发布、设备分配和生产激活。开发者交回 ZIP 和测试报告后，由
AIOS 发布环境完成签名和挂载。

## 五分钟开始

需要 Python 3.11 或更高版本，无第三方依赖。

macOS / Linux：

```bash
./tools/aios-capability init sample-capability \
  --display-name "示例工程能力" --repo-root .
./tools/aios-capability build \
  capabilities/sample-capability/0.1.0/capability.source.json --repo-root .
./tools/aios-capability verify \
  dist/capability-packs/sample-capability-0.1.0.zip
```

Windows：

```powershell
.\tools\aios-capability.cmd init sample-capability --display-name "示例工程能力" --repo-root .
.\tools\aios-capability.cmd build capabilities/sample-capability/0.1.0/capability.source.json --repo-root .
.\tools\aios-capability.cmd verify dist/capability-packs/sample-capability-0.1.0.zip
```

详细步骤见 [中文快速指南](docs/capability-quickstart.md)。
给其他电脑分配开发任务时，可直接使用
[Codex 任务模板](docs/codex-task-template.md)。

## 开发者最终交付

```text
<capability-id>-<version>.zip
测试报告
如确实需要：独立 Adapter 候选包及接口说明
```

不要提交客户模型、真实工程文件、许可证、模型 Key、云端地址、设备凭证或签名私钥。
本地授权样本放在 `local-inputs/` 或仓库外目录，这些目录默认不进入 Git。

## 公开边界

本仓库公开的是 Capability Pack 的开发合同、模板和本地构建工具，不包含 AIOS
平台实现。AIOS Core、Control Plane、Workbench、客户配置、真实 Adapter、发布系统、
签名密钥和工程数据不属于本仓库。

当前仓库未授予开源许可证；公开内容用于阅读和按 AIOS 授权开发兼容能力。未经许可，
不得将本仓库内容作为独立产品复制、修改或再分发。

## 边界

- Capability Pack：客户无关的能力定义、通用规则、UI 元数据和 Skill。
- Customer Pack：客户目录、命名、模板、字段映射和客户差异。
- Desktop / Adapter：CATIA、机器人软件、厂商 DLL 和本机执行入口。
- Workbench：读取 Pack 的通用能力卡、表单、任务和下载信息。

仅修改 Pack 不需要重建 AIOS Docker 或 Desktop。只有新增本机执行入口、Adapter 或
Workbench 尚不支持的交互时，才需要独立的 Desktop 变更。
