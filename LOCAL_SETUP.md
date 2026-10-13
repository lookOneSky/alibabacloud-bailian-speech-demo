# Windows 本地运行

项目目录：`I:\CodeAll\alibabacloud-bailian-speech-demo`。

1. 双击项目根目录的 `start.bat`，打开 <http://127.0.0.1:7860>。
2. 在页面填入北京地域的百炼 API Key，输入文字并点击“生成语音（调用云端）”。也可将 Key 填入根目录 `.env` 中的 `DASHSCOPE_API_KEY=`，保存后直接生成，无需重启。
3. 在页面试听或下载 MP3；原始音频保存在 `audio-results`。

本地页面默认使用 `qwen-audio-3.1-tts-flash` 和 `longanfengyue_v3.1`，也可切换仓库示例使用的 3.0 模型。模型和音色必须匹配。页面中输入的 Key 不写入文件；`.env` 已被 Git 忽略。

在“创建声音”页可选择两种方式：

- 描述声音：填写声音名称、声音描述和 15～200 字的试听文字，点击创建后保存音色 ID，并播放接口返回的试听音频。不会额外调用语音合成。
- 复刻录音：填写公网可直接下载的录音文件链接（例如 OSS 链接），点击创建后保存音色 ID。此方式不会自动合成试听语音；本地文件路径和内网链接不可使用。

创建后，“生成语音”会自动选中相同模型和新音色；切换到该页后可自行生成语音。CosyVoice 3.5 没有系统音色，需要先创建自定义声音。云端审核可能需要时间，可在“我的声音”页点击“检查当前自定义声音状态（调用云端）”。状态为“可用”后再合成。

“我的声音”的列表保存在本机 `voices.json`，按 Key 的摘要隔离记录，不保存明文 Key。该文件已被 Git 忽略，并禁止通过页面文件下载接口访问。刷新列表和加载页面只读本地配置，不调用百炼。只有明确标注“调用云端”的按钮才发起请求。换用新 Key 后，旧 Key 的音色不会自动显示。

创建音色的 HTTP 地址默认根据 `DASHSCOPE_WEBSOCKET_URL` 的域名生成，也可在 `.env` 中设置 `DASHSCOPE_HTTP_URL=https://你的业务空间ID.cn-beijing.maas.aliyuncs.com/api/v1`。使用专属域名时，应同步修改 WebSocket 地址为 `wss://你的业务空间ID.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference`。

创建请求不自动重试。如果请求超时或本地保存失败，请先在百炼控制台核对是否已经创建，并保留页面返回的音色 ID，避免重复创建。

这是百炼云端 API 的本地调用界面，实际语音合成需要有效的 Key 和模型调用权限。环境安装、页面启动和本地验证可在没有 Key 时完成。

Git 已沿用本机的持久代理 `http://127.0.0.1:10808`。此项目的 pip 代理保存在 `.venv\pip.ini`，运行代理保存在 `.env` 的 `NETWORK_PROXY`。本地页面地址已配置代理绕过。

Python 依赖安装在项目独立的 `.venv` 中，FFmpeg 放在 `.venv\Scripts\ffmpeg.exe`。重装依赖使用：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-local.lock.txt
```

要运行官方原始 Python 示例，先配置环境变量 `DASHSCOPE_API_KEY`，使用 `.venv` 的 Python，并将 `.venv\Scripts` 加入当前终端 PATH。原始示例不自动读取 `.env`，且默认仍为 3.0 模型。

- [项目源码](https://github.com/aliyun/alibabacloud-bailian-speech-demo)
- [获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)
- [官方音色列表](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)
- [声音设计指南](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)
- [声音设计 API](https://help.aliyun.com/zh/model-studio/voice-design-api-references)
- [声音复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)
