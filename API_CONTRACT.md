# 前后端接口契约 v0.5.0

> 角色：
> - **公库** = `Nikki-SU/CSD`（公开）：只放代码、本契约与文档；**零数据**。
> - **本地后端**：唯一运行时。承载 API、任务队列、文件读写；数据目录 `data/`，人可读。
> 传输层：本地 HTTP，默认只绑 `127.0.0.1:8765`；`--lan` 时绑 `0.0.0.0` 并校验访问码。GitHub 只做代码托管，不参与运行时。
> 本文件是前后端唯一事实源。字段、路径、枚举以本文为准；改动按 §十三 执行。

## 零、硬约束

1. 公库不得出现任何真实文献数据：PDF、扫描页、裁剪图、渲染图、样本表、标注、统计底表、缓存、分享包。
2. `result.json` 只下发 `candidate_id`，不下发 SMILES / InChIKey / 分子名，避免审核人被答案暗示。
3. 每图候选数 ≤ 3，`max_candidates` 固定 3，前端不得改。
4. 指标由后端 `report` 计算，前端只展示。
5. 没有后端数据就不显示结果区，不造假、不预填。
6. `legible=true` 的图**必须有 `query_features`**（从文献图提取的粗特征）；不得只算候选侧特征，查询侧缺值就无法初筛。
7. 运行数据只落本地 `data/`；仓库与公库零数据。数据目录不进 git。

---

## 一、命名规范

### 1.1 通用

| 项 | 规则 |
|---|---|
| 字段名 | 一律 `snake_case`；JSON 与 CSV 同名，不做 camelCase 转换 |
| 枚举 | 小写 `snake_case`，如 `done`、`mismatch`、`chemcheck` |
| 时间 | ISO 8601，UTC，带 `Z`，如 `2026-11-22T06:30:00Z` |
| 布尔 | JSON `true/false`；CSV `true/false`（不写 1/0） |
| 空值 | JSON `null`；CSV 空字符串 |
| 编码 | UTF-8；CSV 带 BOM，LF 换行 |
| 数值 | 分数 0–1，保留 4 位小数；像素为整数 |
| 坐标 | `bbox = [x1,y1,x2,y2]`，原点左上，`x2>x1`、`y2>y1`，页面按 **200 dpi** 渲染 |

### 1.2 标识符

| 字段 | 格式 | 示例 | 规则 |
|---|---|---|---|
| `job_id` | `j_YYYYMMDD_HHMM_<6hex>` | `j_20261122_1430_a1b2c3` | 时间取 UTC；全局唯一；不重用 |
| `figure_id` | `p{page:03d}_f{idx:02d}` | `p004_f01` | `page` 从 1 起；`idx` 为页内阅读顺序，从 1 起 |
| `candidate_id` | `c_<8hex>` | `c_7f3a91d2` | 同一 job 内唯一且稳定；不含任何结构信息 |

### 1.3 路径与文件名

- 路径全小写，只用 `a-z0-9_-` 与 `/`，不含空格、中文、括号。
- 目录：`inbox/{job_id}/`、`outbox/{job_id}/`、`labels/`、`settings/`。
- 文件名：

| 文件 | 路径 |
|---|---|
| 任务配置 | `inbox/{job_id}/job.json` |
| 源 PDF | `inbox/{job_id}/source.pdf` |
| 进度 | `outbox/{job_id}/.progress.json` |
| 结果 | `outbox/{job_id}/result.json` / `result.csv` |
| 文档核验 | `outbox/{job_id}/doc.json` |
| 裁剪图 | `outbox/{job_id}/crops/{figure_id}.png` |
| 对比图 | `outbox/{job_id}/compare/{figure_id}.png` |
| 单候选渲染 | `outbox/{job_id}/compare/{figure_id}_r{rank}.png` |
| 指标 | `outbox/{job_id}/metrics.json` |
| 标注 | `labels/{job_id}.csv` |
| 后端版本 | `settings/backend-version.csv` |

### 1.4 代码命名

