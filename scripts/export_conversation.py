import json
import re
import os
from pathlib import Path
from datetime import datetime

TRANSCRIPT_PATH = Path(r"C:\Users\Venu Gopal\.gemini\antigravity\brain\95870c81-28ad-40cf-b9dd-f30b5f5da135\.system_generated\logs\transcript_full.jsonl")
WORKSPACE_DIR = Path(r"d:\enam_assignment")
OUTPUT_MD = WORKSPACE_DIR / "CONVERSATION_EXPORT.md"
OUTPUT_HTML = WORKSPACE_DIR / "CONVERSATION_EXPORT.html"

SECRET_REGEX = re.compile(r"(AQ\.[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,})")

def mask_secrets(text: str) -> str:
    if not text:
        return ""
    return SECRET_REGEX.sub("[REDACTED_API_KEY]", text)

def clean_user_content(text: str) -> str:
    # If the user prompt has <USER_REQUEST> tags, extract that
    m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", text, re.DOTALL)
    if m:
        req = m.group(1).strip()
    else:
        req = text.strip()
    return mask_secrets(req)

def run_export():
    if not TRANSCRIPT_PATH.exists():
        print("Transcript path does not exist!")
        return

    messages = []
    
    with open(TRANSCRIPT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue

            msg_type = entry.get("type")
            source = entry.get("source")
            content = entry.get("content", "")
            created_at = entry.get("created_at", "")

            # User message
            if msg_type == "USER_INPUT" and source == "USER_EXPLICIT":
                clean_text = clean_user_content(content)
                if clean_text:
                    messages.append({
                        "role": "User",
                        "time": created_at,
                        "text": clean_text
                    })
            
            # Assistant response
            elif msg_type == "PLANNER_RESPONSE" and source == "MODEL":
                if content and content.strip():
                    masked_content = mask_secrets(content.strip())
                    # Avoid duplicate back-to-back assistant messages if any
                    if messages and messages[-1]["role"] == "Assistant" and messages[-1]["text"] == masked_content:
                        continue
                    messages.append({
                        "role": "Assistant (FINN AI)",
                        "time": created_at,
                        "text": masked_content
                    })

    print(f"Extracted {len(messages)} conversation turns.")

    # 1. Generate Markdown export
    md_lines = [
        "# FINN Project — Complete Conversation Transcript",
        f"> Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}  ",
        f"> Project: FINN (Financial Investment Agent — ENAM Holdings Build Challenge)  ",
        f"> Total Dialogue Turns: {len(messages)}  ",
        "",
        "---",
        ""
    ]

    for i, msg in enumerate(messages, 1):
        role_badge = "👤 **USER**" if msg["role"] == "User" else "🤖 **FINN AI ASSISTANT**"
        time_str = msg["time"][:19].replace("T", " ") if msg["time"] else ""
        md_lines.append(f"### Turn {i} — {role_badge}  `{time_str}`")
        md_lines.append("")
        md_lines.append(msg["text"])
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    OUTPUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"Saved Markdown export to: {OUTPUT_MD}")

    # 2. Generate Standalone HTML export
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>FINN Project — Conversation Transcript</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.6;
      background-color: #0b1120;
      color: #e2e8f0;
      margin: 0;
      padding: 40px 20px;
    }}
    .container {{
      max-width: 860px;
      margin: 0 auto;
    }}
    h1 {{
      font-size: 26px;
      font-weight: 800;
      color: #38bdf8;
      margin-bottom: 6px;
    }}
    .meta {{
      font-size: 13px;
      color: #64748b;
      margin-bottom: 30px;
      border-bottom: 1px solid #1e293b;
      padding-bottom: 15px;
    }}
    .turn {{
      margin-bottom: 30px;
      border-radius: 12px;
      padding: 20px;
      background: #1e293b;
      border: 1px solid #263548;
    }}
    .turn.user {{
      background: #0f172a;
      border-left: 4px solid #38bdf8;
    }}
    .turn.assistant {{
      background: #131d31;
      border-left: 4px solid #10b981;
    }}
    .turn-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .role-user {{
      color: #38bdf8;
    }}
    .role-assistant {{
      color: #10b981;
    }}
    .time {{
      color: #64748b;
      font-weight: normal;
    }}
    .content {{
      font-size: 14px;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    pre {{
      background: #0b1120;
      padding: 12px;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 13px;
    }}
    code {{
      font-family: Consolas, Monaco, "Andale Mono", monospace;
      background: #0b1120;
      padding: 2px 4px;
      border-radius: 4px;
      color: #38bdf8;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>FINN Project — Complete Conversation Transcript</h1>
    <div class="meta">
      Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')} | Total Turns: {len(messages)} | ENAM Holdings AI Engineer Build Challenge
    </div>
"""

    for i, msg in enumerate(messages, 1):
        is_user = msg["role"] == "User"
        cls = "user" if is_user else "assistant"
        role_cls = "role-user" if is_user else "role-assistant"
        role_label = "👤 User" if is_user else "🤖 FINN AI Assistant"
        time_str = msg["time"][:19].replace("T", " ") if msg["time"] else ""
        
        # Simple HTML escape
        escaped_text = (
            msg["text"]
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

        html_content += f"""
    <div class="turn {cls}">
      <div class="turn-header">
        <span class="{role_cls}">{role_label}</span>
        <span class="time">{time_str}</span>
      </div>
      <div class="content">{escaped_text}</div>
    </div>
"""

    html_content += """
  </div>
</body>
</html>
"""
    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    print(f"Saved HTML export to: {OUTPUT_HTML}")

if __name__ == "__main__":
    run_export()
