# 五子棋 Web 项目

基于 `Python + aiohttp + WebSocket` 的五子棋项目，支持本地人机、网络对战、聊天、悔棋、AI 提示、每手读秒和竞技禁手规则。

## 当前状态

- 本地普通 AI 默认使用 C 引擎，`depth=20` 配合每手 `800ms` 时间控制自动迭代加深。
- 竞技模式也可使用 C 引擎，C 侧已实现黑棋禁手过滤，Python 侧仍保留最终合法性兜底。
- Render 部署会在 build 阶段自动编译 C 扩展，不需要提交 `.dll` 或 `.so`。
- C 版 VCF 探针已实测收益约为 0，当前已移除，避免额外维护复杂度。

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
- 在 800ms 时间预算下，C 引擎能自然搜索到较深层，VCF 探针覆盖的强制线已基本被 alpha-beta 深搜包含。
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

中期：

- 升级评估函数，细分跳三、眠三、连三等棋型。
- 加入双方威胁的非线性组合分数。
- 用固定测试集评估战术正确率、搜索稳定性和 Elo。

长期：

- 评估 NNUE 或小型神经网络估值，但这属于新的工程阶段。
