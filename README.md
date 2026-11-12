# 街道积水升级预警检测器

智慧城市课程中期项目。街道传感器首次测到超过 10 mm 的积水后，检测器在第 5 分钟判断风险；尚未告警且有新读数时，第 8 分钟再判断一次。目标是在首湿后 35 分钟内水深达到 4 英寸（10.16 cm）之前，留出至少 5 分钟的处置时间。

[课堂主讲 · 6 页](presentation/talk.pdf) · [含答疑的完整汇报](presentation/midterm.pdf) · [离线检测器](nyc/FloodNet-街道积水升级检测器.html) · [实验索引](experiments/) · [下载与原始数据](https://github.com/Owen2005-brilliant/smart_city/releases/tag/midterm-report-v1)

## 怎样看这个项目

| 想看什么 | 从这里开始 |
|---|---|
| 课堂演示 | 下载中期发布页的检测器 HTML，用浏览器打开。可以输入读数，也可以同屏回放真实街道事件。[演示步骤与讲解顺序](presentation/demo.md) |
| 规则有多少收益 | [纽约基础算法对照](experiments/baselines/)和[三篇论文的方法对照](experiments/paper-benchmarks/)给出相同误报次数下能及时捕获多少次升级。 |
| 为什么维持当前门槛 | [非潮汐首报优化](experiments/first-alert/)解释哪些事件值得提前发警；[外地逐场回放](external/paired-replay/)检验放宽后是否真能多报中。 |
| 当有新事件时 | [在 GitHub 手动运行验证](https://github.com/Owen2005-brilliant/smart_city/actions/workflows/independent-validation.yml)，或从仓库根目录运行 `python3 nyc/prospective/validate_new.py`。[冻结规则与入组说明](nyc/prospective/) |

## 中期结论

纽约后期 859 场可评分积水中，有 192 场升级。在各方案均产生 **66 次误报**时，相同评分输入只看一次，能及时捕获 68 场；允许复查后为 **83 场**（35.4% → 43.2%）。使用过去选定的正式门槛时，检测器实际及时捕获 97/192 场、误报 121/667 场。前一项用于对齐代价比较模型，后一项报告冻结规则的实际表现。

在非潮汐站，纽约回看中学习型放宽首报门槛曾多及时捕获 2 场。台湾与麦迪逊 152 场外地配对回放中，学习版和原版发警时刻逐场相同。台湾站点的潮汐属性未知，分别作两种情景分析。正式规则沿用 [midterm-freeze-v1](https://github.com/Owen2005-brilliant/smart_city/tree/midterm-freeze-v1)，研究版本独立归档。

## 数据和复现

[纽约数据来源与复现环境](nyc/README.md) · [外部数据与观测质量](external/) · [全部实验与运行入口](experiments/)

纽约数据来自 FloodNet（NYU、CUNY）与 NYC DEP；台湾日档来自水利署 Civil IoT 资料及其固定修订镜像；麦迪逊数据来自 USGS。逐项来源、单位转换、筛选条件和可评分样本数见对应目录。
