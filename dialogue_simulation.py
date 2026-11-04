"""
人文系・言語文化箱庭シミュレーション Prototype v2
統合版（ローカルPC実行 / Gemini API利用）

必要環境:
    python -m pip install -U google-genai pydantic

実行方法:
    python dialogue_simulation.py

注意:
- Pythonプログラム自体はローカルで動作しますが、対話生成および記録分析にはGemini APIを使用します。
- Gemini APIキーが必要です。環境変数 GEMINI_API_KEY を設定するか、実行時に入力してください。
- MODEL_CANDIDATES のモデル名は、利用可能なGemini APIモデルに合わせて調整してください。
  環境変数 GEMINI_MODEL_CANDIDATES（カンマ区切り）で実行時に上書き指定することも可能です。
"""

import getpass
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

# SDKおよびPydanticの安全なインポート
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore

try:
    from pydantic import BaseModel, Field
except ImportError:
    # 外部依存ライブラリが未インストールの環境でも構文エラーにならず、
    # API非依存テストやモック実行ができるよう軽量なフォールバッククラスを提供
    class BaseModel:  # type: ignore
        def __init__(self, **kwargs: Any) -> None:
            annotations = getattr(self.__class__, "__annotations__", {})
            for k, v in kwargs.items():
                target_type = annotations.get(k)
                if isinstance(v, list) and hasattr(target_type, "__args__"):
                    elem_type = target_type.__args__[0]
                    if hasattr(elem_type, "model_validate"):
                        v = [
                            elem_type.model_validate(item) if isinstance(item, dict) else item
                            for item in v
                        ]
                elif isinstance(v, dict) and hasattr(target_type, "model_validate"):
                    v = target_type.model_validate(v)
                setattr(self, k, v)

        def model_dump(self) -> dict[str, Any]:
            res: dict[str, Any] = {}
            for k, v in self.__dict__.items():
                if isinstance(v, list):
                    res[k] = [
                        item.model_dump() if hasattr(item, "model_dump") else item
                        for item in v
                    ]
                elif hasattr(v, "model_dump"):
                    res[k] = v.model_dump()
                else:
                    res[k] = v
            return res

        @classmethod
        def model_validate(cls, obj: Any) -> Any:
            if isinstance(obj, cls):
                return obj
            if isinstance(obj, dict):
                return cls(**obj)
            raise TypeError(f"Cannot validate {type(obj)} as {cls.__name__}")

        @classmethod
        def model_validate_json(cls, json_str: str) -> Any:
            data = json.loads(json_str)
            return cls.model_validate(data)

    def Field(default: Any = None, default_factory: Any = None, description: str = "", **kwargs: Any) -> Any:  # type: ignore
        if default_factory is not None:
            return default_factory()
        return default


# ============================================================
# 1. 設定 & 環境変数 (.env) ロード
# ============================================================

def load_dotenv(env_path: str = ".env") -> None:
    """軽量な.env読み込み（外部依存なしでAPIキーや設定を自動ロード）"""
    candidates = [
        env_path,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join("..", env_path),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
    ]
    target_file = None
    for c in candidates:
        if os.path.exists(c) and os.path.isfile(c):
            target_file = c
            break

    if not target_file:
        return

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# .env ファイルが存在すればロード
load_dotenv()

# 利用可能なGeminiモデルの候補リスト（一般公開されている安定モデルを優先）
DEFAULT_MODEL_CANDIDATES = [
    "gemini-2.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]

# 環境変数 GEMINI_MODEL_CANDIDATES が指定されていれば上書き（カンマ区切り）
_env_models = os.environ.get("GEMINI_MODEL_CANDIDATES", "").strip()
MODEL_CANDIDATES: list[str] = (
    [m.strip() for m in _env_models.split(",") if m.strip()]
    if _env_models
    else DEFAULT_MODEL_CANDIDATES
)

MAX_ATTEMPTS_PER_MODEL = 3
REQUEST_INTERVAL_SECONDS = 2.0

RECORD_EVERY = 3
RECENT_TURNS = 4
MEMORY_SIZE = 3
DIALOGUE_MAX_TOKENS = 2048
RECORDER_MAX_TOKENS = 3000
DEFAULT_ROUNDS = 10
OUTPUT_FILENAME = "dialogue_experiment_v2.json"


# ============================================================
# 2. Gemini APIクライアント
# ============================================================

def create_client(api_key: str | None = None) -> Any:
    """
    Gemini APIクライアントを初期化する。
    環境変数 GEMINI_API_KEY または安全なプロンプト入力からAPIキーを取得。
    """
    if genai is None or types is None:
        raise ImportError(
            "google-genai パッケージがインストールされていません。\n"
            "先に 'pip install -r requirements.txt' を実行してください。"
        )

    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if api_key:
            print("[INFO] 環境変数または .env から Gemini API キーを読み込みました。")
    if not api_key:
        api_key = getpass.getpass("Gemini API Key: ").strip()
    if not api_key:
        raise ValueError("Gemini APIキーが入力されていません。")

    # SDK内蔵の自動リトライを抑え、generate_with_fallback で再試行を一元管理する
    http_options = None
    try:
        http_options = types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=1)
        )
    except (AttributeError, TypeError):
        http_options = None

    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if http_options is not None:
        client_kwargs["http_options"] = http_options

    return genai.Client(**client_kwargs)


