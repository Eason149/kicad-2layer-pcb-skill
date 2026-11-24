---
name: kicad-2layer-pcb
description: 用 KiCad 从零新画普通双面板：根据需求画原理图、选件、布局、布线、铺铜、检查，交付含原理图的完整 KiCad 工程，无水印。用户说画电路板、画双面板/两层板、设计 PCB、根据需求或原理图新建 KiCad 工程时都应使用，即使没有提 skill 或 KiCad 接口。不用于 4 层及以上、HDI、受控阻抗或特殊高速板，也不用于只解释 PCB 概念。
---

# KiCad 新画普通双面板

目标：从用户需求新建一个 KiCad 10 工程，画好原理图和双面 PCB，能直接打开。
你做电路和布局决策，坐标由程序计算。直接猜走线坐标容易造成短路和间距错误。

每次都是**新画**：不要把目录里已有的 PCB 当作输入、模板、参考或测试数据，除非用户点名要用。用户直接提供原理图时，从第 4 步开始，原理图原样保留。

## 范围

只做 2 层、无特殊高速、无受控阻抗、无 HDI。超出就停止并说明依据。
市电/高压、射频、天线、单面铝基板，或大电流缺参数：先问用户。

## 要求

1. 原理图是交付物：真实可编辑的 `.kicad_sch`，有规范符号、真实引脚名、连线、电源符号和功能分区。不能只放方框加标签，也不能用图片代替。
2. 原理图经用户确认后锁定，画 PCB 时不再改。要改就先告诉用户，重新确认并锁定。
3. **无水印**：原理图、标题栏、丝印、铜层、阻焊、注释层都不添加 AI、工具、模型、作者、日期、Logo、网址。接口名、极性、1 脚、位号等功能性丝印可以有。KiCad 默认图框会打印 "KiCad E.D.A."，因此把 `assets/sheet.kicad_wks` 复制进工程，并在 `.kicad_pro` 的 `schematic` 和 `pcbnew` 中设置 `page_layout_descr_file`。
4. 按数据手册核对引脚和封装，不编造参数；未知的标 UNKNOWN，影响安全或正确性的停下问。
5. 不靠放宽规则、改网络、删器件、添加 DRC/ERC 排除来凑通过。
6. 没运行的检查要说"未验证"。

## 流程

`<skill>` 指本目录。

### 1. 环境

`python <skill>/scripts/doctor.py`

缺 KiCad 10、Java 或 Freerouting 时，列出版本、官方来源、大小，用户同意后再安装。命令参数以本机 `--help` 为准。
`scripts/kicad_adapter.py` 的 DSN 导出和铺铜已在 KiCad 10.0.6（Windows）实测，SES 导入未实测，首次使用先在副本上试。没装 Freerouting 时，小板可全部用 A* 布线。

### 2. 确认需求

问清：功能、输入电压、各路最大电流、接口、板子尺寸和安装孔、使用环境、指定器件、板厂工艺。只问缺的，一次问完；可合理默认的给出默认值。

### 3. 画原理图

1. 选件并逐脚核对符号、封装、电气类型。优先 KiCad 官方库；自建的放进工程。
2. 在 `work/<工程名>/` 生成 `.kicad_pro` 和 `.kicad_sch`，必要时分子图。
3. 检查去耦、复位、启动配置、上下拉、保护和未用引脚。
4. 跑 ERC，error 为 0；导出网表，逐网核对设计意图：
   `kicad-cli sch erc --severity-all --format json -o <临时>/erc.json <工程>.kicad_sch`
5. 渲染看图：无重叠、文字可读、连线清楚。给用户看并请其确认。

### 4. 锁定原理图

`python <skill>/scripts/check_project.py lock <work/工程名> <临时>/lock.json`

### 5. 建板与布局

