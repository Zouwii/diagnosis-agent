"""StateGraph 可视化工具 —— Mermaid + PNG"""

import sys
sys.path.insert(0, ".")

from agent.graph import app

g = app.get_graph()

# 1. PNG（VSCode 直接打开）
png = g.draw_mermaid_png()
with open("graph.png", "wb") as f:
    f.write(png)
print("✅ graph.png 已生成")

# 2. Mermaid 文本（复制到 https://mermaid.live 或 .md 文件中查看）
mermaid = g.draw_mermaid()
with open("graph.mermaid", "w") as f:
    f.write(mermaid)
print("✅ graph.mermaid 已生成")
print()
print(mermaid[:500])
