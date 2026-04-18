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

## 部署（Render）

仓库已包含 `render.yaml`。推送到 GitHub 后，Render 会自动触发部署（若已开启自动部署）。

手动部署常用流程：

```powershell
git add .
git commit -m "Update gomoku web app"
git push origin main
```
