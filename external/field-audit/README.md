# 外部路面积水数据与门槛验证

本次查找要解决的问题是：在没有参加纽约模型选择的地方，第 5 分钟降低首报门槛，能否在不多报的情况下多捕获至少提前 5 分钟的真实升级？数据包整理日期为 2026-11-12。冻结纽约未来事件的入组起点仍是 2026-11-13 00:00 UTC。本次复查纽约官方库仍为 3,581 个事件、492 个部署，最新事件起始 2026-10-26。

## 两个实际取得的外部数据集

| 资料及取得方式 | 样本 | 逐事件结果 |
|---|---|---|
| 台湾水利署及水利署与地方政府合建淹水传感器。国网中心登记的 Civil IoT 数据，下载自固定 Git 修订的原始日档镜像。连续取 2021-08 和 2023-07 两个完整月份，每天两种来源，共 124 个 ZIP。两个便利样本月份不代表全年。 | 原始 13,680,072 行，包含电压等非水深通道。只留单位 cm、水深或淹水深度、名称或说明明示“路面”的观测，共 5,200,388 行（去重前）、394 站。 | 1,284 场首次湿读数候选；70 场满足观测要求（38 站，63 场未升级、7 场升级），其中只有 8 场可以在第 8 分钟复查。 |
| Madison, Wisconsin。USGS 官方仪表板公布的路面阈值和站点历史接口配对。除去演示项和项目以前用过的 Johnson and Third，分析其他 11 站全部 2026 年 6–8 月数据。 | 496,100 行，均标记为 Provisional；按 ft、无 qualifier、有限实数、同一时间无冲突等条件取 494,196 个读数。水深代理为 max(0, 水位英尺−当前公布的道路高程门槛英尺)×30.48 cm。未获得逐日高程变更记录或逐例图像。 | 21 场候选，10 场首判前已越线；2 场可评分，均在 Sherman and Trailsway，1 正 1 负，2 场均可复查、0 场属于“等不起”。 |

台湾样本未提供可直接使用的潮汐影响标志，台账中的经纬度可辅助逐站核实。两张站点表精确按 station_id + PQ_id 联结，394 站中 375 站匹配到坐标；不能因事件发生在雨天就指定它为非潮汐。台账内时间保留原 CSV 表示，未把未标 UTC 偏移的本地字符串与其他地区时区直接合并。

## 时间和质量检查

每站按时间排序，不用双向插值。通常由一次零读数重新开启候选，首个超过 1 cm 的读数记为第 0 分钟。台湾两个不相邻月份分别切段。若首湿前只有很久前的零读数，真实起涨可能早于记录；台账同时给出距前一次读数和距前一个零读数的时间，可自行收紧。第 5 分钟要求两次不同时刻的读数、仍湿、最新点距首判至多 3 分钟且未曾达到 10.16 cm。标签窗止于首湿后第 35 分钟或已观测到退水归零，相邻支持点及窗口边界最多隔 5 分钟。第 8 分钟复查还需在首判后收到新的有效湿读数且此前未越线。每个短暂归零都可能分出新的候选；台账是本项目筛出的事件，未经逐例人工确认。不同站点同一天的记录也可能来自同一场天气过程。

“等不起”指事后观测显示，第 5 分钟报可以确认至少 5 分钟提前量，而第 8 分钟再报会不足 5 分钟或已无法复查。台湾符合这个定义的仅两场，均发生在 2021-08-07。桃园中正东路一段 840 巷在第 5 至第 8 分钟没有新读数；屏东林边邮局有新读数，提前量从 6 分 19 秒降到 3 分 19 秒。两场都是判断时机的事后标签，不能据此说降低门槛一定能多报中两场。若进一步要求首湿前 5 分钟内明确记录为零，仅 27 场可评分、1 场升级、0 场“等不起”。2021-08 贡献 57 场可评分、6 场升级；2023-07 为 13、1。有效样本少的主要原因有 856 场没有可用于第 5 分钟首判的足够新鲜湿读数。

麦迪逊按纽约冻结门槛在两场上盲于外部标签做回放。正式版、历史学习放宽版和统一放宽版都在同一场升级中第 5 分钟告警，另一场不报警；可确认的提前量仅 2 分 02 秒。升级仅一个读数越线，且水深是排水设施水位相对路面高程的代理。现有样本无法估计稳定的误报率或支持门槛更改。两个地区分开报告，均不用于拟合门槛。

## 使用资料

- tw_events.csv / mad_events.csv：所有候选的入组原因、升级及“等不起”标签；空标签表示排除。tw_curves.csv / mad_curves.csv：所有可评分案例的逐笔 cm 水深，时间为距首湿秒数。tw_streams.csv / mad_inventory.csv：测点、读数间隔、峰值等。mad_replay.csv：纽约三种门槛逐事件回放。
- tw_summary.json / mad_summary.json、mad_replay_summary.json 汇总结果。manifest.json、mad_manifest.json 提供原始来源、文件路径或月份、SHA-256。纽约官方空结果见 nyc_snapshot_report.json。
- 本包内含美方使用的 33 个月站 CSV。从本项目 [中期发布页](https://github.com/Owen2005-brilliant/smart_city/releases/tag/midterm-report-v1) 下载的台湾原始日档 ZIP 解压到本目录后即有 tw/ 子目录，也可运行 python3 restore_tw.py 下载原文件并核对哈希。运行 python3 audit_tw.py、python3 audit_mad.py、python3 replay_mad.py 可离线重算（Python 标准库）。audit_tw.py 使用同修订的 sensors.csv；nyc_locked_rules.json 是纽约历史训练参数。export_gate.py 仅用于从前期纽约仓库 nyc 目录重新导出参数，需要其训练依赖。
- [国网中心历史资料目录](https://scidm.nchc.org.tw/en/dataset/civiliot_history_data) · [水利署 IoW 资料说明](https://data.gov.tw/en/datasets/142980) · [日档镜像](https://github.com/cjw612/Flood_Analysis/tree/12c9c16280ee79419550de354343e7d9b5ddf686/Data/raw_data) · [桃园市水务局路面感测实例](https://wrb.tycg.gov.tw/News_Content.aspx?n=10829&s=1339476)
- [USGS 面板](https://www.arcgis.com/home/item.html?id=c18c71eb81df4c3b923c319f16d24294) · [道路门槛图层](https://services.arcgis.com/v01gqwM5QqNysAAi/arcgis/rest/services/Current_Flood_Sensor_Data/FeatureServer/0) · [Sherman and Trailsway 实测](https://waterdata.usgs.gov/monitoring-location/USGS-430734089215001/) · [纽约官方事件](https://data.cityofnewyork.us/d/aq7i-eu5q)
