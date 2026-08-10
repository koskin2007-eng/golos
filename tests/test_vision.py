from __future__ import annotations

import unittest

from PIL import Image

from voice_input.config import build_config, DEFAULT_CONFIG_DATA
from voice_input.vision.translator import _parse_result, _prepare_image, _reasoning_effort


class VisionTranslatorTests(unittest.TestCase):
    def test_default_vision_configuration_is_economical(self) -> None:
        config = build_config(DEFAULT_CONFIG_DATA)
        self.assertTrue(config.vision.enabled)
        self.assertEqual(config.vision.hotkey, "F9")
        self.assertEqual(config.vision.model, "gpt-5-nano")
        self.assertEqual(config.vision.detail, "high")

    def test_large_image_is_resized_without_changing_aspect_ratio(self) -> None:
        image = Image.new("RGB", (3200, 1600), "white")
        prepared = _prepare_image(image, 1600)
        self.assertEqual(prepared.size, (1600, 800))

    def test_json_result_is_parsed(self) -> None:
        result = _parse_result(
            '{"source_language":"English","source_text":"Hello","translated_text":"Привет"}'
        )
        self.assertEqual(result["translated_text"], "Привет")

    def test_reasoning_effort_matches_model_family(self) -> None:
        self.assertEqual(_reasoning_effort("gpt-5-nano"), "minimal")
        self.assertEqual(_reasoning_effort("gpt-5.6-luna"), "none")


if __name__ == "__main__":
    unittest.main()
