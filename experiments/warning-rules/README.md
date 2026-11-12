# 论文发警规则在纽约街道上的对照

## 比较对象

Casado-Rodríguez 等（2025）利用欧洲 EFAS 的集合流量预报评估概率阈值和信号持续性。作者代码以最近 y 次预测中有 x 次达到阈值定义持续性。纽约缺少对应集合预报；本包保留发警规则，用当地历史训练的逻辑回归风险分数替代其超越概率，按两次可用判断分别测试单次达标和两次连续达标。作者原研究使用的河流阈值、起报间隔、预见期和评价单位均与本项目不同。本包只复现判定逻辑，不运行作者的欧洲数据处理流程。[论文](https://doi.org/10.1175/JHM-D-24-0054.1) · [作者源码](https://github.com/casadoj/EFAS_skill)

另外两项相关工作适合用于讨论研究定位。彰化研究用多站水深、降雨、随机森林和时空 LSTM 预报未来三小时水深；此前的纽约随机森林基线没有复现其完整系统。TEASER 用可靠性分类器决定是否需要更多观测，与项目中的等待决策相似；其完整方法未在本包实现。[彰化论文](https://www.sciencedirect.com/science/article/pii/S2212420924000256) · [TEASER](https://doi.org/10.1007/s10618-020-00690-z) · [TEASER 作者代码](https://github.com/patrickzib/SFA)

## 复现

进入本实验目录后运行：

    python -m pip install -r ../../nyc/requirements.txt
    python benchmark.py ../../nyc --out rerun.csv

输入为官方完整快照。数据归属 FloodNet（NYU、CUNY）及 NYC DEP。[事件](https://data.cityofnewyork.us/d/aq7i-eu5q) · [站点](https://data.cityofnewyork.us/d/kb2e-tjy3) · [冻结项目](https://github.com/Owen2005-brilliant/smart_city/tree/midterm-freeze-v1)

## 如何读 metrics.csv

- main 是 2026-07-01 至 10-26；prior 是 2026 上半年。每期只用更早的事件训练。三条规则共享同一输入、评分器、决策时刻、复查资格和 35 分钟真值截止点。首个湿读数后第 5 分钟可首报；第 8 分钟只有收到有效新读数、尚未越线才可复查。
- timely 评分器在训练中区分仍有 5 分钟提前量的升级与未升级，省去报晚正例；评估保留全部升级。any_upgrade 评分器用所有升级作为训练正例。前者输出排序分数，其绝对数值不能解释为真实事件概率。
- any_one 在任意一次过门槛时发警。confirm_both 要求两次都过同一门槛，最早第 8 分钟发警。higher_first 是项目的规则，首判得分扣 log(2)，复查时使用原分数。
- matched 单独在每个测试分组的阴性事件上对齐误报，各规则各取门槛；固定哈希打破并列。historical 在之前的验证期设门槛（阴性事件误报率至多 10%，同分同判），到测试期报告实际误报。后者属于本次比较的阈值协议，与已发布产品的部署阈值分开。全网及非潮汐子集分别评估，不相加。
- timely 加 late 加 missed 等于 upgrades。相同事件多站同日可能相关；原始计数差只描述本次历史回测。该快照已被重复用于探索。