client: Any = None


# ============================================================
# 3. Agent & Persona
# ============================================================

@dataclass
class Persona:
    """エージェントのキャラクター性・立場・思考様式を定義するクラス"""
    name: str
    role_description: str
    language: str = "日本語"
    cultural_knowledge: str = ""
    logical_style: str = ""
    system_instruction: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換する（シリアライズ用）"""
        return {
            "name": self.name,
            "role_description": self.role_description,
            "language": self.language,
            "cultural_knowledge": self.cultural_knowledge,
            "logical_style": self.logical_style,
            "system_instruction": self.system_instruction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Persona":
        """辞書からPersonaインスタンスを復元する"""
        return cls(
            name=data.get("name", "Unknown"),
            role_description=data.get("role_description", ""),
            language=data.get("language", "日本語"),
            cultural_knowledge=data.get("cultural_knowledge", ""),
            logical_style=data.get("logical_style", ""),
            system_instruction=data.get("system_instruction"),
        )


@dataclass
class Agent:
    """箱庭シミュレーションの参加者エージェント"""
    name: str
    language: str
    cultural_knowledge: str
    persona: Persona | None = None
    memory: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """後方互換性を保ちつつ、Personaが未指定の場合は属性から自動生成する"""
        if self.persona is None:
            self.persona = Persona(
                name=self.name,
                role_description=self.cultural_knowledge,
                language=self.language,
                cultural_knowledge=self.cultural_knowledge,
            )

    @classmethod
    def from_persona(cls, persona: Persona) -> "Agent":
        """PersonaからAgentを生成するファクトリメソッド"""
        return cls(
            name=persona.name,
            language=persona.language,
            cultural_knowledge=persona.cultural_knowledge,
            persona=persona,
        )

    def remember(self, item: dict[str, Any]) -> None:
        """長期記憶を追加し、最新のMEMORY_SIZE件のみを保持する"""
        self.memory.append(item)
        if len(self.memory) > MEMORY_SIZE:
            self.memory[:] = self.memory[-MEMORY_SIZE:]

    def reset_memory(self) -> None:
        """エージェントの長期記憶をリセットする（実験同士の状態混信を防止）"""
        self.memory.clear()


# ============================================================
# 4. Structured Output用Schema
# ============================================================

class Claim(BaseModel):
    speaker: str = Field(description="発言者")
    claim: str = Field(description="発言者が実際に述べた主要な主張。短く要約する。")
    reason: str = Field(description="その主張について実際に示された理由。短く要約する。")
    assumptions: list[str] = Field(
        default_factory=list,
        description="その論証に含まれる暗黙または明示的な前提。最大3個。",
    )


class DialogueRecord(BaseModel):
    claims: list[Claim] = Field(
        default_factory=list, description="主要な主張。最大6個。"
    )
    conclusions: list[str] = Field(
        default_factory=list, description="対話から導かれた結論。最大4個。"
    )
    objections: list[str] = Field(
        default_factory=list, description="相手への主要な反論。最大4個。"
    )
    agreements: list[str] = Field(
        default_factory=list, description="双方が同意した点。最大4個。"
    )
    unresolved_points: list[str] = Field(
        default_factory=list, description="まだ解決していない論点。最大4個。"
    )


# ============================================================
# 5. API呼び出し・エラー判定・フォールバック
# ============================================================

def is_retryable_error(exc: Exception) -> bool:
    """
    一時的な通信エラーやレート制限など、再試行すべき例外かどうかを判定する。
    400 (Bad Request), 401/403 (認証/権限), 404 (Not Found) 等は再試行しない。
    """
    message = str(exc).upper()
    # 即時失敗すべきエラーマーカー（再試行しても無意味なもの）
    non_retryable_markers = (
        "400", "INVALID_ARGUMENT", "BAD_REQUEST",
        "401", "UNAUTHENTICATED",
        "403", "PERMISSION_DENIED",
        "404", "NOT_FOUND",
    )
    if any(m in message for m in non_retryable_markers):
        return False

    # 一時的・再試行可能なマーカー
    retryable_markers = (
        "503", "UNAVAILABLE",
        "429", "RESOURCE_EXHAUSTED",
        "500", "INTERNAL",
        "504", "GATEWAY_TIMEOUT",
        "408", "DEADLINE_EXCEEDED",
        "CONNECTION RESET", "TIMED OUT",
    )
    return any(marker in message for marker in retryable_markers)


def generate_with_fallback(
    system_instruction: str,
    user_prompt: str,
    max_output_tokens: int = DIALOGUE_MAX_TOKENS,
    response_schema: Any = None,
    api_client: Any = None,
    candidate_models: list[str] | None = None,
) -> tuple[Any, str]:
    """
    一時的なAPIエラーを再試行し、必要に応じて代替モデルへ切り替える。
    戻り値: (response, used_model)
    """
    active_client = api_client if api_client is not None else client
    if active_client is None:
        raise RuntimeError(
            "Gemini APIクライアントが初期化されていません。"
            "main() を実行するか、api_client を渡してください。"
        )

    models_to_try = candidate_models or MODEL_CANDIDATES
    last_error: Exception | None = None

    for model in models_to_try:
        print(f"[API] Using model: {model}")

        for attempt in range(MAX_ATTEMPTS_PER_MODEL):
            try:
                config_args: dict[str, Any] = {
                    "system_instruction": system_instruction,
                    "max_output_tokens": max_output_tokens,
                }

                # automatic_function_calling を安全に無効化
                if types is not None and hasattr(types, "AutomaticFunctionCallingConfig"):
                    try:
                        config_args["automatic_function_calling"] = (
                            types.AutomaticFunctionCallingConfig(disable=True)
                        )
                    except (TypeError, ValueError):
                        pass

                if response_schema is not None:
                    config_args["response_mime_type"] = "application/json"
                    config_args["response_schema"] = response_schema

                config = types.GenerateContentConfig(**config_args)
                response = active_client.models.generate_content(
                    model=model,
                    contents=user_prompt,
                    config=config,
                )

                if not getattr(response, "text", None) and getattr(response, "parsed", None) is None:
                    raise RuntimeError("Model returned no text or parsed result.")

                # トークン上限到達の確認
                if hasattr(response, "candidates") and response.candidates:
                    finish_reason = getattr(response.candidates[0], "finish_reason", None)
                    if str(finish_reason).endswith("MAX_TOKENS"):
                        print(f"[API WARNING] {model}: 出力が max_output_tokens 上限に達しました。")

                time.sleep(REQUEST_INTERVAL_SECONDS)
                return response, model

            except Exception as exc:
                last_error = exc
                if not is_retryable_error(exc):
                    # モデル名が存在しないなどの404/引数不正等の場合、現在のモデルの再試行は打ち切る
                    print(f"[API] Non-retryable error for {model}: {exc}")
                    break

                if attempt < MAX_ATTEMPTS_PER_MODEL - 1:
                    wait_seconds = min(
                        5 * (2 ** attempt) + random.uniform(0, 3),
                        60,
                    )
                    print(
                        f"Temporary API error: {str(exc)[:160]}\n"
                        f"Retry {attempt + 1}/{MAX_ATTEMPTS_PER_MODEL - 1} "
                        f"in {wait_seconds:.1f}s..."
                    )
                    time.sleep(wait_seconds)
                else:
                    print(f"[API] {model} unavailable after retries.")

        print("[API] Switching to the next model...")

    raise RuntimeError(
        "All candidate models failed. Check the latest API error."
    ) from last_error


def ask_llm(
    system_instruction: str,
    user_prompt: str,
    max_output_tokens: int = DIALOGUE_MAX_TOKENS,
    api_client: Any = None,
) -> str:
    """対話参加エージェントの発言を生成する"""
    response, _used_model = generate_with_fallback(
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        max_output_tokens=max_output_tokens,
        api_client=api_client,
    )
    if not getattr(response, "text", None):
        raise RuntimeError("Model returned no text.")
    return response.text.strip()


def ask_recorder(
    system_instruction: str,
    user_prompt: str,
    api_client: Any = None,
) -> DialogueRecord:
    """Recorderによる論理構造化出力を取得する"""
    response, used_model = generate_with_fallback(
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        max_output_tokens=RECORDER_MAX_TOKENS,
        response_schema=DialogueRecord,
        api_client=api_client,
    )

    parsed = getattr(response, "parsed", None)
    if parsed is not None:
        if isinstance(parsed, DialogueRecord):
            return parsed
        return DialogueRecord.model_validate(parsed)

    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError(f"Recorder on {used_model} returned no text.")

    return DialogueRecord.model_validate_json(text)


# ============================================================
# 6. 世界設定・プリセット定義
# ============================================================

@dataclass
class PresetDefinition:
    """対話シミュレーションのプリセット定義"""
    key: str
    title: str
    description: str
    default_topic: str
    agent_a: Persona
    agent_b: Persona


PRESETS: dict[str, PresetDefinition] = {
    "utilitarian_vs_deontology": PresetDefinition(
        key="utilitarian_vs_deontology",
        title="功利主義 vs 義務論（カント倫理学）",
        description="結果の幸福最大化・効用計算を重視する立場と、人間の尊厳・普遍的義務を重視する立場の対話",
        default_topic=(
            "AIによるトリアージ（緊急医療資源の配分判断）や完全自動運転の緊急回避アルゴリズムにおいて、"
            "全体の被害を最小化する計算は、個人の不可侵な権利・尊厳に優先されるべきか。"
        ),
        agent_a=Persona(
            name="功利主義者 (Utilitarian)",
            role_description="結果主義・効用主義の立場。全体の幸福・利益の総和を最大化し、苦痛・損害を最小化することを最善の倫理的判断とする。",
            language="日本語",
            cultural_knowledge="ジェレミ・ベンサム、J.S.ミルの思想体系、費用便益分析、公共選択論、ゲーム理論の知見を持つ。",
            logical_style="具体的な帰結・実被害の規模・期待値の計算をもとに論理を展開し、感情論や抽象的タブーを排して現実的な効用最大化を主張する。",
            system_instruction="あなたは功利主義の哲学的立場に立つ対話者です。常に帰結と効用の最大化に基づき、理性的かつ説得力ある論理を展開してください。",
        ),
        agent_b=Persona(
            name="義務論者 (Deontologist)",
            role_description="カント的義務論の立場。人間をいかなる目的のための「単なる手段」としても扱ってはならず、普遍化可能な道徳法則を遵守すべきとする。",
            language="日本語",
            cultural_knowledge="イマヌエル・カントの実践理性批判、定言命法、基本的人権論、立憲主義の思想体系を持つ。",
            logical_style="行為それ自体の内在的正しさ、個人の尊厳の不可侵性、普遍化可能性の検証を用いて反論し、功利主義の孕む『少数の犠牲の正当化』を厳しく批判する。",
            system_instruction="あなたはカント的義務論の哲学的立場に立つ対話者です。人間の尊厳と普遍的道徳法則を固守し、帰結主義の論理的欠陥を突いてください。",
        ),
    ),
    "positivism_vs_phenomenology": PresetDefinition(
        key="positivism_vs_phenomenology",
        title="実証科学（客観主義） vs 現象学（身体性・生の意味論）",
        description="客観的データ・観測可能性・計算可能性を重視する立場と、主観的体験・身体性・実存的意味を重視する立場の対話",
        default_topic=(
            "高度な生成AIが創作した詩や絵画、あるいは対話応答に対して、"
            "人間と同等の『美的価値』『意識』『心』を認めることはできるか。"
        ),
        agent_a=Persona(
            name="実証科学者 (Positivist)",
            role_description="実証主義・物理主義の立場。客観的に観測可能な行動、神経科学的・計算論的データ、再現性のある検証可能性のみを科学的実在の根拠とする。",
            language="日本語",
            cultural_knowledge="認知科学、計算機科学、分析哲学、行動主義、統計的学習理論の知見を持つ。",
            logical_style="反証可能性、実験的検証、出力データの統計的性質から論理を組み立て、神秘化された『内面』や『主観』の独我論的罠を指摘する。",
            system_instruction="あなたは実証主義的な科学者の立場に立つ対話者です。客観的観測データと論理的整合性を基軸に対話してください。",
        ),
        agent_b=Persona(
            name="現象学者 (Phenomenologist)",
            role_description="現象学・解釈学の立場。生きられた身体（Leib）、風土、歴史的・主観的体験（Erlebnis）、世界内存在としての意味の生成を根本とする。",
            language="日本語",
            cultural_knowledge="フッサール、ハイデガー、メルロ＝ポンティ、西田幾多郎、和辻哲郎の思想体系を持つ。",
            logical_style="一人称的な経験の先行性、身体的コミットメントのない記号操作の限界、意味の文脈依存性を指摘し、客観主義が前提とする『客観』自体の成り立ちを問う。",
            system_instruction="あなたは現象学・解釈学の哲学的立場に立つ対話者です。身体性や生の体験、意味の地平から客観主義的還元主義を深く吟味してください。",
        ),
    ),
    "digital_democracy_vs_deliberative": PresetDefinition(
        key="digital_democracy_vs_deliberative",
        title="デジタル直接民主主義 vs 熟議民主主義",
        description="AIとデジタル技術による民意の直接反映と効率化を推進する立場と、市民間の熟議・対話・慎重な合意形成を重視する立場の対話",
        default_topic=(
            "現代の議会制民主主義の停滞や既得権益を打破するため、"
            "法案の起草・意思決定プロセスにAIと直接市民投票（デジタル直接民主主義）を全面的に導入すべきか。"
        ),
        agent_a=Persona(
            name="デジタル民主主義推進派 (Digital Reformer)",
            role_description="デジタル・プラットフォームやAIによる意思決定の透明化、直接参加、民意のリアルタイム集約を推進する立場。",
            language="日本語",
            cultural_knowledge="オードリー・タンのシビックテック、流動性民主主義（Liquid Democracy）、分散型自律組織（DAO）、オープンガバメントの知見を持つ。",
            logical_style="代議制の制度疲労、代理人問題（エージェンシー問題）、既得権益の打破、集合知とAIによる最適配分の有効性を論理的に提示する。",
            system_instruction="あなたはシビックテックとデジタル民主主義を推進する立場です。技術革新による民意の直接反映と透明性の価値を熱意をもって論証してください。",
        ),
        agent_b=Persona(
            name="熟議民主主義派 (Deliberative Democrat)",
            role_description="対話と熟議（Deliberation）、少数者配慮、理性的な議論のプロセス自体に民主主義の正統性を見出す立場。",
            language="日本語",
            cultural_knowledge="ハーバーマスの討議倫理学、公共圏論、政治社会学、ポピュリズム研究の知見を持つ。",
            logical_style="直接投票の衆愚化・分断激化リスク、アルゴリズムのブラックボックス化、選好の単なる集計と熟議による選好変容の違いを指摘し、対話の制度的価値を強調する。",
            system_instruction="あなたは熟議民主主義の立場に立つ対話者です。単なる多数決や技術至上主義を批判し、人間同士の対話・相互理解・少数者保護の重要性を説いてください。",
        ),
    ),
    "classic_jp_us": PresetDefinition(
        key="classic_jp_us",
        title="日米文化比較（オリジナル）",
        description="日本語話者（日本の文脈・調和・教育的配慮）と英語話者（個人の自律・批判的思考・透明性）の対話",
        default_topic="高校社会科の授業において、AIによるレポート作成は認められるべきかどうか。",
        agent_a=Persona(
            name="JP",
            role_description="日本語を使用しながら、アメリカについて学習し、教育的配慮や文化的調和を大切にする話者。",
            language="日本語",
            cultural_knowledge="""
