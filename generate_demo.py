"""
議論形成の場 Agora: デモデータ生成スクリプト
実際に Gemini API を呼び出して対話セッションを実行し、
発表用オフラインデモデータ（JSON）として保存します。

使い方:
    python generate_demo.py                       # 既定: 功利主義 vs 義務論 / 3ラウンド
    python generate_demo.py <preset_key> <rounds>
"""

import json
import os
import sys
from datetime import datetime

import dialogue_simulation as ds

# 保存先ファイル名（プリセットキーごと）
DEMO_FILENAME_TEMPLATE = "sample_debate_{key}.json"


def generate(preset_key: str = "utilitarian_vs_deontology", rounds: int = 3) -> str:
    """指定プリセットで実API対話を実行し、デモ用JSONを保存してパスを返す"""
    client = ds.create_client()
    agent_a, agent_b, topic = ds.create_agents_from_preset(preset_key)

    result = ds.run_dialogue_session(
        topic=topic,
        rounds=rounds,
        agents=(agent_a, agent_b),
        api_client=client,
    )

    # 実API生成であることを明記するメタ情報を付与（手書きデータとの区別のため）
    result["experiment"]["preset_key"] = preset_key
    result["experiment"]["preset_title"] = ds.PRESETS[preset_key].title
    result["experiment"]["generated_by"] = "Gemini API (generate_demo.py)"
    result["experiment"]["generated_at"] = datetime.now().isoformat()

    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, DEMO_FILENAME_TEMPLATE.format(key=preset_key))
    ds.save_result(result, out_path)
    return out_path


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "utilitarian_vs_deontology"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    path = generate(key, n)
    print(f"DEMO_GENERATED: {path}")
