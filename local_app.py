"""Local controls for the repository's DashScope tts_v2 speech synthesis demo."""

from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import sys
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / ".env"
RESULTS = ROOT / "audio-results"
VOICE_STORE = ROOT / "voices.json"
VOICE_LOCK = threading.RLock()
SYNTHESIS_LOCK = threading.Lock()
TITLE = "阿里云百炼 · 语音合成"


def read_settings() -> dict[str, str]:
    settings = {key: value for key, value in dotenv_values(CONFIG_PATH).items() if value is not None}
    for key in (
        "DASHSCOPE_API_KEY", "TTS_MODEL", "TTS_VOICE", "DASHSCOPE_WEBSOCKET_URL",
        "DASHSCOPE_HTTP_URL",
        "NETWORK_PROXY", "NO_PROXY", "APP_PORT",
    ):
        if os.environ.get(key):
            settings[key] = os.environ[key]
    return settings


settings = read_settings()
proxy = settings.get("NETWORK_PROXY", "http://127.0.0.1:10808")
for proxy_variable in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ[proxy_variable] = proxy
for bypass_variable in ("NO_PROXY", "no_proxy"):
    os.environ[bypass_variable] = settings.get("NO_PROXY", "127.0.0.1,localhost,::1")
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
os.environ["GRADIO_TEMP_DIR"] = str(ROOT / ".local-cache")
os.environ["PATH"] = str(ROOT / ".venv" / "Scripts") + os.pathsep + os.environ.get("PATH", "")

import dashscope
import gradio as gr
import requests
from dashscope.audio.tts_v2 import SpeechSynthesizer

VOICES = {
    "qwen-audio-3.1-tts-flash": [
        ("龙安风悦 · 女声", "longanfengyue_v3.1"),
        ("龙安欢 · 女声", "longanhuan_v3.1"),
        ("龙安灵心 · 女声", "longanlingxin_v3.1"),
        ("许南川 · 男声", "xunanchuan_v3.1"),
        ("于小云 · 元气亲切", "yuxiaoyun_v3.1"),
        ("安明远 · 清亮自然", "anmingyuan_v3.1"),
        ("叶清禾 · 温柔亲切", "yeqinghe_v3.1"),
    ],
    "qwen-audio-3.0-tts-flash": [
        ("龙安风悦", "longanfengyue"),
        ("龙安欢", "longanhuan_v3.6"),
        ("龙安灵希", "longanlingxi"),
    ],
    "qwen-audio-3.0-tts-plus": [
        ("龙安灵心", "longanlingxin"),
        ("龙安鲁风", "longanlufeng"),
    ],
    "cosyvoice-v3.5-plus": [],
    "cosyvoice-v3.5-flash": [],
}


def configuration_status() -> str:
    configured = bool(read_settings().get("DASHSCOPE_API_KEY", "").strip())
    return "已读取本机 API Key（尚未联网验证）。只有点击云端操作按钮才会发起调用。" if configured else "请在下方填写北京地域 API Key，或填入项目的 .env 文件。"


def resolve_key(api_key: str = "", *, required: bool = True) -> str:
    key = (api_key or read_settings().get("DASHSCOPE_API_KEY", "")).strip()
    if required and not key:
        raise gr.Error("尚未配置 API Key。请填写北京地域的百炼 API Key。")
    return key


def voice_owner(key: str) -> str:
    # Keep voices for different credentials separate without storing the API key.
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def read_voice_store() -> list[dict]:
    with VOICE_LOCK:
        if not VOICE_STORE.exists():
            return []
        try:
            records = json.loads(VOICE_STORE.read_text(encoding="utf-8"))
            if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
                raise ValueError("invalid voice store")
            return records
        except (OSError, ValueError):
            raise gr.Error("本地音色记录无法读取，请检查 voices.json；原文件未被覆盖。") from None


def saved_voices(api_key: str = "", model: str | None = None) -> list[dict]:
    key = resolve_key(api_key, required=False)
    if not key:
        return []
    return [
        item for item in read_voice_store()
        if item.get("owner") == voice_owner(key)
        and item.get("model") in VOICES and item.get("voice_id")
        and (model is None or item["model"] == model)
    ]


