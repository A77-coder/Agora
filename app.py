"""
議論形成の場 Agora: 人文系・言語文化箱庭シミュレーション
Web GUI アプリケーション (Streamlit)

機能:
1. リアルタイム対話レンダリング（AI同士の議論を即時ストリーミング表示）
2. 発表本番用「オフライン・デモ再生モード」（API不要・通信遮断セーフティネット）
3. 議論構造の視覚化（Mermaidによる論点ツリー ＆ 合意・対立点カード）
4. JSON/HTMLレポートのワンクリックエクスポート

起動方法:
    streamlit run app.py
または
    run_web_ui.bat (Windows) / run_web_ui.command (Mac)
    ルート直下の「Agora(Web版)を起動.command / .bat」でも起動可能
"""

import html
import json
import os
import time
from datetime import datetime
from typing import Any

import streamlit as st

# 旧API（st.components.v1.html）は廃止予定のため、存在する場合のみ互換用に読み込む
try:
    import streamlit.components.v1 as components
except Exception:  # 将来のバージョンで削除された場合
    components = None

# コアモジュールの読み込み
import dialogue_simulation as ds
import visualization as vz

# ============================================================
# 1. ページ基本設定
# ============================================================
st.set_page_config(
    page_title="議論形成の場 Agora",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# セッション状態の初期化
if "dialogue_history" not in st.session_state:
    st.session_state.dialogue_history = []
if "a_records" not in st.session_state:
    st.session_state.a_records = []
if "b_records" not in st.session_state:
    st.session_state.b_records = []
if "experiment_meta" not in st.session_state:
    st.session_state.experiment_meta = {}
if "demo_step" not in st.session_state:
    st.session_state.demo_step = 0
if "live_unlocked" not in st.session_state:
    st.session_state.live_unlocked = False


# ============================================================
# 1.5 クラウド公開用の秘密情報読み込み（Streamlit Community Cloud 対応）
# ============================================================
def load_streamlit_secrets() -> None:
    """
    st.secrets に設定された値を環境変数へ反映する。
    ローカル実行で secrets.toml が無い場合は何もしない（.env が使われる）。
    """
    try:
        for key in ("GEMINI_API_KEY", "GEMINI_MODEL_CANDIDATES", "APP_PASSWORD"):
            if key in st.secrets and not os.environ.get(key):
                os.environ[key] = str(st.secrets[key])
    except Exception:
        # secrets.toml が存在しない環境では例外になるため無視する
        pass


load_streamlit_secrets()

# 公開URLでAPIキーを第三者に浪費されないためのパスワード（未設定なら保護なし＝ローカル用）
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()


# ============================================================
# 2. サイドバー設定
# ============================================================
with st.sidebar:
    st.title("🏛️ Agora 設定")
    st.caption("人文系・言語文化箱庭シミュレーション")

    st.markdown("---")
    st.subheader("実行モード")
    mode = st.radio(
        "モード選択",
        ["🌐 リアルタイム対話 (Gemini API)", "🎬 発表デモ再生モード (API不要)"],
        # クラウド公開環境では訪問者が迷わずすぐ見られるようデモ再生を推奨
        index=0,
    )

    st.markdown("---")
    if mode == "🌐 リアルタイム対話 (Gemini API)":
        st.subheader("1. APIキー設定 (BYOK)")
        st.caption("各自のGoogle Gemini APIキー（無料）を使用してリアルタイム対話を行います。キーはサーバーに保存されません。")

        # ローカルの .env にキーがある場合はそれを検知
        existing_env_key = os.environ.get("GEMINI_API_KEY", "").strip()
        
        user_api_key = st.text_input(
            "Gemini API キー",
            type="password",
            placeholder="AIzaSy... (お持ちのキーを貼り付け)",
            help="Google AI Studio (https://aistudio.google.com/app/apikey) で無料で取得できます。",
        )
        if user_api_key.strip():
            active_api_key = user_api_key.strip()
            st.success("✅ APIキーが入力されました。")
        elif existing_env_key:
            active_api_key = existing_env_key
            st.info("💻 ローカル環境（.env）のAPIキーを使用します。")
        else:
            active_api_key = ""
            st.warning("🔑 リアルタイム対話にはGemini APIキーが必要です。\n\nキーをお持ちでない場合は、上のモード選択で **「🎬 発表デモ再生モード」** をお選びください（通信ゼロ・キー不要で全機能体験可能）。")
            st.markdown("[👉 Google AI Studio で無料APIキーを取得する](https://aistudio.google.com/app/apikey)")

        st.markdown("---")
        st.subheader("2. プリセット選択")
        preset_options = list(ds.PRESETS.keys()) + ["custom"]
        preset_labels = {
            "utilitarian_vs_deontology": "功利主義 vs 義務論（カント倫理学）",
            "positivism_vs_phenomenology": "実証科学 vs 現象学（身体性・意味論）",
            "digital_democracy_vs_deliberative": "デジタル直接民主主義 vs 熟議民主主義",
            "classic_jp_us": "日米文化比較（オリジナル）",
            "custom": "🛠️ カスタム（自由設定）",
        }

        selected_preset_key = st.selectbox(
            "対話プリセット",
            options=preset_options,
            format_func=lambda k: preset_labels.get(k, k),
            index=0,
        )

        if selected_preset_key != "custom":
            preset = ds.PRESETS[selected_preset_key]
            st.info(f"**概要**: {preset.description}")
            agent_a = ds.Agent.from_persona(preset.agent_a)
            agent_b = ds.Agent.from_persona(preset.agent_b)
            default_topic = preset.default_topic
        else:
            st.markdown("#### カスタムエージェント設定")
            name_a = st.text_input("エージェントA 名前", value="肯定派")
            role_a = st.text_area("エージェントA 立場・思考スタイル", value="提案を積極的に肯定・推進する立場")
            name_b = st.text_input("エージェントB 名前", value="慎重派")
            role_b = st.text_area("エージェントB 立場・思考スタイル", value="懸念や批判的視点を提示する立場")
            agent_a = ds.Agent.from_persona(ds.Persona(name=name_a, role_description=role_a, language="日本語"))
            agent_b = ds.Agent.from_persona(ds.Persona(name=name_b, role_description=role_b, language="日本語"))
            default_topic = "高校社会科の授業において、AIによるレポート作成は認められるべきかどうか。"

        st.markdown("---")
        st.subheader("3. 議題とラウンド")
        topic = st.text_area("議論のテーマ（議題）", value=default_topic, height=90)
        rounds = st.slider("対話ラウンド数", min_value=1, max_value=8, value=3)

        st.markdown("---")
        if not active_api_key:
            st.button("🚀 議論を開始する", disabled=True, help="APIキーを入力すると有効化されます")
            start_button = False
        else:
            start_button = st.button("🚀 議論を開始する", use_container_width=True, type="primary")

    else:
        # デモ再生モード：同梱の sample_debate_*.json から選択する
        st.info("💡 **発表・プレゼン用セーフティネット**\n通信エラーやAPI制限を気にせず、事前にGemini APIで生成・保存した議論を確実に実演できます。")
        app_dir = os.path.dirname(os.path.abspath(__file__))
        demo_files = sorted(
            f for f in os.listdir(app_dir)
            if f.startswith("sample_debate_") and f.endswith(".json")
        )
        if demo_files:
            demo_file = st.selectbox("デモデータ", demo_files)
        else:
            demo_file = None
            st.error("デモデータ（sample_debate_*.json）が見つかりません。")

        demo_action = st.radio("再生方法", ["1発言ずつ送る（ステップ再生）", "一括で全展開"], index=0)
        start_demo = st.button("🎬 デモをロード／リセット", use_container_width=True, type="primary")


# ============================================================
# 3. メイン画面ヘッダー ＆ エージェント紹介
# ============================================================
st.title("🏛️ 議論形成の場 Agora")
st.markdown(
    "**対立する哲学・思想・文化的立場を持つ2体のAIが対話し、"
    "第三者（Recorder）がその論理構造・合意点・対立点をリアルタイムに抽出・構造化する箱庭シミュレーション基盤です。**"
)

# デモモード時：デモデータを読み込み、記録されたプリセットからエージェント情報を復元
demo_data: dict[str, Any] | None = None
if mode.startswith("🎬"):
    if demo_file:
        demo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), demo_file)
        with open(demo_path, "r", encoding="utf-8") as f:
            demo_data = json.load(f)
    meta = demo_data.get("experiment", {}) if demo_data else {}
    preset_key = meta.get("preset_key", "utilitarian_vs_deontology")
    preset = ds.PRESETS.get(preset_key, ds.PRESETS["utilitarian_vs_deontology"])
    agent_a = ds.Agent.from_persona(preset.agent_a)
    agent_b = ds.Agent.from_persona(preset.agent_b)
    topic = meta.get("topic", preset.default_topic)

