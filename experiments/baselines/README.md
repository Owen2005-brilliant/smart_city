# 五种预警方法的等误报历史对照

安装依赖后在本目录运行以下命令。

    python -m pip install -r ../../nyc/requirements.txt
    python compare_algorithms.py ../../nyc

metrics.csv 记录总体与非潮汐组的分类准确率、告警查准率、及时召回率和混淆矩阵。paired.csv 记录同一评分有无复查的逐场汇总。后期为 2026-07 至 10 月；前一期为 2026 上半年，两期各自训练。共同主要输入是外推水深和潮汐属性，raw 只用外推水深。阈值按每个测试期和站点组的未升级事件事后匹配 10% 左右的误报。全网与单组分别匹配，不应相加。算法排名对应本次历史评分比较。正式产品在部署时使用其冻结门槛。各模型仅使用其判断时刻及以前的输入。
随机森林使用固定的 200 棵树、最小叶节点 10、种子 42，未搜索超参数。两阶段学习模型均使用同样的训练目标、首判惩罚和复查资格。两模型均在每阶段分别拟合。首个湿点后第 5 分钟判断，第 8 分钟允许复查。真值达到 4 英寸；及时要求告警到越线前最后一次低读数至少 5 分钟。一般准确率将报晚也计为真阳性。

数据归属 FloodNet（NYU、CUNY）与 NYC DEP。事件 https://data.cityofnewyork.us/d/aq7i-eu5q ，部署 https://data.cityofnewyork.us/d/kb2e-tjy3 。历史代码版本 https://github.com/Owen2005-brilliant/smart_city/tree/midterm-freeze-v1 。
