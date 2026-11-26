# DEPENDENCIES.md — 依赖清单

> 按 `CLAUDE.md` §二.11：含两类——① 安装的库依赖；② 自定义函数依赖（函数 + 用到的字段）。
> 全库扫描日期：2026-11-26。函数/字段变更时据此判断引用处如何改。

---

## 一、安装的库依赖

实际安装源：`requirements.txt`（bootstrap 双击时读取，装进项目内 `.runtime`，不污染系统）。

| 库 | 最低版本 | 用在哪 | 状态 |
|---|---|---|---|
| pymupdf | 1.26 | PDF 解析、裁图、文本层 | requirements ✓ |
| requests | 2.31 | 下载 PDF / API | requirements ✓ |
| numpy | 2.0 | 全部图像计算 | requirements ✓ |
| opencv-python-headless | 4.10 | cv2 图像处理 | requirements ✓ |
| scipy | 1.11 | 连通域、距离变换 | requirements ✓ |
| scikit-image | 0.22 | skeletonize | requirements ✓ |
| scikit-learn | 1.4 | 分类器 | requirements ✓ |
| joblib | 1.3 | 模型持久化 | requirements ✓ |
| Pillow | 10.0 | 图像 IO | requirements ✓ |
| rdkit | 2024.3 | 分子→图、拓扑指标、渲染 | requirements ✓ |
| huggingface_hub | 0.20 | 模型下载 | requirements ✓ |
| ultralytics | 8.3 | MolDet 结构式检测 | requirements ✓ |
| **networkx** | 3.2 | `training/layer1_graph.py` 图论找环 | **2026-11-26 补入** |
| **rapidocr_onnxruntime** | 1.4 | `training/ocr_pixels.py` 像素 OCR | **2026-11-26 补入** |

快速核对：`grep -rhE '^(import|from) [a-zA-Z_]' --include="*.py" training/ pipeline/ backend/ scripts/`

### 未登记但出现的 import

- **playwright**：`scripts/` 下浏览器自动化用。判断为开发期工具，非运行时依赖，暂不进 requirements。若 bootstrap 需要请补。

---

## 二、自定义函数依赖

> 只列跨模块被调用的关键函数（全库 `from training.* / pipeline.* import` 扫描结果）。
> 字段 = 调用方用到该函数返回/消费的字段；改函数时这些字段必须保留或同步改引用。

### training 模块

| 函数 | 定义处 | 被谁用 | 关键字段 |
|---|---|---|---|
| `load_substituents` | `substituents.py` | `style.py`（渲染）、`substituent_delta.py` | `hetero` / `ring` / `smiles` |
| `match_substituent` | `substituents.py` | `topo.py`、`ocr_pixels.py` | 同上 |
| `normalize_label_text` | `substituents.py` | `topo.py` | 下标/上标归一 |
| `detect_page` / `load_model` | `detect.py` | `backend`、`scripts/sample_parallel.py` | `boxes[].bbox` |
| `resolve_pdf` | `detect.py` | `backend` | PDF 路径 |
| `extract_topology` | `topo.py` | 拓扑比对链 | `rings` / `ring_sizes` / `labels` |
| `build_candidates` | `candidates.py` | `pipeline` | 候选图 + 分数 |
| `TopoIndex` | `library.py` | 候选检索 | 拓扑键 |
| `find_vertices` / `draw_vertices` | `vertices.py` | （当前独立工具） | `lines` / `n_vertices` / `sizes` |
| `our_algorithm` / `truth_from_rdkit` / `ring_systems` | `layer1_graph.py` | `substituent_delta.py` | `ring_sizes` / `n_rings` / `has_fused_fragment` / `has_disconnected_fragment` |
| `delta_from_smiles` / `delta_of` | `substituent_delta.py` | （当前独立工具） | 六指标 + `smiles` / `hetero` |
| `read_pixels` | `ocr_pixels.py` | （当前独立工具） | `symbols` / `hetero` / `substituents` |

### 关键字段说明（拓扑指标六项，2026-11-26 用户口径）

- `has_ring`：有没有环
- `has_multi_ring`：环总数 ≥ 2
- `has_fused_fragment`：某片环系里 ≥2 环（如萘）
- `has_disconnected_fragment`：存在**孤立单环**（Ph 自身即满足）
- `small_ring` / `big_ring`：3/4 元环、≥7 元环（5/6 中环靠排除法）

### pipeline 模块

| 函数 | 定义处 | 被谁用 | 关键字段 |
|---|---|---|---|
| `process_article` | `pipeline/article.py` | 采样主流程 | — |
| `JournalCell` | `pipeline/sample.py` | 采样 | 年代/刊物格子 |
| `Config` | `pipeline/config.py` | 全流程 | 配置 |
| `verify_title` | `pipeline/verify.py` | 身份核验 | verify_status |
| `judge_caption` | `pipeline/figures.py` | 图注判定 | has_structure |
| `SemanticJudge` | `pipeline/llm.py` | 语义比对 | — |

---

## 维护纪律

- 新增 pip 包：先加 `requirements.txt`，再在本表登记。
- 新增跨模块函数：在本表登记"函数 + 被谁用 + 关键字段"。
- 改函数签名/返回字段：先查本表，确认所有引用处同步改。
