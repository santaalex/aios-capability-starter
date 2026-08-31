# Adapter 接入边界

Capability Pack 不是任意代码插件。一个全新能力如果需要 CATIA、机器人软件或其他
本机程序，必须有明确的 Core/Adapter 固定入口。

开发者需要交付：

- Adapter 名称和候选版本；
- 固定调用名；
- 输入 JSON；
- 输出 JSON 和产物列表；
- 软件/许可证前置条件；
- 一个最小本机测试报告。

开发者不需要也不应获得 AIOS Core、Control Plane、Workbench 或其他客户 Adapter
源码。CATIA 接口开发可在另行授权时参考独立仓库
`santaalex/aios-catia-adapter`，但客户模型和许可证不进入该仓库。

如果能力只是更新通用规则、UI 元数据或已有 Adapter 的参数，就只交 Capability Pack，
不发布新的 Desktop。
