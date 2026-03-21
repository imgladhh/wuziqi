# 五子棋 Web 项目

这是一个基于 Python 标准库实现的 Web 五子棋项目，支持本地人机和联网对战，并带有简单但完整的浏览器 UI。

## 当前功能

- 本地人机对局
- 联网房间对战
- `minimax + alpha-beta 剪枝 + 位置评分` AI
- 本地自由悔棋
- 联机悔棋需对方同意
- 联机房间文本聊天
- 联机房间语音消息
- 显示对方上一手位置
- 联机每手读秒
- 房主创建房间时可设置每手时限
- 房间无操作自动过期
- 每位玩家每局一次 AI 提示
  - 会给出推荐落点
  - 会解释为什么建议这样下
  - 使用提示时当前回合读秒会临时暂停

## 主要文件

- `web_server.py`：Python HTTP 服务、房间逻辑、联机 API
- `gomoku_core.py`：棋盘规则、胜负判断、AI 搜索与提示解释
- `web/index.html`：Web 页面结构
- `web/assets/app.js`：前端交互、棋盘渲染、联机轮询
- `web/assets/style.css`：页面样式
- `render.yaml`：Render 部署配置
- `requirements.txt`：依赖声明

## 本地运行

在 `E:\wuziqi` 目录下运行：

```powershell
py .\web_server.py
```

如果你的环境里 `py` 不可用，也可以试：

```powershell
python .\web_server.py
```

启动后在浏览器打开：

```text
http://127.0.0.1:8000
```

如果前端代码刚更新过，建议进入页面后按一次：

```text
Ctrl + Shift + R
```

## 本地联机测试

同一台电脑上可以这样模拟两个玩家：

1. 普通窗口打开 `http://127.0.0.1:8000`
2. 无痕窗口再打开一次 `http://127.0.0.1:8000`
3. 一边创建房间，另一边输入房间码加入

## 联机说明

### 创建房间

1. 进入 `Online Mode`
2. 输入昵称
3. 选择每手时限
4. 点击 `Create Room`

### 加入房间

1. 打开同一个网页地址
2. 输入昵称
3. 输入房间码
4. 点击 `Join Room`

## AI 提示规则

- 仅联网对战可用
- 每位玩家每局最多使用一次
- 只能在轮到自己时使用
- 使用后会显示推荐坐标和原因说明
- 使用提示时，本回合读秒会暂时暂停

相关可调参数：

- `ROOM_HINT_PAUSE_SECONDS`
  - 默认值：`20`
  - 含义：使用 AI 提示后读秒暂停的秒数

## 房间与计时规则

- 房间数据保存在内存中，服务重启后房间会失效
- 房间默认 `30` 分钟无活动自动过期
- 默认每手时限由房主创建房间时选择
- 若超时未落子，对手直接判胜

可调环境变量：

- `HOST`
- `PORT`
- `ROOM_TTL_SECONDS`
- `ROOM_TURN_LIMIT_SECONDS`
- `ROOM_HINT_PAUSE_SECONDS`

## 语音消息说明

- 语音消息是“房间语音留言”，不是实时语音通话
- 浏览器需要麦克风权限
- 当前单条语音最长 `15` 秒
- 如果系统或浏览器禁用了麦克风，发送会失败

## Render 部署

### 推送到 GitHub

```powershell
cd E:\wuziqi
git add .
git commit -m "Update gomoku web app"
git push
```

### 在 Render 部署

1. 打开 [Render](https://render.com/)
2. 选择 `New +`
3. 选择 `Blueprint`
4. 连接 GitHub 仓库
5. 选择本项目仓库
6. 部署

项目已经包含 `render.yaml`，Render 会自动读取配置。

## 已知说明

- 当前联机使用轮询同步，不是 WebSocket
- 免费 Render 实例可能会休眠，首次访问会稍慢
- 浏览器缓存旧前端资源时，可能需要强制刷新页面
