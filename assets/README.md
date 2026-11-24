# 训练产物（随 GitHub 走）

这里放**训练后会变化**的模块资产。每次训练完由人推送到 GitHub；
演示机 pull 下来就是最新版。与 `models/`（MolDet 基础权重，bootstrap 自动下、不随训练变）区分。

## 文件

| 文件 | 来源 | 作用 |
|---|---|---|
| `classifier.joblib` | `training.collect train/refine` | 结构式二分类器，首审剔除回流重训 |
| `templates.json` | `training.topo build_templates` | 按风格档位的字符模板（跨时代字体） |
| `calibration.json` | `training.calibrate run` | 页级判据参数（逼近 baseline 的最优值） |
| `style_profiles/*.json` | `training.style cluster` | 风格档位参数 |

## 约定

- 训练完把产物复制到这里，commit + push（人来做）。
- 后端/训练代码从 `assets/` 读这些文件；`data/`、`models/` 只放本机运行缓存，不进库。
- MolDet 权重不在这里——它在 `models/`，由 `bootstrap/fetch_models.py` 首次自动下载。
