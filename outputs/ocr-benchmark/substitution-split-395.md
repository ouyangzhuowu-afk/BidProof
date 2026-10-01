# Substitution split of the 395 wrong characters (pending_audit)

Evidence note only. Recognition, the scoring formula, the thresholds, the ground truth, render scale, `max_side_len`, and the OCR model are unchanged. The greedy line matcher is unchanged. OCR was not re-run. No character was deleted. No letterhead was masked. OCR text was not copied into the ground truth. `outputs/pilot-ledger.csv` and `outputs/icp-outreach.csv` were not touched. T-005 stays blocked.

This split does not pass any gate. The underlying line CER stays **1302/29835 (4.36%) GATE_FAIL**. Key-field F1 stays **97.17%**. TEDS stays **95.80%**. Overall gate stays **GATE_FAIL**. `product_pass` stays false.

Scored pages: **54**. Denominator: **29835**. Line edits: **1302**. Substitution characters labeled: **395**. Piece sum: **395**. Remainder against 395: **0**.

## Exclusive rule

Each of the 395 substitution characters keeps the greedy pair that already produced it. Pairs are not changed, and there is no distance cutoff. Piece 1 compares the original line text, before _norm. Spaces and case stay. A character is piece 1 when its pair meets either structural test on that original text, and piece 2 when it meets neither. Test A: the OCR line the matcher chose is equal to a different ground-truth line on the same page. Test B: this ground-truth line is equal to a different OCR line on the same page, and that other OCR line is not paired to another ground-truth line with this same original text. The same-text guard stops a repeated line's own misread from being called a wrong line when the other copy was read exactly. If both tests match, the character is piece 1 once. Equality after deleting whitespace or lowercasing is not a whole-line mismatch. _norm (NFKC, all whitespace removed, English lowercased) is not the comparison. Piece 2 is every remaining substitution character.

Piece 1 is a whole ground-truth line paired to the wrong OCR line, judged on the original line text. Piece 2 is every remaining substitution character. A character is in one piece only. The same-text guard kept **0** characters in piece 2 on this set.

Audit's raw-text check is **208** whole-line mismatches and **187** true in-line misreads. This recount is **208** and **187**.

Letterhead substitutions already counted in the header bucket are not part of the 395. This walk excluded **15** of them, the same 15 paired letterhead substitutions as the seven-bucket table.

## Piece totals

| Piece | Characters |
|---|---:|
| 1. Whole line paired to the wrong OCR line | 208 |
| 2. True wrong characters inside a correctly paired line | 187 |
| Sum | 395 |
| Remainder against 395 | 0 |

208 + 187 = 395. Remainder against 395 is 0.

Next to audit's check: this recount is 208 and 187; audit's check is 208 and 187.

The other six bucket totals are unchanged: not in the text layer **47**, header or letterhead **286**, whole-line miss **151**, missing span inside a paired line **363**, extra inserted characters **28**, unaligned fragments **32**. The substitution bucket stays **395**. The line-edit total stays **1302**. None of these labels passes a gate.

## 1. Whole line paired to the wrong OCR line

Total: **208** characters.

Pages in this piece, sorted by character count. The column sums to the piece total.

| source file | page | characters in this piece |
|---|---:|---:|
| source4-zbtb.pdf | 5 | 53 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 47 |
| source2-shaanxi.pdf | 6 | 46 |
| pub-gx-info-center-compute-2026.pdf | 5 | 37 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 17 |
| pub-gx-ventilator-monitors.pdf | 5 | 5 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 3 |

## 2. True wrong characters inside a correctly paired line

Total: **187** characters.

Pages in this piece, sorted by character count. The column sums to the piece total.

