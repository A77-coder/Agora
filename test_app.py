"""
議論形成の場 Agora: Web UI（app.py）のヘッドレス動作テスト
Streamlit の AppTest を使い、ブラウザなし・APIなしで画面の描画とデモ再生を検証します。
"""

import os
import unittest

from streamlit.testing.v1 import AppTest

APP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")


class TestWebApp(unittest.TestCase):
    """app.py の描画・デモモード・パスワード保護の検証"""

    def setUp(self) -> None:
        # テスト間で環境変数が漏れないように退避
        self._saved_pw = os.environ.pop("APP_PASSWORD", None)

    def tearDown(self) -> None:
        os.environ.pop("APP_PASSWORD", None)
        if self._saved_pw is not None:
            os.environ["APP_PASSWORD"] = self._saved_pw

    def test_initial_render_without_error(self) -> None:
        """起動直後の画面が例外なく描画されること"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        self.assertFalse(at.exception, f"描画時に例外: {at.exception}")
        self.assertIn("議論形成の場 Agora", at.title[0].value)

    def test_demo_mode_step_playback(self) -> None:
        """デモモードでロード→1発言進める操作ができること"""
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        at.sidebar.radio[0].set_value("🎬 発表デモ再生モード (API不要)").run()
        self.assertFalse(at.exception, f"デモ切替で例外: {at.exception}")

        # 「デモをロード／リセット」ボタンを押す
        load_btn = [b for b in at.sidebar.button if "デモをロード" in b.label][0]
        load_btn.click().run()
        self.assertFalse(at.exception, f"デモロードで例外: {at.exception}")

        # 「次の発言へ進む」を押すと対話履歴が1件増える
        next_btn = [b for b in at.button if "次の発言へ進む" in b.label][0]
        next_btn.click().run()
        self.assertFalse(at.exception, f"ステップ再生で例外: {at.exception}")
        self.assertEqual(len(at.session_state.dialogue_history), 1)

    def test_password_gate_hides_start_button(self) -> None:
        """APP_PASSWORD 設定時は、パスワード入力前に開始ボタンが出ないこと"""
        os.environ["APP_PASSWORD"] = "test-pass"
        at = AppTest.from_file(APP_PATH, default_timeout=30).run()
        # 公開環境ではデモが既定なので、リアルタイムに切り替える
        at.sidebar.radio[0].set_value("🌐 リアルタイム対話 (Gemini API)").run()
        labels = [b.label for b in at.sidebar.button]
        self.assertFalse(any("議論を開始する" in l for l in labels))

        # 正しいパスワードを入れると開始ボタンが現れる
        at.sidebar.text_input[-1].set_value("test-pass").run()
        labels = [b.label for b in at.sidebar.button]
        self.assertTrue(any("議論を開始する" in l for l in labels))


if __name__ == "__main__":
    unittest.main()