- 前端路由：`/`（任务列表）、`/new`（新建）、`/jobs/:jobId/review`（审阅）、`/jobs/:jobId/report`（结果）、`/settings`（连接）。
- 前端本地存储键：`csd.pat`、`csd.owner`、`csd.repo`、`csd.branch`、`csd.reviewer`；IndexedDB 库名 `csd`，表 `settings`。
- React 组件 `PascalCase`，文件 `kebab-case.tsx`；TS 类型字段直接用契约的 `snake_case`，不做映射层。
- 后端模块固定为：`ingest`、`filter`、`candidate`、`render`、`match`、`store`、`report`；函数 `snake_case`。

---

## 二、数据流

```
① 前端 POST /api/jobs：source_type=pdf|image，source_ref=本地路径或目录
② 本地后端写 data/inbox/{job}/job.json，后台线程排队
③ 依次 ingest → docverify → render → coarse → fine → chemcheck，写 data/outbox/{job}/
④ 前端轮询 GET /api/jobs/{job}；人审读 /files/ 下的缩略图，POST /api/labels 写标注
⑤ 本地 report 算 metrics.json；GET /api/export/{job} 打 zip 导出
```

---

## 三、`job.json`

```json
{
  "job_id": "j_20261122_1430_a1b2c3",
  "schema": 2,
  "created_at": "2026-11-22T06:30:00Z",
  "source_type": "pdf",
  "source_ref": "inbox/j_20261122_1430_a1b2c3/source.pdf",
  "doi": null,
  "style_profile": "default_1970s",
  "params": {"max_candidates": 3},
  "reviewer": null
}
```

- `source_type`：`pdf` | `doi`。`doi` 时 `source_ref` 为 `null`，由后端取 PDF 并落 `source.pdf`。
- `style_profile`：`default_1950s` | `default_1960s` | `default_1970s` | `default_1980s`；配置放私库，不硬编码。
- `params.max_candidates` 必须为 3。

---

## 四、`doc.json`

文章级核验，进度到 `docverify` 后即可出现。

```json
{
  "job_id": "j_20261122_1430_a1b2c3",
  "verify_status": "verified",
  "doi": "10.1021/ja01101a001",
  "title_claim": "The Synthesis of ...",
  "title_pdf": "The synthesis of ...",
  "title_sim": 0.97,
  "pages": 12,
  "source": "publisher",
  "checked_at": "2026-11-22T06:40:00Z"
}
```

- `verify_status`：`verified` | `mismatch` | `unreadable`。
- `source`：`oa` | `publisher` | `repository` | `other`（只记获取路径，不参与可信度判断）。
- `mismatch` / `unreadable` 时前端必须显示显著横幅，且该 job 的结果标记为不可直接采信。

---

## 五、`result.json`

```json
{
  "job_id": "j_20261122_1430_a1b2c3",
  "schema": 2,
  "status": "done",
  "doc": {"verify_status": "verified", "doi": "10.1021/ja01101a001", "source": "publisher"},
  "counts": {"figures": 12, "legible": 11, "has_structure": 12},
  "figures": [
    {
      "figure_id": "p004_f01",
      "page": 4,
      "bbox": [112, 240, 389, 331],
      "page_wh": [1700, 2200],
      "thumb_path": "outbox/j_20261122_1430_a1b2c3/thumbs/p004_f01.jpg",
      "crop_path": "D:/csd/outbox/j_20261122_1430_a1b2c3/crops/p004_f01.png",
      "compare_path": "D:/csd/outbox/j_20261122_1430_a1b2c3/compare/p004_f01.png",
      "legible": true,
      "has_structure": true,
      "query_features": {"edges": 14, "rings": 1, "ring_sizes": [5], "labels": ["N", "O"]},
      "candidates": [
        {
          "rank": 1,
          "candidate_id": "c_7f3a91d2",
          "render_path": "outbox/j_20261122_1430_a1b2c3/compare/p004_f01_r1.png",
          "score": {"phash": 0.91, "ssim": 0.82, "topo_match": true},
          "features": {"edges": 14, "rings": 1, "ring_sizes": [5], "labels": ["N", "O"]}
        }
      ]
    }
  ]
}
```

