# EES 使用手册

EES-Cross（Python 包 `cross_domain_scaling`，命令行 `cross-domain-scaling`）根据通用 JSON 领域目录构建多领域工具环境，不依赖固定数据集或特定模型服务。

项目只关注 **cross-domain composition 与 verification**。输入必须是已经可以执行的单域 contract；
单域环境生成和单域审计不在本项目范围内。

本项目采用**组合式运行时**，不修改并拼接领域类源码。每个领域在隔离模块中加载，并通过
`calendar__create_event` 这样的命名空间路由暴露操作，因此类名、方法名和状态不会互相冲突。

## 快速开始

EES 领域目录（domain catalog）不包含在本次发布中，格式见 [ees-catalog-schema.md](ees-catalog-schema.md)。

```bash
# 在仓库根目录执行
pip install -e .

cross-domain-scaling validate path/to/catalog.json
cross-domain-scaling build path/to/catalog.json \
  --output artifacts/demo \
  --count 5 \
  --seed 17 \
  --scenarios-per-environment 1 \
  --rollout-mode reference
cross-domain-scaling inspect artifacts/demo/bundle.json
```

默认流程完全离线且可复现。需要用模型生成世界背景或进行语义评审时，安装 `llm` 可选依赖，
并通过环境变量配置服务：

```bash
pip install -e '.[llm]'
export CROSS_DOMAIN_SCALING_API_KEY='...'
export CROSS_DOMAIN_SCALING_BASE_URL='https://api.openai.com/v1'
export CROSS_DOMAIN_SCALING_MODEL='gpt-4.1-mini'
export CROSS_DOMAIN_SCALING_EMBEDDING_MODEL='text-embedding-3-large'
```

完整模型模式会执行 embedding 候选召回、亲和度 rubric、shared-world 生成与 judge、跨域任务生成、
rollout 和 executable predicate 验证：

```bash
cross-domain-scaling build path/to/catalog.json \
  --output artifacts/llm-run \
  --affinity-mode semantic \
  --affinity-threshold 0.6 \
  --context-mode llm \
  --judge-mode llm \
  --scenarios-per-environment 2 \
  --scenario-mode llm \
  --rollout-mode llm
```

输入格式见 [ees-catalog-schema.md](ees-catalog-schema.md)。

