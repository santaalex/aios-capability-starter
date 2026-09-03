# AIOS 能力开发中文快速指南

## 1. 先用一句话定义能力

请写清楚：

- 工程师拿什么作为输入；
- 点击执行后能力做什么；
- 最后得到什么结果；
- 哪些情况必须停止并让工程师确认。

一个能力只解决一个清楚的工程任务，不把多个无关功能塞进同一张能力卡。

## 2. 初始化

推荐先从 `task-template/` 创建本次 Task Bundle，再执行：

```bash
python tools/aios-capability task-validate path/to/task.json
python tools/aios-capability init --task path/to/task.json --repo-root .
```

没有 Task Bundle 时仍可使用原命令：

```bash
python tools/aios-capability init my-capability \
  --display-name "我的工程能力" --repo-root .
```

会生成：

```text
capabilities/my-capability/0.1.0/
```

## 3. 只修改必要文件

1. `ui/form.json`：中文名称、用途、输入和输出。
2. `schemas/`：真实输入、工程师确认和结果结构。
3. `runtime/main.py`：客户无关逻辑，或调用已批准的固定 Adapter。
4. `skills/`：什么时候用、怎么用、什么时候停。
5. `golden/minimal.json`：一个最小授权案例。
6. `docs/README.md`：能力、客户配置和本机 Adapter 的边界。

模板的运行结果是 `NOT_IMPLEMENTED`。没有实现和验证前不得交付。

## 4. 构建和检查

使用 Task Bundle 时：

```bash
python tools/aios-capability build --task path/to/task.json --repo-root .
python tools/aios-capability result-validate \
  dist/task-results/<task-id>.result.json --task path/to/task.json
```

这会生成标准 `result.json`。如果功能 Golden 尚未真实执行并报告，结果会明确标为
`NEEDS_ATTENTION`。

不使用 Task Bundle 时：

```bash
python tools/aios-capability build \
  capabilities/my-capability/0.1.0/capability.source.json --repo-root .
python tools/aios-capability verify \
  dist/capability-packs/my-capability-0.1.0.zip
```

相同源码构建两次必须得到相同 SHA-256。

## 5. 本地样本

真实客户文件不进入本仓库。把授权样本放在 `local-inputs/` 或仓库外的项目目录，
只把脱敏后的最小期望结果写进候选包。

## 6. 交回 AIOS 发布环境

交回 ZIP、`result.json`、功能测试报告和必要的 Adapter 候选包。开发电脑不持有签名
私钥，不直接登记 Control Plane，不直接给客户设备分配能力。
