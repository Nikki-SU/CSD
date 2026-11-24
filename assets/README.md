# 训练产物（随 GitHub 走）

## 数据 vs 训练产物（红线）

**数据（原材料，不进 GitHub，随 PDF 数据包拷）**：文献 PDF、结构式原图、人工标注样本、成员明细（哪篇文章属于哪个档位）。

**训练产物（能力，进 GitHub，每次训练后推送）**：从数据里训练出来的模型权重、参数、模板——不含任何原图或文章索引。

判定标准：**产物里只要含原图、原图路径、文章名/年份索引，就是数据，不能进这里。**
这类文件用 `_local.json` 后缀，已被 gitignore。

## 这里放什么

| 文件 | 来源 | 含数据？ | 作用 |
|---|---|---|---|
| `classifier.joblib` | `training.collect train/refine` | 否（数值特征向量+标签，非原图） | 结构式二分类器 |
| `templates.json` | `training.topo build_templates` | 否（字符小图模板，是"学到的特征"） | 按档位的字符模板 |
| `calibration.json` | `training.calibrate run` | 否（纯参数） | 页级判据最优参数 |
| `style_profiles/档位_N.json` | `training.style cluster` | 否（已剥离 members） | 风格档位画法参数 |

不放：`models/`（MolDet 基础权重，bootstrap 自动下、不随训练变）、任何 `_local.json`（数据明细）、任何 PDF/原图。

## 流程

**训练完自动回传**：`python -m training.pipeline run --step <训练步>` 结束后自动把纯产物回传到这里
（`training/publish.py`），人不用手动拷——只需 `git commit + push`，演示机 pull 即最新版。
也可单独跑 `python -m training.pipeline publish --root <工作区>`。
回传时自动剥掉 `members` 原图索引、跳过 `_local.json`，数据不会进库。
