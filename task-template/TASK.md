# [能力中文名称]开发任务

## 目标

[用一句话说明工程师提供什么输入、能力执行什么工作、最终得到什么。]

## 不做

- 不签名或发布。
- 不操作 Control Plane 或客户设备。
- 不提交客户资料或秘密。

## 交付物

- Capability Pack ZIP。
- `result.json`。
- 一个最小脱敏 Golden 的真实执行结果。
- 已知限制；如需要本机程序，另交 Adapter 候选和固定接口。

## 收口

运行 `build --task`，再用 `result-validate --task` 检查最终回执。功能 Golden 必须
单独真实执行，不能因为 Pack 构建成功而自动声称通过。
