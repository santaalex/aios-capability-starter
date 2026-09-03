# 来源与兼容基线

Starter v0.2.0 从已验收的 AIOS Capability Pack v1 开发范式抽取并脱敏，新增公开的
AIOS Task Bundle v0.1alpha1 合同。
精确的内部来源记录由 AIOS 发布环境保留，不在公开开发包中暴露。
- pack schema version: `1.0`
- runtime API: `aios-capability-runtime.v1`

复制出的三份 schema SHA-256：

- capability-pack-manifest.v1.schema.json:
  `9babd4d7543a01b91206661886b68dc0323502eb45d25b640b267ef0820f3d7f`
- capability-pack-source.v1.schema.json:
  `232b4d5b4012afa4235257698b971597ff703d79a0a8d158caae0f5dd21464b9`
- capability-contract.v1.schema.json:
  `c851ccea9e531b94f7827f24a053205d35ec7750ab4a220385b8630bc5991c14`
- task-bundle.v0.1alpha1.schema.json:
  `2c03f802b8648e2e78755f267fc3fc16ed16f812d4d59506d75e634034b3bfa7`
- task-result.v0.1alpha1.schema.json:
  `3fec5250ddb54d86f2df4eb74c07e2cc23d6d9bf1af8909cc2df04093d5400d9`

Starter 不同步跟踪主仓。合同变化时必须发布新的 Starter 版本，避免开发电脑无意间接受
未冻结的格式。