def save_voice(key: str, record: dict) -> None:
    with VOICE_LOCK:
        records = read_voice_store()
        owner = voice_owner(key)
        records = [
            item for item in records
            if (item.get("owner"), item.get("voice_id")) != (owner, record["voice_id"])
        ]
        records.append({**record, "owner": owner})
        temporary = VOICE_STORE.with_name(".voices.json.tmp")
        try:
            temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(VOICE_STORE)
        finally:
            temporary.unlink(missing_ok=True)


def voice_choices(model: str, api_key: str = "") -> list[tuple[str, str]]:
    return VOICES.get(model, []) + [
        (f"{item.get('name', item['voice_id'])} · 我的声音", item["voice_id"])
        for item in saved_voices(api_key, model)
    ]


def voice_dropdown(model: str, api_key: str = "", selected: str | None = None):
    choices = voice_choices(model, api_key)
    values = {item[1] for item in choices}
    value = selected if selected in values else (choices[0][1] if choices else None)
    return gr.Dropdown(choices=choices, value=value, interactive=True)


def voice_rows(api_key: str = "") -> list[list[str]]:
    return [
        [item.get("name", ""), item["model"], item["voice_id"], item.get("kind", ""),
         {"OK": "可用", "DEPLOYING": "审核中", "UNDEPLOYED": "审核未通过"}.get(
             item.get("status"), "未查询"
         )]
        for item in saved_voices(api_key)
    ]


def refresh_local_voices(api_key: str, model: str, voice: str | None):
    return voice_dropdown(model, api_key, voice), voice_rows(api_key)


def change_model(model: str, api_key: str = ""):
    return voice_dropdown(model, api_key)


def change_creation_method(method: str):
    return gr.update(visible=method == "描述声音"), gr.update(visible=method == "复刻录音")


def enrollment_call(key: str, inputs: dict, parameters: dict | None = None) -> dict:
    config = read_settings()
    base_url = config.get("DASHSCOPE_HTTP_URL", "").strip()
    if not base_url:
        websocket = urlsplit(config.get("DASHSCOPE_WEBSOCKET_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"))
        base_url = urlunsplit(("https" if websocket.scheme == "wss" else "http", websocket.netloc, "/api/v1", "", ""))
    body = {"model": "voice-enrollment", "input": inputs}
    if parameters:
        body["parameters"] = parameters
    # A single POST: automatically retrying a creation can create duplicate voices.
    with requests.post(
        base_url.rstrip("/") + "/services/audio/tts/customization",
        headers={"Authorization": f"Bearer {key}"}, json=body,
        timeout=(15, 120), allow_redirects=False,
    ) as response:
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"服务返回了非 JSON 响应（HTTP {response.status_code}）。") from None
        if not isinstance(payload, dict):
            raise RuntimeError("服务返回格式异常。")
        if response.status_code != 200 or payload.get("code"):
            code = payload.get("code", f"HTTP {response.status_code}")
            message = payload.get("message", "请检查 Key、模型权限和地域配置。")
            raise RuntimeError(f"{code}: {message}")
        output = payload.get("output")
        if not isinstance(output, dict):
            raise RuntimeError("服务未返回有效的音色信息。")
        return output


def validate_audio_url(audio_url: str) -> str:
    url = audio_url.strip()
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if parsed.scheme not in ("https", "http") or not hostname or parsed.username or parsed.password:
            raise ValueError("invalid audio URL")
        if hostname.lower() in ("localhost", "localhost.localdomain") or hostname.lower().endswith((".localhost", ".local")):
            raise ValueError("local audio URL")
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("private audio URL")
    except ValueError:
        raise gr.Error("请提供公网可直接下载的 http/https 录音链接，不能使用本地路径或内网地址。") from None
    return url


