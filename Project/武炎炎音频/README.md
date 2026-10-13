# 武炎炎音频

双击 `generate.bat`，默认使用 `qwen-audio-3.0-tts-plus`，用参考录音的音色生成 `文案.txt` 中的文字。输出文件名为 `玄岳门_武炎炎`，WAV、MP3 和 JSON 记录保存在本目录；已有文件会保留，新文件增加时间后缀。

双击 `generate_plus.bat` 使用相同的 Plus 模型，输出文件名为 `玄岳门_武炎炎_Plus`。同一录音、账号、模型和参考时长复用同一音色。原有 `.voice-cache.json` 保留，已创建音色继续使用。

默认参考录音为 `Audio/石殿配音_武炎炎.wav`（15 秒），已复制到本工程。相对录音、文案路径均以本角色目录为基准。缓存和新生成记录中的工程内路径使用相对路径，从其他目录启动或整体复制仓库也能运行。

生成逻辑已提取至 `../common/generate_voice.py`，与玄淼淼共用。角色差异在本目录 `voice.json`，公共模型、语速、风格和参考时长在上级 `voice_defaults.json`；角色配置可覆盖公共参数，命令行参数优先级最高。旧 `generate_voice.py` 仍可直接启动，会转发到共用脚本。

依赖使用仓库根目录 `.venv`，密钥和持久代理读取根目录 `.env`，代理默认 `http://127.0.0.1:10808`。根目录 `.env` 的 `TTS_MODEL` 不影响角色工程。

```powershell
.\generate.bat --text "进了玄岳门，我们的武当之旅就正式开始了！" --name "玄岳门_武炎炎"
.\generate.bat --text-file "其他文案.txt" --name "新配音"
.\generate.bat --check
.\generate_plus.bat
.\generate_plus.bat --reference "Audio/石殿配音_武炎炎.wav" --prompt-seconds 15
```

可选参数：`--reference` 更换参考 WAV；`--text-file` 指定 UTF-8 文案；`--text` 直接指定文案；`--name` 指定输出名；`--instruction` 指定说话风格；`--rate` 调整语速；`--model` 指定模型；`--prompt-seconds` 设置参考时长上限。`--check` 只检查本地配置，不需要 API Key，不调用云端。

共用流程提取参考录音首声道，转换为 24 kHz、16 bit 单声道 WAV，再通过百炼临时存储复刻音色。合成使用非实时 HTTP 接口等待完整音频。改变录音内容、模型或参考时长时会独立缓存音色；创建请求不会自动重试，下次启动先恢复云端已有音色。请保留 `.voice-cache.json`，其中只保存音色记录，不保存 API Key。

公共结构和新增角色方法见上级 `README.md`。
