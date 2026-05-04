# 五子棋 Web 项目

基于 `Python + aiohttp + WebSocket` 的五子棋项目，支持：

- 本地人机对局（Minimax + Alpha-Beta）
- 联机房间对战（WebSocket 实时同步）
- 竞技模式（禁手规则）
- 悔棋、聊天、语音消息、AI 提示、每手读秒
- Bench / Elo 评测工具链

## 快速启动

```powershell
cd E:\wuziqi
python .\web_server.py
```

如果你本机命令是 `py`：

```powershell
py .\web_server.py
```

打开浏览器：

```text
http://127.0.0.1:8000
```

## 测试命令

```powershell
python -m unittest tests/test_gomoku_ai_engine.py
python -m unittest tests/test_engine_p1.py
python -m unittest tests/test_gomoku_competitive.py
```

## Bench / Elo 评测

### 1) 微基准

```powershell
python .\tools\bench_micro.py --dataset bench\midgame.json --loops 5000 --samples 30 --output reports\micro_report.json
```

### 2) 搜索质量基准

```powershell
python .\tools\bench_search.py --dataset bench\midgame.json --depth 3 --time-ms 800 --repeat 3 --disable-forced --disable-opening-book --disable-vcf-vct --output reports\search_report.json
```

### 3) 战术与规则基准

```powershell
python .\tools\bench_tactical.py --tactical bench\tactical.json --rules bench\rules.json --depth 3 --time-ms 800 --output reports\tactical_report.json
```

### 4) Elo 对战评测

```powershell
python .\tools\eval_elo.py --games 200 --depth-a 2 --depth-b 3 --time-a 300 --time-b 500 --output reports\elo_report.md
```

## 本轮 AI 优化（已完成）

### P1：候选分层硬规则

在候选排序里加入硬优先级，确保威胁处理优先于 `history/killer`：

1. 己方成五
2. 挡对方成五
3. 挡对方活四
4. 己方冲四/活四
5. 己方双三
6. 普通点位（再用启发式排序）

### P2：VCF/VCT 窄触发 + 快返回

- 根节点触发门槛：只在“局面有强战术信号”时触发 VCF/VCT
- 剩余时间门槛：时间不足时不触发
- 节点与宽度上限：超限快速返回 `UNKNOWN`
- 目标：避免 VCF/VCT 在平静局面吞掉搜索预算

### P3：评估函数防守增强

- 增大对“对手威胁”的惩罚权重
- 对“对手成五点/活四/强威胁”加入额外负分
- 目标：降低“只顾进攻不回防”的错误

## 最新验证结果（本地实测）

- 单测：`tests/test_gomoku_ai_engine.py`、`tests/test_engine_p1.py` 全通过
- 战术基准：`tactical_accuracy` 提升到 `1.0000`
- Elo（200局）：`Elo(A-B) = -6.95`，置信区间 `[-55.56, 41.39]`

结论：当前版本在战术防守正确率上有提升，但 Elo 仍未达到统计显著提升。

## 下一步路线图（Elo 导向）

执行顺序固定为：

1. 先消融，定位负优化模块
2. 再加速，提升有效搜索深度
3. 再分配，把深度给威胁分支
4. 最后做剪枝与排序微调

一句话原则：

```text
先定位负优化 → 再提升有效深度 → 最后优化深度分配
```

## 阶段一（已开工）：A/B/C/D/E 消融矩阵

目标：找到拖 Elo 的模块（VCF 或 P3 权重是否过强）。

矩阵定义：

- A: baseline（当前默认）
- B: P3 off
- C: VCF/VCT off
- D: P3 half + strict VCF
- E: P3 half only

一键运行：

```powershell
python .\tools\run_ablation_matrix.py --games 400 --depth-a 3 --depth-b 3 --time-a 500 --time-b 500 --bench-depth 3 --bench-time-ms 800 --bench-repeat 3 --output reports\ablation_matrix.md
```

输出：

- `reports/ablation_matrix.md`
- `reports/bench_B_p3_off.json` 等各 profile 的搜索基准

会同时记录这些指标：

- Elo（含 95% CI）
- NPS（估算）
- avg depth（迭代深度均值）
- VCF 决策影响率（`vcf_impact_rate_mean`）
- Root score volatility（分数波动代理）
- First-move fail-high proxy（`1 - first_candidate_final_rate`）

### 阶段一判定规则

- 若 `C_vcf_off` 明显更强：VCF 当前是负资产，继续收紧/临时关
- 若 `B_p3_off` 或 `E_p3_half_only` 更强：P3 防守权重过高
- 若 `D_p3_half_strict_vcf` 最强：方向正确，固定中等强度

## 部署（Render）

仓库已包含 `render.yaml`。推送到 GitHub 后，Render 会自动触发部署（若已开启自动部署）。

手动部署常用流程：

```powershell
git add .
git commit -m "Update gomoku web app"
git push origin main
```
