"""
議論形成の場 Agora: 統合テストスイートランナー
全単体テスト（コアシミュレーション、Persona、プリセット、可視化）を一括実行します。
"""

import unittest
import sys

def run_all() -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # コアテスト
    from test_dialogue_simulation import TestDialogueSimulation
    suite.addTests(loader.loadTestsFromTestCase(TestDialogueSimulation))

    # 可視化テスト
    from test_visualization import TestVisualization
    suite.addTests(loader.loadTestsFromTestCase(TestVisualization))

    # Web UI（Streamlit AppTest）テスト
    from test_app import TestWebApp
    suite.addTests(loader.loadTestsFromTestCase(TestWebApp))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