def create_voice(api_key: str, name: str, model: str, method: str, description: str,
                 preview_text: str, audio_url: str, language: str):
    key = resolve_key(api_key)
    name = name.strip()
    if not name or len(name) > 40:
        raise gr.Error("请输入 1～40 字的声音名称。")
    if model not in VOICES or language not in ("zh", "en"):
        raise gr.Error("请重新选择模型和语言。")
    inputs = {
        "action": "create_voice", "target_model": model,
        "prefix": "v" + uuid.uuid4().hex[:9], "language_hints": [language],
    }
    parameters = None
    if method == "描述声音":
        description, preview_text = description.strip(), preview_text.strip()
        if not description or len(description) > 500:
            raise gr.Error("声音描述需为 1～500 字，请使用中文或英文。")
        if not 15 <= len(preview_text) <= 200:
            raise gr.Error("试听文字需为 15～200 字。")
        inputs.update(voice_prompt=description, preview_text=preview_text)
        parameters = {"sample_rate": 24000, "response_format": "mp3"}
    elif method == "复刻录音":
        inputs["url"] = validate_audio_url(audio_url)
    else:
        raise gr.Error("请选择创建方式。")
    # Check persistence before creating a cloud resource.
    read_voice_store()
    try:
        output = enrollment_call(key, inputs, parameters)
        voice_id = output.get("voice_id")
        if not isinstance(voice_id, str) or not voice_id.strip():
            raise RuntimeError("服务未返回音色 ID，请勿反复点击创建。")
        if output.get("target_model", model) != model:
            raise RuntimeError(f"音色 {voice_id} 返回的模型不匹配，请保留 ID 并核对云端记录。")
        record = {
            "name": name, "model": model, "voice_id": voice_id, "kind": method,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": output.get("status", "UNKNOWN"),
        }
        try:
            save_voice(key, record)
        except Exception:
            raise RuntimeError(f"音色已在云端创建（ID：{voice_id}），但本地保存失败，请保留 ID，不要再次创建。") from None
        message = "声音已创建并保存，已选入“生成语音”的音色列表；云端审核完成后即可使用。"
        path = None
        preview = output.get("preview_audio")
        if isinstance(preview, dict) and preview.get("data"):
            try:
                audio_data = base64.b64decode(preview["data"], validate=True)
                audio_format = preview.get("response_format", "mp3")
                if not audio_data or audio_format not in ("mp3", "wav"):
                    raise ValueError("invalid preview audio")
                RESULTS.mkdir(exist_ok=True)
                path = RESULTS / f"voice-preview-{uuid.uuid4().hex[:12]}.{audio_format}"
                path.write_bytes(audio_data)
            except Exception:
                path = None
                message += " 预览音频保存失败，音色 ID 已保留，无需重新创建。"
        elif method == "描述声音":
            message += " 服务没有返回试听音频，音色 ID 已保留。"
        return (
            voice_id, str(path) if path else None, str(path) if path else None, message,
            gr.Dropdown(value=model), voice_dropdown(model, api_key, voice_id), voice_rows(api_key),
        )
    except requests.RequestException:
        raise gr.Error("网络请求失败或超时，云端可能已创建音色；请先在百炼控制台核对，避免重复创建。") from None
    except Exception as error:
        message = str(error).replace(key, "[API Key]")[:600]
        raise gr.Error(f"创建声音失败：{message}") from None


def check_voice_status(api_key: str, model: str, voice: str | None):
    key = resolve_key(api_key)
    record = next((item for item in saved_voices(api_key, model) if item["voice_id"] == voice), None)
    if record is None:
        raise gr.Error("请先在“生成语音”中选择一个已保存的自定义声音。")
    try:
        output = enrollment_call(key, {"action": "query_voice", "voice_id": voice})
        status = output.get("status", "UNKNOWN")
        save_voice(key, {**record, "status": status})
        message = {"OK": "审核通过，可用于合成。", "DEPLOYING": "审核中，请稍后手动查询。",
                   "UNDEPLOYED": "审核未通过，请在百炼控制台查看。"}.get(status, "服务未返回已知状态。")
        return message, voice_rows(api_key)
    except Exception as error:
        message = str(error).replace(key, "[API Key]")[:600]
        raise gr.Error(f"查询失败：{message}") from None


