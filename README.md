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

若你的环境使用 `py`：

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

## AI 评测（Elo）

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

## Gomoku Engine Roadmap v3.0（可执行任务清单）

说明：
- 当前项目是 Python 版本，引擎优化以“相对收益”为主（如 NPS 提升、命中率提升、确定性保障）。
- ns 级目标可在后续 C++ 内核阶段追求。

### 阶段 1：性能基石 + 防漏杀（Week 1–2）

目标：
- NPS 达到当前 2x~4x
- 10~15 手内简单 VCF 不漏
- 状态可完全回滚（deterministic）

任务清单：
- [ ] 1. 增量状态系统（StateUpdater）
  - 维护：`board`、`zobrist`、四方向线状态、pattern cache（可扩展 legality cache）
  - 接口：`make_move()` / `unmake_move()`
  - 验收：
    - 随机 10k 局 `make -> unmake` 后状态一致
    - 单线程同局面 `best_move` 完全一致
- [ ] 2. 两层 Pattern Lookup（PatternEvaluator）
  - L1：局部窗口 -> 模式类型（FIVE / OPEN_FOUR / FOUR / OPEN_THREE / THREE / TWO / NONE）
  - L2：四方向组合 -> 威胁等级（WIN / MUST_BLOCK / FORCING / NORMAL）
  - 验收：
    - 覆盖测试（窗口组合）
    - 人工 case 分类正确
- [ ] 3. 简版 VCF（VCFSolver）
  - 只搜：冲四 / 防冲四
  - 触发：root、PV、上一手形成强威胁、近叶子
  - 验收：
    - 杀棋题集命中率 >= 95%
    - 不出现调用爆炸和超时
- [ ] 4. 轻量开局库（OpeningBook）
  - 先做 6~8 手轻量命中
  - 验收：开局命中率 >= 80%

### 阶段 2：搜索效率优化（Week 3–4）

目标：
- 同时限深度 +1~2 ply
- fail-high / fail-low 明显下降

任务清单：
- [ ] 5. Aspiration Windows
  - 用前一迭代分数做窄窗，失败后扩窗重搜
- [ ] 6. IID（内部迭代加深）
  - TT miss 且深度较深时，先搜浅层拿 PV move
- [ ] 7. 候选分层硬规则
  - 优先级固定：VCF/VCT > 必防 > 强制威胁 > killer > history
  - 约束：`history` 不能覆盖必防点
- [ ] 8. Threat Quiescence
  - 只扩展：五、活四、冲四（活三可选）
  - 禁止普通静态扩展
- [ ] 9. Eval Correction（轻量）
  - 残差修正 `delta_score`
  - 约束：`|delta| < 主评估 10%` 且不覆盖 FIVE/OPEN_FOUR 规则

### 阶段 3：并行 + 高级战术（Week 5–8）

前置条件：
- 单线程 deterministic 通过
- TT 无污染
- eval 稳定

任务清单：
- [ ] 10. Lazy SMP（ParallelSearch）
  - shared TT + 多线程独立搜索
  - root move 打散 + 轻度深度偏移
- [ ] 11. VCT 扩展版
  - 加入活三、双威胁并控制深宽
- [ ] 12. 禁手增量缓存（ForbiddenChecker）
  - 目标：合法性检查接近 O(1)

## 全局工程约束（必须遵守）

- 相同输入 -> 相同输出（单线程）
- `make -> unmake = identity`
- 威胁优先级高于启发式
- VCF 仅作为剪枝探测器，不接管主搜索

## 验收与 Benchmark 体系

- 性能：NPS、分支因子、TT 命中率
- 正确性：状态一致性、Zobrist 正确性
- 战术：杀棋题/防守题命中率
- 实战：`eval_elo.py`（A/B + ablation）

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
