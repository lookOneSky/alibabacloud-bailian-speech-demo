# 玄淼淼音频

参考录音已复制至 `Audio/石殿配音_xmm_裁剪14秒.wav`，实际时长为 14 秒。默认配置与武炎炎一致：`qwen-audio-3.0-tts-plus`、语速 `1.0`、无附加风格指令、参考时长上限 `15` 秒。参考录音会按共用流程提取首声道并转换为 24 kHz、16 bit 单声道 WAV。

修改 `文案.txt` 后双击 `generate.bat`，输出默认命名为 `玄岳门_玄淼淼`；双击 `generate_plus.bat`，默认命名为 `玄岳门_玄淼淼_Plus`。WAV、MP3、JSON 记录和音色缓存均保存在本角色目录，已有文件会保留。初始文案沿用武炎炎，可独立修改。

角色差异在 `voice.json`，公共参数在上级 `voice_defaults.json`。所有入口复用 `../common` 中的脚本。密钥、代理读取仓库根目录 `.env`，依赖使用根目录 `.venv`。

```powershell
.\generate.bat --check
.\generate.bat --text "要生成的新文案" --name "新配音"
.\generate.bat --text-file "其他文案.txt"
.\generate_plus.bat --rate 1.0
```

`--reference` 和 `--text-file` 的相对路径以本角色目录为基准，从其他目录启动也能运行。`.voice-cache.json` 只保存音色记录，不保存 API Key；首次实际生成会创建玄淼淼的独立音色，请保留缓存以便复用。

完整参数和新增角色方法见上级 `README.md`。