def synthesize(api_key: str, text: str, model: str, voice: str, instruction: str):
    config = read_settings()
    key = resolve_key(api_key)
    text = text.strip()
    if not text:
        raise gr.Error("请输入要合成的文字。")
    if len(text) > 2000:
        raise gr.Error("请将每次合成的文字控制在 2000 字以内。")
    if model not in VOICES or voice not in {item[1] for item in voice_choices(model, api_key)}:
        raise gr.Error("请重新选择与模型匹配的音色。")

    started = time.monotonic()
    try:
        # DashScope synthesis uses global credentials; serialize and always clear them.
        with SYNTHESIS_LOCK:
            dashscope.api_key = key
            dashscope.base_websocket_api_url = config.get(
                "DASHSCOPE_WEBSOCKET_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
            )
            try:
                synthesizer = SpeechSynthesizer(
                    model=model, voice=voice, instruction=instruction.strip() or None
                )
                audio = synthesizer.call(text, timeout_millis=120000)
            finally:
                dashscope.api_key = None
        if not audio:
            raise RuntimeError("服务未返回音频，请检查模型权限、地域及音色配置。")
        RESULTS.mkdir(exist_ok=True)
        path = RESULTS / f"speech-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.mp3"
        path.write_bytes(audio)
        elapsed = time.monotonic() - started
        return str(path), str(path), f"合成完成，用时 {elapsed:.1f} 秒。音频已保存到 audio-results。"
    except Exception as error:
        message = str(error).replace(key, "[API Key]")[:600]
        raise gr.Error(f"合成失败：{message}") from None


