# 五子棋 Web 项目

基于 Python + WebSocket 的五子棋项目，支持本地人机与联机对战，包含竞技规则、聊天、AI 提示等功能。

## 功能概览

- 本地人机对局（Minimax + Alpha-Beta）
- 联机房间对战（房间码）
- WebSocket 实时同步（联机 + 本地）
- 本地悔棋、联机悔棋（需对方同意）
- 聊天（文字 + 语音消息）
- 每手读秒（房主可配置）
- AI 提示（每局每人一次）
- 竞技模式（黑棋禁手：长连 / 四四 / 三三）

## 竞技模式说明

- 本地模式：开始对局前选择是否开启竞技模式
- 联机模式：房主建房时选择，整局生效
- 开启后仅黑棋受禁手约束，白棋不受禁手限制
- AI 落子与 AI 提示会自动规避禁手

禁手规则参考：
- https://www.renju.net/rules/
- https://oconvertor.com/blog/gomoku-competitive-forbidden-moves-guide

## 本地运行

在 `E:\wuziqi` 目录执行：

```powershell
python .\web_server.py
```

如果你的环境使用 `py`：

```powershell
py .\web_server.py
```

安装依赖：

```powershell
python -m pip install -r .\requirements.txt
```

浏览器访问：

```text
http://127.0.0.1:8000
```

前端更新后建议强刷：

```text
Ctrl + Shift + R
```

## 测试

```powershell
python -m unittest -q tests.test_gomoku_competitive
python -m py_compile .\gomoku_core.py .\web_server.py
node --check .\web\assets\app.js
```

## 联机流程

1. 输入昵称，选择每手时限（可选竞技模式）
2. 房主创建房间并复制房间码给对手
3. 对手输入房间码加入
4. 仅房主点击“进入对局”后双方进入棋盘
5. 对局页可聊天、悔棋、重开、退出

## AI 路线图（后续可实现）

当前 AI 仍以 `minimax + alpha-beta` 为核心。后续建议升级：

- 更强走法排序（先搜必赢/必防/强制手）
- 迭代加深 + 每手时间预算
- 置换表（Zobrist Hash）
- 威胁空间优先搜索（活三/活四强制线）
- 分阶段评估函数（开局/中盘/残局）

### 预期收益（经验值）

- 同等硬件下通常可接近 +1～+2 层“有效深度”
- 防守稳定性明显提升，漏防冲四概率下降
- 限时下走子质量更稳定
- 完整实现并调参后，Elo 常见可提升约 +200～+500（需实测）

### 建议评测方式

- 新旧引擎自博弈 100～500 局
- 固定开局集对比
- 输出胜率、平均耗时、Elo 估计增量

## Render 部署

推送代码：

```powershell
cd E:\wuziqi
git add .
git commit -m "Update gomoku web app"
git push
```

Render 部署：

1. 打开 https://render.com/
2. `New +` -> `Blueprint`
3. 连接 GitHub 仓库并选择本项目
4. 使用仓库中的 `render.yaml` 部署

## 环境变量

- `HOST`
- `PORT`
- `ROOM_TTL_SECONDS`
- `ROOM_TURN_LIMIT_SECONDS`
- `ROOM_HINT_PAUSE_SECONDS`

## 已知说明

- Render 免费实例可能休眠，首次访问会有冷启动延迟
- 浏览器缓存旧静态资源时可能出现样式或脚本异常，建议强刷
