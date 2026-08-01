# 错误码知识库

参见 [docs/README.md](../README.md#-错误码系统当前核心工作)

## 数据库

```
kb_storage
├── errcode_documents   ← 错误码文档（含 breadcrumb 级联路径）
├── errcode_chunks      ← 切片表（待填充）
└── errcode_assets      ← 图片/附件引用表
```

## 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/selective_sync.py` | 定向递归同步钉钉 → errcode_documents |
| `scripts/errcode_asset_extractor.py` | 提取图片/附件 → errcode_assets |

## 图片处理

- **不修改主 RAG 流程**（blocks_to_markdown、chunker 不动）
- 图片引用独立存储在 `errcode_assets`
- 切 chunk 时从 assets 表查询关联图片引用
