"""根据角色配置复刻参考录音，并通过百炼非实时 HTTP 接口生成完整语音。"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULTS_FILE = HERE.parent / "voice_defaults.json"


def load_profile(path: Path) -> dict:
    defaults = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8-sig"))
    profile = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(defaults, dict) or not isinstance(profile, dict):
        raise ValueError("公共参数和角色配置必须是 JSON 对象。")
    settings = {**defaults, **profile}
    for field in ("character", "voice_prefix", "reference", "text_file", "output_name"):
        if not isinstance(settings.get(field), str) or not settings[field].strip():
            raise ValueError(f"角色配置缺少有效的 {field}。")
    if not re.fullmatch(r"[a-z0-9]{1,3}", settings["voice_prefix"]):
        raise ValueError("voice_prefix 需为 1～3 位小写字母或数字。")
    return settings


def arguments(default_config: Path | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config, required=default_config is None,
                        help="角色 voice.json 配置文件")
    parser.add_argument("--variant", choices=("standard", "plus"), default="standard",
                        help="plus 使用同一模型，默认输出名增加 _Plus")
    parser.add_argument("--reference", type=Path,
                        help="参考 WAV 录音，相对路径以角色配置所在目录为基准")
    text_group = parser.add_mutually_exclusive_group()
    text_group.add_argument("--text", help="直接指定要合成的文字")
    text_group.add_argument("--text-file", type=Path, help="UTF-8 文案文件，相对路径以角色目录为基准")
    parser.add_argument("--name", help="输出文件名，不含扩展名")
    parser.add_argument("--model",
                        help="复刻和合成使用的同一个模型，默认 qwen-audio-3.0-tts-plus")
    parser.add_argument("--instruction", help="可选的说话风格指令；默认沿用参考音频风格")
    parser.add_argument("--rate", type=float, help="语速，默认 1.0")
    parser.add_argument("--prompt-seconds", type=float,
                        help="用于提取音色的参考时长上限，3～30 秒，默认 15 秒")
    parser.add_argument("--check", action="store_true", help="仅检查本地配置，不调用云端")
    args = parser.parse_args()
    args.config = args.config.resolve()
    settings = load_profile(args.config)
    args.project_dir = args.config.parent
    args.character = settings["character"]
    args.voice_prefix = settings["voice_prefix"]
    for option, field in (("reference", "reference"), ("text_file", "text_file"),
                          ("name", "output_name"), ("model", "model"),
                          ("instruction", "instruction"), ("rate", "rate"),
                          ("prompt_seconds", "prompt_seconds")):
        if getattr(args, option) is None:
            value = settings[field]
            if option == "name" and args.variant == "plus":
                value += "_Plus"
            setattr(args, option, Path(value) if option in ("reference", "text_file") else value)
    return args


def read_config() -> dict:
    from dotenv import dotenv_values

    config = {key: value for key, value in dotenv_values(ROOT / ".env").items() if value is not None}
    for key in ("DASHSCOPE_API_KEY", "NETWORK_PROXY", "NO_PROXY",
                "DASHSCOPE_HTTP_URL", "DASHSCOPE_WEBSOCKET_URL"):
        if os.environ.get(key):
            config[key] = os.environ[key]
    # 每次启动均读取持久配置，HTTP 与 WebSocket 使用同一代理。
    proxy = config.get("NETWORK_PROXY", "http://127.0.0.1:10808")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[key] = proxy
    for key in ("NO_PROXY", "no_proxy"):
        os.environ[key] = config.get("NO_PROXY", "127.0.0.1,localhost,::1")
    websocket_url = config.get("DASHSCOPE_WEBSOCKET_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/inference")
    parsed = urlsplit(websocket_url)
    config["http_url"] = config.get("DASHSCOPE_HTTP_URL", "").strip() or urlunsplit(
        ("https" if parsed.scheme == "wss" else "http", parsed.netloc, "/api/v1", "", "")
    )
    config["websocket_url"] = websocket_url
    return config


def save_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def reference_path(path: Path, project_dir: Path) -> str:
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return str(path)


def audio_info(path_or_bytes: Path | bytes) -> dict:
    source = io.BytesIO(path_or_bytes) if isinstance(path_or_bytes, bytes) else str(path_or_bytes)
    with wave.open(source, "rb") as audio:
        if audio.getcomptype() != "NONE" or audio.getnframes() == 0:
            raise ValueError("音频为空或不是 PCM WAV。")
        return {"duration_seconds": round(audio.getnframes() / audio.getframerate(), 3),
                "sample_rate": audio.getframerate(), "channels": audio.getnchannels(),
                "sample_width_bytes": audio.getsampwidth()}


def finalize_wav(audio: bytes) -> bytes:
    # 流式 WAV 可能使用未知长度占位值；重新封装 PCM，写入实际 RIFF/data 长度。
    with wave.open(io.BytesIO(audio), "rb") as source:
        channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
        frames = source.readframes(source.getnframes())
    if not frames or len(frames) % (channels * width):
        raise ValueError("服务返回的 PCM 音频为空或不完整。")
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(channels)
        target.setsampwidth(width)
        target.setframerate(rate)
        target.writeframes(frames)
    return output.getvalue()


def transcode(source: Path, target: Path, *, reference: bool = False) -> None:
    import imageio_ffmpeg

    options = ["-af", "pan=mono|c0=c0", "-ar", "24000", "-c:a", "pcm_s16le"] if reference else [
        "-c:a", "libmp3lame", "-b:a", "192k"
    ]
    result = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(source), "-vn", *options, str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError("音频转换失败：" + result.stderr.strip()[:500])


class BailianClient:
    def __init__(self, config: dict):
        import requests

        self.session = requests.Session()
        self.base_url = config["http_url"].rstrip("/")
        self.headers = {"Authorization": "Bearer " + config["DASHSCOPE_API_KEY"],
                        "X-DashScope-OssResourceResolve": "enable"}

    @staticmethod
    def payload(response) -> dict:
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"服务返回非 JSON 响应，HTTP {response.status_code}。") from None
        if not isinstance(payload, dict):
            raise RuntimeError("服务响应格式异常。")
        if response.status_code != 200 or payload.get("code"):
            raise RuntimeError(f"{payload.get('code', response.status_code)}: {payload.get('message', '请求失败')}")
        return payload

    def call(self, inputs: dict) -> dict:
        # 创建音色不自动重试，避免超时后重复创建；下次启动按固定前缀恢复。
        with self.session.post(
            self.base_url + "/services/audio/tts/customization", headers=self.headers,
            json={"model": "voice-enrollment", "input": inputs},
            timeout=(15, 120), allow_redirects=False,
        ) as response:
            payload = self.payload(response)
        if not isinstance(payload.get("output"), dict):
            raise RuntimeError("服务未返回有效音色信息。")
        return payload

    def upload(self, path: Path) -> str:
        # 使用百炼自己的临时存储；不需要额外 OSS 密钥或第三方文件托管。
        with self.session.get(
            self.base_url + "/uploads", params={"action": "getPolicy", "model": "voice-enrollment"},
            headers=self.headers, timeout=(15, 60), allow_redirects=False,
        ) as response:
            policy = self.payload(response)["data"]
        object_key = policy["upload_dir"] + "/voice-" + uuid.uuid4().hex + ".wav"
        form = {"OSSAccessKeyId": policy["oss_access_key_id"], "Signature": policy["signature"],
                "policy": policy["policy"], "key": object_key,
                "x-oss-object-acl": policy["x_oss_object_acl"],
                "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
                "success_action_status": "200", "x-oss-content-type": "audio/wav"}
        with path.open("rb") as audio, self.session.post(
            policy["upload_host"], data=form, files={"file": ("reference.wav", audio, "audio/wav")},
            timeout=(15, 120), allow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"参考录音上传失败，HTTP {response.status_code}。")
        return "oss://" + object_key

    def close(self) -> None:
        self.session.close()


    def synthesize(self, model: str, voice: str, text: str, rate: float,
                   instruction: str) -> tuple[bytes, str | None, dict]:
        inputs = {"text": text, "voice": voice, "format": "wav", "sample_rate": 24000,
                  "rate": rate, "language_hints": ["zh"]}
        if instruction.strip():
            inputs["instruction"] = instruction.strip()
        # 不设置 SSE，使用非实时接口等待完整音频；失败时不降级到 WebSocket。
        with self.session.post(
            self.base_url + "/services/audio/tts/SpeechSynthesizer",
            headers={"Authorization": self.headers["Authorization"]},
            json={"model": model, "input": inputs},
            timeout=(15, 120), allow_redirects=False,
        ) as response:
            payload = self.payload(response)
        output = payload.get("output", {})
        if output.get("finish_reason") != "stop":
            raise RuntimeError("非实时接口未返回合成完成状态。")
        audio_url = output.get("audio", {}).get("url", "")
        parsed = urlsplit(audio_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise RuntimeError("非实时接口未返回有效的音频下载地址。")
        # 下载请求不携带百炼 API Key。
        with self.session.get(audio_url, timeout=(15, 120)) as response:
            if response.status_code != 200:
                raise RuntimeError(f"完整音频下载失败，HTTP {response.status_code}。")
            audio = response.content
        return audio, payload.get("request_id"), payload.get("usage", {})


def get_voice(client: BailianClient, config: dict, model: str, reference: Path,
              prompt_seconds: float = 15.0, *, project_dir: Path,
              character: str, voice_prefix: str) -> str:
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    owner = hashlib.sha256(config["DASHSCOPE_API_KEY"].encode()).hexdigest()
    identity_text = f"{owner}|{client.base_url}|{model}|{reference_hash}"
    # 保留默认 15 秒的旧缓存；改变提取时长时独立创建音色。
    if prompt_seconds != 15.0:
        identity_text += f"|prompt_seconds={prompt_seconds:g}"
    identity = hashlib.sha256(identity_text.encode()).hexdigest()
    prefix = voice_prefix + identity[:10 - len(voice_prefix)]
    cache_file = project_dir / ".voice-cache.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    if not isinstance(cache, dict):
        raise ValueError("音色缓存格式异常，请检查 .voice-cache.json。")
    record = cache.get(identity, {})
    voice_id = record.get("voice_id")
    if not voice_id:
        voices = client.call({"action": "list_voice", "prefix": prefix,
                              "page_index": 0, "page_size": 100})["output"].get("voice_list", [])
        voice_id = next((item["voice_id"] for item in voices
                         if item.get("voice_id", "").startswith(f"{model}-{prefix}-")), None)
        if voice_id:
            print(f"已恢复云端已有的{character}音色。", flush=True)
        else:
            print(f"正在上传参考录音并复刻{character}音色……", flush=True)
            prepared = project_dir / ".cache" / f"reference-{reference_hash[:12]}.wav"
            prepared.parent.mkdir(exist_ok=True)
            transcode(reference, prepared, reference=True)
            url = client.upload(prepared)
            payload = client.call({"action": "create_voice", "target_model": model,
                                   "prefix": prefix, "url": url, "language_hints": ["zh"],
                                   "max_prompt_audio_length": prompt_seconds, "enable_preprocess": False})
            voice_id = payload["output"].get("voice_id")
            if not isinstance(voice_id, str) or not voice_id:
                raise RuntimeError("未返回音色 ID；下次启动会先尝试恢复云端记录。")
        record = {"voice_id": voice_id, "model": model, "reference": reference_path(reference, project_dir),
                  "reference_sha256": reference_hash, "max_prompt_audio_length": prompt_seconds,
                  "created_at": datetime.now().astimezone().isoformat()}
        cache[identity] = record
        save_json(cache_file, cache)
    else:
        print(f"正在复用已保存的{character}音色……", flush=True)
    record["reference"] = reference_path(reference, project_dir)
    deadline = time.monotonic() + 120
    while True:
        output = client.call({"action": "query_voice", "voice_id": voice_id})["output"]
        status = output.get("status")
        record["status"] = status
        save_json(cache_file, cache)
        if output.get("target_model", model) != model:
            raise RuntimeError("云端音色绑定的模型不匹配。")
        if status == "OK":
            return voice_id
        if status != "DEPLOYING":
            raise RuntimeError(f"音色暂不可用：{status}；已保留音色 ID：{voice_id}。")
        if time.monotonic() >= deadline:
            raise RuntimeError("音色仍在审核中，请稍后重新运行；将复用本次音色。")
        print("音色正在审核，稍后继续查询……", flush=True)
        time.sleep(3)


def main(default_config: Path | None = None) -> int:
    key = ""
    try:
        args = arguments(default_config)
        config = read_config()
        key = config.get("DASHSCOPE_API_KEY", "").strip()
        project_dir = args.project_dir
        reference = (args.reference if args.reference.is_absolute() else project_dir / args.reference).resolve()
        info = audio_info(reference)
        if not 5 <= info["duration_seconds"] <= 60 or reference.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("参考录音需为 5～60 秒、10 MB 以内的 PCM WAV。")
        text_file = args.text_file if args.text_file.is_absolute() else project_dir / args.text_file
        text = args.text if args.text is not None else text_file.read_text(encoding="utf-8-sig")
        text = text.strip()
        if not text or len(text) > 2000:
            raise ValueError("文案需为 1～2000 字。")
        if not args.name.strip() or any(c in args.name for c in '<>:"/\\|?*') or args.name.endswith((".", " ")):
            raise ValueError("输出文件名无效。")
        if not 0.5 <= args.rate <= 2.0:
            raise ValueError("语速需在 0.5～2.0 之间。")
        if not 3.0 <= args.prompt_seconds <= 30.0:
            raise ValueError("参考音色提取时长需在 3～30 秒之间。")
        model = args.model
        print(f"角色：{args.character}\n参考录音：{reference}（{info['duration_seconds']} 秒）", flush=True)
        print(f"模型：{model}\n文案：{text}", flush=True)
        if args.check:
            import imageio_ffmpeg
            import requests  # noqa: F401

            if not Path(imageio_ffmpeg.get_ffmpeg_exe()).exists():
                raise ValueError("找不到音频转换工具。")
            print(f"本地检查通过；代理：{config.get('NETWORK_PROXY', 'http://127.0.0.1:10808')}；未调用云端。")
            return 0
        if not key:
            raise ValueError("请先在项目根目录 .env 中配置 DASHSCOPE_API_KEY。")
        client = BailianClient(config)
        try:
            voice_id = get_voice(client, config, model, reference, args.prompt_seconds,
                                 project_dir=project_dir, character=args.character,
                                 voice_prefix=args.voice_prefix)
            print("正在通过非实时 HTTP 接口生成完整语音……", flush=True)
            audio, request_id, usage = client.synthesize(model, voice_id, text, args.rate, args.instruction)
        finally:
            client.close()
        if not audio:
            raise RuntimeError("服务未返回音频。")
        audio = finalize_wav(audio)
        generated_info = audio_info(audio)
        stem = args.name
        if any((project_dir / f"{stem}.{extension}").exists() for extension in ("wav", "mp3", "json")):
            stem += "_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        wav_path = project_dir / f"{stem}.wav"
        mp3_path = project_dir / f"{stem}.mp3"
        wav_path.write_bytes(audio)
        transcode(wav_path, mp3_path)
        save_json(project_dir / f"{stem}.json", {
            "character": args.character,
            "text": text, "model": model, "voice_id": voice_id,
            "reference": reference_path(reference, project_dir), "instruction": args.instruction,
            "speech_rate": args.rate, "request_id": request_id, "usage": usage,
            "synthesis_mode": "http_non_streaming", "max_prompt_audio_length": args.prompt_seconds,
            "created_at": datetime.now().astimezone().isoformat(), **generated_info,
            "wav": reference_path(wav_path, project_dir), "mp3": reference_path(mp3_path, project_dir),
        })
        print(f"生成完成（{generated_info['duration_seconds']} 秒）：\n{wav_path}\n{mp3_path}", flush=True)
        return 0
    except Exception as error:
        message = str(error).replace(key, "[API Key]") if key else str(error)
        print("生成失败：" + message[:1000], file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
