# CSD

古早化学文献结构式 → 假古董 → SMILES → 入库。

前端：React + Vite。GitHub Pages 只托管静态前端；真正的后端是本机 Python 服务。

## 启动

双击 `bootstrap\start-windows.bat`（首次会装依赖）。黑窗口开着 = 后端在跑，关窗 = 停。
想开机自启：把该 BAT 的快捷方式放进 `shell:startup`。
前端打开后自动探测 `http://127.0.0.1:8765`，后端没起会显示引导页，起了自动连。

**隔离（不污染演示电脑）**：首次运行下载便携 Python 到项目内 `.runtime\`，所有包装在这个私有 Python 里。
不写系统 PATH、不装系统 Python、不写注册表、不装系统级组件、不写 pip 缓存、不生成散落的 `__pycache__`。
数据落项目内 `data/`，不进 GitHub。**要彻底卸载：双击 `bootstrap\uninstall-windows.bat` 输 YES**，
删掉 `.runtime` 和数据即可，电脑回到运行前状态（源码和 BAT 保留）。

**MolDet 权重**：首次启动自动下到 `models/`（约 50MB，带 SHA 校验，HF 直连/镜像多源回退）。
这个基础权重固定不变，不随训练更新。

**演示流程**：拷 PDF 数据包 → 打开 GitHub Pages → 双击 `bootstrap\start-windows.bat` 按提示启动
→ 新建任务填文件夹路径 → 结构式筛选瀑布流剔除。训练产物（分类器/字符模板/校准参数/风格档位）
放 `assets/`，每次训练后推送到 GitHub，演示机 pull 即为最新版（详见 `assets/README.md`）。

换工作区：把整个项目文件夹复制到新位置再启动（`.runtime` 跟着走，不用重新下载）。

## 训练管道

数据是管道的内容物，管道本身先立住。每步独立可跑、产物落盘、可单独调试。

```
python -m training.pipeline init --root <工作区>       # 建目录
python -m training.make_sample --out <工作区>/training/01-collect  # 造自测图
python -m training.pipeline status --root <工作区>      # 看每步产物
```

① 采集（三件事分别跑）：
```
python -m training.collect doi <PDF文件名>            # DOI 洗净 + Crossref 查元数据
python -m training.collect align --mineru <MinerU输出目录> --out <结果.json>  # 文本-图对齐
python -m training.collect train --positive <结构式图目录> --negative <负样本目录> --out training/models/structure_svc.joblib
python -m training.collect classify --images <图目录> --model <模型> --out <结果.json>
```
负样本用科研场景里易误认的图：学术表格 / plot / 线图 / 仪器图，不要用生活照片。
你瀑布流首审剔除的图 → `python -m training.collect refine --rejected <剔除目录> --model <模型>` 回流重训。

②③④⑤：
```
python -m training.pipeline run --root <工作区> --step topo    # ③ 拓扑（先建字符模板）
python -m training.pipeline run --root <工作区> --step style   # ② 风格聚类（可给 style_seeds.json 作种子）
python -m training.pipeline run --root <工作区> --step render  # ④ 仿古渲染
python -m training.pipeline run --root <工作区> --step match   # ⑤ 匹配排序
```

③ 的字符模板：`python -m training.topo templates --sample <字符小图目录> --out training/templates/templates.json`
字符小图按文件名命名（`N.png` / `Me.png` / `2.png`），按风格档位分子目录。无模板时 labels 为空并告警，不假装识别。

① 的批量取图用 `pipeline/cli.py`（sample/article/cell），需环境变量 `MINERU_API_KEY`。
MinerU 限额约 1000 页/天（多账号可提到 3000），6569+ 张图要排期。

### 工作区与训练轮次（动态更新 / 留出集 / 交叉验证）
```
python -m training.workspace init --root <工作区> --pdf-dir <PDF目录>
python -m training.workspace sync --root <工作区>       # 增量补新文献，已处理的不重跑
python -m training.workspace new-round --root <工作区> --note "第2轮描述"
python -m training.workspace split --root <工作区> --round 1 --folds 5
```
每轮样本写 `rounds/round_NNN/samples.json`（人审结果），split 划分训练集 / 留出集（不参与训练调参）/ 交叉验证折叠 / 负样本池。
人审剔除的图进负样本池，回流训练分类器。

### 页级判据调参（baseline 对比）
```
python -m training.calibrate run --pdf-dir <PDF目录> --baseline <baseline.json> --out <best.json>
```
baseline.json 记录现成模型（MolDet/DocLayout）标注的"哪些页有结构式"；
自动网格搜 page_scan 判据参数，召回优先（F2），让手写判据逼近 baseline。

拓扑指标只用环数 / 环大小 / 标签，**不用边数**；电荷 ⊕ 不算环；跨时代字体用分档字符模板，不靠通用 OCR。

## 部署

每次 push main 由 GitHub Actions 自动构建前端并部署到 Pages。
