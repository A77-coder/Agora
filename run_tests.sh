#!/bin/bash
cd "$(dirname "$0")"

echo "========================================================"
echo "  議論形成の場Agora - 単体テスト実行 (Mac)"
echo "========================================================"
echo ""

if [ -f ".venv/bin/python" ]; then
    echo "[仮想環境 .venv を使用してテストを実行します]"
    .venv/bin/python test_dialogue_simulation.py
else
    echo "[システムの python3 を使用してテストを実行します]"
    python3 test_dialogue_simulation.py
fi

echo ""
echo "========================================================"
