# 武炎炎音频

双击 `generate.bat`，默认使用 `qwen-audio-3.0-tts-plus`，用参考录音的音色生成 `文案.txt` 中的文字。生成的 WAV、MP3 和生成记录保存在本目录。再次运行会复用已保存的音色，已有音频会保留，新文件会增加时间后缀。

双击 `generate_plus.bat` 使用 `qwen-audio-3.0-tts-plus`，输出文件名为 `玄岳门_武炎炎_Plus`。脚本均通过非实时 HTTP 接口一次生成完整音频，不启用 SSE 流式输出或 WebSocket 实时合成。Plus 会基于同一录音创建并缓存绑定该模型的独立音色。

默认参考录音：`Audio/石殿配音_武炎炎.wav`（15 秒），原始音频随项目提交，无需依赖外部目录。默认路径和 `--reference` 指定的相对路径均以本脚本目录为基准，从其他目录启动也能找到录音。项目内参考录音的路径会以相对路径写入音色缓存和生成记录；录音内容未变时，仍复用原有音色。首次运行会提取首声道，转换为 24 kHz、16 bit 单声道 WAV，上传至百炼临时存储，再复刻音色。默认不修改参考音频的说话风格。

依赖使用项目根目录 `.venv`，密钥和网络配置读取根目录 `.env`。脚本默认模型为 `qwen-audio-3.0-tts-plus`，可通过 `--model` 显式指定其他模型；根目录 `.env` 的 `TTS_MODEL` 不影响本脚本。复刻与合成始终使用同一模型。持久代理配置为 `.env` 中的 `NETWORK_PROXY=http://127.0.0.1:10808`。

修改 `文案.txt` 后再次双击即可生成新内容。也可以在此目录执行：

```powershell
.\generate.bat --text "进了玄岳门，我们的武当之旅就正式开始了！" --name "玄岳门_武炎炎"
.\generate.bat --text-file "其他文案.txt" --name "新配音"
.\generate.bat --check
.\generate_plus.bat
.\generate_plus.bat --reference "更清晰的参考.wav" --prompt-seconds 30 --name "新版武炎炎"
```

可选参数：`--reference` 更换参考 WAV；`--instruction` 指定说话风格；`--rate` 调整语速（默认 1.0）；`--model` 指定模型；`--prompt-seconds` 设置音色提取时长上限（3～30 秒，默认 15 秒）。

增加片段不会自动累积训练。每次复刻仅使用一个参考音频，可以选出更好的片段，或拼接声音、语气一致的片段，再重新复刻。官方推荐 10～20 秒清晰录音；上传文件最长 60 秒、10 MB，实际用于音色提取的参考时长最多可设置为 30 秒。新增片段应避免背景音乐、噪声、混响、其他人声和过长停顿。改变参考文件或提取时长时，会独立缓存新音色。

`.voice-cache.json` 保存复刻音色 ID，不保存 API Key。请保留此文件。若创建请求超时，下次运行会先按录音、模型和账号对应的固定前缀恢复已有音色；脚本不会自动重试创建请求。云端音色未通过审核时会报告错误。

实现依据：[非实时合成 API](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-http-api)、[声音复刻 API](https://help.aliyun.com/zh/model-studio/voice-clone-design-http-api)、[参考音频要求](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)、[百炼临时文件上传](https://help.aliyun.com/zh/model-studio/get-temporary-file-url/)。