col1, col2 = st.columns(2)
with col1:
    st.markdown(f"### 🔵 {agent_a.name}")
    st.caption(f"**使用言語**: {agent_a.language}")
    role_text = agent_a.persona.role_description if agent_a.persona else agent_a.cultural_knowledge
    st.write(role_text)
    if agent_a.persona and agent_a.persona.logical_style:
        st.markdown(f"**思考スタイル**: {agent_a.persona.logical_style}")

with col2:
    st.markdown(f"### 🔴 {agent_b.name}")
    st.caption(f"**使用言語**: {agent_b.language}")
    role_text = agent_b.persona.role_description if agent_b.persona else agent_b.cultural_knowledge
    st.write(role_text)
    if agent_b.persona and agent_b.persona.logical_style:
        st.markdown(f"**思考スタイル**: {agent_b.persona.logical_style}")

st.markdown("---")


# ============================================================
# 4. 実行ロジック
# ============================================================

# --- (A) デモ再生モードの実行 ---
if mode.startswith("🎬"):
    if start_demo and demo_data:
        st.session_state.dialogue_history = []
        st.session_state.demo_step = 0
        st.session_state.a_records = demo_data.get("a_records", [])
        st.session_state.b_records = demo_data.get("b_records", [])
        st.session_state.experiment_meta = demo_data.get("experiment", {})

        if demo_action == "一括で全展開":
            st.session_state.dialogue_history = demo_data.get("dialogue", [])
            st.session_state.demo_step = len(st.session_state.dialogue_history)
            st.success("デモデータを一括展開しました。")
        else:
            st.info("デモを初期化しました。「次の発言へ進む」ボタンで対話を進めてください。")

    if demo_action.startswith("1発言") and demo_data:
        all_dialogue = demo_data.get("dialogue", [])
        current_step = st.session_state.demo_step
        col_next, col_status = st.columns([1, 3])
        with col_next:
            if current_step < len(all_dialogue):
                if st.button("▶ 次の発言へ進む", type="primary", use_container_width=True):
                    st.session_state.dialogue_history.append(all_dialogue[current_step])
                    st.session_state.demo_step += 1
                    st.rerun()
            else:
                st.button("✅ 全発言完了", disabled=True, use_container_width=True)
        with col_status:
            st.caption(f"進行状況: {current_step} / {len(all_dialogue)} 発言")