- `status`：`done` | `partial` | `failed`。
- `thumb_path`：私库内缩略图（长边 ≤ 512 px，JPEG），**前端唯一可读的图**。
- `crop_path` / `compare_path`：本地绝对路径，后端本地使用，前端不解析、不请求。
- `figures` 排序：`(page, bbox_y1, bbox_x1)`。
- `candidates`：`rank` 1–3 唯一，按 `rank` 升序；去重后不足 3 个则如实少放。
- `query_features`：从**文献图**上提取的粗特征，与候选侧 `features` 同构；有环 / 无环、杂原子存在性是初筛的左侧输入。`legible=true` 时必填；`legible=false` 的图整条排除，不填。
- `ring_sizes` 升序；`labels` 为大写元素符号并排序。
- 不出现 SMILES / InChIKey / 分子名。

---

## 六、`result.csv`

列顺序固定，新列只能追加到末尾：

```
job_id,figure_id,page,bbox_x1,bbox_y1,bbox_x2,bbox_y2,page_w,page_h,
legible,has_structure,rank,candidate_id,phash,ssim,topo_match,
edges,rings,ring_sizes,labels,crop_path,render_path,compare_path,doc_verify,
query_edges,query_rings,query_ring_sizes,query_labels,thumb_path
```

- 一行一个候选；`ring_sizes` 与 `labels` 用 `|` 分隔，如 `5|6`、`N|O`。
- `query_*` 为**文献图侧**粗特征，每行重复；分隔规则同候选侧。`legible=true` 时不得为空。
- `doc_verify` 为文章级字段，每行重复。

---

## 七、`labels/{job_id}.csv`

```
job_id,figure_id,selected_rank,verdict,redrawn_smiles,reviewer,reviewed_at
```

- `verdict`：`match` | `miss` | `illegible`。
- `match`：`selected_rank` ∈ {1,2,3}，`redrawn_smiles` 空。
- `miss`：`selected_rank` 空，`redrawn_smiles` 必填（Ketcher/JSME 产出）。
- `illegible`：`selected_rank` 空，`redrawn_smiles` 空。
- 幂等：按 `(figure_id, reviewer)` 覆盖；整文件重写前先 GET `sha`。

### 7.1 `labels/{job_id}_topo.csv`

拓扑校对**只记被标红的项**，不记全对项：

```
job_id,figure_id,feature,expected,detected,reviewer,reviewed_at
```

- `feature`：`edges` | `rings` | `ring_sizes` | `labels`；一行一个错项，同一图可多行。
- `expected` 为人工判断的正确值，`detected` 为后端原识别值；`ring_sizes` 用 `|` 分隔。
- 准确率口径：`1 − 标红项数 ÷ (已审图数 × 4)`，分母取 `labels/{job}.csv` 中已审图数。
- **前提**：审一张图必须四项都过目；每张审过的图在 `labels/{job}.csv` 必有一行。否则分母不成立，不得出准确率。

---

## 八、`.progress.json`

```json
{"stage": "fine", "pct": 42, "message": "精判 42/100", "updated_at": "2026-11-22T06:45:00Z"}
```

- `stage`：`queued` | `ingest` | `docverify` | `render` | `coarse` | `fine` | `chemcheck` | `done` | `failed`。
- 终态：`done` / `failed`。

---

## 九、`metrics.json`（仅后端计算）

```json
{
  "job_id": "j_20261122_1430_a1b2c3",
  "schema": 2,
  "n": 100,
  "hit@1": {"count": 40, "rate": 0.4000},
  "hit@2": {"count": 55, "rate": 0.5500},
  "hit@3": {"count": 75, "rate": 0.7500},
  "miss": {"count": 20, "rate": 0.2000},
  "illegible": {"count": 5, "rate": 0.0500},
  "coverage@3": 0.7500,
  "topo": {"reviewed_figures": 80, "wrong_items": 12, "accuracy": 0.9625}
}
```

