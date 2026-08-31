# 来源与兼容基线

Starter v0.1.0 从 AIOS 主仓中已验收的 Capability Pack v1 开发范式抽取并脱敏。

- authoritative source commit:
  `52943e2a2967bbb9b7fa3c703871f650527be66b`
- source change:
  `feat: add capability pack starter workflow`
- pack schema version: `1.0`
- runtime API: `aios-capability-runtime.v1`

复制出的三份 schema SHA-256：

- capability-pack-manifest.v1.schema.json:
  `9babd4d7543a01b91206661886b68dc0323502eb45d25b640b267ef0820f3d7f`
- capability-pack-source.v1.schema.json:
  `232b4d5b4012afa4235257698b971597ff703d79a0a8d158caae0f5dd21464b9`
- capability-contract.v1.schema.json:
  `c851ccea9e531b94f7827f24a053205d35ec7750ab4a220385b8630bc5991c14`

Starter 不同步跟踪主仓。合同变化时必须发布新的 Starter 版本，避免开发电脑无意间接受
未冻结的格式。