| source file | page | characters in this piece |
|---|---:|---:|
| source4-zbtb.pdf | 5 | 52 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 37 |
| source4-zbtb.pdf | 4 | 33 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 13 |
| pub-gx-ventilator-monitors.pdf | 5 | 7 |
| pub-gx-info-center-compute-2026.pdf | 5 | 6 |
| pub-gx-qintang-flow-cytometer.pdf | 3 | 4 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 4 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 4 | 3 |
| pub-gx-minzu-ultrasound-2026.pdf | 6 | 3 |
| pub-gx-nonggang-patrol-2026.pdf | 9 | 3 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 3 |
| pub-gx-nanxishan-dr-mammo-2026.pdf | 2 | 2 |
| pub-gx-ventilator-monitors.pdf | 3 | 2 |
| pub-gx-ventilator-monitors.pdf | 4 | 2 |
| source2-shaanxi.pdf | 3 | 2 |
| source2-shaanxi.pdf | 6 | 2 |
| source4-zbtb.pdf | 9 | 2 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 3 | 1 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 51 | 1 |
| pub-gx-info-center-compute-2026.pdf | 2 | 1 |
| pub-gx-nanning-vascular-doppler.pdf | 16 | 1 |
| pub-gx-yibiatong-phase2-2026.pdf | 3 | 1 |
| source2-nanjing.pdf | 3 | 1 |
| source4-zbtb.pdf | 1 | 1 |

## Pairs that match only after spaces or case are folded

These pairs are whole-line mismatches under `_norm` and are not whole-line mismatches on the original text. There are **7** pairs and **116** characters. They are listed here, outside piece 1. They sit in piece 2. `␣` is a space.

### 1. `source4-zbtb.pdf` page 4 — 32 characters

Ground truth:

```
(2)␣投标人未被列入“中国政府采购网”“信用中国”“中国执行信息公开网”等系
```

OCR:

```
(5)投标人必须具有良好的商业信誉并按标书要求签署提供《公平竞争承诺书》;
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
(5)␣投标人必须具有良好的商业信誉并按标书要求签署提供《公平竞争承诺书》;␣
```

### 2. `source4-zbtb.pdf` page 5 — 17 characters

Ground truth:

```
(2)本项目的采购公告在中国政府采购网上发布。␣
```

OCR:

```
(3)本项目评标方法和标准:综合评分法,总分100分。
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
(3)本项目评标方法和标准:综合评分法,总分100␣分。␣
```

This ground-truth line equals this other OCR line only after `_norm`. That other line's original text is:

```
(2)本项目的采购公告在中国政府采购网上发布。
```

### 3. `source4-zbtb.pdf` page 5 — 18 characters

Ground truth:

```
(3)本项目评标方法和标准:综合评分法,总分100␣分。␣
```

OCR:

```
七、对本次招标提出询问,请按以下方式联系。
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
七、对本次招标提出询问,请按以下方式联系。␣
```

This ground-truth line equals this other OCR line only after `_norm`. That other line's original text is:

```
(3)本项目评标方法和标准:综合评分法,总分100分。
```

### 4. `pub-gx-youjiang-ultrasound.pdf` page 5 — 4 characters

Ground truth:

```
时间:2026␣年6␣月29␣日至2026␣年7␣月13␣日,每天上午00:00␣至11:59,下午
```

OCR:

```
开标时间:2026年7月27日09时00分
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
开标时间:2026␣年7␣月27␣日09␣时00␣分
```

### 5. `pub-gx-youjiang-ultrasound.pdf` page 6 — 29 characters

Ground truth:

```
的提交(投标人可登录“广西政府采购网”,依次进入“办事服务-下载专区”或者登录广
```

OCR:

```
(CA认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
(CA␣认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解
```

### 6. `pub-gx-youjiang-ultrasound.pdf` page 6 — 3 characters

Ground truth:

```
(CA␣认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解
```

OCR:

```
集,,)
```

This ground-truth line equals this other OCR line only after `_norm`. That other line's original text is:

```
(CA认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解
```

### 7. `pub-gx-minzu-ultrasound-2026.pdf` page 1 — 13 characters

Ground truth:

```
购云平台(https://www.gcy.zfcg.gxzf.gov.cn/)获取(下载)招标文件,并于2026␣年
```

OCR:

```
时30分(北京时间)前递交投标文件。
```

The normalized OCR line equals this other ground-truth line only after `_norm`. That other line's original text is:

```
时30␣分(北京时间)前递交投标文件。
```


## Audit example on source4-zbtb.pdf page 5

The procurement-notice ground-truth line is paired to the scoring-method OCR line. That pair has **17** substitution characters. Raw-text equality places them in **piece 2**.

Ground truth:

```
(2)本项目的采购公告在中国政府采购网上发布。␣
```

OCR:

```
(3)本项目评标方法和标准:综合评分法,总分100分。
```

