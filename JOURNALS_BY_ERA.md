# 各时代主流有机化学期刊（抽样框 v1）

> 用途：定义「1950–1980 年有机化学结构式」数据集的抽样框。
> 这是抽样框，不是影响因子排名；入选依据是刊物性质（有机合成/结构式密集）、历史连续性、以及索引覆盖是否足以支撑随机抽样。
> 数据核对日期：2026-11-22；OpenAlex source id 与逐年作品数均由 API 实测，查询条件见文末。

---

## 一、分析单元（硬定义）

1. **单位是文章，不是 PDF 页，也不是期刊。**
2. 一篇入格文章必须**至少含 1 个结构式**（结构图、反应式、图表中的结构均可）。
3. 随机抽样必然抽到不含结构式的文章（物理有机、波谱、理论、综述），这类文章**不入格**，在同刊同年内重抽，不跨刊补。
4. 每格目标 **5 篇**通过验证的文章；**每轮抽 20 篇，最多 5 轮（最多 100 篇）**，用尽仍不足则记**缺口**（ADR-013 的口径）。
5. 两条核验互相独立：
   - `verify_status`：DOI/标题/卷期页是否与声称一致（`verified` / `mismatch` / `unreadable`）。
   - `has_structure`：是否检出结构式（`true` / `false`）；判不清的图 `legible=false` 排除，**不设 `unknown`**。

## 二、抽样框原则

- 按（**刊族**, 年, 有机子集）抽取，刊族 = 同一刊物历次改名/分册的 source id 集合。
- 只用同一刊族的其他 source id 或 Crossref 补抽；**不得用别的刊补格子**。
- 综合刊（JACS、Bull. Chem. Soc. Jpn.、Can. J. Chem.、J. Chem. Soc. 1950–1965）需要有机子集过滤；纯有机刊（JOC、Perkin 1、Tetrahedron Lett.、Synthesis 等）不需要。
- 索引覆盖不足的刊不进抽样框，而不是拿它硬凑。

---

## 三、1950s（1950–1959）

| 刊 | 本段有效年 | OpenAlex | 层级 | 备注 |
|---|---|---|---|---|
| J. Am. Chem. Soc. | 1950–1959 | `S111155417` | 核心 | 综合刊，需有机子集 |
| J. Org. Chem. | 1950–1959 | `S205050996` | 核心 | 纯有机 |
| J. Chem. Soc. (Resumed) | 1950–1959 | `S188789951` | 核心 | 综合刊，需有机子集 |
| Chemische Berichte | 1950–1959 | `S4210215837` | 核心 | 德语，有机为主 |
| Justus Liebigs Ann. Chem. | 1950–1959 | `S4210225590` | 核心 | 纯有机 |
| Helvetica Chimica Acta | 1950–1959 | `S181847678` | 核心 | 有机为主 |
| Angewandte Chemie | 1950–1959 | `S4210200754` | 核心 | 德语原版；英文版 1962 起为选译，去重用 |
| Bull. Chem. Soc. Jpn. | 1950–1959 | `S95305481` | 核心 | 综合刊，需有机子集 |
| Can. J. Chem. | 1951–1959 | `S9189650` | 核心 | 1950 索引缺失，见 §七 |
| Tetrahedron | 1957–1959 | `S205754296` | 核心 | 纯有机 |
| Tetrahedron Lett. | 1959 | `S133942674` | 核心 | 1959 创刊 |
| Monatsh. Chem. | 1950–1959 | `S98631280` | 次级 | 奥地利，有机为主 |
| Z. Naturforsch. B | 1950–1959 | `S104732370` | 次级 | 德语，有机/物化混合 |
| Rec. Trav. Chim. Pays-Bas | 1950–1959 | `S204931651` | 次级 | 荷兰，有机为主 |

## 四、1960s（1960–1969）