あなたは日本語を母語とする話者です。
あなたはアメリカ合衆国について十分な地理的・歴史的・文化的知識を持っています。
あなた自身を「典型的な日本人」として演じる必要はありません。
「日本語を使用しながら、アメリカについて学習している主体」として振る舞ってください。
""".strip(),
            logical_style="協調的・教育的観点から、文脈や他者への配慮、段階的導入の必要性を丁寧に論証する。",
            system_instruction="あなたは日本語話者エージェントです。日本語でのみ発言してください。提示された役割・知識・記憶を利用し、自然な対談相手として応答してください。",
        ),
        agent_b=Persona(
            name="US",
            role_description="English speaker who has learned extensively about Japan, focusing on autonomy, transparency, and critical inquiry.",
            language="English",
            cultural_knowledge="""
You are a speaker whose first language is American English.
You have substantial geographical, historical, and cultural knowledge about Japan.
You are NOT a stereotypical Japanese or American character.
You are an English-speaking participant who has learned extensively about Japan.
""".strip(),
            logical_style="Articulates points based on individual initiative, accountability, transparent guidelines, and practical utility.",
            system_instruction="You are an English-speaking dialogue participant. Respond only in American English. Use the provided context and memory to respond naturally to the Japanese-speaking participant.",
        ),
    ),
}


def create_agents(
    persona_a: Persona | None = None,
    persona_b: Persona | None = None,
) -> tuple[Agent, Agent]:
    """
    対話に参加する2つのエージェントを初期化する。
    引数が省略された場合は従来の classic_jp_us プリセットのエージェントを生成（後方互換性維持）。
    """
    if persona_a is not None and persona_b is not None:
        agent_a = Agent.from_persona(persona_a)
        agent_b = Agent.from_persona(persona_b)
        return agent_a, agent_b

    # 既定の classic_jp_us
    preset = PRESETS["classic_jp_us"]
    agent_a = Agent.from_persona(preset.agent_a)
    agent_b = Agent.from_persona(preset.agent_b)
    return agent_a, agent_b


def create_agents_from_preset(preset_key: str) -> tuple[Agent, Agent, str]:
    """
    指定されたプリセットキーから2体のエージェントと既定の議題を取得する。
    戻り値: (agent_a, agent_b, default_topic)
    """
    if preset_key not in PRESETS:
        raise KeyError(
            f"プリセット '{preset_key}' は存在しません。"
            f"利用可能なキー: {list(PRESETS.keys())}"
        )
    preset = PRESETS[preset_key]
    agent_a = Agent.from_persona(preset.agent_a)
    agent_b = Agent.from_persona(preset.agent_b)
    return agent_a, agent_b, preset.default_topic


# ============================================================
# 7. Memory・Prompt
# ============================================================

def memory_to_text(memory: list[dict[str, Any]]) -> str:
    """記憶リストをプロンプト埋め込み用の整形JSON文字列に変換する"""
    if not memory:
        return "(まだ長期記憶はありません)"
    return json.dumps(memory[-MEMORY_SIZE:], ensure_ascii=False, indent=2)


def filter_memory_by_source(
    memory: list[dict[str, Any]], source_prefix: str
) -> list[dict[str, Any]]:
    """指定された話者・記録係ソースの記憶のみを抽出する"""
    return [
        item for item in memory
        if str(item.get("source", "")).startswith(source_prefix)
    ]


def build_dialogue_prompt(
    agent: Agent,
    dialogue_history: list[dict[str, Any]],
    own_memory: list[dict[str, Any]],
    opposing_memory: list[dict[str, Any]],
    topic: str,
) -> str:
    """対話エージェント用の発言生成プロンプトを構築する"""
    recent_history = dialogue_history[-RECENT_TURNS:]
    history_text = (
        "\n".join(f"{item['speaker']}: {item['text']}" for item in recent_history)
        if recent_history else "(まだ対話はありません)"
    )

    persona = agent.persona
    role_desc = persona.role_description if persona else agent.cultural_knowledge
    logical_style_desc = (
        f"思考・論理スタイル: {persona.logical_style}\n"
        if persona and persona.logical_style else ""
    )

    return f"""
