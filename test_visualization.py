"""
議論形成の場 Agora: ビジュアライゼーション単体テスト
Mermaid構文の生成、サニタイズ、HTML生成をAPI不要で検証します。
"""

import unittest
from typing import Any

from visualization import (
    generate_mermaid_argument_graph,
    render_mermaid_html,
    sanitize_mermaid_text,
)


class TestVisualization(unittest.TestCase):
    """ビジュアライゼーションモジュールの単体テスト"""

    def test_sanitize_mermaid_text(self) -> None:
        """特殊文字が構文破壊を起こさないよう正しく置換・短縮されること"""
        raw = 'これは "引用" と [括弧] と (丸括弧) と --> 矢印 を含む長いテキストです。'
        clean = sanitize_mermaid_text(raw, max_length=30)
        self.assertNotIn('"', clean)
        self.assertNotIn("[", clean)
        self.assertNotIn("]", clean)
        self.assertNotIn("-->", clean)
        self.assertTrue(clean.endswith("…"))

    def test_generate_mermaid_argument_graph(self) -> None:
        """構造化レコードから正しいMermaidコードが生成されること"""
        sample_record: dict[str, Any] = {
            "claims": [
                {"speaker": "功利主義者", "claim": "被害最小化を優先すべき", "reason": "命の数を最大化するため"}
            ],
            "agreements": ["事前の公的ガイドラインが必要である点"],
            "unresolved_points": ["尊厳と効用計算の最終優先度"],
            "conclusions": ["透明性の高い合意が必要"],
        }
        topic = "AIによるトリアージ判断"
        code = generate_mermaid_argument_graph(sample_record, topic=topic)

        self.assertIn("graph TD", code)
        self.assertIn("AIによるトリアージ判断", code)
        self.assertIn("被害最小化を優先すべき", code)
        self.assertIn("事前の公的ガイドラインが必要である点", code)
        self.assertIn("尊厳と効用計算の最終優先度", code)
        self.assertIn("透明性の高い合意が必要", code)

    def test_render_mermaid_html(self) -> None:
        """Mermaid HTML文字列にスクリプトタグとMermaid定義が含まれること"""
        code = "graph TD\n  A --> B"
        html = render_mermaid_html(code)
        self.assertIn("<script src=", html)
        self.assertIn("mermaid.initialize", html)
        self.assertIn("A --> B", html)


if __name__ == "__main__":
    unittest.main()