The ground-truth scoring line keeps a space before 分 and a trailing space (`总分100␣分。␣`). The scoring OCR line is `总分100分`. Those original strings are not equal, so this pair is not piece 1.

On `pub-gx-youjiang-ultrasound.pdf` page 5, the 开标时间 line is paired to the 开标地点 line. That pair has **17** substitution characters in piece 1. This label does not join those lines. The matcher is unchanged.

## Boundary that stayed in piece 2

On the same page, `(3)点击左侧菜单“工作台”-“找项目”模块,找到将参与项目点击【参与】按` is paired to `【与】里目与““目,二“号业工,東类里()`.

That pair has **17** substitution characters. The OCR line is not equal to any other ground-truth line, and this ground-truth line is not equal to any other OCR line, so the rule leaves them in **piece 2**. The reading is heavily damaged. It is the paired line's own OCR string, not the scoring-method line.

Piece 2 also holds the pairs listed above that match another line only after spaces or case are folded. Those characters are not piece 1. The remaining piece-2 characters include short disagreements on lines that otherwise match, such as an em dash read as 一, 〔〕 read as parentheses, and o read as 0.

## Every substitution pair

One row per current greedy pair that contributes substitution characters. Letterhead pairs are omitted. The character column sums to 395. Strings are the original line text; `␣` is a space. `other line` is the original line that made a raw-text test true.

