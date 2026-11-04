#!/bin/bash
# ============================================================
#   議論形成の場 Agora - CLI対話シミュレーション起動スクリプト (Mac用)
# ============================================================

cd "$(dirname "$0")"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
export PYTHONIOENCODING=utf-8

echo "============================================================"
echo "    🏛️ 議論形成の場 Agora (CLIシミュレーション) を起動中..."
echo "============================================================"
echo ""

PYTHON_CMD="python3"

if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
fi

$PYTHON_CMD dialogue_simulation.py

echo ""
echo "============================================================"
echo "プロセスが終了しました。"
echo "============================================================"
read -p "Enterキーを押すと画面を閉じます..."