| 刊 | 本段有效年 | OpenAlex | 层级 | 备注 |
|---|---|---|---|---|
| J. Am. Chem. Soc. | 1960–1969 | `S111155417` | 核心 | 综合刊 |
| J. Org. Chem. | 1960–1969 | `S205050996` | 核心 | 纯有机 |
| J. Chem. Soc. (Resumed) | 1960–1965 | `S188789951` | 核心 | 1966 起拆刊 |
| J. Chem. Soc. C: Organic | 1966–1969 | `S4210199992` | 核心 | 有机分册 |
| J. Chem. Soc. B: Phys. Org. | 1966–1969 | `S4210172504` | 排除 | 物理有机，结构式稀少 |
| Chemical Communications | 1965–1968 | 未收录 | 核心但缺口 | OpenAlex 无该段，见 §七 |
| J. Chem. Soc. D: Chem. Commun. | 1969 | `S5406936830` | 核心 | 1969–1971 |
| Chemische Berichte | 1960–1969 | `S4210215837` | 核心 | |
| Justus Liebigs Ann. Chem. | 1960–1969 | `S4210225590` | 核心 | |
| Helvetica Chimica Acta | 1960–1969 | `S181847678` | 核心 | |
| Angewandte Chemie | 1960–1969 | `S4210200754` | 核心 | |
| Angew. Chem. Int. Ed. Engl. | 1962–1969 | `S4394735490` | 去重参考 | 英文选译，不重复入样 |
| Bull. Chem. Soc. Jpn. | 1960–1969 | `S95305481` | 核心 | |
| Can. J. Chem. | 1960–1969 | `S9189650` | 核心 | |
| Tetrahedron | 1960–1969 | `S205754296` | 核心 | |
| Tetrahedron Lett. | 1960–1969 | `S133942674` | 核心 | |
| J. Organomet. Chem. | 1963–1969 | `S108008259` | 专科 | 有机金属，结构式密集 |
| J. Heterocycl. Chem. | 1964–1969 | `S46134040` | 专科 | 杂环 |
| Carbohydr. Res. | 1965–1969 | `S34126442` | 专科 | 糖化学 |
| Synthesis | 1969 | `S197964166` | 专科 | 1969 创刊，合成方法 |
| Monatsh. Chem. / Z. Naturforsch. B / Rec. Trav. Chim. | 1960–1969 | 同上 | 次级 | |

## 五、1970s（1970–1979）

| 刊 | 本段有效年 | OpenAlex | 层级 | 备注 |
|---|---|---|---|---|
| J. Am. Chem. Soc. | 1970–1979 | `S111155417` | 核心 | |
| J. Org. Chem. | 1970–1979 | `S205050996` | 核心 | |
| J. Chem. Soc. C: Organic | 1970–1971 | `S4210199992` | 核心 | 1972 并入 Perkin 1 |
| J. Chem. Soc. D: Chem. Commun. | 1970–1971 | `S5406936830` | 核心 | |
| J. Chem. Soc., Perkin Trans. 1 | 1972–1979 | `S955628534` | 核心 | 纯有机合成 |
| J. Chem. Soc., Perkin Trans. 2 | 1972–1979 | `S4210187049` | 排除 | 物理有机 |
| J. Chem. Soc., Chem. Commun. | 1972–1979 | `S4210201432` | 核心 | |
| J. Chem. Soc., Dalton Trans. | 1972–1979 | `S4210210551` | 排除 | 无机/金属有机 |
| Chemische Berichte | 1970–1979 | `S4210215837` | 核心 | |
| Justus Liebigs Ann. Chem. | 1970–1978 | `S4210225590` | 核心 | 1979 起改刊，见下 |
| Liebigs Ann. Chem. | 1979 | `S117292697` | 核心 | 1979–1997 |
| Helvetica Chimica Acta | 1970–1979 | `S181847678` | 核心 | |
| Angewandte Chemie | 1970–1979 | `S4210200754` | 核心 | |
| Bull. Chem. Soc. Jpn. | 1970–1979 | `S95305481` | 核心 | |
| Can. J. Chem. | 1970–1979 | `S9189650` | 核心 | |
| Tetrahedron | 1970–1979 | `S205754296` | 核心 | |
| Tetrahedron Lett. | 1970–1979 | `S133942674` | 核心 | |
| Chemistry Letters | 1972–1979 | `S90825563` | 专科 | 日本化学会快报 |
| Synthesis | 1970–1979 | `S197964166` | 专科 | |
| J. Organomet. Chem. | 1970–1979 | `S108008259` | 专科 | |
| J. Heterocycl. Chem. | 1970–1979 | `S46134040` | 专科 | |
| Carbohydr. Res. | 1970–1979 | `S34126442` | 专科 | |
| Heterocycles | 1973–1979 | `S27298842` | 专科 | 1973 创刊 |
| Monatsh. Chem. / Z. Naturforsch. B / Rec. Trav. Chim. | 1970–1979 | 同上 | 次级 | |

---

## 六、刊族沿革映射（补抽用，禁止跨刊补格）