- `n` = 已审且 `legible=true` 的图数；`miss` 与 `illegible` 不计入命中。
- `topo.accuracy = 1 − wrong_items ÷ (reviewed_figures × 4)`；`reviewed_figures` 取 `labels/{job}.csv` 的已审图数，缺 `labels` 时 `topo` 为 `null`，不得估算。
- 分组统计（按年代/刊物/风格）由后端另出 `metrics_by_group.json`，结构同上并增加 `group` 字段。

---

## 十、本地 API

| 方法 | 路径 | 用途 | 回环限制 |
|---|---|---|---|
| GET | `/api/health` | 服务存活与版本 | 否 |
| GET | `/api/jobs` | 任务列表（分页、按状态过滤） | 否 |
| POST | `/api/jobs` | 建任务；body 为 job.json 字段 | **是** |
| GET | `/api/jobs/{job_id}` | 任务元数据 + `.progress.json` | 否 |
| GET | `/api/jobs/{job_id}/result` | `result.json`；未就绪返回 404 | 否 |
| GET | `/api/jobs/{job_id}/doc` | `doc.json`；未就绪返回 404 | 否 |
| GET | `/api/jobs/{job_id}/metrics` | `metrics.json`；未就绪返回 404 | 否 |
| POST | `/api/labels` | 写 `labels/{job}.csv`；按 `(figure_id, reviewer)` 覆盖 | **是** |
| POST | `/api/labels/topo` | 写 `labels/{job}_topo.csv` | **是** |
| GET | `/files/{job_id}/{path}` | 读 outbox 内的缩略图等静态文件 | 否 |
| GET | `/api/export/{job_id}` | 打包该 job 的 outbox 为 zip | **是** |
| DELETE | `/api/jobs/{job_id}` | 删任务；需二次确认参数 `confirm=true` | **是** |

- 回环限制：客户端不是 `127.0.0.1` / `::1` 时返回 403。`--lan` 模式下只读接口仍放行，写接口一律拒绝。
- 鉴权：`--lan` 时要求请求头 `X-Access-Code`，与启动时生成的访问码一致；默认回环模式不校验。
- 静态托管：`/` 返回前端构建产物；`/assets/*` 原样返回。找不到构建产物时返回一句可读提示，不回退到 404 空白页。
- 轮询：5000 ms × 120 次；`stage` 为 `done` / `failed` 终止；页面隐藏时暂停。
- 写并发：同一 job 的 labels 写入串行；整文件重写前先取当前版本，失败重试最多 4 次。

---

## 十一、UI 功能清单

### P0（先做，缺一不可）

1. **服务连接** `/settings`
   - 默认 `http://127.0.0.1:8765`；局域网模式填 `http://<主机IP>:8765` 与访问码。
   - 「测试连接」调 `/api/health`；失败给可读原因（服务未启动 / 访问码错误）。
   - 地址与访问码存 localStorage，不存任何 PAT。
2. **新建任务** `/new`
   - 拖放 PDF 或选择本地目录（PDF 任务一文件一 job；图片任务整目录一 job，串行提交）。
   - 选择 `style_profile`；显示 `max_candidates=3` 只读。
   - 提交到 `POST /api/jobs`；乐观插入任务卡，失败回滚并报错。
   - 校验：文件类型 PDF、单文件 ≤ 100 MB、DOI 格式。
3. **任务列表** `/`
   - 卡片或表格：`job_id`、创建时间、来源、状态、进度、run 链接。
   - 进行中任务轮询；终态停止；空状态与失败状态明确。
4. **审阅页** `/jobs/:jobId/review`
   - 顶部：文档核验横幅（`verified`/`mismatch`/`unreadable`）、进度、筛选（未审/已审/不可读）、已审计数。
   - 左：原图裁剪，支持缩放与平移，显示页码与 bbox。
   - 右：3 个候选卡，每卡显示 `candidate_id`、`rank`、渲染图、特征（edges/rings/ring_sizes/labels）、分数（phash/ssim/topo_match）；可放大。
   - 显示后端拼好的 `compare_path` 对比图。
   - 操作：选 rank1/2/3、全错、标记不可读、跳过。
   - 全错 → 打开 Ketcher/JSME 画布，保存 `redrawn_smiles`。
   - 快捷键：`1/2/3` 选择、`0` 全错、`J/K` 上下一条、`Z` 放大、`Enter` 确认。
   - 写 `labels/{job}.csv`：乐观更新 + 回滚；支持 5 秒内撤销；冲突按 §十 处理。
