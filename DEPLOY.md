# Agora Web公開手順（Streamlit Community Cloud）

先生やクラスメイトがURLを開くだけでAgoraを動かせるようにするための手順です。
**所要時間：約2分（GitHub ログインとリポジトリ選択のみ、Secrets設定は不要）**

> [!NOTE]
> **APIキーの安全設計（BYOK方式）**
> 本アプリは、サイト訪問者各自が自分のGemini APIキー（無料）をブラウザ上で入力して動かす「BYOK（Bring Your Own Key）方式」を採用しています。
> クラウド側に作者のAPIキーを登録する必要は一切ありません（空欄のままでOK）。
> APIキーを持っていない訪問者も、同梱の「🎬 発表デモ再生モード」で全機能を完全に体験できます。

---

## 手順

### 1. Streamlit Community Cloud にログイン
1. https://share.streamlit.io を開く
2. 「Continue with GitHub」で、GitHub アカウントでログイン
3. GitHub 側でアクセス許可を求められたら許可する

### 2. アプリを作成
1. 「Create app」→「Deploy a public app from GitHub」を選択
2. 以下を入力：
   | 項目 | 値 |
   | :--- | :--- |
   | Repository | `A77-coder/Agora` |
   | Branch | `main` |
   | Main file path | `app.py` |
   | App URL | 任意（例：`agora-dialogue`） |
3. 「Advanced settings」を開き、Python バージョンを **3.12** に設定
   ※ Secrets（秘密情報）欄は**何も入力せず空欄のまま**で問題ありません。

### 3. Deploy
「Deploy!」を押すと数分でビルドされ、`https://<App URL>.streamlit.app` で公開されます。

---

## 注意事項

- **Mermaid 図**：論点ツリーは CDN（jsdelivr）から Mermaid.js を読み込みます。学校のネットワークで
  外部CDNがブロックされている場合は図が表示されません（他の機能は動作します）。

## 発表当日の推奨
- 本番は **「🎬 発表デモ再生モード」** を使う（APIキー・通信状態に一切依存せず安定実演可能）
- リアルタイム対話は「時間やリクエストがあれば、自分のキーを入力して実演する」扱いにすると安心です
