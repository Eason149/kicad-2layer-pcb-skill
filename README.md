# kicad-2layer-pcb

让 AI 智能体用 KiCad **从零新画普通双面板**的 Agent Skill：需求 → 原理图 → 布局 → 布线 → 铺铜 → 检查 → 交付 KiCad 工程。

> **状态：实验性。** 已在 KiCad 10.0.6（Windows）上从零画通一块小板（见[示例](#示例)）。SES 导入、较大的板子和 macOS/Linux 尚未验证。投产前必须由工程师复核。

## 能做什么

- 根据文字需求，或你提供的原理图，新建双面板工程
- 原理图必须真实可编辑，经你确认后锁定，之后不得改动
- 不添加 AI、工具、作者、日期、Logo、网址等水印（脚本拦截常见情况，仍需看图）
- ERC/DRC error、未连线、PCB 与原理图不一致、重叠未清零时，不放入 `output/`
- 额外查 KiCad DRC 不报的重叠：同网络走线、过孔在焊盘上、丝印与过孔等
- 只交付工程文件，不含日志、报告、渲染图、Gerber

**不适用**：4 层及以上、HDI、盲埋孔、受控阻抗、特殊高速板。市电/高压、射频、天线、单面铝基板，或缺少参数的大电流设计会先停下来问你。

## 依赖

| 软件 | 用途 |
|---|---|
| 支持 Skill、能执行命令的智能体（如 Claude Code） | 运行本 skill |
| [KiCad 10](https://www.kicad.org/download/) | 原理图、PCB、ERC/DRC |
| [Freerouting](https://github.com/freerouting/freerouting/releases) | 自动布线（小板可不用） |
| Java | 仅 Freerouting 需要，版本以其发布说明为准 |
| Python 3.9+ | 运行检查脚本，无第三方依赖 |

## 安装

先克隆仓库并进入目录：

```text
git clone https://github.com/Eason149/kicad-2layer-pcb-skill.git
cd kicad-2layer-pcb-skill
```

Windows（PowerShell）：

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null; Copy-Item -Recurse -Force skills\kicad-2layer-pcb "$HOME\.claude\skills\"
```

macOS / Linux：

```bash
mkdir -p ~/.claude/skills && cp -R skills/kicad-2layer-pcb ~/.claude/skills/
```

只想在某个项目里用，就复制到该项目的 `.claude/skills/`。其他智能体请让它读取 `skills/kicad-2layer-pcb/SKILL.md`。

检查环境（在仓库目录，macOS/Linux 用 `python3`）：

```text
python skills/kicad-2layer-pcb/scripts/doctor.py
```

找不到软件时设置环境变量：`KICAD_CLI`、`KICAD_PYTHON`（KiCad 自带的 Python）、`FREEROUTING_JAR`。

## 使用

在智能体里直接说：

```text
用 kicad-2layer-pcb 画一块双面板：
12V 输入，5V/2A 输出，50×40 mm，四角 M3 安装孔，
接线端子输入，USB-A 输出。
```

流程：补问缺少的参数 → 画原理图并跑 ERC → **等你确认** → 锁定原理图 → 布局布线铺铜 → DRC 修错 → 交付。

```text
output/<工程名>/     通过全部检查的工程
未完成/<工程名>/     未通过的最好结果
```

## 示例

[examples/NE555_Flasher](examples/NE555_Flasher)：5V NE555 LED 闪烁板，40×30 mm，四角 M3 孔。ERC 和 DRC 0 错误 0 警告，未连线、一致性问题、重叠均为 0。

生成程序在 [examples/scripts](examples/scripts)，**专为这块板写**，其中的模拟退火布局和两层 A* 布线可作参考。不含 Freerouting。

已知不足：安装孔没有预留螺钉头禁铜区，布局还有优化空间，没有打样验证。

## 目录

```text
skills/kicad-2layer-pcb/
  SKILL.md                    流程与规则
  scripts/doctor.py           环境检查
  scripts/check_project.py    锁定原理图、检查、交付
  scripts/check_overlap.py    重叠检查（用 KiCad 自带 Python）
  scripts/kicad_adapter.py    DSN 导出、SES 导入、铺铜（用 KiCad 自带 Python）
  assets/sheet.kicad_wks      无水印图框
examples/                     示例工程与生成程序
```

## 已知限制

- 没有通用的布局、建板、布线程序，由智能体参考示例为每块板编写
- 丝印出板框、被器件遮挡、过孔互相重叠这几项检查未做反向测试
- 水印检查基于关键词和图片，可能漏判或误判
- DRC 通过不代表载流、散热、EMC、安规合格

## 许可证

[MIT](LICENSE)。KiCad、Freerouting 等第三方软件遵循各自的许可证。