| 刊族 | 时间轴与 source id |
|---|---|
| J. Chem. Soc. 有机线 | 1950–1965 `S188789951`（综合）→ 1966–1971 `S4210199992`（C: Organic）→ 1972–1999 `S955628534`（Perkin Trans. 1） |
| Chemical Communications | 1965–1968 **OpenAlex 未收录** → 1969–1971 `S5406936830`（JCS D）→ 1972–1995 `S4210201432`（JCS Chem. Commun.） |
| Liebigs Annalen | 1950–1978 `S4210225590`（Justus Liebigs）→ 1979–1997 `S117292697`（Liebigs Ann. Chem.） |
| Angewandte Chemie | 德语原版 `S4210200754`（1947–）；英文选译 `S4394735490`（1962–）；两版同文，入样只用德语版避免重复 |
| 综合刊有机子集 | JACS、BCSJ、CJC、JCS 1950–1965 按栏目/关键词/concept 过滤；Perkin 1、JOC、Tet Lett、Tetrahedron、Synthesis 等本身即有机，无需过滤 |

## 七、已知缺口与处理

| 缺口 | 事实 | 处理 |
|---|---|---|
| Can. J. Chem. 1950 | OpenAlex 该年无记录（刊 1929 年即存在，属索引缺失） | 用 Crossref（ISSN 0008-4042）按年补 DOI，仍属同一刊 |
| Chemical Communications 1965–1968 | OpenAlex 无该段 source | 用 Crossref（ISSN 0009-241X）按年补 DOI |
| Liebigs 1979 起 | 改名为 Liebigs Ann. Chem. | 换 `S117292697`，属同刊族 |
| JCS 1966–1971 | 拆为 A/B/C 三册 | 只取 C（有机）；B 为物理有机，排除 |
| Gazz. Chim. Ital. | 1948–1985 仅 76 条记录 | 覆盖不足，不进框，不用别的刊补 |
| Bull. Soc. Chim. Fr. | 1945–1985 仅 202 条记录 | 同上 |
| Proc. Chem. Soc. | 1957–1964 仅 104 条，且内容与 JCS 重复 | 排除 |

## 八、与旧 8 刊名单的差异

旧名单：JACS、JOC、JCS (Resumed)、Perkin 1、Chem. Commun.、Tetrahedron Lett.、Bull. Chem. Soc. Jpn.、Can. J. Chem.。

问题不是这 8 本不正，而是：
1. 只绑单一 source id，没接刊族，1966–1971 的 JCS 有机分册、1965–1968 的 Chem. Commun.、1979 起的 Liebigs 全落空。
2. 缺德语区核心刊（Chem. Ber.、Liebigs、Helv.、Angew.），1950s/1960s 的欧洲画法样本会系统性缺失。
3. 缺 Tetrahedron 与 1970s 的 Synthesis/Chemistry Letters/Heterocycles，1970s 合成方法样本偏薄。
4. 没有「文章必须含结构式」的入格校验；旧 716 条已整体废弃删除，不保留、不复用。

## 九、抽样执行规则（下一步实现）

1. 每（刊族, 年）查询：`type:article`、`has_doi:true`、年份精确匹配；**每轮取 20 条**，用固定 seed 洗牌。
2. 逐条：取 PDF → `verify_status`（文本层优先；无文本层才用 Mineru 转，标题与 DOI 元数据语义比对）→ 判断有没有图（文本层图注 / 图形区块；扫描件无他法才整篇过一次 Mineru）→ 有图即进入结构式判定。
3. 结构式判定：有图注按图注内容判；无图注时按格子统计「有图但无图注」占比——**≤20% 可跳过，>20% 必须处理**（图像侧粗特征 / 视觉判定 / 人工复核），确认是结构式才收图；所有图注都明确不是结构式才作废。
4. 一轮 20 条筛完仍不足 **5 篇**，再抽下一轮；**最多 5 轮**；仍不足记缺口，不跨刊补。
4. 落盘：查询 URL、检索时间、source id、seed、逐条拒绝原因、缺口表。
5. 旧文件已整体删除；最终样本另出 `sample.csv`（只在私库）。

## 十、证据与可复现

- OpenAlex Sources API：`GET https://api.openalex.org/sources?search=<刊名>&select=id,display_name,issn_l,works_count`
- OpenAlex 逐年覆盖：`GET https://api.openalex.org/works?filter=primary_location.source.id:<id>,publication_year:1945-1985&group_by=publication_year`
- 核对日期：2026-11-22。索引覆盖会变，抽样前应重跑一次逐年覆盖检查并记录日期。
