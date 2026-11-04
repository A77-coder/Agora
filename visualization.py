"""
議論形成の場 Agora: 議論構造ビジュアライゼーションモジュール
Recorderの構造化出力（claims, agreements, unresolved_points, conclusions）から
Mermaidダイアグラム定義を生成し、HTMLレンダリングをサポートします。
"""

from typing import Any


def sanitize_mermaid_text(text: str, max_length: int = 40) -> str:
    """Mermaidの構文エラーを防ぐため特殊文字をエスケープ・短縮する"""
    if not text:
        return "（なし）"
    clean = (
        text.replace("&", "＆")
        .replace("<", "＜")
        .replace(">", "＞")
        .replace('"', "'")
        .replace("[", "［")
        .replace("]", "］")
        .replace("(", "（")
        .replace(")", "）")
        .replace("{", "｛")
        .replace("}", "｝")
        .replace("-->", "→")
        .replace("\n", " ")
        .strip()
    )
    if len(clean) > max_length:
        clean = clean[:max_length] + "…"
    return clean


def generate_mermaid_argument_graph(
    record: dict[str, Any], topic: str = "議論の論点構造"
) -> str:
    """
    Recorderの分析辞書からMermaid.js用のフローチャートコードを生成する。
    Claims, Agreements, Unresolved Points, Conclusions を論理展開ツリーとして配置。
    """
    claims = record.get("claims", [])
    agreements = record.get("agreements", [])
    unresolved = record.get("unresolved_points", [])
    conclusions = record.get("conclusions", [])

    clean_topic = sanitize_mermaid_text(topic, max_length=50)

    lines: list[str] = [
        "graph TD",
        "  %% スタイル定義",
        "  classDef topicStyle fill:#eceff1,stroke:#455a64,stroke-width:2px,color:#263238,font-weight:bold;",
        "  classDef claimStyle fill:#e3f2fd,stroke:#1976d2,stroke-width:2px,color:#0d47a1;",
        "  classDef agreeStyle fill:#e8f5e9,stroke:#388e3c,stroke-width:2px,color:#1b5e20;",
        "  classDef unresStyle fill:#fff3e0,stroke:#f57c00,stroke-width:2px,color:#e65100;",
        "  classDef conclStyle fill:#f3e5f5,stroke:#8e24aa,stroke-width:2px,color:#4a148c;",
        "",
        f'  ROOT["議題: {clean_topic}"]:::topicStyle',
        "",
    ]

    # 1. 主張（Claims）
    claim_nodes: list[str] = []
    if claims:
        lines.append("  subgraph CLAIMS [主要な主張・根拠]")
        for idx, c in enumerate(claims[:4], start=1):
            speaker = sanitize_mermaid_text(c.get("speaker", "話者"), max_length=15)
            claim_text = sanitize_mermaid_text(c.get("claim", ""), max_length=30)
            cid = f"C{idx}"
            lines.append(f'    {cid}["【{speaker}】<br>{claim_text}"]:::claimStyle')
            claim_nodes.append(cid)
        lines.append("  end")
        for cid in claim_nodes:
            lines.append(f"  ROOT --> {cid}")
        lines.append("")

    # 2. 合意点（Agreements）
    agree_nodes: list[str] = []
    if agreements:
        lines.append("  subgraph AGREEMENTS [🤝 到達した合意点]")
        for idx, a in enumerate(agreements[:3], start=1):
            a_text = sanitize_mermaid_text(a, max_length=35)
            aid = f"A{idx}"
            lines.append(f'    {aid}["{a_text}"]:::agreeStyle')
            agree_nodes.append(aid)
        lines.append("  end")
        if claim_nodes:
            for cid in claim_nodes:
                for aid in agree_nodes:
                    lines.append(f"  {cid} -.合意.-> {aid}")
        else:
            for aid in agree_nodes:
                lines.append(f"  ROOT --> {aid}")
        lines.append("")

    # 3. 未解決の対立点（Unresolved Points）
    unres_nodes: list[str] = []
    if unresolved:
        lines.append("  subgraph UNRESOLVED [⚡ 未解決の対立・論点]")
        for idx, u in enumerate(unresolved[:3], start=1):
            u_text = sanitize_mermaid_text(u, max_length=35)
            uid = f"U{idx}"
            lines.append(f'    {uid}["{u_text}"]:::unresStyle')
            unres_nodes.append(uid)
        lines.append("  end")
        if claim_nodes:
            for cid in claim_nodes:
                for uid in unres_nodes:
                    lines.append(f"  {cid} -.対立.-> {uid}")
        else:
            for uid in unres_nodes:
                lines.append(f"  ROOT --> {uid}")
        lines.append("")

    # 4. 結論（Conclusions）
    if conclusions and agree_nodes:
        lines.append("  subgraph CONCLUSIONS [導かれた結論・展望]")
        for idx, concl in enumerate(conclusions[:2], start=1):
            concl_text = sanitize_mermaid_text(concl, max_length=35)
            ccid = f"CC{idx}"
            lines.append(f'    {ccid}["{concl_text}"]:::conclStyle')
            for aid in agree_nodes:
                lines.append(f"  {aid} ==> {ccid}")
        lines.append("  end")

    return "\n".join(lines)


def render_mermaid_html(mermaid_code: str, height: int = 500) -> str:
    """HTML内にMermaid.js CDNを埋め込み、安全にSVG描画するHTML文字列を生成する"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <script>
            mermaid.initialize({{
                startOnLoad: true,
                theme: 'neutral',
                flowchart: {{ useMaxWidth: true, htmlLabels: true, curve: 'basis' }}
            }});
        </script>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                margin: 0;
                padding: 10px;
                display: flex;
                justify-content: center;
                align-items: center;
                background-color: transparent;
            }}
            .mermaid {{
                width: 100%;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid">
{mermaid_code}
        </div>
    </body>
    </html>
    """