あなたは対談実験の参加者です。

【あなた自身】
名前: {agent.name}
使用言語: {agent.language}
役割・基本的立場:
{role_desc}
{logical_style_desc}文化的背景・前提知識:
{agent.cultural_knowledge}

【今回の議題】
{topic}

【あなた側の長期記憶】
{memory_to_text(own_memory)}

【相手側の長期記憶】
{memory_to_text(opposing_memory)}

【直近の対談】
{history_text}

【ルール】
1. 必ず {agent.language} で発言する。
2. 一回の発言は1〜3段落程度（200〜450文字程度）にし、文を途中で途切れさせず必ず完結した自然な文章脈で終える。
3. 相手の直前の発言に具体的に反応する。
4. 過去の記録を必要に応じて参照する。
5. 自分の過去の主張と矛盾する場合、その変化を自然に説明する。
6. ステレオタイプ的な決めつけを避け、論理と根拠をもって論じる。
7. 必ずしも相手に同意する必要はない。
8. 相手の論理に問題があると考えた場合は、その理由を述べる。
9. 自分の主張を無理に維持する必要はない。新しい情報や説得的な論証から考えが変化してもよい。
10. メタ的に「私はAIです」などと説明しない。

今のターンの発言だけを出力してください。
""".strip()


def build_recorder_prompt(
    recorder_language: str,
    side_name: str,
    new_dialogue: list[dict[str, Any]],
    previous_record: dict[str, Any] | None = None,
) -> str:
    """論理構造記録係用のプロンプトを構築する"""
    history_text = "\n".join(
        f"{item['speaker']}: {item['text']}" for item in new_dialogue
    )
    previous_text = (
        json.dumps(previous_record, ensure_ascii=False, indent=2)
        if previous_record else "(なし)"
    )

    return f"""
