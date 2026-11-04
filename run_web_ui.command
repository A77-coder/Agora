#!/bin/bash
# ============================================================
#   議論形成の場 Agora - Web UI 起動スクリプト (Mac用)
# ============================================================

cd "$(dirname "$0")"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
export PYTHONIOENCODING=utf-8

echo "============================================================"
echo "    🏛️ 議論形成の場 Agora (Webサイト版) を起動中..."
echo "============================================================"
echo ""

STREAMLIT_CMD=""

# 1. 仮想環境 .venv 内の streamlit / python を探索
if [ -f ".venv/bin/streamlit" ]; then
    STREAMLIT_CMD=".venv/bin/streamlit"
elif [ -f ".venv/bin/python" ] && .venv/bin/python -c "import streamlit" >/dev/null 2>&1; then
    STREAMLIT_CMD=".venv/bin/python -m streamlit"
# 2. システムの streamlit / python3 を探索
elif command -v streamlit >/dev/null 2>&1; then
    STREAMLIT_CMD="streamlit"
elif python3 -c "import streamlit" >/dev/null 2>&1; then
    STREAMLIT_CMD="python3 -m streamlit"
fi

# Streamlitが見つからない場合の自動案内・インストール
if [ -z "$STREAMLIT_CMD" ]; then
    echo "【お知らせ】Streamlit がインストールされていません。"
    echo "必要なパッケージ（streamlit, pydantic, google-genai）をインストールしますか？"
    echo ""
    read -p "インストールを開始しますか？ [y/N]: " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo ""
        echo "パッケージをインストール中..."
        if [ -f ".venv/bin/python" ]; then
            .venv/bin/python -m pip install -r requirements.txt
            if [ -f ".venv/bin/streamlit" ]; then
                STREAMLIT_CMD=".venv/bin/streamlit"
            else
                STREAMLIT_CMD=".venv/bin/python -m streamlit"
            fi
        else
            python3 -m pip install --break-system-packages -r requirements.txt 2>/dev/null || python3 -m pip install --user -r requirements.txt
            STREAMLIT_CMD="python3 -m streamlit"
        fi
    else
        echo ""
        echo "起動をキャンセルしました。"
        echo "手動でインストールする場合: pip install -r requirements.txt"
        echo ""
        read -p "Enterキーを押すと画面を閉じます..."
        exit 1
    fi
fi

echo "ブラウザで Web UI を開きます..."
echo "URL: http://localhost:8501"
echo ""
echo "※ 終了する場合は、この画面で [Ctrl + C] を押してください。"
echo "============================================================"
echo ""

$STREAMLIT_CMD run app.py

echo ""
echo "Agora Web UI を終了しました。"
read -p "Enterキーを押すと画面を閉じます..."
