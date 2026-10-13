"""共享脚本重构的离线回归测试，不调用百炼。"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from common import generate_voice as pipeline


MODEL = "qwen-audio-3.0-tts-plus"
OFFLINE_CONFIG = {"DASHSCOPE_API_KEY": "offline-key", "http_url": "https://example.invalid/api/v1"}
# 原脚本以这组账号、地址、模型和录音生成的缓存键，用于验证重构兼容旧缓存。
LEGACY_IDENTITY = "651e5d3ce74d874c3e9be7d44f6f48930e3e4ce5dcfbf5962f54f7c18dcc32e5"


def wav_bytes(seconds=5):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\0\0" * (24000 * seconds))
    return output.getvalue()


class VoicePipelineTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        temporary = tempfile.TemporaryDirectory(prefix="voice-pipeline-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name).resolve()
        self.profile = self.directory / "voice.json"
        self.profile.write_text(json.dumps({
            "character": "测试角色", "voice_prefix": "tst",
            "reference": "Audio/参考.wav", "text_file": "文案.txt", "output_name": "测试配音",
        }, ensure_ascii=False), encoding="utf-8")
        (self.directory / "Audio").mkdir()
        self.reference = self.directory / "Audio" / "参考.wav"
        self.reference.write_bytes(wav_bytes())
        (self.directory / "文案.txt").write_text("默认文案", encoding="utf-8")

    def get_voice(self, client, directory=None, prefix="wyy"):
        return pipeline.get_voice(client, OFFLINE_CONFIG, MODEL, self.reference,
                                  project_dir=directory or self.directory,
                                  character="测试角色", voice_prefix=prefix)

    def test_legacy_cache_reuses_voice_without_enrollment(self):
        self.reference.write_bytes(b"legacy reference")
        old_voice = MODEL + "-wyy651e5d3-existing"
        pipeline.save_json(self.directory / ".voice-cache.json", {
            LEGACY_IDENTITY: {"voice_id": old_voice, "reference": "D:/old/reference.wav"},
        })
        client = Mock(base_url=OFFLINE_CONFIG["http_url"])
        client.call.return_value = {"output": {"status": "OK", "target_model": MODEL}}

        self.assertEqual(self.get_voice(client), old_voice)
        client.call.assert_called_once_with({"action": "query_voice", "voice_id": old_voice})
        client.upload.assert_not_called()
        saved = json.loads((self.directory / ".voice-cache.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[LEGACY_IDENTITY]["reference"], "Audio/参考.wav")

    def test_other_character_recovers_its_own_prefix_and_cache(self):
        self.reference.write_bytes(b"legacy reference")
        other_directory = self.directory / "玄淼淼音频"
        other_directory.mkdir()
        old_cache = {LEGACY_IDENTITY: {"voice_id": "old-wuyanyan-voice"}}
        pipeline.save_json(self.directory / ".voice-cache.json", old_cache)
        new_voice = MODEL + "-xmm651e5d3-recovered"
        client = Mock(base_url=OFFLINE_CONFIG["http_url"])
        client.call.side_effect = [
            {"output": {"voice_list": [{"voice_id": new_voice}]}},
            {"output": {"status": "OK", "target_model": MODEL}},
        ]

        self.assertEqual(self.get_voice(client, other_directory, "xmm"), new_voice)
        self.assertEqual(client.call.call_args_list[0].args[0], {
            "action": "list_voice", "prefix": "xmm651e5d3", "page_index": 0, "page_size": 100,
        })
        client.upload.assert_not_called()
        self.assertEqual(json.loads((self.directory / ".voice-cache.json").read_text()), old_cache)
        saved = json.loads((other_directory / ".voice-cache.json").read_text(encoding="utf-8"))
        self.assertEqual(saved[LEGACY_IDENTITY]["voice_id"], new_voice)

    def test_cli_overrides_profile_and_shared_defaults(self):
        profile = json.loads(self.profile.read_text(encoding="utf-8"))
        profile["rate"] = 1.2
        self.profile.write_text(json.dumps(profile), encoding="utf-8")
        with patch.object(sys, "argv", ["generate", "--variant", "plus"]):
            args = pipeline.arguments(self.profile)
        self.assertEqual((args.model, args.rate, args.name), (MODEL, 1.2, "测试配音_Plus"))
        with patch.object(sys, "argv", ["generate", "--variant", "plus", "--rate", "0.9",
                                       "--name", "指定输出", "--model", "custom-model"]):
            args = pipeline.arguments(self.profile)
        self.assertEqual((args.model, args.rate, args.name), ("custom-model", 0.9, "指定输出"))

    def test_new_voice_uses_character_prefix_and_prepared_reference(self):
        client = Mock(base_url=OFFLINE_CONFIG["http_url"])
        new_voice = MODEL + "-xmm-new"
        client.upload.return_value = "oss://offline/reference.wav"
        client.call.side_effect = [
            {"output": {"voice_list": []}},
            {"output": {"voice_id": new_voice}},
            {"output": {"status": "OK", "target_model": MODEL}},
        ]

        self.assertEqual(self.get_voice(client, prefix="xmm"), new_voice)
        create_request = client.call.call_args_list[1].args[0]
        self.assertEqual(create_request["action"], "create_voice")
        self.assertEqual(create_request["target_model"], MODEL)
        self.assertTrue(create_request["prefix"].startswith("xmm"))
        self.assertEqual(len(create_request["prefix"]), 10)
        self.assertEqual(create_request["max_prompt_audio_length"], 15.0)
        self.assertFalse(create_request["enable_preprocess"])
        prepared = client.upload.call_args.args[0]
        self.assertEqual(prepared.parent, self.directory / ".cache")
        info = pipeline.audio_info(prepared)
        self.assertEqual((info["sample_rate"], info["channels"], info["sample_width_bytes"]),
                         (24000, 1, 2))

    def test_check_without_key_never_constructs_cloud_client(self):
        with patch.object(sys, "argv", ["generate", "--check"]), \
                patch.object(pipeline, "read_config", return_value={}), \
                patch.object(pipeline, "BailianClient") as client:
            self.assertEqual(pipeline.main(self.profile), 0)
        client.assert_not_called()

    def test_relative_text_and_outputs_work_from_another_directory(self):
        (self.directory / "另一个文案.txt").write_text("自定义文案", encoding="utf-8-sig")
        client = Mock()
        client.synthesize.return_value = (wav_bytes(1), "offline-request", {})
        other_cwd = self.directory / "启动目录"
        other_cwd.mkdir()
        original_cwd = Path.cwd()
        try:
            os.chdir(other_cwd)
            with patch.object(sys, "argv", ["generate", "--text-file", "另一个文案.txt"]), \
                    patch.object(pipeline, "read_config", return_value=OFFLINE_CONFIG), \
                    patch.object(pipeline, "BailianClient", return_value=client), \
                    patch.object(pipeline, "get_voice", return_value="test-voice"):
                self.assertEqual(pipeline.main(self.profile), 0)
                original_wav = (self.directory / "测试配音.wav").read_bytes()
                self.assertEqual(pipeline.main(self.profile), 0)
        finally:
            os.chdir(original_cwd)
        records = list(self.directory.glob("测试配音*.json"))
        self.assertEqual(len(records), 2)
        self.assertEqual((self.directory / "测试配音.wav").read_bytes(), original_wav)
        for path in records:
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["text"], "自定义文案")
            self.assertEqual(record["reference"], "Audio/参考.wav")
            self.assertFalse(Path(record["wav"]).is_absolute())
            self.assertFalse(Path(record["mp3"]).is_absolute())
            self.assertGreater((self.directory / record["mp3"]).stat().st_size, 0)
        self.assertEqual(list(other_cwd.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
