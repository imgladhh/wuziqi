# 五子棋 Web 项目

这是一个基于 Python 的五子棋 Web 项目，支持本地人机与联机对战，提供简洁 UI、联机实时同步、聊天、AI 提示和竞技规则。

## 主要功能

- 本地人机对局
- 联机房间对战（房间码）
- 联机 WebSocket 实时同步
- 本地 WebSocket 实时同步（HTTP 兜底）
- `minimax + alpha-beta + 局面评分` AI
- AI 提示（每局每人一次）
- 本地悔棋
- 联机悔棋（需对方同意）
- 联机聊天（文本 + 语音消息）
- 每手读秒（房主创建房间时可配置）
- 房间空闲自动过期
- 竞技模式（黑棋禁手：长连 / 四四 / 三三）

## 竞技模式说明

项目支持“竞技五子棋”开关：

- 本地模式：可在开始本地对局前选择是否开启竞技模式。
- 联机模式：房主创建房间时可选择是否开启竞技模式（全房间生效）。

开启竞技模式后：

- 黑棋落子会执行禁手判定：
  - 长连（overline，6 子及以上）
  - 四四（double-four）
  - 三三（double-three）
- 白棋不受禁手限制。
- AI 落子与 AI 提示会自动规避禁手。

> 规则参考：
> - https://www.renju.net/rules/
> - https://oconvertor.com/blog/gomoku-competitive-forbidden-moves-guide

## AI 能力增强

当前 AI 在原有 minimax/alpha-beta 基础上新增：

- 合法落子约束接口（竞技模式下禁手过滤）
- 威胁分叉（fork）奖励（更重视可形成多重威胁的点）
- 强制手优先逻辑（即时取胜/必防）
- 候选点预筛与排序缓存

## 项目结构

- `web_server.py`：HTTP / WebSocket 服务、房间与对局状态管理
- `gomoku_core.py`：棋盘规则、禁手判定、AI 搜索与评估
- `web/index.html`：页面结构
- `web/assets/app.js`：前端交互、棋盘渲染、联机/本地 WS 同步
- `web/assets/style.css`：页面样式
- `tests/test_gomoku_competitive.py`：竞技规则与 AI 合法性测试
- `render.yaml`：Render 部署配置
- `requirements.txt`：Python 依赖

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

运行竞技规则相关测试：

```powershell
python -m unittest -q tests.test_gomoku_competitive
```

语法检查：

```powershell
python -m py_compile .\gomoku_core.py .\web_server.py
node --check .\web\assets\app.js
```

## 联机玩法

### 创建房间

1. 进入联机大厅
2. 输入昵称
3. 选择每手时限
4. 选择是否开启竞技模式
5. 点击“创建房间”

### 加入房间

1. 输入昵称
2. 输入房间码
3. 点击“加入房间”

### 进入对局

- 只有房主点击“进入对局”后，双方才会进入棋盘页面。

### 退出对局

- 对局页右上角可“退出棋局”。
- 一方退出后自己立即返回大厅，另一方会收到提示并在 3 秒后自动返回大厅。

## AI 提示规则

- 仅联机模式可用
- 每位玩家每局最多一次
- 仅在自己回合可用
- 返回推荐坐标与原因
- 使用时当前回合读秒会暂停

相关参数：

- `ROOM_HINT_PAUSE_SECONDS`（默认 `20`）

## 房间与计时规则

- 房间数据保存在内存中，服务重启后房间会失效
- 房间默认 `30` 分钟无活动自动过期
- 超时未落子：对手超时胜

相关环境变量：

- `HOST`
- `PORT`
- `ROOM_TTL_SECONDS`
- `ROOM_TURN_LIMIT_SECONDS`
- `ROOM_HINT_PAUSE_SECONDS`

## Render 部署

### 推送到 GitHub

```powershell
cd E:\wuziqi
git add .
git commit -m "Update gomoku web app"
git push
```

### 在 Render 部署

1. 打开 https://render.com/
2. `New +` -> `Blueprint`
3. 连接 GitHub 仓库
4. 选择本项目仓库
5. 直接部署（读取 `render.yaml`）

## 已知说明

- Render 免费实例可能休眠，首次访问会较慢
- 浏览器缓存旧资源时可能需强制刷新
