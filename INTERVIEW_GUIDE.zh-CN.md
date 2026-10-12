# CoastKind / WAINET：整改后的讲解与练习

## 先正确定位这个项目

这是用 AI 辅助开发的社区海岸观察原型。它能说明你如何把 AI 接口、Python
后端、数据校验、权限和人工审核串成一个完整流程，以及你如何验证故障行为。
它还不能说明你已经运营过银行级 AI 平台。公开网页使用合成演示数据，不能
把它说成真实用户已经在使用的在线 AI 产品。

## 这次具体改了什么

1. 把模型响应处理提取到 `ai_transport.py`，限制读取大小，检查响应格式，
   区分超时、限流、拒答、认证失败、服务不可用等情况。
2. 保留原始照片和描述；AI 失败不产生有效分析，也不能进入获准导出数据。
   人工审核原本就存在，这次补充了针对故障场景的回归验证。
3. 增加请求编号和结构化排错日志。日志不记录照片、描述、邮箱、GPS 或密钥。
4. 数据库无法访问时，健康检查明确返回 503。
5. 配置自动化测试流水线；远端运行结果必须等实际运行后才能声称通过。

## 与 AI 工程岗位如何关联

| 岗位关注点 | 你可以展示的证据 | 不应夸大的部分 |
| --- | --- | --- |
| Python、API、端到端交付 | 上传、验证、入库、异步分析、人工审核、页面展示 | 当前后端仍是原型服务器 |
| AI 的可靠性与治理 | 严格结构验证、人工审核、拒答与故障分类 | 不代表回答一定真实，也没有生产准确率 |
| 可观测性 | 请求编号、状态、耗时、失败类别 | 尚无完整分布式追踪和告警平台 |
| 可复用工程能力 | 独立 provider adapter、自动化回归测试 | 不是企业 SDK 或多租户平台 |
| 安全与身份 | 已有会话、角色、CSRF、隐私约束 | 不是银行 SSO 或正式安全认证 |

这能增强对 BNZ AI Domain 类岗位的技术讨论，但 Senior 级别仍会考察真实
系统交付、工程取舍、协作影响和生产问题处理。不要因为项目加了这些功能就
把所有高级岗位要求都视为满足。也不需要为了投递无限增加新技术名词。

## 一段可练习的英文介绍

“CoastKind is an AI-assisted prototype I developed for community coastal
observations. It connects a Python API and SQLite evidence store to a multimodal
AI workflow, with human review before eligible observations contribute to shared
outputs. I used failure-injection tests to check that timeouts, malformed outputs
and refusals preserve the original evidence without publishing an analysis. I
also added request tracing that excludes personal content. The public demo uses
synthetic data; I would still need model-quality evaluation and production
infrastructure before releasing it as a live service.”

只有在你自己运行、读懂并能解释相关代码之后，才自然地使用这段介绍。被问到
开发方式时，如实说明用了 AI 辅助，并解释自己验证了什么、作出了哪些判断。

## 两天内完成的练习

第一天：约 6 小时。

- 1.5 小时：读 `server.analyze`、`process_next`、`ai_transport.py`，画出数据流程。
- 1.5 小时：运行 `python -m unittest test_reliability -v`，逐项解释故障场景。
- 1 小时：启动本地服务，调用 `/api/health`，找到响应与日志中的相同请求编号。
- 1 小时：读既有权限和人工审核测试，解释为什么 AI 输出不能直接发布。
- 1 小时：录制 3 分钟介绍，删掉不能用代码或测试证明的说法。

第二天：约 6 小时。

- 2 小时：亲自新增一个有意义的失败测试，例如结构合法但出现不受支持的安全
  结论。先说明现有规则能否阻止它；不要为了通过而把真实缺陷隐藏掉。
- 1.5 小时：拟定小规模模型评估集及评分规则，先不调用付费 API。
- 1 小时：练习下面的问题，用业务影响和工程取舍解释，不只讲论文术语。
- 1.5 小时：据实际掌握的内容准备申请材料和项目演示，不把等待项目完美作为
  延迟所有投递的理由。

## 常见追问

**为什么不直接重试？** 超时不等于提供商没有处理请求，重复调用可能重复计费。
目前失败后保留证据、由操作人员判断；启动恢复也可能重复调用，尚未实现外部
模型调用的 exactly-once。

**JSON 合法就安全吗？** 不是。格式校验解决结构问题，不解决事实性问题。
仍需要语义评估、人工审核，并明确不从照片判断水质安全。

**为什么不用 RAG？** 当前核心是图片和描述的结构化观察，没有检索需求。
以后若增加基于官方资料的问答，才需要来源可信度、时效、引用与拒答评估。

**与之前测试经验怎么关联？** 说明你如何设计正常/异常场景、复现错误、验证
原始资料没有丢失、隔离外部依赖并防止回归。不要把本项目练习写成商业生产经验。

**上线还缺什么？** 生产应用服务器、任务队列与超时管理、限流、恢复演练、
保留和删除策略、监控告警、真实模型评估和组织安全审核。
