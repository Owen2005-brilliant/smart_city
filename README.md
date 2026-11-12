# smart_city

## 街道积水升级预警检测器

智慧城市课程项目。给定一个测点早期的水深读数，比较立即告警和等待一次复查能否及时预测未来 30 分钟内的积水升级。升级阈值为 4 英寸（10.16 厘米），及时告警要求至少提前 5 分钟。研究范围为已发生积水、观测质量足以评分的站点事件。

## 冻结版本与独立验证

[中期冻结版本 midterm-freeze-v1](https://github.com/Owen2005-brilliant/smart_city/tree/midterm-freeze-v1) 含可离线运行的新版检测器、早晚首判同屏回放和逐场对照。正式产品采用第 5 分钟首判、第 8 分钟可复查。研究用早判、加急规则保留为冻结对照。

在仓库根目录运行 `python3 nyc/prospective/validate_new.py`，即可从官方取得新快照，排除历史数据并评分。冻结后尚无新事件时，命令输出“暂无冻结后新增事件”。[独立验证口径与使用说明](nyc/prospective/README.md) · [加急实验、误差分解与复现](nyc/selective_early/README.md)

也可以在 [GitHub 上运行独立验证](https://github.com/Owen2005-brilliant/smart_city/actions/workflows/independent-validation.yml)。点击 **Run workflow**，运行结束后从该次运行的 **Artifacts** 下载报告和数据快照。

## 本地演示

下载仓库并解压，用浏览器打开 [街道积水升级检测器](nyc/FloodNet-街道积水升级检测器.html)。支持真实站点回放和手动输入读数。首个湿读数后第 5 分钟首次判断，暂缓事件在第 8 分钟复查。

点击「早判与晚判对照」可并排回放两套首判方案，逐时刻观察同一组水深读数和告警结果。两个案例分别展示提前 6 分钟的命中与一次早判误报。打开「运行检测器」可自行输入观测。[课堂操作与 5 分钟讲解顺序](中期演示与排练.md) · [首判实验口径及数据](nyc/first_look_README.md)

## 数据与来源

| 目录 | 内容与归属 |
|---|---|
| [nyc](nyc/) | 2026-11-10 的纽约市开放数据快照，3,581 条事件、492 个部署。来源为 FloodNet (New York University and The City University of New York) 和 NYC DEP。[事件](https://data.cityofnewyork.us/d/aq7i-eu5q) · [部署](https://data.cityofnewyork.us/d/kb2e-tjy3) · [指定论文 Mydlarz et al. 2024](https://doi.org/10.1029/2023WR036806) |
| [external](external/) | Beaufort 真实路面相对水位（Adam Gold，CC BY 4.0）、Madison 真实路口排水设施观测（USGS），以及 UrbanFlood24 的深圳模拟网格抽样（Cao、Wang、Qin，CC BY 4.0）。[逐项来源、单位及转换](external/README.txt) |

原始数据与派生数据保留各来源的条款和署名。深圳部分仅包含复现实验所用的单场景 625 个网格点。纽约早期连续数据的两份可选月文件由 [FloodNet Zenodo](https://zenodo.org/records/10211443) 单独提供。

## 复现实验

实验使用 Python 3.14。先在项目根目录创建并激活虚拟环境，执行 `python -m pip install -r nyc/requirements.txt`。以下脚本均在指明的目录内运行。

| 目录 | 命令 | 结果 |
|---|---|---|
| nyc | `python audit.py` | 检查事件与传感器关联、时间间隔、峰值一致性和最初的模型基线 |
| nyc | `python validate.py` | 重跑时序验证、区间覆盖与非潮汐站分析，生成回放输入 |
| nyc | `python check_controls.py`、`python check_delay.py` | 比较强基线及等待 0–5 分钟的策略 |
| nyc | `python build_model.py` | 导出冻结的模型参数、示例与浏览器一致性检查输入 |
| nyc | `python first_look.py` | 比较首判时刻，重建 985 场主测试集及冻结参数至 result/compare.json，供同屏对照使用 |
| nyc | `python presentation.py`、`python assemble.py` | 依次生成课堂回放和完整检测器（先运行 validate.py 与 build_model.py） |
| external | `python audit_external.py` | 用归档的纽约模型与外地数据重跑验证；见本目录说明 |

可选浏览器测试：在 nyc 目录运行 build_model.py 后，安装 playwright 并执行 `python -m playwright install chromium`，再运行 `python test_product.py` 和 `python verify_compare.py`。已有 Chrome 可通过环境变量 PLAYWRIGHT_CHROMIUM_EXECUTABLE 指定可执行文件。

## 解读结果

本版原型锁定历史告警门槛后，在 859 条纽约后期测试事件中至少提前 5 分钟捕获 97/192 次升级，误报 121/667。该指标的分母是可评分的积水事件，不能解释为全天候每站误报率。对照实验另有“匹配相同误报数”的结果，需分开解读。深圳网格来自模拟，不计作真实道路验证。