あなたは{side_name}側の論理構造記録係です。
記録言語: {recorder_language}

以下の対話だけを分析してください。

【今回の対話】
{history_text}

【前回の記録】
{previous_text}

ルール:
- 実際に発言された内容だけを記録する。
- 推測で情報を追加しない。
- 真偽判定はしない。
- 各項目は短く要約する。
- claimsは最大6個。
- assumptionsは各主張につき最大3個。
- conclusions / objections / agreements / unresolved_points はそれぞれ最大4個。
- 該当する項目がなければ空の配列にする。
- 必ず指定されたJSON構造だけを返す。
- JSON以外の文章は返さない。
""".strip()


# ============================================================
# 8. Recorder結果をAgentのMemoryへ追加
# ============================================================

def update_agent_memories(
    japan_side: Agent,
    us_side: Agent,
    jp_record: DialogueRecord,
    us_record: DialogueRecord,
    round_no: int,
) -> None:
    """Recorderの分析結果を両エージェントの長期記憶に記録する"""
    jp_item = {
        "round": round_no,
        "source": "JP_recorder",
        "record": jp_record.model_dump(),
    }
    us_item = {
        "round": round_no,
        "source": "US_recorder",
        "record": us_record.model_dump(),
    }

    # 両方の記録を両方のAgentに共有する
    for agent in (japan_side, us_side):
        agent.remember(jp_item)
        agent.remember(us_item)


# ============================================================
# 9. 対話セッション実行ヘルパー
# ============================================================

def _record_dialogue_segment(
    segment_dialogue: list[dict[str, Any]],
    round_label: int,
    agent_a: Agent,
    agent_b: Agent,
    a_records: list[dict[str, Any]],
    b_records: list[dict[str, Any]],
    api_client: Any = None,
    ask_recorder_fn: Callable[..., DialogueRecord] = ask_recorder,
) -> None:
    """指定区間の対話をRecorderで分析し、記録とAgent記憶を更新する"""
    previous_a_record = a_records[-1]["record"] if a_records else None
    previous_b_record = b_records[-1]["record"] if b_records else None

    # Agent A側の論理構造分析
    a_result = ask_recorder_fn(
        system_instruction=(
            f"あなたは{agent_a.name}側の論理構造分析係です。"
            "発言を捏造せず、実際の対話から論理構造だけを抽出してください。"
        ),
        user_prompt=build_recorder_prompt(
            recorder_language=agent_a.language,
            side_name=agent_a.name,
            new_dialogue=segment_dialogue,
            previous_record=previous_a_record,
        ),
        api_client=api_client,
    )
    a_records.append({
        "round": round_label,
        "record": a_result.model_dump(),
    })

    # Agent B側の論理構造分析
    b_system_instr = (
        f"You are a logical dialogue recorder for {agent_b.name}. "
        "Do not invent claims. Extract only the logical structure actually present."
        if agent_b.language.lower().startswith("en")
        else (
            f"あなたは{agent_b.name}側の論理構造分析係です。"
            "発言を捏造せず、実際の対話から論理構造だけを抽出してください。"
        )
    )
    b_result = ask_recorder_fn(
        system_instruction=b_system_instr,
        user_prompt=build_recorder_prompt(
            recorder_language=agent_b.language,
            side_name=agent_b.name,
            new_dialogue=segment_dialogue,
            previous_record=previous_b_record,
        ),
        api_client=api_client,
    )
    b_records.append({
        "round": round_label,
        "record": b_result.model_dump(),
    })

    update_agent_memories(
        japan_side=agent_a,
        us_side=agent_b,
        jp_record=a_result,
        us_record=b_result,
        round_no=round_label,
    )

    print(f"\n[{agent_a.name} MEMORY UPDATED]")
    print(json.dumps(a_result.model_dump(), ensure_ascii=False, indent=2))
    print(f"\n[{agent_b.name} MEMORY UPDATED]")
    print(json.dumps(b_result.model_dump(), ensure_ascii=False, indent=2))


def run_dialogue_session(
    topic: str,
    rounds: int = DEFAULT_ROUNDS,
    agents: tuple[Agent, Agent] | None = None,
    api_client: Any = None,
    ask_llm_fn: Callable[..., str] = ask_llm,
    ask_recorder_fn: Callable[..., DialogueRecord] = ask_recorder,
) -> dict[str, Any]:
    """
    指定された議題、ラウンド数、エージェント構成で対話セッションを実行する。
    エージェントが渡された場合も記憶を初期化し、過去実験の記憶混信を防ぐ。
    """
    if agents is not None:
        agent_a, agent_b = agents
        agent_a.reset_memory()
        agent_b.reset_memory()
    else:
        agent_a, agent_b = create_agents()

    dialogue_history: list[dict[str, Any]] = []
    a_records: list[dict[str, Any]] = []
    b_records: list[dict[str, Any]] = []
    last_record_index = 0

    # システムプロンプトの決定（Personaに設定があれば優先）
    a_instruction = (
        agent_a.persona.system_instruction
        if agent_a.persona and agent_a.persona.system_instruction
        else (
            f"あなたは{agent_a.name}エージェントです。{agent_a.language}でのみ発言してください。"
            "提示された役割・知識・記憶を利用し、自然な対談相手として応答してください。"
        )
    )
    b_instruction = (
        agent_b.persona.system_instruction
        if agent_b.persona and agent_b.persona.system_instruction
        else (
            f"You are {agent_b.name}. Respond only in {agent_b.language}. "
            "Use the provided context and memory to respond naturally."
            if agent_b.language.lower().startswith("en")
            else (
                f"あなたは{agent_b.name}エージェントです。{agent_b.language}でのみ発言してください。"
                "提示された役割・知識・記憶を利用し、自然な対談相手として応答してください。"
            )
        )
    )

    for round_no in range(1, rounds + 1):
        print("\n" + "=" * 60)
        print(f"ROUND {round_no}")
        print("=" * 60)

        # Agent A側の発言生成（A側の記録を自記憶、B側の記録を相手記憶として渡す）
        a_prefix = "JP" if agent_a.name == "JP" else agent_a.name
        b_prefix = "US" if agent_b.name == "US" else agent_b.name

        a_own_memory = filter_memory_by_source(agent_a.memory, a_prefix)
        a_opposing_memory = filter_memory_by_source(agent_a.memory, b_prefix)

        a_prompt = build_dialogue_prompt(
            agent=agent_a,
            dialogue_history=dialogue_history,
            own_memory=a_own_memory,
            opposing_memory=a_opposing_memory,
            topic=topic,
        )
        a_text = ask_llm_fn(
            system_instruction=a_instruction,
            user_prompt=a_prompt,
            api_client=api_client,
        )
        dialogue_history.append({
            "round": round_no,
            "speaker": agent_a.name,
            "language": agent_a.language,
            "text": a_text,
            "timestamp": datetime.now().isoformat(),
        })
        print(f"\n[{agent_a.name}]")
        print(a_text)

        # Agent B側の発言生成（B側の記録を自記憶、A側の記録を相手記憶として渡す）
        b_own_memory = filter_memory_by_source(agent_b.memory, b_prefix)
        b_opposing_memory = filter_memory_by_source(agent_b.memory, a_prefix)

        b_prompt = build_dialogue_prompt(
            agent=agent_b,
            dialogue_history=dialogue_history,
            own_memory=b_own_memory,
            opposing_memory=b_opposing_memory,
            topic=topic,
        )
        b_text = ask_llm_fn(
            system_instruction=b_instruction,
            user_prompt=b_prompt,
            api_client=api_client,
        )
        dialogue_history.append({
            "round": round_no,
            "speaker": agent_b.name,
            "language": agent_b.language,
            "text": b_text,
            "timestamp": datetime.now().isoformat(),
        })
        print(f"\n[{agent_b.name}]")
        print(b_text)

        # 定期的な論理構造記録
        if round_no % RECORD_EVERY == 0:
            start_round = last_record_index // 2 + 1
            end_round = len(dialogue_history) // 2
            print("\n" + "-" * 60)
            print(f"RECORDING ROUNDS {start_round}〜{end_round}")
            print("-" * 60)

            segment = dialogue_history[last_record_index:]
            _record_dialogue_segment(
                segment_dialogue=segment,
                round_label=round_no,
                agent_a=agent_a,
                agent_b=agent_b,
                a_records=a_records,
                b_records=b_records,
                api_client=api_client,
                ask_recorder_fn=ask_recorder_fn,
            )
            last_record_index = len(dialogue_history)

    # 最終ターンが RECORD_EVERY の倍数でない場合、未記録の最後の対話を Recorder で記録する
    if last_record_index < len(dialogue_history):
        start_round = last_record_index // 2 + 1
        end_round = len(dialogue_history) // 2
        print("\n" + "-" * 60)
        print(f"RECORDING FINAL UNRECORDED ROUNDS {start_round}〜{end_round}")
        print("-" * 60)

        segment = dialogue_history[last_record_index:]
        _record_dialogue_segment(
            segment_dialogue=segment,
            round_label=end_round,
            agent_a=agent_a,
            agent_b=agent_b,
            a_records=a_records,
            b_records=b_records,
            api_client=api_client,
            ask_recorder_fn=ask_recorder_fn,
        )
        last_record_index = len(dialogue_history)

    return {
        "experiment": {
            "model_candidates": MODEL_CANDIDATES,
            "topic": topic,
            "rounds": rounds,
            "record_every": RECORD_EVERY,
            "recent_turns": RECENT_TURNS,
            "memory_size": MEMORY_SIZE,
            "agent_a": agent_a.persona.to_dict() if agent_a.persona else {"name": agent_a.name},
            "agent_b": agent_b.persona.to_dict() if agent_b.persona else {"name": agent_b.name},
            "timestamp": datetime.now().isoformat(),
        },
        "dialogue": dialogue_history,
        "jp_records": a_records,  # 後方互換性維持
        "us_records": b_records,  # 後方互換性維持
        "a_records": a_records,
        "b_records": b_records,
        "jp_memory": agent_a.memory,  # 後方互換性維持
        "us_memory": agent_b.memory,  # 後方互換性維持
        "a_memory": agent_a.memory,
        "b_memory": agent_b.memory,
    }


# ============================================================
# 10. JSON保存・起動
# ============================================================

def save_result(result: dict[str, Any], filename: str = OUTPUT_FILENAME) -> None:
    """実行結果をUTF-8の整形JSONファイルに保存する"""
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(f"\nSaved: {filename}")


def main() -> None:
    """メイン実行エントリーポイント"""
    global client
    client = create_client()

    print("\n" + "=" * 60)
    print("議論形成の場 Agora: 人文系・言語文化箱庭シミュレーション")
    print("=" * 60)
    print("対話プリセットを選択してください:")
    preset_keys = list(PRESETS.keys())
    for idx, key in enumerate(preset_keys, start=1):
        preset = PRESETS[key]
        print(f"  [{idx}] {preset.title}")
        print(f"      - {preset.description}")
    print("  [5] カスタム（自由入力）")

    choice_input = input("\n選択番号 (1-5, 既定値 1): ").strip()
    selected_idx = int(choice_input) if choice_input.isdigit() else 1

    if 1 <= selected_idx <= len(preset_keys):
        preset_key = preset_keys[selected_idx - 1]
        agent_a, agent_b, default_topic = create_agents_from_preset(preset_key)
        print(f"\n【選択プリセット】: {PRESETS[preset_key].title}")
    else:
        # カスタム入力
        print("\n--- カスタムエージェント設定 ---")
        name_a = input("エージェントAの名前 (既定: 肯定派): ").strip() or "肯定派"
        role_a = input("エージェントAの立場・役割: ").strip() or "提案を積極的に肯定・推進する立場"
        name_b = input("エージェントBの名前 (既定: 慎重派): ").strip() or "慎重派"
        role_b = input("エージェントBの立場・役割: ").strip() or "懸念や批判的視点を提示する立場"

        persona_a = Persona(name=name_a, role_description=role_a, language="日本語")
        persona_b = Persona(name=name_b, role_description=role_b, language="日本語")
        agent_a, agent_b = create_agents(persona_a, persona_b)
        default_topic = "高校社会科の授業において、AIによるレポート作成は認められるべきかどうか。"

    print(f"\n既定の議題:\n  {default_topic}")
    topic_input = input("\n議題を変更する場合は入力してください（空欄なら既定の議題）: ").strip()
    topic = topic_input if topic_input else default_topic

    rounds_input = input(f"対話ラウンド数（既定値 {DEFAULT_ROUNDS}）: ").strip()
    rounds = int(rounds_input) if rounds_input.isdigit() and int(rounds_input) >= 1 else DEFAULT_ROUNDS

    result = run_dialogue_session(
        topic=topic,
        rounds=rounds,
        agents=(agent_a, agent_b),
        api_client=client,
    )
    save_result(result, OUTPUT_FILENAME)
    if rounds < 1:
        raise ValueError("ラウンド数は1以上にしてください。")

    result = run_dialogue_session(topic=topic, rounds=rounds, api_client=client)
    save_result(result, OUTPUT_FILENAME)


if __name__ == "__main__":
    main()
