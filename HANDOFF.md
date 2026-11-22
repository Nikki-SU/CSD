# 交接说明：文献批量获取与结构式数据集

> 给下一个本地工作区的 Agent。先读这一页，再动手。

## 一、现在在做什么

从 1900–1979 年的有机化学期刊里，按「刊 × 年」每个格子取 **10 篇有机文章**，建立 PDF 池，后续从 PDF 里抽化学结构式图。

数据集口径以 `DATASET_WORKFLOW.md` 和 `JOURNALS_BY_ERA.md` 为准，本文件只是交接快照。

## 二、已经完成的事

### 1. 抽样与清单

- `pipeline/sample.py`
  - 从 `JOURNALS_BY_ERA.md` 解析刊物与 OpenAlex source id
  - 按（刊, 年）向 OpenAlex 取候选
  - **有机过滤**：标题先匹配强正向词（合成、机理、结构、反应类型、化合物类别、人名反应），命不中再看学科标签，要求第一标签是 `Organic Chemistry`
  - 每格查询池 60 篇，只输出 10 篇
- 产物：
  - `exports/dois.txt`：纯文本，每行一个 DOI，共 **6486 条**
  - `exports/doi_organic_10.csv`：同批 DOI + 刊名、年份、卷期、标题
  - 覆盖 1900–1979、26 种刊、657 个「刊 × 年」格子；629 格满 10 篇，28 格不足

### 2. 取全文

- `pipeline/acquire.py`：走 OpenAlex / Semantic Scholar / Unpaywall / Europe PMC 的 OA 源自动下载
- `pipeline/batch_download.py`：读用户浏览器登录态（Netscape cookies / Cookie 头 / Copy as cURL），按出版社模板批量下 PDF
- `pipeline/browser_fetch.py`：Playwright 起真实 Chromium 过 Cloudflare，仅用于标注为免费的站点
- `exports/run_batch_serial.ps1`：本地 PowerShell 串行批下载，每批 200、批间冷却、断点续跑

### 3. 页级判图（省 MinerU 额度）

- `pipeline/page_scan.py` + 命令 `python -m pipeline pagescan --pdf <文件或目录> --out pagescan.csv`
  - 有文本层：行首图注（Fig./Figure/Scheme/Chart）直接判有图
  - 扫描页：150 dpi 渲染 → 二值化 → 连通域，块高超过字高 2.5 倍判有图
  - 实测 27–96 ms/页，7 页样本判定与原版一致

## 三、必须遵守的规则

1. **每格 10 篇**，只收有机方向；每篇只算 1 篇合格。
2. **不碰灰源**：ScanSci PDF 配置已是
   - `download_strategy=legal_only`
   - `scihub_enabled=false`
   - `auto_relogin=false`（会话过期不弹登录，直接判失败继续）
   - `cn_auto_login=false`
   - `cn_databases_enabled=false`
3. **MinerU 每天 1000 页**。先用 `pagescan` 筛页，只把有图页送解析。
4. **公库零数据**：PDF、裁剪图、清单、CSV 一律放 `.private/` 或 `exports/`（均已 gitignore），不进公库。
5. **密钥不落盘**：MinerU token 只从环境变量 `MINERU_API_KEY` 读，不写进任何文件、不提交。

## 四、下一步

1. 本地把 `dois.txt` 跑完，PDF 落到 `pdfs\`
2. **对照实验**（当前重点）：
   - 第一组：MinerU 全量转换，作为基准，记录每页是否含图
   - 第二组：`pagescan` 页级判定
   - 指标：页级 precision / recall，重点统计「漏掉了含结构式的页」
   - 输入：同一批 PDF；产出 `pagescan.csv` 与 `content_list.json`
3. 结构式图块级判别：区分「细线段 + 环」的结构式与直方图、照片。仍在本地做，不送 MinerU。
4. 筛过的页再送 MinerU，做图注解析与存图。

## 五、已知的坑

- PowerShell 5.1 读脚本必须是 **UTF-8 带 BOM + CRLF**，否则中文破坏语法
- `NativeCommandError` 多半只是工具把 INFO 日志写到 stderr，不是下载失败；判断成功看 `scansci_batches\done\*.done`
- `--no-lanes` 只是取消车道调度，**不等于取消机构级联**；渠道由 `download_strategy` 控制
- 沙箱出口 IP 会轮换，Cloudflare 会话不稳定；机构登录在用户本地，不在沙箱
- 早期（1900–1925）部分刊物在 OpenAlex 没有学科标签，靠标题关键词兜底，可能整格取空，按缺口记录，不要跨刊补

## 六、文件索引

| 路径 | 用途 |
|---|---|
| `exports/dois.txt` | 待下载 DOI 清单 |
| `exports/doi_organic_10.csv` | DOI 元数据 |
| `exports/run_batch_serial.ps1` | 本地串行批下载 |
| `pipeline/sample.py` | 抽样 + 有机过滤 |
| `pipeline/acquire.py` | OA 自动取全文 |
| `pipeline/batch_download.py` | 登录态批量取全文 |
| `pipeline/browser_fetch.py` | 浏览器过 Cloudflare 取件 |
| `pipeline/page_scan.py` | 页级判图 |
| `pipeline/cell.py` | 按格跑轮次、报警、缺口 |
| `pipeline/article.py` | 单篇处理（核验 → 选页 → MinerU → 存图） |
