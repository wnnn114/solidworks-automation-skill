---
name: solidworks-automation
description: 使用 SolidWorks 创建或修改参数化零件、装配体、原生动画和工程图，并验证生成的 CAD 文件。
metadata: { "openclaw": { "homepage": "https://github.com/wzyn20051216/solidworks-automation-skill", "os": ["win32"], "requires": { "anyBins": ["python", "py"] } } }
---

# SolidWorks 自动化技能

按请求选择工作流。完整项目通常先完成零件和装配，再用最终装配录制动画和出图。局部修改时先定位受影响的文件和引用，再复核受影响的成果。

| 工作流 | 参考资料与执行入口 |
| --- | --- |
| 零件建模 | [零件建模](references/part-modeling.md)、[孔槽](references/complex-hole-features.md)、[圆角与倒角](subskills/solidworks-fillet-chamfer-cnc/SKILL.md)、[螺纹孔](subskills/solidworks-threaded-holes/SKILL.md)。复用 `scripts/sw_part.py`、`scripts/sw_sketch_quality.py` 和 `scripts/sw_hole_features.py`。 |
| 装配体 | [装配与配合](references/assembly.md)。复用 `scripts/sw_assembly.py`，核对组件实例、Mate、自由度、运动范围和干涉。 |
| SolidWorks 原生动画 | [键帧动画与原生视频](subskills/solidworks-coursework/references/native-animation.md) 和 [Motion Study](references/motion-study.md)。先确定算例类型，再使用 `scripts/sw_motion.py` 或已核验的原生界面流程。 |
| 工程图 | [工程图子技能](subskills/solidworks-engineering-drawing/SKILL.md) 和 [原生图纸细节](subskills/solidworks-coursework/references/drawings.md)。复用 `scripts/sw_drawing.py` 和 `scripts/sw_drawing_package.py`。 |

多个阶段或模具机构需要衔接时，读取 [联合工作流](subskills/solidworks-coursework/SKILL.md)。

## 执行与验收

1. 在 Windows 上用 `python SKILL_DIR/scripts/sw_preflight.py --no-install` 检查本机 SolidWorks 和 Python COM 环境。核对目标版本、进程与当前文档，优先附着已有会话。运行目录以实际安装路径替换 `SKILL_DIR`。
2. 先读取图纸及用户提供的尺寸、材料、配合、动作和出图范围。关键输入缺失时，标出未定项。使用标准或设计补设值时保留来源和计算依据。
3. 复用 `scripts/sw_session.py`、`scripts/sw_connect.py` 及对应领域封装。COM 写操作串行，关闭本轮拥有的文档前先确认依赖。API 长度通常为米，明确区分草图、模型与装配坐标。未封装接口按目标版本查证，参见 [API 查证](references/api-lookup.md)。
4. 对照 `capabilities.yaml` 确认目标版本和能力等级。保存并重开原生文件，检查重建、引用和任务所需的尺寸、配合或版面。需要预览和证据时复用 [结果复核](references/review.md)，并将其与用户要求的交付文件区分开。

### 各阶段的验收重点

- **建模**：检查真实草图尺寸、约束、关联特征、材料和关键尺寸。用驱动尺寸和几何关系表达设计意图。
- **装配体**：检查零件引用、实际配合与必要的运动自由度。齿轮联动使用真实 Gear Mate。核对实际干涉检查结果及其覆盖范围。
- **原生动画**：保存重开后跳转到关键时间并读取显示变换，验收过程只读。如果需要视频，使用 SolidWorks 内置导出并检查完整解码与关键帧。动画键帧与需要物理结果的求解算例分别验收。
- **工程图**：检查图幅、投影法、图纸视图、尺寸关联与悬空状态，按要求加入剖视、标题栏和装配 BOM。导出 PDF 时目视核对版面和标注。
