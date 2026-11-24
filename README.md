# CSD

古早化学文献结构式 → 假古董 → SMILES → 入库。

前端：React + Vite。GitHub Pages 只托管静态前端；真正的后端是本机 Python 服务。

## 启动

双击 `bootstrap\start-windows.bat`（首次会装依赖）。黑窗口开着 = 后端在跑，关窗 = 停。
想开机自启：把该 BAT 的快捷方式放进 `shell:startup`。
前端打开后自动探测 `http://127.0.0.1:8765`，后端没起会显示引导页，起了自动连。

数据落本地 `data/`，不进 GitHub。换工作区：把后端目录整个复制到新文件夹再启动。

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

拓扑指标只用环数 / 环大小 / 标签，**不用边数**；电荷 ⊕ 不算环；跨时代字体用分档字符模板，不靠通用 OCR。

## 部署

每次 push main 由 GitHub Actions 自动构建前端并部署到 Pages。
