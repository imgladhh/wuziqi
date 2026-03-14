# 五子棋 Web 项目

这是一个基于 Python 标准库实现的 Web 五子棋项目，包含：

- 浏览器本地人机对局
- 浏览器房间码联机对战
- `minimax + 位置打分` AI
- 本地自由悔棋
- 联机悔棋协商
- 联机房间文本聊天
- 高亮显示对方上一手

## 主要文件

- `web_server.py`: Python HTTP 服务与联机房间 API
- `gomoku_core.py`: 棋盘规则、胜负判断、AI 搜索
- `web/index.html`: Web 页面
- `web/assets/app.js`: 前端交互和棋盘渲染
- `web/assets/style.css`: 页面样式
- `run_web_game.bat`: Windows 启动脚本
- `render.yaml`: Render 部署配置
- `requirements.txt`: Python 依赖声明

## 本地启动

在 `E:\wuziqi` 下运行：

```powershell
python .\web_server.py
```

或者直接双击：

```bat
run_web_game.bat
```

启动后浏览器访问：

```text
http://127.0.0.1:8000
```

## GitHub + Render 快速部署

### 1. 推到 GitHub

先把项目推到你的 GitHub 仓库。

如果你本地已经装好 Git，典型流程是：

```powershell
cd E:\wuziqi
git init
git add .
git commit -m "Initial web gomoku app"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

### 2. 在 Render 创建 Web Service

1. 打开 [Render](https://render.com/)
2. 选择 `New +`
3. 选择 `Blueprint` 或 `Web Service`
4. 连接你的 GitHub 仓库
5. 选中这个项目仓库

如果使用 `Blueprint`，Render 会直接读取项目里的 `render.yaml`。

当前配置是：

- Runtime: Python
- Start Command: `python web_server.py`
- Port: 由 Render 注入 `PORT` 环境变量

### 3. 部署完成后访问公网地址

Render 会分配一个类似下面的公网地址：

```text
https://wuziqi-web.onrender.com
```

你和朋友都打开这个地址，就可以通过房间码联机。

## 联机方式

1. 房主打开网页，点击“创建房间”
2. 页面会生成一个 6 位房间码
3. 把房间码发给朋友
4. 朋友访问同一个网页地址，输入房间码后点击“加入房间”

## 说明

- 当前服务端数据保存在内存中，服务重启后房间会清空
- 本地默认监听端口是 `8000`
- 部署到 Render 时会自动读取平台注入的 `PORT`
- 房间默认 30 分钟无活动自动过期，可通过环境变量 `ROOM_TTL_SECONDS` 调整
