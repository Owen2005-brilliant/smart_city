FloodNet NYC 检测器：外部数据可行性回放（2026-11-12）
Python 3 + NumPy；解压后切换至本目录，运行 python audit_external.py。
case_ledger.csv 为逐例筛选与判断；alarm=0/3 代表首判发警/3分钟后发警，空代表无预警或不评分，须结合 reason。
external_results.json 为完整计数。纽约模型直接复制自前期检测器，未用外部标签训练、选阈值或重校准。

真实数据
1. Adam Gold, Storm drain water level measurements from Beaufort, North Carolina (2022).
https://doi.org/10.5281/zenodo.7135955 。CSV 原文件 CC BY 4.0，无修改。MD5 f56061b09274ddab5695652bde1ed63a。
测量参考、英尺单位、漂移校正及采集/传输延迟见 https://doi.org/10.1029/2022WR032392 。
以 road_water_level_adj × 12 得到英寸（负值截为零）。非缺失且未标记问题才保留。本站按潮汐影响站处理。
2. USGS，430548089213101，N 3rd St Storm Sewer at E Johnson St, Madison, WI。连续瞬时 00065，英尺。
https://waterdata.usgs.gov/monitoring-location/USGS-430548089213101/
市政府的 3.9 英尺路面基准：
https://www.cityofmadison.com/engineering/projects/flood-warning-signs-at-e-johnson-street-and-n-third-street
以 max(0,(value-3.9)×12) 作路面相对水深代理。仅保留未附 qualifier 的数值；数据下载时为 Provisional，在线版可能修订。
mad/ 为官方 API 的观测列子集（部分按周查询再按月合并），2025-04 到 2026-10，存在空月或长缺口。fetch_mad.py 可从数据服务重新取得。
3. 两地均为单点压力式排水设施观测，路面高程是参考面。代理值有别于纽约街面正下方的超声测距。没有以摄像头逐例复核；按测量时间回放，不含通信延迟。

模拟数据
UrbanFlood24，Cao, Wang & Qin, CC BY 4.0，https://doi.org/10.6084/m9.figshare.28082549.v1
作者项目与单位说明：https://holmescao.github.io/datasets/urbanflood24 ，https://github.com/holmescao/U-RNN/blob/main/tutorials/en/02-datasets.md 。
来源为上述数据包的 urbanflood24/test/flood/location2/G1166_intensity_246/flood.npy，一场6小时的模拟。
为控制下载量选用 location2 测试集内压缩体积最小的成员，通过 HTTP Range 按 ZIP 目录读取、解压并检查成员 CRC。
压缩包内提供该场景的抽样派生数据 shenzhen_grid.npz，保留所有360个分钟帧、原始米单位及浮点精度。
网格行列从索引10开始每20格取一个，共25×25个点，只评第一次超过10 mm的过程。
未按洪水深度挑点，未套道路掩膜。在模拟降雨条件下统一走非潮汐分支；这是假设而非实测站点属性。
未湿点不构成事件负例，同一场景中各点空间相关；不应当作独立风暴或真实车行道实测。

回放
真实序列先按UTC排序、以30分钟无>10 mm读数（同一段内观测间隔最多12分钟）分隔候选过程。
到路面或路面以下（<=0）视为退水，当前事件的预测窗在退水或35分钟时停止。
首湿第5分钟最新观测必须仍湿且年龄<=3分钟，之前不能越线；未来必须有观测支持（相邻支持点与窗边界间隙不超过5分钟）。
纽约阈值和系数不变，第8分钟需有新增湿观测且尚未越线。未使用插值。
及时命中 = 告警到首次越线前一个低读数仍有至少5分钟，超阈标准为4英寸（10.16厘米）。
候选分段不等于原论文的人审事件。不宜把不同单位（实测事件和模拟网格）合并评分。