| piece | source file | page | chars | reason | ground truth | ocr line | other line |
|---|---|---:|---:|---|---|---|---|
| 2 | source2-nanjing.pdf | 3 | 1 | same line | 时10␣分—9␣时30␣分,地址:南京市公共资源交易中心一楼1232␣房间,联系 | 时10分一9时30分,地址:南京市公共资源交易中心一楼1232房间,联系 |  |
| 2 | source2-shaanxi.pdf | 3 | 2 | same line | (详见招标文件第四章〈招标内容及采购要求〉)。 | (详见招标文件第四章(招标内容及采购要求))。 |  |
| 2 | source2-shaanxi.pdf | 6 | 1 | same line | tp://www.sxggzyjy.cn/),选择“电子交易平台—陕西政府采购交易系统 | tp://www.sxggzyjy.cn/),选择“电子交易平台一陕西政府采购交易系统 |  |
| 2 | source2-shaanxi.pdf | 6 | 1 | same line | —企业端”进行登录,登录后选择“交易乙方”身份进入投标人界面后, | 一企业端”进行登录,登录后选择“交易乙方”身份进入投标人界面后, |  |
| 1 | source2-shaanxi.pdf | 6 | 8 | ocr equals another ground-truth line | 项目〗中点击“项目流程>交易文件下载”免费下载电子招标文件。 | 1、提交投标文件:电子投标文件一份。 | 1、提交投标文件:电子投标文件一份。 |
| 1 | source2-shaanxi.pdf | 6 | 14 | ocr equals another ground-truth line | (陕西省)网站〖首页·〉服务指南·〉下载专区〗中的《陕西省省级单 | 位电子化政府采购项目投标指南》。 | 位电子化政府采购项目投标指南》。 |
| 1 | source2-shaanxi.pdf | 6 | 9 | both tests | 位电子化政府采购项目投标指南》。 | 本项目不收取投标保证金。 | 本项目不收取投标保证金。 |
| 1 | source2-shaanxi.pdf | 6 | 6 | ground truth equals another ocr line | 本项目不收取投标保证金。 | 单“目,里中目 | 本项目不收取投标保证金。 |
| 1 | source2-shaanxi.pdf | 6 | 9 | both tests | 1、提交投标文件:电子投标文件一份。 | 3、开标时间:同提交投标文件截止时间 | 3、开标时间:同提交投标文件截止时间 |
| 2 | source4-zbtb.pdf | 1 | 1 | same line | 项目编号:MOC2024GK0809005␣ | 项目编号:M0C2024GK0809005 |  |
| 2 | source4-zbtb.pdf | 4 | 1 | same line | 项目编号:MOC2024GK0809005␣ | 项目编号:M0C2024GK0809005 |  |
| 2 | source4-zbtb.pdf | 4 | 32 | same line | (2)␣投标人未被列入“中国政府采购网”“信用中国”“中国执行信息公开网”等系 | (5)投标人必须具有良好的商业信誉并按标书要求签署提供《公平竞争承诺书》; |  |
| 1 | source4-zbtb.pdf | 5 | 36 | ocr equals another ground-truth line | 处选择“公采云代理机构公共服务平台-公采云交易运营平台DDDD99”进入支点国际电 | 钮,按提示操作完成报名即可下载本项目采购文件(未注册供应商须先进行“供应商注 | 钮,按提示操作完成报名即可下载本项目采购文件(未注册供应商须先进行“供应商注 |
| 2 | source4-zbtb.pdf | 5 | 17 | same line | (3)点击左侧菜单“工作台”-“找项目”模块,找到将参与项目点击【参与】按 | 【与】里目与““目,二“号业工,東类里() |  |
| 1 | source4-zbtb.pdf | 5 | 17 | ground truth equals another ocr line | 钮,按提示操作完成报名即可下载本项目采购文件(未注册供应商须先进行“供应商注 | (2)本项目的采购公告在中国政府采购网上发布。 | 钮,按提示操作完成报名即可下载本项目采购文件(未注册供应商须先进行“供应商注 |
| 2 | source4-zbtb.pdf | 5 | 17 | same line | (2)本项目的采购公告在中国政府采购网上发布。␣ | (3)本项目评标方法和标准:综合评分法,总分100分。 |  |
| 2 | source4-zbtb.pdf | 5 | 18 | same line | (3)本项目评标方法和标准:综合评分法,总分100␣分。␣ | 七、对本次招标提出询问,请按以下方式联系。 |  |
| 2 | source4-zbtb.pdf | 9 | 1 | same line | ␣开标一览表:为方便唱标,投标人须另备“开标一览表”1␣份并单独密封,␣ | ·开标一览表:为方便唱标,投标人须另备“开标一览表”1份并单独密封, |  |
| 2 | source4-zbtb.pdf | 9 | 1 | same line | ␣投标文件逾期送达的;␣ | ●投标文件逾期送达的; |  |
| 2 | pub-gx-daxin-ultrasound-anesthesia.pdf | 3 | 1 | same line | ▲气动电控呼吸机 | ■气动电控呼吸机 |  |
| 2 | pub-gx-daxin-ultrasound-anesthesia.pdf | 4 | 1 | same line | (https://www.gcy.zfcg.gxzf.gov.cn)-进入“项目采购”应用,在获取采购文件菜单中 | (https://www.gcy.zfcg.gxzf.gov.cn)一进入“项目采购”应用,在获取采购文件菜单中 |  |
| 2 | pub-gx-daxin-ultrasound-anesthesia.pdf | 4 | 2 | same line | 网)、ggzy.jgswj.gxzf.gov.cn/czggzy【全国公共资源交易平台】(广西.崇左)。 | 网)、ggzy.igswi.gxzf.gov.cn/czggzy【全国公共资源交易平台】(广西.崇左)。 |  |
| 2 | pub-gx-daxin-ultrasound-anesthesia.pdf | 51 | 1 | same line | 100␣万元×l.5␣%=1.5␣万元 | 100万元×1.5%=1.5万元 |  |
| 2 | pub-gx-nanning-vascular-doppler.pdf | 16 | 1 | same line | 3.16␣双胎心率重合报警(SOV); | 3.16双胎心率重合报警(S0V); |  |
| 2 | pub-gx-qintang-flow-cytometer.pdf | 3 | 1 | same line | 广西政府采购云平台“项目采购—获取采购文件”获取竞争性谈判采购文件,并于2026␣年6 | 广西政府采购云平台“项目采购一获取采购文件”获取竞争性谈判采购文件,并于2026年6 |  |
| 2 | pub-gx-qintang-flow-cytometer.pdf | 3 | 1 | same line | 最高限价:人民币伍拾玖万元整(¥590000.00␣元) | 最高限价:人民币伍拾玖万元整(Y590000.00元) |  |
| 2 | pub-gx-qintang-flow-cytometer.pdf | 3 | 1 | same line | 本项目是否接受联合体:是,否。 | 本项目是否接受联合体:口是,否。 |  |
| 2 | pub-gx-qintang-flow-cytometer.pdf | 3 | 1 | same line | 专门面向中小企业采购的项目(供应商应为中小微企业、监狱企业、残疾人 | 口专门面向中小企业采购的项目(供应商应为中小微企业、监狱企业、残疾人 |  |
| 2 | pub-gx-ventilator-monitors.pdf | 3 | 1 | same line | 预算总金额:人民币肆佰柒拾万元整(¥4700000.00) | 预算总金额:人民币肆佰柒拾万元整(Y4700000.00) |  |
| 2 | pub-gx-ventilator-monitors.pdf | 3 | 1 | same line | 最高限价:人民币肆佰贰拾伍万元整(¥4250000.00) | 最高限价:人民币肆佰贰拾伍万元整(Y4250000.00) |  |
| 2 | pub-gx-ventilator-monitors.pdf | 4 | 2 | same line | 3、根据财政部《关于在政府采购活动中查询及使用信用记录有关问题的通知》(财库〔2016〕 | 3、根据财政部《关于在政府采购活动中查询及使用信用记录有关问题的通知》(财库(2016) |  |
| 2 | pub-gx-ventilator-monitors.pdf | 5 | 3 | same line | 角—服务中心—帮助文档—项目采购): | 角一服务中心一帮助文档一项目采购): |  |
| 2 | pub-gx-ventilator-monitors.pdf | 5 | 1 | same line | https://service.zcygov.cn/#/knowledges/tree?tag=AG1DtGwBFdiHxlNdhY0r;及时完成CA␣申领 | https://service.zcygov.cn/#/knowledges/tree?tag=AG1DtGwBFdiHxlNdhYOr;及时完成CA␣申领 |  |
| 2 | pub-gx-ventilator-monitors.pdf | 5 | 2 | same line | 和绑定(见广西壮族自治区政府采购网—办事服务—下载专区-广西政府采购云平台CA␣证书办理操 | 和绑定(见广西壮族自治区政府采购网一办事服务一下载专区-广西政府采购云平台CA证书办理操 |  |
| 1 | pub-gx-ventilator-monitors.pdf | 5 | 5 | ocr equals another ground-truth line | 或拨打广西政府采购云平台服务热线95763␣获取热线服务帮助。 | 1.采购人信息 | 1.采购人信息 |
| 2 | pub-gx-ventilator-monitors.pdf | 5 | 1 | same line | 9、交易服务单位:钦州市公共资源交易中心;联系电话:［已隐去电话］。 | 9、交易服务单位:钦州市公共资源交易中心:联系电话:[已隐去电话]。 |  |
| 2 | pub-gx-youjiang-ultrasound.pdf | 5 | 4 | same line | 时间:2026␣年6␣月29␣日至2026␣年7␣月13␣日,每天上午00:00␣至11:59,下午 | 开标时间:2026年7月27日09时00分 |  |
| 1 | pub-gx-youjiang-ultrasound.pdf | 5 | 17 | ocr equals another ground-truth line | 开标时间:2026␣年7␣月27␣日09␣时00␣分 | 开标地点:广西政府采购云平台电子开标大厅 | 开标地点:广西政府采购云平台电子开标大厅 |
| 2 | pub-gx-youjiang-ultrasound.pdf | 6 | 29 | same line | 的提交(投标人可登录“广西政府采购网”,依次进入“办事服务-下载专区”或者登录广 | (CA认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解 |  |
| 2 | pub-gx-youjiang-ultrasound.pdf | 6 | 5 | same line | 如在操作过程中遇到问题或者需要技术支持,请致电客服热线:95763␣或者［已隐去电话］)。 | 如在操作过程中遇到问题或者需要技术支持,请致电客服热线:95763或者0771- |  |
| 2 | pub-gx-youjiang-ultrasound.pdf | 6 | 3 | same line | (CA␣认证)登录广西政府采购云平台电子开标大厅现场按规定时间对加密的投标文件进行解 | 集,,) |  |
| 2 | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 1 | same line | 9.␣ISO-E␣快换接口,显示屏幕:≥2.1cm×5.3cm; | 9.IS0-E快换接口,显示屏幕:≥2.1cm×5.3cm; |  |
| 2 | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 1 | same line | 1.线缆长4m,具有ISO␣-␣E␣快换接口。 | 1.线缆长4m,具有IS0-E快换接口。 |  |
| 2 | pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 1 | same line | 1.体积小,最大外径φ30mm,长130mm,轻质合金材料制造,可高温高压消 | 1.体积小,最大外径中30mm,长130mm,轻质合金材料制造,可高温高压消 |  |
| 2 | pub-gx-nanxishan-dr-mammo-2026.pdf | 2 | 2 | same line | 第七章其他文书、文件格式90 | 第七章其他文书、文件格式06 |  |
| 2 | pub-gx-minzu-ultrasound-2026.pdf | 1 | 13 | same line | 购云平台(https://www.gcy.zfcg.gxzf.gov.cn/)获取(下载)招标文件,并于2026␣年 | 时30分(北京时间)前递交投标文件。 |  |
| 1 | pub-gx-minzu-ultrasound-2026.pdf | 1 | 1 | ocr equals another ground-truth line | 时30␣分(北京时间)前递交投标文件。 | 招标文件。 | 招标文件。 |
| 1 | pub-gx-minzu-ultrasound-2026.pdf | 1 | 2 | both tests | 招标文件。 | 标项二 | 标项二 |
| 1 | pub-gx-minzu-ultrasound-2026.pdf | 2 | 34 | ocr equals another ground-truth line | 件;未注册的供应商可在广西政府采购云平台完成注册后再行报名。如在操作过程中遇到问题或需技术 | 2、地点:本项目将在广西政府采购云平台电子开标大厅解密、开标。本项目采用远程异地评标,评 | 2、地点:本项目将在广西政府采购云平台电子开标大厅解密、开标。本项目采用远程异地评标,评 |
| 1 | pub-gx-minzu-ultrasound-2026.pdf | 2 | 13 | ground truth equals another ocr line | 2、地点:本项目将在广西政府采购云平台电子开标大厅解密、开标。本项目采用远程异地评标,评 | 自本公告发布之日起5个工作日。 | 2、地点:本项目将在广西政府采购云平台电子开标大厅解密、开标。本项目采用远程异地评标,评 |
| 2 | pub-gx-minzu-ultrasound-2026.pdf | 6 | 2 | same line | 信部联企业〔2011〕300␣号),本次采购标的属于:工业。 | 信部联企业(2011)300号),本次采购标的属于:工业。 |  |
| 2 | pub-gx-minzu-ultrasound-2026.pdf | 6 | 1 | same line | 3.1.2␣支持OLED␣显示器≥22␣英寸,对比度≥22550:1,10bit␣色深无闪烁, | 3.1.2支持0LED显示器≥22英寸,对比度≥22550:1,10bit色深无闪烁, |  |
| 2 | pub-gx-info-center-compute-2026.pdf | 2 | 1 | same line | 简要规格描述或项目基本概况介绍、用途:为自治区级政务云提供不少于35PFLOPS(FP16)算 | 简要规格描述或项目基本概况介绍、用途:为自治区级政务云提供不少于35PFL0PS(FP16)算 |  |
| 1 | pub-gx-info-center-compute-2026.pdf | 5 | 28 | ocr equals another ground-truth line | 三、服务项目中伴随货物的,根据《财政部发展改革委生态环境部市场监管总局关于调整 | 四、服务项目中伴随的货物包含列入《网络关键设备和网络安全专用产品目录》的网络安全专 | 四、服务项目中伴随的货物包含列入《网络关键设备和网络安全专用产品目录》的网络安全专 |
| 2 | pub-gx-info-center-compute-2026.pdf | 5 | 2 | same line | 优化节能产品、环境标志产品政府采购执行机制的通知》(财库〔2019〕9␣号)和《关于印发节能产 | 优化节能产品、环境标志产品政府采购执行机制的通知》(财库(2019)9号)和《关于印发节能产 |  |
| 2 | pub-gx-info-center-compute-2026.pdf | 5 | 2 | same line | 品政府采购品目清单的通知》(财库〔2019〕19␣号)的规定,采购需求中的产品属于节能产品政府 | 品政府采购品目清单的通知》(财库(2019)19号)的规定,采购需求中的产品属于节能产品政府 |  |
| 1 | pub-gx-info-center-compute-2026.pdf | 5 | 4 | both tests | 四、服务项目中伴随的货物包含列入《网络关键设备和网络安全专用产品目录》的网络安全专 | 服务内容和要求 | 服务内容和要求 |
| 2 | pub-gx-info-center-compute-2026.pdf | 5 | 2 | same line | 知》(工信部联企业〔2011〕300␣号),本次采购标的属于:软件和信息技术服务业。 | 知》(工信部联企业(2011)300号),本次采购标的属于:软件和信息技术服务业。 |  |
| 1 | pub-gx-info-center-compute-2026.pdf | 5 | 5 | ground truth equals another ocr line | 服务内容和要求 | 1.1总体要求 | 服务内容和要求 |
| 2 | pub-gx-yibiatong-phase2-2026.pdf | 3 | 1 | same line | 本项目(是/否)接受联合体投标:□是/☑否。 | 本项目(是/否)接受联合体投标:口是/否。 |  |
| 2 | pub-gx-nonggang-patrol-2026.pdf | 9 | 2 | same line | 3、最低照度彩色不大于0.0002lx,黑白不大于0.0001lx。␣ | 3、最低照度彩色不大于0.00021x,黑白不大于0.00011x。 |  |
| 2 | pub-gx-nonggang-patrol-2026.pdf | 9 | 1 | same line | 16、同时支持DC12V␣和POE␣供电,且在不小于DC12V±30%范围内变化时可以正常工 | 16、同时支持DC12V和POE供电,且在不小于DC12V土30%范围内变化时可以正常工 |  |

## Page check against the substitution bucket

For every page that has substitution characters, the two pieces sum to that page's substitution count from the seven-bucket table. Pages with no substitutions are omitted. Those page sums total 395.

| source file | page | piece 1 | piece 2 | substitution |
|---|---:|---:|---:|---:|
| source4-zbtb.pdf | 5 | 53 | 52 | 105 |
| source2-shaanxi.pdf | 6 | 46 | 2 | 48 |
| pub-gx-minzu-ultrasound-2026.pdf | 2 | 47 | 0 | 47 |
| pub-gx-info-center-compute-2026.pdf | 5 | 37 | 6 | 43 |
| pub-gx-youjiang-ultrasound.pdf | 6 | 0 | 37 | 37 |
| source4-zbtb.pdf | 4 | 0 | 33 | 33 |
| pub-gx-youjiang-ultrasound.pdf | 5 | 17 | 4 | 21 |
| pub-gx-minzu-ultrasound-2026.pdf | 1 | 3 | 13 | 16 |
| pub-gx-ventilator-monitors.pdf | 5 | 5 | 7 | 12 |
| pub-gx-qintang-flow-cytometer.pdf | 3 | 0 | 4 | 4 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 4 | 0 | 3 | 3 |
| pub-gx-minzu-ultrasound-2026.pdf | 6 | 0 | 3 | 3 |
| pub-gx-nonggang-patrol-2026.pdf | 9 | 0 | 3 | 3 |
| pub-gx-tianlin-yuegui-devices-2026.pdf | 8 | 0 | 3 | 3 |
| pub-gx-nanxishan-dr-mammo-2026.pdf | 2 | 0 | 2 | 2 |
| pub-gx-ventilator-monitors.pdf | 3 | 0 | 2 | 2 |
| pub-gx-ventilator-monitors.pdf | 4 | 0 | 2 | 2 |
| source2-shaanxi.pdf | 3 | 0 | 2 | 2 |
| source4-zbtb.pdf | 9 | 0 | 2 | 2 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 3 | 0 | 1 | 1 |
| pub-gx-daxin-ultrasound-anesthesia.pdf | 51 | 0 | 1 | 1 |
| pub-gx-info-center-compute-2026.pdf | 2 | 0 | 1 | 1 |
| pub-gx-nanning-vascular-doppler.pdf | 16 | 0 | 1 | 1 |
| pub-gx-yibiatong-phase2-2026.pdf | 3 | 0 | 1 | 1 |
| source2-nanjing.pdf | 3 | 0 | 1 | 1 |
| source4-zbtb.pdf | 1 | 0 | 1 | 1 |

## Reproduce

```bash
uv run python -m work.eval.substitution_split
```

The command rewrites only `outputs/ocr-benchmark/substitution-split-395.md` and `.json`. It does not write a pilot or ICP ledger, it does not call OCR, and it does not change the seven-bucket files.

Generated at `2026-10-01T16:50:56.184717+00:00`. Status: `pending_audit`.
