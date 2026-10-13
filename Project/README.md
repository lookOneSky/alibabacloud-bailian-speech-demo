# 角色音频工程

武炎炎和玄淼淼共用 `common/generate_voice.py` 的生成逻辑、根目录 `.venv` 的依赖及根目录 `.env` 的密钥和持久代理。角色目录仅保存角色配置、参考录音、文案和独立的生成结果、音色缓存。

```text
Project/
├── voice_defaults.json         公共模型、语速、风格和参考时长参数
├── common/
│   ├── generate.bat            共用运行入口
│   └── generate_voice.py       共用复刻、合成和缓存逻辑
├── 武炎炎音频/
│   ├── voice.json              武炎炎的差异配置
│   ├── Audio/石殿配音_武炎炎.wav
│   ├── 文案.txt
│   ├── generate.bat
│   └── generate_plus.bat
└── 玄淼淼音频/
    ├── voice.json              玄淼淼的差异配置
    ├── Audio/石殿配音_xmm_裁剪14秒.wav
    ├── 文案.txt
    ├── generate.bat
    └── generate_plus.bat
```

修改角色目录中的 `文案.txt` 后，双击该目录的 `generate.bat` 即可生成 WAV、MP3 和 JSON 记录。两个角色初始文案相同，可分别修改。默认模型为 `qwen-audio-3.0-tts-plus`，语速为 `1.0`，无附加风格指令，参考时长上限为 `15` 秒。`generate_plus.bat` 使用相同配置，默认文件名增加 `_Plus`；同一角色、录音和模型会复用同一个音色。

公共参数只需修改 `voice_defaults.json`。角色可在自己的 `voice.json` 中覆盖这些参数；命令行参数优先级最高。根目录 `.env` 的 `TTS_MODEL` 不影响角色工程，`NETWORK_PROXY` 默认沿用 `http://127.0.0.1:10808`。

`voice.json` 中的录音、文案路径以及命令行 `--reference`、`--text-file` 的相对路径均以角色目录为基准，不依赖启动时所在目录。缓存和新生成记录中，工程内素材及输出路径也使用相对路径。原始参考录音随工程保存，整个仓库复制到其他位置后仍可运行。

```powershell
# 在仓库根目录执行；--check 只检查本地，不调用云端，也不需要 API Key。
.\Project\武炎炎音频\generate.bat --check
.\Project\玄淼淼音频\generate.bat --check
.\Project\玄淼淼音频\generate.bat --text "进了玄岳门，我们的武当之旅就正式开始了！" --name "玄岳门_玄淼淼"
.\Project\玄淼淼音频\generate_plus.bat --reference "Audio/石殿配音_xmm_裁剪14秒.wav"
```

生成通过非实时 HTTP 接口等待完整音频。首次实际生成时创建角色对应的音色，再运行复用缓存。两个角色的 `.voice-cache.json` 和 `.cache/` 各自独立；武炎炎保留原有缓存身份和云端前缀，不需要重新创建已有音色。已有输出会保留，新文件自动增加时间后缀。

增加角色时，复制一个角色目录的入口和配置，放入新录音并修改 `voice.json` 的 `character`、`voice_prefix`、`reference`、`output_name`。`voice_prefix` 使用独立的 1～3 位小写字母或数字；不要复制其他角色的 `.voice-cache.json`、`.cache/` 或生成结果。共用脚本无需修改。
