import unittest
from unittest.mock import patch

import content


class HindiNewsQualityTests(unittest.TestCase):
    def test_rule_based_script_uses_up_to_seven_translated_facts(self):
        topic = {"title": "AI technology update", "link": "https://example.com/story", "summary": ""}
        article = " ".join(
            f"The company announced an important technology update number {i} with new features for users."
            for i in range(1, 8)
        )
        with patch.object(content, "_translate_sentence_to_hindi",
                          side_effect=[f"कंपनी ने तकनीक से जुड़ी महत्वपूर्ण जानकारी साझा की है संख्या {i}।"
                                       for i in range(1, 8)]) as translate:
            script = content._rule_based_script(topic, article, {"channel": {"name": "USHORA"}})
        self.assertEqual(script["source_fact_count"], 7)
        self.assertEqual(translate.call_count, 7)
        self.assertGreaterEqual(len(script["scenes"]), 9)
        self.assertEqual(len({s["visual_query"] for s in script["scenes"]}), len(script["scenes"]))

    def test_rule_based_script_fails_closed_when_translation_fails(self):
        topic = {"title": "AI update", "link": "https://example.com", "summary": ""}
        article = " ".join(
            f"The technology company announced a significant product update for customers number {i}."
            for i in range(1, 4)
        )
        with patch.object(content, "_translate_sentence_to_hindi", side_effect=RuntimeError("offline")):
            with self.assertRaisesRegex(RuntimeError, "no video made"):
                content._rule_based_script(topic, article, {"channel": {"name": "USHORA"}})

    def test_content_qa_rejects_generic_source_script(self):
        cfg = {"channel": {"spoken_name": "Ushora AI"}}
        script = {"title": "Tech news", "scenes": [
            {"voice": "नमस्ते दोस्तों आज की खबर सुनिए", "caption": "नमस्ते"},
            {"voice": "पूरी जानकारी के लिए original source पढ़ें", "caption": "source"},
            {"voice": "Comment करें और subscribe करें", "caption": "comment"},
        ], "source_fact_count": 1}
        with self.assertRaisesRegex(RuntimeError, "source facts"):
            content.validate_script(script, cfg, require_source=True)

    def test_content_qa_accepts_three_hindi_facts(self):
        cfg = {"channel": {"spoken_name": "Ushora AI"}}
        fact = "कंपनी ने अपने नए सॉफ्टवेयर में कई महत्वपूर्ण बदलाव किए हैं।"
        script = {"title": "तकनीक अपडेट", "source_fact_count": 3, "scenes": [
            {"voice": fact, "caption": fact},
            {"voice": fact, "caption": fact},
            {"voice": fact, "caption": fact},
        ]}
        result = content.validate_script(script, cfg, require_source=True)
        self.assertEqual(len(result["scenes"]), 3)


if __name__ == "__main__":
    unittest.main()
