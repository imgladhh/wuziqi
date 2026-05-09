# 五子棋 Web 项目

基于 `Python + aiohttp + WebSocket` 的五子棋项目，支持本地人机、网络对战、聊天室、悔棋、AI 提示、每手读秒和竞技禁手规则。

## 当前状态

- 本地普通 AI 默认使用 C 引擎，`depth=20` 配合每手 `800ms` 时间控制自动迭代加深。
- 竞技模式也可使用 C 引擎，C 侧已实现黑棋禁手过滤，Python 侧仍保留最终合法性兜底。
- Render 部署会在 build 阶段自动编译 C 扩展，不需要提交 `.dll` 或 `.so`。
- C 版 VCF 探针实测收益约为 0，当前已移除，避免额外维护复杂度。

## 已修复的关键问题

- 修复本地模式竞态：`refresh()` 轮询、WebSocket 重连消息和本地落子响应可能乱序到达。前端现在使用 `game_id + move_count` 防止旧状态覆盖新棋盘。
- 修复 Python fallback 搜索回滚：`place -> search -> remove` 现在使用 `try/finally`，避免搜索超时时把临时棋子遗留在真实棋盘上。
- 修复语音消息 XSS：聊天室渲染改为 DOM API，不再把 `audio_data` 或文本拼进 `innerHTML`；服务端只允许 `data:audio/(webm|mp4|mpeg|ogg|wav|aac);base64,` 格式的语音数据。
- 修复平局终局语义：本地和联机状态都通过 `win_reason` 标识 `line` / `timeout` / `draw`，前端和后端都会把平局当作终局处理。

## 剩余已知问题（暂不处理）

- P2：房间 TTL 可能清掉有活跃 WebSocket 的房间。当前 TTL 基于 `updated_at`，长时间无落子/聊天的房间仍可能被清理。
- P3：全局锁包住 AI 计算。当前并发量低时可接受，但高并发下会阻塞其他房间的状态更新和计时。
- P3：C 引擎使用进程级全局状态，非线程安全。当前服务端通过全局锁规避并发调用；如果未来把 AI 计算移出锁，需要先给 C 引擎加上下文对象或互斥。
- 架构：本地棋局存在服务器内存里。Render 重启、重新部署或实例休眠/唤醒后，本地棋局会丢失；长期方案是浏览器端存储本地棋局，或服务端持久化。

## 快速启动

```powershell
cd E:\wuziqi
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" .\web_server.py
```

打开浏览器：

```text
http://127.0.0.1:8000
```

如果你的 `python` 命令可用，也可以直接运行：

```powershell
python .\web_server.py
```

## C 引擎

源码位于：

```text
engine_c/gomoku_engine.c
engine_c/c_bridge.py
engine_c/build.py
```

本地编译：

```powershell
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" .\engine_c\build.py
```

编译产物：

- Windows: `engine_c/gomoku_engine.dll`
- Linux/Render: `engine_c/gomoku_engine.so`

这些产物已被 `.gitignore` 忽略。若 C 扩展缺失或加载失败，`GomokuAI` 会自动回退 Python 引擎。

## AI 结果

主要已验证收益：

| 对比 | 结果 |
|---|---:|
| Python depth 3 vs C depth 5 | C 约 +269 Elo |
| Python 基线 vs C 时间控深搜 | C 约 +288 Elo |
| C 深搜 + VCF 探针 | 约 0 Elo 增益 |

结论：

- 最大收益来自 C 引擎、增量评估和时间控深搜。
- 在 `800ms` 时间预算下，C 引擎能自然搜索到较深层，VCF 探针覆盖的强制线已基本被 alpha-beta 深搜包含。
- 下一阶段若继续提升棋力，优先方向应是评估函数质量，而不是继续增加独立战术探针。

## 常用测试

运行全部单测：

```powershell
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" -m unittest discover -s tests
```

只跑竞技禁手测试：

```powershell
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" -m unittest tests.test_gomoku_competitive
```

## Elo 评测

C 引擎时间控 vs Python 基线：

```powershell
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" .\tools\eval_elo.py `
  --games 200 `
  --depth-a 3 --depth-b 20 `
  --time-a 800 --time-b 800 `
  --use-c-engine-b `
  --output reports\c_engine_elo.md
```

C depth 5 vs C depth 20 时间控：

```powershell
& "C:\Users\imglad1991\AppData\Local\Programs\Python\Python313\python.exe" .\tools\eval_elo.py `
  --games 100 `
  --depth-a 5 --depth-b 20 `
  --time-a 200 --time-b 200 `
  --use-c-engine-a --use-c-engine-b `
  --output reports\depth20_vs_depth5.md
```

## Render 部署

`render.yaml` 已配置自动构建：

```yaml
buildCommand: |
  pip install -r requirements.txt
  python engine_c/build.py
startCommand: python web_server.py
```

推送到 GitHub 后，如果 Render 已开启自动部署，会自动编译 Linux `.so` 并启动服务。部署日志中应能看到类似：

```text
Built: /opt/render/project/src/engine_c/gomoku_engine.so
```

## 下一步路线

短期：

- 上线当前 C 引擎版本。
- 持续保留 Elo/bench 工具，避免后续优化出现负收益。
- 记录并监控剩余已知问题，优先处理影响线上稳定性的部分。

中期：

- 升级评估函数，细分跳三、眠三、连三等棋型。
- 加入双方威胁的非线性组合分数。
- 用固定测试集评估战术正确率、搜索稳定性和 Elo。

长期：

- 评估 NNUE 或小型神经网络估值，但这属于新的工程阶段。