# --- (B) リアルタイムAPI対話の実行 ---
if mode.startswith("🌐") and "start_button" in locals() and start_button:
    if not active_api_key:
        st.error("⚠️ Gemini APIキーが設定されていません。サイドバーにAPIキーを入力してください。")
        st.stop()
    try:
        api_client = ds.create_client(api_key=active_api_key)
    except Exception as e:
        st.error(f"⚠️ Gemini API クライアントの初期化に失敗しました: {e}")
        st.info("入力されたAPIキーが正しいか、または利用制限にかかっていないか確認してください。")
        st.stop()

    st.session_state.dialogue_history = []
    st.session_state.a_records = []
    st.session_state.b_records = []
    agent_a.reset_memory()
    agent_b.reset_memory()

    progress_bar = st.progress(0, text="対話セッションを初期化中...")
    status_text = st.empty()

    live_chat_container = st.container()

    last_record_index = 0
    a_instruction = (
        agent_a.persona.system_instruction
        if agent_a.persona and agent_a.persona.system_instruction
        else f"あなたは{agent_a.name}エージェントです。{agent_a.language}でのみ発言してください。"
    )
    b_instruction = (
        agent_b.persona.system_instruction
        if agent_b.persona and agent_b.persona.system_instruction
        else f"あなたは{agent_b.name}エージェントです。{agent_b.language}でのみ発言してください。"
    )

    for r in range(1, rounds + 1):
        status_text.markdown(f"**🔄 ラウンド {r} / {rounds} 進行中...**")
        progress_bar.progress((r - 1) / rounds)

        # Agent A 発言
        a_prefix = "JP" if agent_a.name == "JP" else agent_a.name
        b_prefix = "US" if agent_b.name == "US" else agent_b.name
        a_own = ds.filter_memory_by_source(agent_a.memory, a_prefix)
        a_opp = ds.filter_memory_by_source(agent_a.memory, b_prefix)

        with live_chat_container:
            with st.chat_message(name=agent_a.name, avatar="🔵"):
                with st.spinner(f"🔵 {agent_a.name} が思考中..."):
                    prompt_a = ds.build_dialogue_prompt(
                        agent=agent_a,
                        dialogue_history=st.session_state.dialogue_history,
                        own_memory=a_own,
                        opposing_memory=a_opp,
                        topic=topic,
                    )
                    text_a = ds.ask_llm(
                        system_instruction=a_instruction,
                        user_prompt=prompt_a,
                        api_client=api_client,
                    )
                st.markdown(f"**{agent_a.name}** （第 {r} ラウンド）")
                st.write(text_a)

        msg_a = {
            "round": r,
            "speaker": agent_a.name,
            "language": agent_a.language,
            "text": text_a,
            "timestamp": datetime.now().isoformat(),
        }
        st.session_state.dialogue_history.append(msg_a)

        # Agent B 発言
        b_own = ds.filter_memory_by_source(agent_b.memory, b_prefix)
        b_opp = ds.filter_memory_by_source(agent_b.memory, a_prefix)

        with live_chat_container:
            with st.chat_message(name=agent_b.name, avatar="🔴"):
                with st.spinner(f"🔴 {agent_b.name} が思考中..."):
                    prompt_b = ds.build_dialogue_prompt(
                        agent=agent_b,
                        dialogue_history=st.session_state.dialogue_history,
                        own_memory=b_own,
                        opposing_memory=b_opp,
                        topic=topic,
                    )
                    text_b = ds.ask_llm(
                        system_instruction=b_instruction,
                        user_prompt=prompt_b,
                        api_client=api_client,
                    )
                st.markdown(f"**{agent_b.name}** （第 {r} ラウンド）")
                st.write(text_b)

        msg_b = {
            "round": r,
            "speaker": agent_b.name,
            "language": agent_b.language,
            "text": text_b,
            "timestamp": datetime.now().isoformat(),
        }
        st.session_state.dialogue_history.append(msg_b)

        # 定期記録
        if r % ds.RECORD_EVERY == 0:
            status_text.markdown(f"**📝 Recorderによる論理構造分析中 (ラウンド {r})...**")
            segment = st.session_state.dialogue_history[last_record_index:]
            ds._record_dialogue_segment(
                segment_dialogue=segment,
                round_label=r,
                agent_a=agent_a,
                agent_b=agent_b,
                a_records=st.session_state.a_records,
                b_records=st.session_state.b_records,
                api_client=api_client,
            )
            last_record_index = len(st.session_state.dialogue_history)

    # 最終未記録ターンの回収
    if last_record_index < len(st.session_state.dialogue_history):
        status_text.markdown("**📝 最終ターンの論理構造を整理・記録中...**")
        segment = st.session_state.dialogue_history[last_record_index:]
        ds._record_dialogue_segment(
            segment_dialogue=segment,
            round_label=rounds,
            agent_a=agent_a,
            agent_b=agent_b,
            a_records=st.session_state.a_records,
            b_records=st.session_state.b_records,
            api_client=api_client,
        )

    progress_bar.progress(1.0, text="✨ 議論セッション完了！")
    status_text.success(f"全 {rounds} ラウンドの対話と論理構造抽出が完了しました。")

    st.session_state.experiment_meta = {
        "topic": topic,
        "rounds": rounds,
        "agent_a": agent_a.persona.to_dict() if agent_a.persona else {"name": agent_a.name},
        "agent_b": agent_b.persona.to_dict() if agent_b.persona else {"name": agent_b.name},
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================
# 5. 結果表示エリア（3大タブ）
# ============================================================
if st.session_state.dialogue_history:
    tab1, tab2, tab3 = st.tabs(["💬 対話チャット", "📊 論理構造 ＆ ツリー可視化", "📁 レポート出力 (JSON/HTML)"])

    # --- TAB 1: 対話ログ ---
    with tab1:
        st.subheader("対話タイムライン")
        for msg in st.session_state.dialogue_history:
            speaker = msg["speaker"]
            is_a = (speaker == agent_a.name)
            avatar = "🔵" if is_a else "🔴"
            with st.chat_message(name=speaker, avatar=avatar):
                st.markdown(f"**{speaker}** （第 {msg['round']} ラウンド）")
                st.write(msg["text"])

    # --- TAB 2: 論理構造 ＆ ツリー可視化 ---
    with tab2:
        st.subheader("論理構造分析ダッシュボード")

        latest_record = None
        if st.session_state.b_records:
            latest_record = st.session_state.b_records[-1]["record"]
        elif st.session_state.a_records:
            latest_record = st.session_state.a_records[-1]["record"]

        if latest_record:
            # 1. 合意点・未解決点カード
            col_agree, col_unres = st.columns(2)
            with col_agree:
                st.success("#### 🤝 到達した合意点（Agreements）")
                agreements = latest_record.get("agreements", [])
                if agreements:
                    for item in agreements:
                        st.markdown(f"- **{item}**")
                else:
                    st.write("(明示的な合意点はまだありません)")

            with col_unres:
                st.warning("#### ⚡ 未解決の対立・論点（Unresolved Points）")
                unresolved = latest_record.get("unresolved_points", [])
                if unresolved:
                    for item in unresolved:
                        st.markdown(f"- **{item}**")
                else:
                    st.write("(未解決点はありません)")

            st.markdown("---")

            # 2. Mermaid による論点展開ツリー
            st.subheader("🌲 論点展開ツリー（Mermaid ダイアグラム）")
            st.caption("議論の議題から各主体の主張、対立と合意、導かれた結論への論理構造のつながりを図示しています。")
            mermaid_code = vz.generate_mermaid_argument_graph(latest_record, topic=topic)

            with st.expander("Mermaid 構文ソースコードを確認する"):
                st.code(mermaid_code, language="mermaid")

            # Mermaid.js をHTML埋め込みでレンダリング
            mermaid_html = vz.render_mermaid_html(mermaid_code, height=520)
            # 新API st.iframe を優先し、無い古いバージョンでは components.html にフォールバック
            if hasattr(st, "iframe"):
                st.iframe(mermaid_html, height=540)
            elif components is not None:
                components.html(mermaid_html, height=540, scrolling=True)

            st.markdown("---")

            # 3. 主張と根拠（アコーディオン）
            st.subheader("🔍 抽出された主要な主張と前提（Claims & Reasons）")
            claims = latest_record.get("claims", [])
            if claims:
                for idx, c in enumerate(claims, start=1):
                    with st.expander(f"主張 {idx}: 【{c.get('speaker', '')}】 {c.get('claim', '')}"):
                        st.markdown(f"**示された理由**: {c.get('reason', '（明示なし）')}")
                        assumptions = c.get("assumptions", [])
                        if assumptions:
                            st.markdown(f"**暗黙の前提**: {', '.join(assumptions)}")
            else:
                st.write("(抽出された主張はありません)")
        else:
            st.info("対話の記録データがまだありません。")

    # --- TAB 3: レポート出力 ---
    with tab3:
        st.subheader("保存とエクスポート")
        export_data = {
            "experiment": st.session_state.experiment_meta,
            "dialogue": st.session_state.dialogue_history,
            "a_records": st.session_state.a_records,
            "b_records": st.session_state.b_records,
        }
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.download_button(
                label="📥 議論ログをJSONでダウンロード",
                data=json_str,
                file_name=f"agora_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                type="primary",
                use_container_width=True,
            )
        with col_d2:
            # HTML簡易レポートの生成（XSS・構文破壊防止のためhtml.escapeを適用）
            escaped_topic = html.escape(topic)
            escaped_dialogue = "".join(
                f"<div class='bubble'><strong>{html.escape(m['speaker'])} (Round {m['round']}):</strong><br>{html.escape(m['text'])}</div>"
                for m in st.session_state.dialogue_history
            )
            escaped_agrees = "".join(
                f"<p>・{html.escape(str(a))}</p>"
                for a in (latest_record.get("agreements", []) if latest_record else [])
            )
            escaped_unres = "".join(
                f"<p>・{html.escape(str(u))}</p>"
                for u in (latest_record.get("unresolved_points", []) if latest_record else [])
            )
            html_report = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Agora 議論レポート</title>
<style>body{{font-family:sans-serif;max-width:800px;margin:20px auto;line-height:1.6;padding:0 20px;}}
h1{{border-bottom:2px solid #333;padding-bottom:10px;}}
.bubble{{padding:12px 16px;border-radius:8px;margin:10px 0;background:#f1f3f4;}}
.agree{{background:#e8f5e9;padding:10px;border-left:4px solid #4caf50;margin:10px 0;}}
.unres{{background:#fff3e0;padding:10px;border-left:4px solid #ff9800;margin:10px 0;}}
</style></head><body>
<h1>🏛️ 議論形成の場 Agora: 議論レポート</h1>
<p><strong>議題:</strong> {escaped_topic}</p>
<hr><h2>💬 対話ログ</h2>
{escaped_dialogue}
<hr><h2>📊 到達した合意点</h2>
<div class='agree'>{escaped_agrees}</div>
<h2>⚡ 未解決の対立点</h2>
<div class='unres'>{escaped_unres}</div>
</body></html>"""
            st.download_button(
                label="📄 HTMLレポートをダウンロード",
                data=html_report,
                file_name=f"agora_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                use_container_width=True,
            )

        st.markdown("#### JSONデータプレビュー")
        st.json(export_data)
