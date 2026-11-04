"""
人文系・言語文化箱庭シミュレーション 単体テストスイート
APIキー不要でAgent、Prompt、Schema、JSON保存、エラー判定、未記録ターン処理を検証します。
"""

import json
import os
import tempfile
import unittest
from typing import Any

import dialogue_simulation as ds


class TestDialogueSimulation(unittest.TestCase):
    """APIキー不要の単体テスト"""

    def setUp(self) -> None:
        """各テストの事前準備"""
        self.jp_agent, self.us_agent = ds.create_agents()

    def test_agent_initialization(self) -> None:
        """エージェントの基本属性が正しく初期化されること"""
        self.assertEqual(self.jp_agent.name, "JP")
        self.assertEqual(self.jp_agent.language, "日本語")
        self.assertIn("日本語を使用しながら", self.jp_agent.cultural_knowledge)
        self.assertEqual(self.jp_agent.memory, [])

        self.assertEqual(self.us_agent.name, "US")
        self.assertEqual(self.us_agent.language, "English")
        self.assertIn("American English", self.us_agent.cultural_knowledge)
        self.assertEqual(self.us_agent.memory, [])

    def test_agent_memory_limit_and_reset(self) -> None:
        """記憶がMEMORY_SIZE（最新3件）に保たれ、リセットで初期化されること"""
        for i in range(5):
            self.jp_agent.remember({"round": i, "content": f"claim_{i}"})

        # 最新の3件だけが残っていること
        self.assertEqual(len(self.jp_agent.memory), ds.MEMORY_SIZE)
        self.assertEqual(self.jp_agent.memory[0]["round"], 2)
        self.assertEqual(self.jp_agent.memory[1]["round"], 3)
        self.assertEqual(self.jp_agent.memory[2]["round"], 4)

        # リセットの検証
        self.jp_agent.reset_memory()
        self.assertEqual(len(self.jp_agent.memory), 0)

    def test_filter_memory_by_source(self) -> None:
        """記憶ソース（JP / US）ごとのフィルタリングが正しく機能すること"""
        memory = [
            {"round": 1, "source": "JP_recorder", "data": "jp1"},
            {"round": 1, "source": "US_recorder", "data": "us1"},
            {"round": 2, "source": "JP_recorder", "data": "jp2"},
        ]
        jp_mem = ds.filter_memory_by_source(memory, "JP")
        us_mem = ds.filter_memory_by_source(memory, "US")

        self.assertEqual(len(jp_mem), 2)
        self.assertEqual(jp_mem[0]["data"], "jp1")
        self.assertEqual(jp_mem[1]["data"], "jp2")

        self.assertEqual(len(us_mem), 1)
        self.assertEqual(us_mem[0]["data"], "us1")

    def test_build_dialogue_prompt(self) -> None:
        """対話プロンプトにエージェント情報、議題、記憶、直近の対話が反映されること"""
        history = [
            {"round": 1, "speaker": "JP", "text": "こんにちは"},
            {"round": 1, "speaker": "US", "text": "Hello there"},
        ]
        own_mem = [{"round": 1, "source": "JP_recorder", "record": {}}]
        opposing_mem = [{"round": 1, "source": "US_recorder", "record": {}}]
        topic = "AI技術と教育について"

        prompt = ds.build_dialogue_prompt(
            agent=self.jp_agent,
            dialogue_history=history,
            own_memory=own_mem,
            opposing_memory=opposing_mem,
            topic=topic,
        )

        self.assertIn("JP", prompt)
        self.assertIn("日本語", prompt)
        self.assertIn(topic, prompt)
        self.assertIn("こんにちは", prompt)
        self.assertIn("Hello there", prompt)
        self.assertIn("JP_recorder", prompt)
        self.assertIn("US_recorder", prompt)

    def test_build_recorder_prompt(self) -> None:
        """Recorderプロンプトに対象の対話スライスとルールが含まれること"""
        new_dialogue = [
            {"speaker": "JP", "text": "AIは学習支援に有用です。"},
            {"speaker": "US", "text": "Critical thinking might decrease."},
        ]
        prev_record = {"claims": []}

        prompt = ds.build_recorder_prompt(
            recorder_language="日本語",
            side_name="JP",
            new_dialogue=new_dialogue,
            previous_record=prev_record,
        )

        self.assertIn("JP側の論理構造記録係", prompt)
        self.assertIn("AIは学習支援に有用です。", prompt)
        self.assertIn("Critical thinking might decrease.", prompt)
        self.assertIn("claimsは最大6個", prompt)

    def test_schema_model_dump_and_validate(self) -> None:
        """スキーマのシリアライズおよびデシリアライズが動作すること"""
        claim = ds.Claim(
            speaker="JP",
            claim="AIは思考を補助するツールである",
            reason="適切にプロンプトを考える過程で批判的思考が養われるため",
            assumptions=["学習者が思考を放棄しないという前提"],
        )
        record = ds.DialogueRecord(
            claims=[claim],
            conclusions=["適切なガイドラインがあればAI活用は有益"],
            objections=["丸写しによる思考停止の懸念"],
            agreements=["目的とルールの明確化が必要という点"],
            unresolved_points=["評価基準の公平性をどう担保するか"],
        )

        dumped = record.model_dump()
        self.assertEqual(len(dumped["claims"]), 1)
        self.assertEqual(dumped["claims"][0]["speaker"], "JP")
        self.assertEqual(dumped["conclusions"][0], "適切なガイドラインがあればAI活用は有益")

        # JSONシリアライズ/デシリアライズの確認
        json_str = json.dumps(dumped, ensure_ascii=False)
        reconstructed = ds.DialogueRecord.model_validate_json(json_str)
        self.assertEqual(len(reconstructed.claims), 1)
        # オブジェクト属性アクセス
        self.assertEqual(reconstructed.claims[0].claim, "AIは思考を補助するツールである")
        self.assertEqual(reconstructed.claims[0].speaker, "JP")

    def test_is_retryable_error(self) -> None:
        """リトライ可能エラーと即時失敗エラーが正しく分類されること"""
        # リトライ可能
        self.assertTrue(ds.is_retryable_error(Exception("503 Service Unavailable")))
        self.assertTrue(ds.is_retryable_error(Exception("429 Resource Exhausted")))
        self.assertTrue(ds.is_retryable_error(Exception("500 Internal Server Error")))
        self.assertTrue(ds.is_retryable_error(Exception("Deadline Exceeded (408)")))
        self.assertTrue(ds.is_retryable_error(Exception("Connection reset by peer")))

        # リトライ不可（即時終了・フォールバックへ）
        self.assertFalse(ds.is_retryable_error(Exception("404 Model Not Found")))
        self.assertFalse(ds.is_retryable_error(Exception("401 Unauthenticated: Invalid API key")))
        self.assertFalse(ds.is_retryable_error(Exception("403 Permission Denied")))
        self.assertFalse(ds.is_retryable_error(Exception("400 Invalid Argument / Bad Request")))

    def test_save_result(self) -> None:
        """save_result で結果が正しいJSON形式でファイルに保存されること"""
        dummy_data: dict[str, Any] = {
            "experiment": {"topic": "テスト議題", "rounds": 1},
            "dialogue": [{"speaker": "JP", "text": "テスト"}],
            "jp_records": [],
            "us_records": [],
        }

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            ds.save_result(dummy_data, filename=temp_path)
            self.assertTrue(os.path.exists(temp_path))

            with open(temp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)

            self.assertEqual(loaded["experiment"]["topic"], "テスト議題")
            self.assertEqual(len(loaded["dialogue"]), 1)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_session_records_unrecorded_final_rounds(self) -> None:
        """
        最終ターンが RECORD_EVERY の倍数でない場合（例: rounds=4, RECORD_EVERY=3）、
        未記録の最後の対話（round 4）も最後にRecorderによって記録されることを検証。
        """
        # モック関数の定義（API通信なしで高速動作）
        def fake_ask_llm(
            system_instruction: str,
            user_prompt: str,
            max_output_tokens: int = 500,
            api_client: Any = None,
        ) -> str:
            return "テスト用発言テキスト"

        def fake_ask_recorder(
            system_instruction: str,
            user_prompt: str,
            api_client: Any = None,
        ) -> ds.DialogueRecord:
            return ds.DialogueRecord(
                claims=[
                    ds.Claim(speaker="JP", claim="テスト主張", reason="テスト理由", assumptions=[])
                ],
                conclusions=["テスト結論"],
                objections=[],
                agreements=[],
                unresolved_points=[],
            )

        # rounds=4, RECORD_EVERY=3 の場合、round 3 と round 4（最終回収）の計2回記録される
        result = ds.run_dialogue_session(
            topic="テスト議題",
            rounds=4,
            ask_llm_fn=fake_ask_llm,
            ask_recorder_fn=fake_ask_recorder,
        )

        # 対話ターン数: 4ラウンド × 2エージェント = 8発言
        self.assertEqual(len(result["dialogue"]), 8)

        # 記録回数: round 3（定期記録） + round 4（未記録の最終回収） = 2回
        self.assertEqual(len(result["jp_records"]), 2)
        self.assertEqual(len(result["us_records"]), 2)
        self.assertEqual(result["jp_records"][0]["round"], 3)
        self.assertEqual(result["jp_records"][1]["round"], 4)

        # エージェントの記憶にも両方の記録が反映されていること
        self.assertGreater(len(result["jp_memory"]), 0)
        self.assertGreater(len(result["us_memory"]), 0)

    def test_persona_attributes_and_serialization(self) -> None:
        """Personaの生成、属性アクセス、辞書シリアライズ/デシリアライズの検証"""
        persona = ds.Persona(
            name="功利主義者",
            role_description="結果の効用最大化を重視する立場",
            language="日本語",
            cultural_knowledge="ベンサム、ミルの思想体系",
            logical_style="コストベネフィット分析と期待値計算",
            system_instruction="功利主義の哲学的立場で対話してください。",
        )
        self.assertEqual(persona.name, "功利主義者")
        self.assertEqual(persona.language, "日本語")

        # to_dict と from_dict の可逆性
        p_dict = persona.to_dict()
        self.assertEqual(p_dict["name"], "功利主義者")
        self.assertEqual(p_dict["logical_style"], "コストベネフィット分析と期待値計算")

        restored = ds.Persona.from_dict(p_dict)
        self.assertEqual(restored.name, persona.name)
        self.assertEqual(restored.role_description, persona.role_description)
        self.assertEqual(restored.logical_style, persona.logical_style)
        self.assertEqual(restored.system_instruction, persona.system_instruction)

    def test_agent_from_persona(self) -> None:
        """PersonaからAgentを生成し、属性と初期記憶が正しく設定されること"""
        persona = ds.Persona(
            name="義務論者",
            role_description="普遍的道徳法則の遵守",
            language="日本語",
            cultural_knowledge="カントの定言命法",
            logical_style="定言命法と人間の尊厳から演繹",
        )
        agent = ds.Agent.from_persona(persona)
        self.assertEqual(agent.name, "義務論者")
        self.assertEqual(agent.language, "日本語")
        self.assertEqual(agent.cultural_knowledge, "カントの定言命法")
        self.assertIsNotNone(agent.persona)
        self.assertEqual(agent.persona.logical_style, "定言命法と人間の尊厳から演繹")
        self.assertEqual(len(agent.memory), 0)

    def test_presets_integrity(self) -> None:
        """全プリセットの整合性（必須属性、キーの一致、両エージェントの存在）を検証"""
        self.assertGreater(len(ds.PRESETS), 0)
        expected_keys = [
            "utilitarian_vs_deontology",
            "positivism_vs_phenomenology",
            "digital_democracy_vs_deliberative",
            "classic_jp_us",
        ]
        for key in expected_keys:
            self.assertIn(key, ds.PRESETS)
            preset = ds.PRESETS[key]
            self.assertEqual(preset.key, key)
            self.assertTrue(bool(preset.title))
            self.assertTrue(bool(preset.description))
            self.assertTrue(bool(preset.default_topic))
            self.assertIsNotNone(preset.agent_a)
            self.assertIsNotNone(preset.agent_b)
            self.assertTrue(bool(preset.agent_a.name))
            self.assertTrue(bool(preset.agent_b.name))

    def test_create_agents_from_preset(self) -> None:
        """プリセット指定によるエージェント生成とトピック取得の検証"""
        agent_a, agent_b, topic = ds.create_agents_from_preset("utilitarian_vs_deontology")
        self.assertEqual(agent_a.name, "功利主義者 (Utilitarian)")
        self.assertEqual(agent_b.name, "義務論者 (Deontologist)")
        self.assertIn("トリアージ", topic)

        # 存在しないキーを指定した場合は KeyError が発生すること
        with self.assertRaises(KeyError):
            ds.create_agents_from_preset("non_existent_preset")

    def test_build_dialogue_prompt_with_persona(self) -> None:
        """Personaの論理スタイル・役割がプロンプトに反映されること"""
        persona = ds.Persona(
            name="現象学者",
            role_description="一人称的体験と身体性を重視する立場",
            language="日本語",
            cultural_knowledge="メルロ＝ポンティ、和辻哲郎の風土論",
            logical_style="身体的コミットメントと意味の文脈依存性を問う",
        )
        agent = ds.Agent.from_persona(persona)
        prompt = ds.build_dialogue_prompt(
            agent=agent,
            dialogue_history=[],
            own_memory=[],
            opposing_memory=[],
            topic="AIと心の実在について",
        )
        self.assertIn("現象学者", prompt)
        self.assertIn("一人称的体験と身体性を重視する立場", prompt)
        self.assertIn("身体的コミットメントと意味の文脈依存性を問う", prompt)
        self.assertIn("メルロ＝ポンティ、和辻哲郎の風土論", prompt)

    def test_session_with_custom_agents(self) -> None:
        """カスタムエージェントペアを指定した対話セッションの実行とメタデータ検証"""
        agent_a, agent_b, topic = ds.create_agents_from_preset("utilitarian_vs_deontology")

        def fake_ask_llm(
            system_instruction: str,
            user_prompt: str,
            max_output_tokens: int = 500,
            api_client: Any = None,
        ) -> str:
            return "カスタム対話発言"

        def fake_ask_recorder(
            system_instruction: str,
            user_prompt: str,
            api_client: Any = None,
        ) -> ds.DialogueRecord:
            return ds.DialogueRecord(
                claims=[ds.Claim(speaker="功利主義者", claim="効用最大化", reason="被害最小", assumptions=[])],
                conclusions=[],
                objections=[],
                agreements=[],
                unresolved_points=[],
            )

        result = ds.run_dialogue_session(
            topic=topic,
            rounds=2,
            agents=(agent_a, agent_b),
            ask_llm_fn=fake_ask_llm,
            ask_recorder_fn=fake_ask_recorder,
        )

        # 発言者がプリセット名になっていること
        speakers = [item["speaker"] for item in result["dialogue"]]
        self.assertIn("功利主義者 (Utilitarian)", speakers)
        self.assertIn("義務論者 (Deontologist)", speakers)

        # 実験メタデータに Persona 情報が含まれていること
        self.assertIn("agent_a", result["experiment"])
        self.assertEqual(result["experiment"]["agent_a"]["name"], "功利主義者 (Utilitarian)")
        self.assertIn("agent_b", result["experiment"])
        self.assertEqual(result["experiment"]["agent_b"]["name"], "義務論者 (Deontologist)")


if __name__ == "__main__":
    unittest.main()