- 用 KiCad 自带 Python 新建 2 层板。KiCad 10 没有可依赖的无界面"从原理图更新 PCB"命令，所以由网表加载封装、设置位号、值、符号路径，绑定焊盘网络。封装缺失就问，不用相似的代替。
- 按用户尺寸建板框。规则取板厂工艺；未给时默认线宽 0.20、间距 0.20、过孔 0.60/0.30、铜到板边 0.30 mm，最后告知。
- 布局顺序：安装孔、接口 → 主芯片 → 电源 → 去耦 → 晶振 → 模拟 → 其余。你给分组和约束，用模拟退火或力导向求坐标。
- 硬约束：courtyard 不重叠、不出板框、避开禁布区。软目标：线短、交叉少、去耦靠近电源脚、开关电源回路小、热源分散、接口朝板边。

### 6. 布线

把网络分成 GND、电源、大电流、时钟、模拟、差分、普通信号，按此顺序：大电流和电源 → 时钟/晶振/模拟/差分 → 锁定 → Freerouting 布其余 → 补线。

```text
<KiCad Python> <skill>/scripts/kicad_adapter.py export-dsn <board.kicad_pcb> <临时>/b.dsn
<KiCad Python> <skill>/scripts/kicad_adapter.py import-ses <board.kicad_pcb> <临时>/b.ses
```

电源线宽和过孔数按电流、铜厚、温升算。DSN 可能丢 `.kicad_dru` 和板边间距，要转成等价或更严格的约束。
关键线和补线需要算法时写两层网格 A*（间距膨胀、过孔代价、拆线重布），放 `workflow/` 复用，以 DRC 为准。
避免锐角和多余过孔；晶振下方不穿无关信号；尽量不切断地回流。

### 7. 铺铜

B.Cu 以 GND 为主，F.Cu 按需补；多个地不擅自短接；补地过孔、去孤岛、避免细颈。

`<KiCad Python> <skill>/scripts/kicad_adapter.py fill <board.kicad_pcb>`

### 8. 检查与修错

`kicad-cli pcb drc --refill-zones --schematic-parity --severity-all --format json -o <临时>/drc.json <board.kicad_pcb>`

`<KiCad Python> <skill>/scripts/check_overlap.py <board.kicad_pcb> <临时>/overlap.json`

两项都要跑。KiCad DRC 不报同网络走线重叠、过孔打在焊盘上、丝印被器件遮挡，`check_overlap.py` 专查这些，以及器件、丝印、过孔重叠。首次使用某套流程时做反向对照：在副本上故意断线、短路、重叠，确认检查能报出来。

顺序：短路 → 重叠 → 未连线 → 间距 → 板边 → 其他。每轮备份板文件、修一组、铺铜、重检；变差就恢复换策略。最多 8 轮，连续 3 轮无改善停止。
最后重新打开保存后的文件再检查，并看各层渲染图：极性丝印要正对自己的引脚、位号不被器件挡住、图面无水印。

### 9. 交付

```text
python <skill>/scripts/check_project.py deliver <work/工程名> output/<工程名> --lock <临时>/lock.json --erc <临时>/erc.json --drc <临时>/drc.json --overlap <临时>/overlap.json
```

脚本会检查：双层、无盲埋孔、原理图存在且与锁定时一致、无水印、库路径可移植、ERC/DRC error 0、DRC 项未被关闭或排除、重叠 0、未连线 0、PCB 与原理图一致。水印靠关键词和图片识别，不能替代看图。
未通过时放 `未完成/<工程名>`，不放 `output/`，列出剩余问题。

只交付工程文件夹：`.kicad_pro`、全部 `.kicad_sch`、`.kicad_pcb`、规则、库表、自建的符号/封装/3D 模型。自建库用 `${KIPRJMOD}`。不交付日志、报告、渲染图、BOM、Gerber、备份、缓存。
对话里用几行说明：是否通过、错误数、所用默认值、待确认项、路径，并提醒投产前人工复核载流、散热、EMC。