def build_app():
    model_default = settings.get("TTS_MODEL", "qwen-audio-3.1-tts-flash")
    if model_default not in VOICES:
        model_default = "qwen-audio-3.1-tts-flash"
    choices_default = voice_choices(model_default)
    voice_default = settings.get("TTS_VOICE")
    if voice_default not in {item[1] for item in choices_default}:
        voice_default = choices_default[0][1] if choices_default else None
    with gr.Blocks(title=TITLE) as app:
        gr.Markdown("# 阿里云百炼 · 语音合成\n生成语音，也可以创建并保存自己的声音。")
        status = gr.Markdown(configuration_status())
        api_key = gr.Textbox(
            label="北京地域 API Key", type="password",
            placeholder="已配置 .env 或环境变量时可留空",
            info="在页面填写的 Key 仅供本次请求使用，不写入配置文件。",
        )
        with gr.Tab("生成语音"):
            with gr.Row():
                model = gr.Dropdown(list(VOICES), value=model_default, label="模型")
                voice = gr.Dropdown(choices_default, value=voice_default, label="音色", interactive=True)
            gr.Markdown("CosyVoice 3.5 需先创建自定义声音；创建和合成必须使用相同模型。")
            text = gr.Textbox(
                label="待合成文字", lines=5,
                value="你好，欢迎使用阿里云百炼语音合成。今天的天气真不错，我们一起出去玩吧！",
            )
            instruction = gr.Textbox(
                label="说话风格（可选）", placeholder="例如：温柔自然的声音，语速适中", lines=2
            )
            gr.Examples(
                examples=[
                    ["今天的天气真不错！我们一起出去玩吧！", "自然亲切，语速适中"],
                    ["在很久很久以前，村庄里住着一只可爱的小兔子。", "温柔舒缓，适合睡前故事"],
                ], inputs=[text, instruction],
            )
            submit = gr.Button("生成语音（调用云端）", variant="primary")
            audio = gr.Audio(label="试听", type="filepath")
            download = gr.File(label="下载 MP3")
            result = gr.Textbox(label="结果", interactive=False)
        with gr.Tab("创建声音"):
            gr.Markdown("描述声音可以从零设计音色；复刻录音可提取录音中的音色。只有点击创建按钮才会调用云端。")
            with gr.Row():
                voice_name = gr.Textbox(label="声音名称", placeholder="例如：温柔讲故事的女声")
                create_model = gr.Dropdown(list(VOICES), value="cosyvoice-v3.5-plus", label="声音使用的模型")
                language = gr.Dropdown([("中文", "zh"), ("英文", "en")], value="zh", label="语言")
            method = gr.Radio(["描述声音", "复刻录音"], value="描述声音", label="创建方式")
            with gr.Column() as design_fields:
                description = gr.Textbox(
                    label="声音描述", lines=3, info="中文或英文，最多 500 字。",
                    placeholder="例如：年轻女性，声音温柔清亮，吐字清晰，适合讲故事",
                )
                preview_text = gr.Textbox(
                    label="试听文字", lines=2, info="15～200 字，与上方语言一致。",
                    value="你好，很高兴认识你。我会用温柔自然的声音，为你讲述一个有趣的故事。",
                )
            with gr.Column(visible=False) as clone_fields:
                audio_url = gr.Textbox(
                    label="录音文件链接", placeholder="https://.../voice.wav",
                    info="需为公网可直接下载的录音链接，例如 OSS 链接；本地文件路径无法使用。",
                )
                gr.Markdown("使用你有权使用的清晰单人录音，避免背景音乐和多人说话；此方式不自动生成试听语音。")
            create = gr.Button("创建声音（调用云端）", variant="primary")
            created_id = gr.Textbox(label="创建的音色 ID", interactive=False)
            preview_audio = gr.Audio(label="声音设计试听", type="filepath")
            preview_download = gr.File(label="下载试听音频")
            creation_result = gr.Textbox(label="创建结果", interactive=False)
        with gr.Tab("我的声音"):
            gr.Markdown("展示当前 Key 在本机创建并保存的声音。刷新列表只读本地记录；切换“生成语音”的模型即可选择相应声音。")
            library = gr.Dataframe(
                headers=["名称", "模型", "音色 ID", "创建方式", "云端状态"],
                datatype=["str"] * 5, value=voice_rows(), interactive=False,
                label="已保存的声音", column_count=5,
            )
            refresh = gr.Button("刷新本地列表")
            check = gr.Button("检查当前自定义声音状态（调用云端）")
            check_result = gr.Textbox(label="音色状态", interactive=False)
        gr.Markdown(
            "使用百炼云端模型；调用会按账号额度和计费规则扣费。"
            " [获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key)"
            " · [官方音色列表](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)"
            " · [声音设计](https://help.aliyun.com/zh/model-studio/voice-design-user-guide)"
            " · [声音复刻](https://help.aliyun.com/zh/model-studio/voice-cloning-user-guide)"
        )
        # input only handles manual changes, preserving the voice selected by creation.
        model.input(change_model, inputs=[model, api_key], outputs=voice, api_name=False)
        method.change(change_creation_method, inputs=method, outputs=[design_fields, clone_fields], api_name=False)
        local_inputs = [api_key, model, voice]
        local_outputs = [voice, library]
        api_key.change(refresh_local_voices, inputs=local_inputs, outputs=local_outputs, api_name=False)
        refresh.click(refresh_local_voices, inputs=local_inputs, outputs=local_outputs, api_name=False)
        submit.click(
            synthesize, inputs=[api_key, text, model, voice, instruction],
            outputs=[audio, download, result], concurrency_limit=1,
            concurrency_id="cloud_operations", api_name="synthesize",
        )
        create.click(
            create_voice, inputs=[api_key, voice_name, create_model, method, description, preview_text, audio_url, language],
            outputs=[created_id, preview_audio, preview_download, creation_result, model, voice, library],
            concurrency_limit=1, concurrency_id="cloud_operations", api_name="create_voice",
        )
        check.click(
            check_voice_status, inputs=local_inputs, outputs=[check_result, library],
            concurrency_limit=1, concurrency_id="cloud_operations", api_name="check_voice_status",
        )
        app.load(configuration_status, outputs=status, api_name=False)
        app.load(refresh_local_voices, inputs=local_inputs, outputs=local_outputs, api_name=False)
    return app


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not CONFIG_PATH.exists():
        shutil.copyfile(ROOT / ".env.example", CONFIG_PATH)
    port = int(read_settings().get("APP_PORT", "7860"))
    url = f"http://127.0.0.1:{port}"
    with socket.socket() as probe:
        already_running = probe.connect_ex(("127.0.0.1", port)) == 0
    if already_running:
        import urllib.request

        try:
            with urllib.request.urlopen(url + "/config", timeout=3) as response:
                is_our_app = json.load(response).get("title") == TITLE
        except Exception:
            is_our_app = False
        if not is_our_app:
            raise RuntimeError(f"端口 {port} 已被其他程序使用，请修改 .env 中的 APP_PORT。")
        print(f"页面已运行：{url}", flush=True)
        if args.open_browser:
            webbrowser.open(url)
        return
    print(f"本地页面：{url}", flush=True)
    build_app().queue(max_size=8).launch(
        server_name="127.0.0.1", server_port=port, share=False,
        inbrowser=args.open_browser, allowed_paths=[str(RESULTS)],
        blocked_paths=[str(CONFIG_PATH), str(VOICE_STORE), str(ROOT / ".voices.json.tmp"),
                       str(ROOT / ".venv"), str(ROOT / ".git")],
    )


if __name__ == "__main__":
    main()