5. **结果与导出** `/jobs/:jobId/report`
   - 下载 `result.csv`；展示失败清单与缺口；提供 Actions run 链接。
6. **全局状态**
   - 没有后端数据不显示结果区；所有错误可读、可复制、不吞。

### P1（P0 跑通后）

7. **指标页**：读 `metrics.json`，展示 hit@1/2/3、coverage@3、miss、illegible；支持按年代/刊物/风格分组。
8. **筛选与批量**：按年代、刊物、`verify_status`、`legible` 过滤；批量导出。
9. **参数微调**：阈值与特征权重写入 `job.json` 的 `params`；后端未支持时隐藏，不做假控件。
10. **任务管理**：重跑、删除（删除需二次确认，并清理私库对应目录）。

### 非功能要求

- 图片一律经 Contents API 读为 blob URL，用完 revoke；不得写入仓库、不得进 localStorage。
- 大文件走 Blob API；写操作串行；滚动条隐形；长列表虚拟滚动。
- 移动端至少能完成审阅与三选一。
- 不展示任何 SMILES / InChIKey / 分子名。
- 开发期占位数据在代码里合成，不提交真实数据。

---

## 十二、错误与空状态

| 场景 | 前端行为 |
|---|---|
| `result.json` 404 | 显示「后端处理中」，继续轮询，不报错 |
| `doc.json` 404 | 不显示核验横幅，不阻塞 |
| Actions 失败 | 显示 run 链接，不吞错误 |
| `verify_status=mismatch` | 显著横幅；结果可看但标记不可采信 |
| 判定字段非法 | 标红该条，不写整批 |
| 409/422 | 静默重试；最终失败回滚并给可读错误 |
| 无 PAT / 无权限 | 引导到 `/settings`，不显示假数据 |

---

## 十三、契约变更规则

- 本文件版本号 `vMAJOR.MINOR.PATCH`；`schema` 为数据模式整数。
- 追加可选字段：MINOR +1，`schema` 不变。
- 字段改名、删除、语义变化、枚举增减：MAJOR +1，`schema` +1，并在下方变更记录写明迁移方式。
- 前端必须容忍未知字段；后端必须容忍缺省可选字段。
- 变更后由后端在公库提交本文件，UI 侧按最新版本对齐。

## 十四、变更记录

| 版本 | 变更 |
|---|---|
| v0.5.0 | 运行时改为本地后端：取消私库与 GitHub Contents API，新增 §十 本地 API 与回环/访问码规则；数据只落本地 `data/`；前端 `/settings` 改为服务地址与访问码；`job.json` 的 `source_ref` 为本地路径 |
| v0.4.0 | 存储分工改为「本地处理、私库只存文本与缩略图」：`result.json` 新增 `thumb_path`（私库内，前端唯一可读图），`crop_path/compare_path` 明确为本地路径；`result.csv` 末尾追加 `thumb_path`；新增 `labels/{job}_topo.csv` 与 `metrics.topo` 口径；PDF 与大图不进私库；`schema` 升为 2 |
| v0.3.1 | 补上文献图侧粗特征：`result.json` 增加图级 `query_features`，`result.csv` 追加 `query_edges/query_rings/query_ring_sizes/query_labels`；§零 明确 `legible=true` 时查询侧特征必填 |
| v0.3.0 | 重写：新增命名规范、UI 功能清单、零数据红线；统一 `figure_id`；新增 `doc.json` 与 `verify_status`；候选去 SMILES/InChIKey；`labels` 明确三种 verdict；明确大文件与写并发处理 |
| v0.2.0 | 文件即接口；路径制契约；轮询与写入规范 |
