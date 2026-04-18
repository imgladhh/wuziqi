# 五子棋 Web 项目

基于 Python + WebSocket 的五子棋项目，支持本地人机与联机对战，包含竞技规则、聊天、AI 提示与 Elo 评测。

## 功能概览

- 本地人机对局（Minimax + Alpha-Beta）
- 联机房间对战（房间码）
- WebSocket 实时同步（联机 + 本地）
- 本地悔棋、联机悔棋（需对方同意）
- 聊天（文字 + 语音消息）
- 每手读秒（房主可配置）
- AI 提示（每局每人一次）
- 竞技模式（黑棋禁手：长连 / 四四 / 三三）

## 本地运行

```powershell
cd E:\wuziqi
python .\web_server.py
```

若环境使用 `py`：

```powershell
py .\web_server.py
```

浏览器访问：

```text
http://127.0.0.1:8000
```

## 测试

```powershell
python -m unittest -q tests.test_gomoku_competitive tests.test_gomoku_ai_engine
python -m py_compile .\gomoku_core.py .\web_server.py .\tools\eval_elo.py
node --check .\web\assets\app.js
```

## AI 评测（Elo 与消融）

常规 A/B：

```powershell
python .\tools\eval_elo.py --games 200 --depth-a 2 --depth-b 3 --time-a 800 --time-b 1200 --output reports\elo_report.md
```

消融评测（一次跑模块贡献）：

```powershell
python .\tools\eval_elo.py --ablation --ablation-mode single --ablation-games 200 --depth-a 2 --depth-b 3 --time-a 800 --time-b 1200 --output reports\ablation_report.md
```

全组合消融：

```powershell
python .\tools\eval_elo.py --ablation --ablation-mode all --ablation-games 200 --depth-a 2 --depth-b 3 --time-a 800 --time-b 1200 --output reports\ablation_report.md
```

## P0 评测脚本（已实现）

微基准（模块级）：

```powershell
python .\tools\bench_micro.py --dataset bench\midgame.json --loops 5000 --samples 30 --output reports\micro_report.json
```

搜索质量基准（固定局面）：

```powershell
python .\tools\bench_search.py --dataset bench\midgame.json --depth 3 --time-ms 800 --repeat 3 --disable-forced --output reports\search_report.json
```

战术与规则基准：

```powershell
python .\tools\bench_tactical.py --tactical bench\tactical.json --rules bench\rules.json --depth 3 --time-ms 800 --output reports\tactical_report.json
```

---

## 优先级调整（先做什么）

为了把“性能提升”转化成“棋力提升”，后续开发按下面顺序推进：

### P0：先补评测管线（优先于继续堆新算法）

- [ ] `tools/bench_micro.py`
  - 模块微基准：`make/unmake`、`eval`、候选生成、禁手检查、TT probe/store、VCF（后续）
  - 输出：平均耗时、p95、p99
- [ ] `tools/bench_search.py`
  - 固定局面集搜索质量评测
  - 指标：nodes、depth、branching factor、cutoff 位置、TT 命中、aspiration 失败次数、re-search 次数、qsearch 占比、VCF 调用统计
- [ ] `tools/bench_tactical.py`
  - 战术题命中率（杀棋/必防/禁手）
  - 指标：命中率、平均解题时间、漏杀率、漏防率
- [ ] 固定测试集目录
  - `bench/opening.json`
  - `bench/midgame.json`
  - `bench/tactical.json`
  - `bench/rules.json`

说明：只有评测管线先稳定，后面每个优化才能知道“到底有用没有”。

### P1：性能基石 + 防漏杀（Week 1–2）

- [x] 增量状态系统（StateUpdater）
  - 维护：`board`、`zobrist`、方向线状态、pattern cache
  - 接口：`make_move()` / `unmake_move()`
  - 验收：
    - 随机 10k 局 `make -> unmake` 后状态完全一致
    - 单线程同局面 `best_move` 完全一致
- [x] 两层 Pattern Lookup（PatternEvaluator）
  - L1：窗口 -> PatternType
  - L2：4方向组合 -> ThreatLevel
  - 验收：窗口覆盖测试 + 人工 case 正确
- [x] 简版 VCF（只冲四/防冲四）
  - 仅作为剪枝探测器
  - 验收：杀棋题命中率 >= 95%，不出现调用爆炸
- [x] 轻量开局库（6~8 手）
  - 验收：开局命中率 >= 80%

### P2：搜索效率优化（Week 3–4）

- [x] Aspiration Windows
- [x] IID（内部迭代加深）
- [x] 候选分层硬规则（VCF/VCT > 必防 > 强制威胁 > killer > history）
- [x] Threat Quiescence（只扩展五/活四/冲四/可选活三）
- [x] Eval Correction（轻量残差，`|delta| < 主评估 10%`）

### P3：并行 + 高级战术（Week 5–8）

- [x] Lazy SMP（shared TT，多线程独立搜索）
- [x] VCT 扩展版（活三、双威胁）
- [x] 禁手增量缓存（ForbiddenChecker）

---

## 全局硬约束（必须遵守）

- 相同输入 -> 相同输出（单线程 deterministic）
- `make -> unmake = identity`
- threat 优先级高于 heuristic
- VCF 仅作探测器，不接管主搜索

---

## 统一评测流程（每次改动都跑）

1. 微基准：模块是否真变快  
2. 搜索质量：同时限下树是否更聪明  
3. 棋力评估：A/B Elo（200~500 局起，含置信区间）

成功判定模板（必须同时成立）：

1. 模块 benchmark 更好  
2. 搜索质量指标更好  
3. Elo 在至少一个时控下显著提升  

若只满足 1，不算成功；若 1+2+3 同时成立，才算“真正提棋力”。

---

## 建议输出总表（版本回归）

每次评估建议统一输出：

`Version | NPS | AvgDepth | TT Hit | VCF Hit | Tactical Acc | Elo vs Base`

这样可以快速区分：
- 纯性能优化
- 战术增强
- 真正提升 Elo 的组合

---

## 环境变量

- `HOST`
- `PORT`
- `ROOM_TTL_SECONDS`
- `ROOM_TURN_LIMIT_SECONDS`
- `ROOM_HINT_PAUSE_SECONDS`

## 部署（Render）

```powershell
cd E:\wuziqi
git add .
git commit -m "Update gomoku web app"
git push
```

在 Render 选择 `Blueprint` 并读取仓库中的 `render.yaml`。
