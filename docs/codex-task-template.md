# 给其他电脑 Codex 的统一任务指令

复制下面整段，并把方括号里的内容替换为本次能力信息：

```text
请使用公开仓库 santaalex/aios-capability-starter 开发一个独立的 AIOS
Capability Pack。

能力目标：[用一句中文写清楚工程师输入什么、能力做什么、输出什么]
能力 ID：[小写 kebab-case]
版本：0.1.0
本地授权资料目录：[只写这台电脑上的本地路径，不提交客户文件]

执行要求：
1. 先阅读 README.md、docs/capability-quickstart.md、
   docs/capability-pack-contract.md 和 docs/capability-vs-customer-pack.md。
2. 使用 tools/aios-capability init 创建能力，不手工另造目录结构。
3. 用工程师能看懂的中文完成能力卡、输入、输出、限制和操作说明。
4. 客户无关逻辑放 Capability Pack；客户命名、目录、模板和字段映射不要放进去。
5. 不提交客户模型、真实工程文件、许可证、模型 Key、云端地址、设备凭证或任何密钥。
6. 如果需要 CATIA/机器人等本机执行，先按 docs/adapter-interface.md 给出窄接口和
   Adapter 候选包；不要索取或复制 AIOS 主仓源码。
7. 只运行最小验证：一个最小 Golden、build、verify、重复构建 SHA 一致。
8. 不签名、不发布、不操作 Control Plane、不给设备分配能力。

最终交付：
- <capability-id>-0.1.0.zip
- 测试报告：Golden 结果、build/verify 结果、ZIP 大小和 SHA-256
- 如需要：独立 Adapter 候选包、固定调用名和输入输出合同
- 已知限制与下一步
```
