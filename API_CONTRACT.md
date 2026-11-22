# 前后端接口契约 v0.3.0

> 角色：
> - **公库** = `Nikki-SU/CSD`（公开）：只放代码、本契约与文档；**零数据**。
> - **私库** = 使用者自己的私有工作库（默认 `csd-workspace`）：放 PDF、裁剪图、样本、标注、缓存，跑 GitHub Actions。
> 传输层：不建 HTTP 服务。前端用 GitHub Contents API 读写私库文件。
> 本文件是前后端唯一事实源。字段、路径、枚举以本文为准；改动按 §十三 执行。

## 零、硬约束

1. 公库不得出现任何真实文献数据：PDF、扫描页、裁剪图、渲染图、样本表、标注、统计底表、缓存、分享包。
2. `result.json` 只下发 `candidate_id`，不下发 SMILES / InChIKey / 分子名，避免审核人被答案暗示。
3. 每图候选数 ≤ 3，`max_candidates` 固定 3，前端不得改。
4. 指标由后端 `report` 计算，前端只展示。
5. 没有后端数据就不显示结果区，不造假、不预填。

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
① 前端写 inbox/{job}/source.pdf（或 doi） + job.json
② 私库 Actions 由 paths: inbox/** 触发：ingest → docverify → render → coarse → fine → chemcheck
③ 结果 commit 回 outbox/{job}/；前端轮询 .progress.json 与 result.json
④ 人工三选一 / 全错 → 写 labels/{job}.csv
⑤ 后端 report 读 labels 算 metrics.json；前端只展示
```

---

## 三、`job.json`

```json
{
  "job_id": "j_20261122_1430_a1b2c3",
  "schema": 1,
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
  "schema": 1,
  "status": "done",
  "doc": {"verify_status": "verified", "doi": "10.1021/ja01101a001", "source": "publisher"},
  "counts": {"figures": 12, "legible": 11, "has_structure": 12},
  "figures": [
    {
      "figure_id": "p004_f01",
      "page": 4,
      "bbox": [112, 240, 389, 331],
      "page_wh": [1700, 2200],
      "crop_path": "outbox/j_20261122_1430_a1b2c3/crops/p004_f01.png",
      "compare_path": "outbox/j_20261122_1430_a1b2c3/compare/p004_f01.png",
      "legible": true,
      "has_structure": true,
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
- `figures` 排序：`(page, bbox_y1, bbox_x1)`。
- `candidates`：`rank` 1–3 唯一，按 `rank` 升序；去重后不足 3 个则如实少放。
- `ring_sizes` 升序；`labels` 为大写元素符号并排序。
- 不出现 SMILES / InChIKey / 分子名。

---

## 六、`result.csv`

列顺序固定，新列只能追加到末尾：

```
job_id,figure_id,page,bbox_x1,bbox_y1,bbox_x2,bbox_y2,page_w,page_h,
legible,has_structure,rank,candidate_id,phash,ssim,topo_match,
edges,rings,ring_sizes,labels,crop_path,render_path,compare_path,doc_verify
```

- 一行一个候选；`ring_sizes` 与 `labels` 用 `|` 分隔，如 `5|6`、`N|O`。
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
  "schema": 1,
  "n": 100,
  "hit@1": {"count": 40, "rate": 0.4000},
  "hit@2": {"count": 55, "rate": 0.5500},
  "hit@3": {"count": 75, "rate": 0.7500},
  "miss": {"count": 20, "rate": 0.2000},
  "illegible": {"count": 5, "rate": 0.0500},
  "coverage@3": 0.7500
}
```

- `n` = 已审且 `legible=true` 的图数；`miss` 与 `illegible` 不计入命中。
- 分组统计（按年代/刊物/风格）由后端另出 `metrics_by_group.json`，结构同上并增加 `group` 字段。

---

## 十、GitHub Contents API 调用规范

| 操作 | 调用 |
|---|---|
| 读文件 | `GET /repos/{owner}/{repo}/contents/{path}?ref={branch}`，`cache: 'no-store'` |
| 读目录 | `GET /repos/{owner}/{repo}/contents/{dir}?ref={branch}` |
| 写文件 | `PUT /repos/{owner}/{repo}/contents/{path}`，body 含 `message`、`content`(base64)、`branch`；已存在时带 `sha` |
| 大文件 | 响应正文为空或 >1MB → `GET /repos/{owner}/{repo}/git/blobs/{sha}`，取 base64 |
| 轮询 | 5000 ms × 120 次；`stage` ∈ {`done`,`failed`} 终止；页面隐藏时暂停 |
| 写并发 | 全局串行队列；同一文件禁止并发 PUT |
| 竞态 | `409/422` → 400/800/1600 ms 退避后重取 `sha`，最多 4 次；仅 `404` 可不带 `sha` 创建 |
| Actions 状态 | run 退避 2s 起、×1.5、封顶 12s |

鉴权：fine-grained PAT，存 IndexedDB；权限 `Contents: Read and write`，一键安装另需 `Workflows: Read and write`。公库内不得出现任何 token。

---

## 十一、UI 功能清单

### P0（先做，缺一不可）

1. **连接设置** `/settings`
   - 输入 PAT、owner、repo、branch；测试连接；保存到 IndexedDB。
   - 显示权限自检结果；失败给可读原因。
2. **新建任务** `/new`
   - 拖放 PDF（多选时一文件一 job，串行提交）或输入 DOI。
   - 选择 `style_profile`；显示 `max_candidates=3` 只读。
   - 提交写 `source.pdf` + `job.json`；乐观插入任务卡，失败回滚并报错。
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
| v0.3.0 | 重写：新增命名规范、UI 功能清单、零数据红线；统一 `figure_id`；新增 `doc.json` 与 `verify_status`；候选去 SMILES/InChIKey；`labels` 明确三种 verdict；明确大文件与写并发处理 |
| v0.2.0 | 文件即接口；路径制契约；轮询与写入规范 |
