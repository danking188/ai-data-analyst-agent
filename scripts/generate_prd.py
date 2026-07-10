from pathlib import Path
from datetime import date

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "docs" / "product"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / "AI_Data_Analyst_Agent_产品需求规格说明书_V1.0.docx"

BLUE = "1F4E79"
DARK = "17365D"
MID = "5B6573"
LIGHT = "EAF1F8"
LIGHTER = "F5F7FA"
GRAY = "D9E1E8"
WHITE = "FFFFFF"
RED = "9C0006"
GOLD = "7F6000"
GREEN = "1B5E20"
BLACK = "1F1F1F"


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=90, start=120, bottom=90, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for m, v in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def set_table_borders(table, color="B7C4D2", size=6):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), str(size))
        tag.set(qn("w:color"), color)


def set_table_geometry(table, widths_dxa, indent_dxa=120):
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths_dxa)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(indent_dxa))
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths_dxa[i]))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(widths_dxa[i] / 1440)
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


def add_field(paragraph, instruction, placeholder=""):
    run = paragraph.add_run()
    fld_char = OxmlElement("w:fldChar")
    fld_char.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    text = OxmlElement("w:t")
    text.text = placeholder
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([fld_char, instr, sep, text, end])


def set_run_font(run, size=None, bold=None, color=None, italic=None):
    run.font.name = "Calibri"
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.rFonts
    if r_fonts is None:
        r_fonts = OxmlElement("w:rFonts")
        r_pr.insert(0, r_fonts)
    r_fonts.set(qn("w:ascii"), "Calibri")
    r_fonts.set(qn("w:hAnsi"), "Calibri")
    r_fonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def configure_styles(doc):
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.color.rgb = RGBColor.from_string(BLACK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    heading_specs = {
        "Title": (25, DARK, 0, 8),
        "Subtitle": (13, MID, 0, 14),
        "Heading 1": (16, BLUE, 16, 8),
        "Heading 2": (13, BLUE, 12, 6),
        "Heading 3": (11.5, DARK, 8, 4),
        "Heading 4": (10.5, BLACK, 6, 3),
    }
    for name, (size, color, before, after) in heading_specs.items():
        style = styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(size)
        style.font.bold = name != "Subtitle"
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    if "Requirement ID" not in styles:
        s = styles.add_style("Requirement ID", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = styles["Heading 3"]
        s.font.name = "Calibri"
        s._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        s.font.size = Pt(11)
        s.font.bold = True
        s.font.color.rgb = RGBColor.from_string(DARK)
        s.paragraph_format.space_before = Pt(8)
        s.paragraph_format.space_after = Pt(3)
        s.paragraph_format.keep_with_next = True

    if "Requirement Detail" not in styles:
        s = styles.add_style("Requirement Detail", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        s.font.name = "Calibri"
        s._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        s.font.size = Pt(10)
        s.paragraph_format.left_indent = Inches(0.16)
        s.paragraph_format.space_after = Pt(3)
        s.paragraph_format.line_spacing = 1.08

    for style_name in ("List Bullet", "List Number"):
        style = styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(10.5)
        style.paragraph_format.left_indent = Inches(0.5)
        style.paragraph_format.first_line_indent = Inches(-0.25)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.167

    if "Table Text" not in styles:
        s = styles.add_style("Table Text", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        s.font.name = "Calibri"
        s._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        s.font.size = Pt(9)
        s.paragraph_format.space_after = Pt(2)
        s.paragraph_format.line_spacing = 1.05

    if "Caption Small" not in styles:
        s = styles.add_style("Caption Small", WD_STYLE_TYPE.PARAGRAPH)
        s.base_style = normal
        s.font.name = "Calibri"
        s._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        s.font.size = Pt(8.5)
        s.font.color.rgb = RGBColor.from_string(MID)
        s.paragraph_format.space_before = Pt(4)
        s.paragraph_format.space_after = Pt(4)


def add_doc_bullet(doc, text, level=0):
    style = "List Bullet" if level == 0 else "List Bullet 2"
    p = doc.add_paragraph(style=style)
    p.add_run(text)
    return p


def create_decimal_numbering(doc):
    numbering = doc.part.numbering_part.element
    abstract_ids = [int(x.get(qn("w:abstractNumId"))) for x in numbering.findall(qn("w:abstractNum"))]
    num_ids = [int(x.get(qn("w:numId"))) for x in numbering.findall(qn("w:num"))]
    abstract_id = max(abstract_ids, default=0) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "decimal")
    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(qn("w:val"), "%1.")
    suff = OxmlElement("w:suff")
    suff.set(qn("w:val"), "tab")
    p_pr = OxmlElement("w:pPr")
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), "720")
    tabs.append(tab)
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "720")
    ind.set(qn("w:hanging"), "360")
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "80")
    spacing.set(qn("w:line"), "280")
    spacing.set(qn("w:lineRule"), "auto")
    p_pr.extend([tabs, ind, spacing])
    lvl.extend([start, num_fmt, lvl_text, suff, p_pr])
    abstract.append(lvl)
    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    numbering.append(num)
    return num_id


def add_numbered_list(doc, items):
    num_id = create_decimal_numbering(doc)
    for text in items:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        num_pr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        num_id_el = OxmlElement("w:numId")
        num_id_el.set(qn("w:val"), str(num_id))
        num_pr.extend([ilvl, num_id_el])
        p._p.get_or_add_pPr().append(num_pr)
        p.add_run(text)


def add_label_para(doc, label, text, color=None):
    p = doc.add_paragraph(style="Requirement Detail")
    r = p.add_run(f"{label}：")
    set_run_font(r, size=10, bold=True, color=color or DARK)
    r = p.add_run(text)
    set_run_font(r, size=10)
    return p


def add_callout(doc, label, text, fill=LIGHT, color=DARK):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    set_table_borders(table, color=fill, size=4)
    set_repeat_table_header(table.rows[0])
    cell = table.cell(0, 0)
    set_cell_shading(cell, fill)
    p = cell.paragraphs[0]
    p.style = doc.styles["Normal"]
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(f"{label}  ")
    set_run_font(r, size=10.5, bold=True, color=color)
    r = p.add_run(text)
    set_run_font(r, size=10.5, color=BLACK)
    doc.add_paragraph().paragraph_format.space_after = Pt(1)


def add_table(doc, headers, rows, widths, font_size=9):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    set_table_geometry(table, widths)
    set_table_borders(table)
    hdr = table.rows[0]
    set_repeat_table_header(hdr)
    for i, h in enumerate(headers):
        set_cell_shading(hdr.cells[i], LIGHT)
        p = hdr.cells[i].paragraphs[0]
        p.style = doc.styles["Table Text"]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        r = p.add_run(str(h))
        set_run_font(r, size=font_size, bold=True, color=DARK)
    for row_data in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row_data):
            p = cells[i].paragraphs[0]
            p.style = doc.styles["Table Text"]
            if i == 0 and len(str(value)) <= 12:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(str(value))
            set_run_font(r, size=font_size)
    return table


def add_requirement(doc, rid, title, priority, description, acceptance, precondition=None, exceptions=None):
    p = doc.add_paragraph(style="Requirement ID")
    r = p.add_run(f"{rid}｜{title}")
    set_run_font(r, size=11, bold=True, color=DARK)
    r = p.add_run(f"   [{priority}]")
    set_run_font(r, size=9, bold=True, color=RED if priority == "P0" else GOLD if priority == "P1" else MID)
    add_label_para(doc, "需求描述", description)
    if precondition:
        add_label_para(doc, "前置/触发", precondition)
    if exceptions:
        add_label_para(doc, "异常与边界", exceptions)
    add_label_para(doc, "验收标准", acceptance, GREEN)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = paragraph.add_run("第 ")
    set_run_font(r, size=8.5, color=MID)
    add_field(paragraph, "PAGE", "1")
    r = paragraph.add_run(" 页")
    set_run_font(r, size=8.5, color=MID)


def configure_page(doc):
    for section in doc.sections:
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.top_margin = Inches(0.82)
        section.bottom_margin = Inches(0.78)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        section.header_distance = Inches(0.42)
        section.footer_distance = Inches(0.42)


def configure_headers(doc):
    for section in doc.sections:
        section.different_first_page_header_footer = True
        hp = section.header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        hp.paragraph_format.space_after = Pt(0)
        r = hp.add_run("AI DATA ANALYST AGENT  ·  产品需求规格说明书")
        set_run_font(r, size=8, bold=True, color=MID)
        fp = section.footer.paragraphs[0]
        add_page_number(fp)


def add_cover(doc):
    for _ in range(4):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(9)
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("产品需求规格说明书")
    set_run_font(r, size=12, bold=True, color=BLUE)
    p = doc.add_paragraph(style="Title")
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run("AI Data Analyst Agent")
    set_run_font(r, size=28, bold=True, color=DARK)
    p = doc.add_paragraph(style="Subtitle")
    r = p.add_run("证据优先、可审查、可复现的数据分析工作流生成器")
    set_run_font(r, size=14, color=MID)
    doc.add_paragraph()
    add_callout(
        doc,
        "产品定义",
        "用户上传 CSV、Excel 或 Parquet 后，系统生成一套可审查、可修改、可验证、可重新执行的数据分析工程。",
        fill=LIGHT,
    )
    for _ in range(5):
        doc.add_paragraph()
    add_table(
        doc,
        ["文档属性", "内容"],
        [
            ("文档版本", "V1.0"),
            ("文档状态", "评审稿"),
            ("适用范围", "MVP 产品、设计、研发、测试及项目验收"),
            ("编制日期", date.today().isoformat()),
            ("建议评审人", "产品负责人、技术负责人、数据科学负责人、安全负责人、测试负责人"),
        ],
        [1800, 7560],
        font_size=9.5,
    )
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def add_front_matter(doc):
    doc.add_heading("文档控制", level=1)
    add_table(
        doc,
        ["版本", "日期", "状态", "变更说明"],
        [("V1.0", date.today().isoformat(), "评审稿", "依据项目总设计形成完整 PRD/SRS，补齐功能编号、非功能指标、验收标准与风险边界。")],
        [900, 1500, 1200, 5760],
    )
    doc.add_heading("阅读说明", level=2)
    add_doc_bullet(doc, "“应”“必须”表示上线或验收不可缺失的强制需求；“宜”“建议”表示优化方向。")
    add_doc_bullet(doc, "P0 为 MVP 必须完成；P1 为重要增强；P2 为后续规划。")
    add_doc_bullet(doc, "标注“建议基线”的数值用于启动评审，不等同于最终 SLA；应在技术预研后冻结。")
    add_doc_bullet(doc, "本文件同时承担产品需求文档（PRD）和软件需求规格说明书（SRS）的作用。")
    doc.add_heading("目录", level=1)
    toc_rows = [
        ("1", "文档概述", "3"), ("2", "产品愿景与目标", "3"), ("3", "用户、角色与使用场景", "4"),
        ("4", "产品范围与优先级", "5"), ("5", "产品原则与业务规则", "5"), ("6", "端到端业务流程", "6"),
        ("7", "详细功能需求", "7"), ("8", "页面与交互需求", "17"), ("9", "数据与对象模型", "17"),
        ("10", "系统架构与接口边界", "18"), ("11", "非功能需求", "19"), ("12", "安全、隐私与合规要求", "19"),
        ("13", "日志、监控与审计", "20"), ("14", "验收策略与测试要求", "20"), ("15", "开发路线与里程碑", "21"),
        ("16", "风险、依赖与应对", "21"), ("17", "数据分析与产品埋点", "22"), ("18", "假设、待确认事项与决策记录", "22"),
        ("A", "需求追踪矩阵", "23"), ("B", "关键结构示例", "23"), ("C", "MVP 完成定义", "24"),
    ]
    add_table(doc, ["章节", "标题", "页码"], toc_rows, [850, 7410, 1100], font_size=7.7)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def add_sections(doc):
    doc.add_heading("1. 文档概述", level=1)
    doc.add_heading("1.1 编写目的", level=2)
    doc.add_paragraph(
        "本说明书用于统一 AI Data Analyst Agent 的业务目标、产品边界、交互规则、系统能力、质量属性和验收口径，"
        "作为产品设计、架构设计、研发拆分、测试设计、里程碑评审与上线验收的共同基线。"
    )
    doc.add_heading("1.2 项目背景", level=2)
    doc.add_paragraph(
        "通用“数据问答”产品往往只输出答案或图表，却缺少稳定的数据版本、可复现代码和结论证据。"
        "当数据发生变化、用户质疑数字来源或分析涉及泄露风险时，结果难以复查。本项目将 AI 的职责限制在理解、规划与解释，"
        "将所有数字计算交给确定性工具，并以 DatasetVersion、AnalysisRun、Artifact 和 Claim 建立完整证据链。"
    )
    doc.add_heading("1.3 术语与缩略语", level=2)
    add_table(
        doc,
        ["术语", "定义"],
        [
            ("DatasetVersion", "一次不可变的数据快照；记录来源、哈希、父版本、行列数和生成操作。"),
            ("AnalysisSpec", "经用户确认的正式分析任务定义，包括任务类型、目标、时间点、拆分策略与指标。"),
            ("Artifact", "由真实代码执行产生并持久化的结果，如统计量、图表、模型指标或数据表。"),
            ("Claim", "面向用户的结论；必须关联证据、数据版本、结论级别、限制条件和验证状态。"),
            ("AnalysisRun", "一次可追踪的分析执行，包含步骤、代码、参数、日志、产物和状态。"),
            ("EDA", "探索性数据分析（Exploratory Data Analysis）。"),
            ("数据泄露", "使用在预测时点不可获得、由目标直接派生或跨数据划分泄漏的信息。"),
            ("确定性工具", "参数相同且输入版本相同，能产生可验证结果的预实现代码工具。"),
        ],
        [1900, 7460],
    )

    doc.add_heading("2. 产品愿景与目标", level=1)
    add_callout(doc, "核心价值", "让用户获得的不只是一个答案，而是一份能够证明答案如何产生、可被别人检查并可在数据更新后重新执行的数据分析工程。")
    doc.add_heading("2.1 产品定位", level=2)
    doc.add_paragraph(
        "AI Data Analyst Agent 是面向表格数据的证据优先数据科学工作流生成器。它服务于缺少编程能力或需要快速验证数据的用户，"
        "提供数据接入、Schema 推断、质量检查、清洗审批、自动 EDA、基础建模、自然语言分析、证据验证与报告导出的一体化流程。"
    )
    doc.add_heading("2.2 业务目标", level=2)
    for text in [
        "降低非技术用户完成可信表格分析的门槛，同时保留专业分析所需的审查能力。",
        "让报告中的重要数字能够反向追踪到 Artifact、执行步骤、代码、参数和数据版本。",
        "将不可控的 LLM 自由生成收敛为结构化规划、受控工具调用和可验证叙述。",
        "形成可重复执行的数据分析资产，支持数据替换或更新后的重跑与差异比较。",
    ]:
        add_doc_bullet(doc, text)
    doc.add_heading("2.3 成功指标（建议基线）", level=2)
    add_table(
        doc,
        ["指标", "MVP 建议目标", "计算口径"],
        [
            ("端到端任务成功率", "≥ 85%", "固定 Demo 数据集从上传到报告导出无人工修复完成。"),
            ("数字可追溯率", "100%", "正式报告中数字性 Claim 均能解析到有效 Artifact。"),
            ("分析可重跑率", "≥ 95%", "在相同环境与输入版本下，AnalysisRun 可成功复现。"),
            ("高风险清洗误执行", "0", "未经用户确认不得执行破坏性或语义改变型清洗。"),
            ("字段幻觉率", "0", "发布内容不得引用 Schema 中不存在的字段。"),
            ("基础任务首份结果时间", "P50 ≤ 60 秒", "10 万行、30 列以内数据生成质量摘要和基础 EDA；硬件基线待确认。"),
        ],
        [2100, 1700, 5560],
    )

    doc.add_heading("3. 用户、角色与使用场景", level=1)
    doc.add_heading("3.1 目标用户", level=2)
    add_table(
        doc,
        ["角色", "主要目标", "关键痛点", "MVP 权限"],
        [
            ("业务分析用户", "快速理解 Excel、验证业务假设、导出报告", "不会编程；担心 AI 编造数字", "创建项目、上传、确认、分析、导出"),
            ("初级数据分析师", "加速清洗、EDA 与 baseline", "重复劳动多；分析过程难沉淀", "全部分析功能、查看代码与产物"),
            ("数据科学学习者", "学习规范的数据科学流程", "缺少正确拆分与验证意识", "查看计划、代码、限制与解释"),
            ("研究/产品/运营人员", "形成可复核的阶段性结论", "数据更新后难以复现", "重跑、比较版本、导出证据"),
            ("系统管理员", "维护运行环境与安全策略", "资源、失败任务、审计难管理", "查看全局运行与安全配置；不默认读取原始数据"),
        ],
        [1600, 2400, 2860, 2500],
        font_size=8.5,
    )
    doc.add_heading("3.2 核心用户旅程", level=2)
    add_numbered_list(doc, [
        "创建项目并上传 CSV、XLS/XLSX 或 Parquet。",
        "选择 Excel Sheet，查看加载摘要、Schema 建议和低置信度字段。",
        "审阅数据质量问题，查看影响范围与清洗前后预览。",
        "确认或拒绝清洗操作，生成新的不可变 DatasetVersion。",
        "描述分析问题，确认 AnalysisSpec、预测时点、目标字段和评价指标。",
        "运行自动 EDA、统计分析或 baseline 建模，并查看步骤进度。",
        "点击结论查看证据、代码、参数、数据版本与限制条件。",
        "导出 HTML 报告、Notebook、清洗数据与运行 Manifest；数据更新后重跑。",
    ])
    doc.add_heading("3.3 典型场景", level=2)
    add_doc_bullet(doc, "房价预测：识别邮编的类别语义、发现泄露字段、完成回归 baseline 与特征重要性。")
    add_doc_bullet(doc, "客户流失：处理类别不平衡、使用时间拆分、比较模型与 Dummy baseline、分析分组误差。")
    add_doc_bullet(doc, "电商订单：检查重复订单和金额对账，生成时间趋势，并保留清洗与计算证据。")

    doc.add_heading("4. 产品范围与优先级", level=1)
    doc.add_heading("4.1 MVP 范围（P0）", level=2)
    for text in [
        "CSV、XLS/XLSX、Parquet 上传与不可变 DatasetVersion。",
        "物理类型、语义类型和分析角色的三层 Schema 推断与用户覆盖。",
        "确定性数据质量检测、清洗建议、预览、审批、执行和回滚。",
        "自动 EDA、规则化图表、分类/回归 baseline、拆分策略和基本误差分析。",
        "Artifact、Claim、Claim Validator、HTML 报告、Notebook 和清洗数据导出。",
        "受控代码执行、脱敏、审计日志、错误恢复和基础可观测性。",
    ]:
        add_doc_bullet(doc, text)
    doc.add_heading("4.2 P1 增强", level=2)
    doc.add_paragraph("自然语言分析、最小上下文管理、独立验证器、DuckDB 查询、增强型泄露检测和项目历史比较。")
    doc.add_heading("4.3 明确不在 MVP 范围", level=2)
    for text in [
        "深度学习、完整 AutoML、自动超参数搜索、复杂时间序列、因果推断。",
        "多人实时协作、细粒度企业组织权限、云端数据仓库和多表关联。",
        "超大规模分布式计算、任意 Python 自由执行、外网访问。",
        "SHAP、PDF 报告、定时报告、本地模型与自定义报告模板。",
    ]:
        add_doc_bullet(doc, text)
    add_callout(doc, "范围控制", "P2 能力可保留扩展接口，但不得以牺牲 P0 的证据链、版本不可变和安全边界为代价提前实现。", fill="FFF4CE", color=GOLD)

    doc.add_heading("5. 产品原则与业务规则", level=1)
    doc.add_heading("5.1 核心业务规则", level=2)
    principles = [
        ("BR-01 AI 规划，代码执行", "AI 负责需求理解、计划、工具选择、解释和报告草稿；加载、清洗、统计、绘图、建模与指标均由代码执行。"),
        ("BR-02 原始数据永不覆盖", "原始版本只读；每次已确认转换产生新版本，并记录父版本和操作链。"),
        ("BR-03 结论必须绑定证据", "没有有效 Artifact 引用的数字性结论不得进入正式报告。"),
        ("BR-04 默认不自动修改", "系统可提出建议，但类型转换、删除、替换、填补等操作须经用户确认。"),
        ("BR-05 允许拒答", "字段不存在、样本量不足、质量过差、运行失败或证据不充分时必须停止并说明原因。"),
        ("BR-06 结构化输出优先", "分析计划、清洗方案与 Claim 必须通过 Pydantic/JSON Schema 校验。"),
        ("BR-07 最小充分上下文", "不得向模型发送完整 DataFrame、全部历史、无关字段和过期结果。"),
        ("BR-08 区分关联与因果", "除非满足预先定义的因果分析条件（MVP 不支持），不得将相关或预测解释为因果。"),
        ("BR-09 可重复执行", "运行必须保存输入版本、参数、工具版本、随机种子、代码/模板版本和依赖环境摘要。"),
        ("BR-10 发布前验证", "Claim Validator、字段校验、数字核对和敏感信息检查全部通过后方可发布。"),
    ]
    for title, body in principles:
        p = doc.add_paragraph(style="Heading 3")
        p.add_run(title)
        doc.add_paragraph(body)

    doc.add_heading("6. 端到端业务流程", level=1)
    doc.add_heading("6.1 主流程", level=2)
    add_numbered_list(doc, [
        "上传并校验文件，计算 SHA-256，保存原始只读文件。",
        "解析数据并转换为内部 Parquet，创建 raw 状态 DatasetVersion。",
        "运行字段画像、Schema 推断与质量检测。",
        "用户确认低置信度字段、行语义、目标和时间信息。",
        "系统生成清洗计划和影响预览；用户逐项或批量确认。",
        "确定性引擎执行清洗并校验不变量，创建 cleaned DatasetVersion。",
        "系统生成 EDA/分析计划；用户确认 AnalysisSpec。",
        "Agent 仅调用注册工具；每一步保存状态、参数、日志和 Artifact。",
        "Validator 生成并核验 Claim，未通过内容进入阻断或降级流程。",
        "用户审阅报告、证据和代码，导出或在新数据版本上重跑。",
    ])
    doc.add_heading("6.2 关键状态", level=2)
    add_table(
        doc,
        ["对象", "状态", "允许迁移"],
        [
            ("DatasetVersion", "creating / ready / failed / archived", "creating→ready|failed；ready→archived；版本内容不可变"),
            ("QualityIssue", "open / accepted / resolved / ignored", "open→accepted|ignored；accepted→resolved|open"),
            ("CleaningPlan", "draft / awaiting_approval / approved / rejected / executed / failed", "仅 approved 可执行；executed 后产生新版本"),
            ("AnalysisRun", "queued / running / blocked / succeeded / failed / cancelled", "失败可从可重试步骤复制为新 Run，不覆写旧 Run"),
            ("Claim", "draft / validation_failed / passed / published / withdrawn", "仅 passed 可 published；证据失效时 withdrawn"),
        ],
        [1800, 2800, 4760],
        font_size=8.5,
    )

    doc.add_heading("7. 详细功能需求", level=1)
    doc.add_heading("7.1 项目与数据接入", level=2)
    reqs = [
        ("FR-PRJ-001", "创建与管理项目", "P0", "用户可创建项目并维护名称、描述、默认时区、语言和业务背景；项目隔离数据、运行与报告。", "项目创建后生成唯一 project_id；必填校验生效；项目之间的对象不可串读。", "用户已进入系统。", "名称重复允许但 ID 唯一；删除采用归档，MVP 不物理删除。"),
        ("FR-ING-001", "上传文件", "P0", "支持 CSV、XLS、XLSX、Parquet；显示上传进度、文件名、大小、格式和校验结果。", "允许格式可正常进入解析；不支持格式被阻断并给出可操作提示。", "项目处于可编辑状态。", "空文件、损坏文件、加密 Excel、大小超限必须明确报错。"),
        ("FR-ING-002", "文件安全与哈希", "P0", "保存前校验扩展名与内容特征，计算 SHA-256；原文件只读保存并记录上传人、时间和大小。", "同一文件可被识别；元数据完整；业务流程不得改写原文件。", "上传完成。", "哈希失败时不得创建 ready 版本。"),
        ("FR-ING-003", "CSV 解析探测", "P0", "自动探测编码、分隔符、引号、表头与换行；低置信度时允许用户选择并预览。", "UTF-8、GBK 等常见编码及逗号/制表符场景可正确预览；用户配置被保存。", "文件为 CSV。", "乱码或列数不一致时显示问题行，不静默丢弃。"),
        ("FR-ING-004", "Excel Sheet 选择", "P0", "列出可见工作表、维度和预览；用户选择一个 Sheet 作为单表数据源。", "选中 Sheet 与 DatasetVersion 元数据一致；空 Sheet 不可继续。", "文件为 XLS/XLSX。", "合并单元格、公式错误和多行表头应提示潜在解析风险。"),
        ("FR-ING-005", "内部格式转换", "P0", "将可解析数据转换为内部 Parquet，并创建包含来源、哈希、行列数、Sheet 和父版本的 DatasetVersion。", "Parquet 可重新加载；记录数量与解析结果一致；失败不留下 ready 状态对象。", "解析参数已确认。", "转换中断可清理临时文件并保留错误日志。"),
        ("FR-ING-006", "数据预览", "P0", "提供分页、抽样的数据预览和行列规模，不向前端一次传输全表。", "首尾值、缺失和类型展示一致；超大文本被截断但可查看原值。", "DatasetVersion=ready。", "敏感字段在无明文权限时掩码显示。"),
        ("FR-ING-007", "数据版本浏览与比较", "P0", "展示版本链、状态、创建原因、父版本、哈希、行列变化与操作摘要。", "可从任一衍生版本追溯至原始版本；比较结果不修改任一版本。", "项目至少有一个版本。", "跨不同数据集的版本不得比较。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.2 Schema 推断与字段管理", level=2)
    reqs = [
        ("FR-SCH-001", "字段画像", "P0", "为每列计算非空数、唯一数、示例、分位数/频数、长度和解析成功率等确定性画像。", "画像与数据版本绑定；重复运行在相同输入上结果一致。", "DatasetVersion=ready。", "高基数文本仅保留受限样本与摘要，避免内存和隐私风险。"),
        ("FR-SCH-002", "物理类型推断", "P0", "识别整数、浮点、字符串、布尔、日期时间等存储类型，并记录候选、置信度和证据。", "测试集中的标准类型达到约定准确率；解析失败比例可查看。", "字段画像完成。", "混合类型不得被强制无损转换。"),
        ("FR-SCH-003", "语义类型推断", "P0", "识别数值、类别、日期、ID、文本、货币、百分比、有序类别和地理编码。规则打分为主，LLM 仅辅助语义判断。", "邮编、编码等不被默认当作连续数值；推断记录证据与模型/规则版本。", "物理类型和画像可用。", "低置信度字段标记为待确认，不自动定型。"),
        ("FR-SCH-004", "分析角色推断", "P0", "为字段建议 feature、target、entity_key、time、identifier、text、excluded 等分析角色。", "角色与语义类型兼容；ID 默认不作为连续特征。", "语义类型可用。", "同一任务仅允许一个主 target；冲突需用户处理。"),
        ("FR-SCH-005", "用户覆盖与持久化", "P0", "用户可修改语义类型、分析角色、日期格式、有序类别顺序和敏感标记。", "覆盖结果独立保存、可审计，并用于后续运行；不改写原始值。", "用户拥有编辑权限。", "不兼容转换必须先预览并作为清洗操作执行。"),
        ("FR-SCH-006", "Schema 变更影响分析", "P1", "用户变更字段定义时，系统提示受影响的质量规则、清洗计划、分析与报告。", "受影响对象被标为需重算或过期，不继续冒用旧证据。", "存在依赖该字段的对象。", "无法安全重用时强制新建 AnalysisRun。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.3 数据质量", level=2)
    reqs = [
        ("FR-QLT-001", "确定性质量扫描", "P0", "检测缺失/伪缺失、重复、主键重复、类型冲突、常量列、高基数、异常值、偏态、日期异常、数据断层、类别不一致和潜在泄露。", "不依赖 LLM 可生成结构化 QualityIssue；每项包含指标、严重程度、字段、规则版本和状态。", "Schema 初步可用。", "单项失败不得掩盖其他检测结果，应记录部分成功。"),
        ("FR-QLT-002", "严重程度与质量评分", "P0", "根据影响比例、字段角色、可逆性和下游风险计算 issue severity，并生成透明的质量评分。", "相同问题在相同规则版本下分级一致；用户可查看评分构成。", "质量扫描完成。", "不得用单一综合分掩盖高风险泄露或主键问题。"),
        ("FR-QLT-003", "问题详情与证据", "P0", "展示检测规则、事实指标、受影响样例、风险解释和建议操作；AI 解释不得改变事实值。", "详情中的数字来源于扫描 Artifact；示例行受权限和脱敏规则约束。", "QualityIssue 已创建。", "样例不足时明确标注，不补造示例。"),
        ("FR-QLT-004", "潜在数据泄露检测", "P0", "基于字段名称、与目标的确定性关系、时间可用性和衍生关系识别泄露候选。", "高风险候选在建模前必须确认排除或给出理由；记录用户决定。", "AnalysisSpec 含 target/预测时点时执行增强扫描。", "检测结果为风险提示，不声称覆盖所有泄露。"),
        ("FR-QLT-005", "质量问题处置状态", "P0", "用户可接受建议、忽略问题或恢复 open；忽略时需记录原因。", "状态迁移合法且有审计记录；忽略不等于已修复。", "QualityIssue=open。", "高风险问题忽略时在报告限制中持续展示。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.4 清洗计划与版本控制", level=2)
    reqs = [
        ("FR-CLN-001", "结构化清洗建议", "P0", "针对质量问题生成包含操作、字段、方法、参数、理由、影响范围、风险与可逆性的 CleaningPlan。", "计划通过 Schema 校验；只引用存在字段和白名单操作。", "质量问题与 Schema 可用。", "无安全方案时仅给出说明，不生成可执行操作。"),
        ("FR-CLN-002", "处理前后预览", "P0", "在执行前展示受影响行数、代表性样例、统计变化和可能副作用；预览使用与正式执行相同的确定性函数。", "用户可区分原值与建议值；预览与最终执行参数一致。", "计划=draft/awaiting_approval。", "样本预览不得被当作全量影响统计。"),
        ("FR-CLN-003", "逐项审批", "P0", "默认要求用户逐项批准、拒绝或编辑参数；批量批准仅适用于可逆且低风险操作。", "未经 approved 的计划不能调用执行器；决定记录用户、时间和理由。", "用户具有编辑权限。", "删除行、覆盖语义和高影响填补不得隐含批准。"),
        ("FR-CLN-004", "确定性执行与不变量", "P0", "执行已批准的纯函数操作，验证行数、主键、Schema、目标分布等配置化不变量。", "执行成功生成新 DatasetVersion 与操作日志；不变量失败则新版本标记 failed 且不作为当前版本。", "CleaningPlan=approved。", "部分步骤失败时不得提交半成品 ready 版本。"),
        ("FR-CLN-005", "回滚与分支", "P0", "用户可将任一 ready 版本设为当前版本，或从历史版本创建新的清洗分支。", "回滚不删除后续版本；版本关系保持可追溯。", "目标版本存在且可读取。", "已有运行仍绑定原版本，不随当前版本指针变化。"),
        ("FR-CLN-006", "变更差异", "P0", "提供行列规模、缺失、分布、值替换、删除和类型变化摘要，并可查看对应代码。", "差异由两个明确版本计算；大数据采用聚合/抽样并标注口径。", "至少两个同源版本。", "不能精确逐行对齐时不展示伪精确的行级差异。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.5 分析目标与计划", level=2)
    reqs = [
        ("FR-ANA-001", "行语义确认", "P0", "分析前确认每行代表的实体/事件，以及 entity_key、time_column 和数据粒度。", "关键信息写入 AnalysisSpec；不明确时系统阻断高风险建模。", "当前版本可用。", "重复实体或多粒度混合时提示聚合/拆分需求。"),
        ("FR-ANA-002", "任务类型识别", "P0", "将用户意图映射为描述分析、比较、统计检验、二分类、多分类或回归；MVP 外任务应降级或拒绝。", "任务类型与 target 语义一致；用户可修改并确认。", "用户提出问题或选择向导。", "禁止将观察性比较自动宣称为因果分析。"),
        ("FR-ANA-003", "AnalysisSpec 确认", "P0", "展示并确认 target、特征范围、预测时点、拆分策略、指标、排除字段、分组字段和随机种子。", "确认后生成版本化 AnalysisSpec；后续参数变化创建新修订版。", "任务类型已识别。", "缺失 target、时间逻辑冲突或指标不兼容时不得启动。"),
        ("FR-ANA-004", "分析计划预览", "P0", "Agent 生成结构化步骤，列出工具、输入、输出和依赖；执行前进行字段、工具和参数校验。", "计划只能调用 Tool Registry 中的工具；无效步骤被阻断并返回可修正错误。", "AnalysisSpec 已确认。", "LLM 输出解析失败时可重试一次，仍失败则转人工修改。"),
        ("FR-ANA-005", "取消与重试", "P1", "用户可取消排队/运行任务；失败后可从可重试步骤复制参数并创建新 Run。", "旧 Run 和日志保留；新 Run 具有独立 ID 和来源关系。", "Run 未结束或已失败。", "涉及非幂等写入的步骤不得原地重试。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.6 自动 EDA、图表与自然语言分析", level=2)
    reqs = [
        ("FR-EDA-001", "基础自动 EDA", "P0", "生成数值分布、类别频数、缺失分布、相关性、时间趋势、分组统计和异常值摘要。", "每项结果保存为 Artifact 并绑定版本；无适用字段时跳过并说明。", "DatasetVersion ready 且 Schema 已确认。", "高基数或极端规模采用 Top-N、抽样或聚合，并标注口径。"),
        ("FR-EDA-002", "目标驱动 EDA", "P0", "围绕目标生成特征关系、群体差异、缺失状态关系、时间变化、潜在泄露和可检验假设。", "仅执行与任务类型兼容的分析；多重比较等限制进入解释。", "AnalysisSpec 含 target。", "样本不足或类别稀疏时不输出不稳定结论。"),
        ("FR-EDA-003", "Chart Planner", "P0", "依据字段类型、数据量和分析意图从白名单图表中选择类型、聚合、排序和编码；LLM 不直接拼装任意绘图代码。", "图表配置通过 Schema；轴字段存在；默认避免误导性截断与双轴。", "已有待可视化 Artifact。", "数据超限时先聚合或抽样，不将全量明细发送浏览器。"),
        ("FR-EDA-004", "图表审查与导出", "P0", "图表可查看标题、口径、数据版本、筛选、生成参数，并导出图片和底层数据表。", "导出内容与页面显示同源；包含版本和时间戳。", "图表 Artifact 有效。", "敏感明细不得通过底层数据导出绕过权限。"),
        ("FR-NLQ-001", "自然语言提问", "P1", "用户可围绕当前数据版本提问；系统解析意图、选择字段、生成计划、调用工具并返回证据化回答。", "回答中的数字均来自 Artifact；不存在字段或证据不足时明确拒答。", "当前数据版本和 Schema 可用。", "问题歧义影响结论时必须请求用户澄清，不自行猜测关键业务定义。"),
        ("FR-NLQ-002", "追问与上下文", "P1", "保留最近 6–10 轮原文、长期结构化摘要、当前 AnalysisSpec 和用户决定，按需构建最小上下文。", "追问可引用当前任务；切换版本后旧结果被标记；完整数据不进入模型上下文。", "存在会话。", "摘要失败时退化为较短窗口，不扩大数据泄露范围。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.7 Baseline 建模", level=2)
    reqs = [
        ("FR-MDL-001", "支持的建模任务", "P0", "支持二分类、多分类和回归；分类提供 Dummy、LogisticRegression、HistGradientBoosting，回归提供 Dummy、Ridge、HistGradientBoostingRegressor。", "每个任务至少运行 Dummy baseline；不支持的 target 类型被阻断。", "AnalysisSpec 合法。", "样本量不足或单一类别不得训练。"),
        ("FR-MDL-002", "数据拆分", "P0", "支持随机、分层、时间和 Group 拆分；根据时点与实体结构给出建议，用户确认。", "测试集不参与预处理拟合；时间拆分不使用未来训练过去；Group 不跨集合。", "行语义、target 和相关字段已确认。", "无法满足最小样本或类别覆盖时停止并解释。"),
        ("FR-MDL-003", "预处理 Pipeline", "P0", "缺失处理、编码、缩放与模型封装在 sklearn Pipeline 中，仅在训练集拟合。", "运行记录包含 Pipeline 配置；验证集/测试集变换不泄露统计量。", "拆分完成。", "未知类别采用明确策略，不静默丢行。"),
        ("FR-MDL-004", "模型评估", "P0", "分类至少支持 PR-AUC、ROC-AUC、F1、召回率、精确率和混淆矩阵的适用子集；回归支持 MAE、RMSE、R²和残差。", "指标来自保留集并与 Dummy 对比；阈值与正类定义可见。", "模型训练成功。", "不平衡分类默认突出 PR-AUC/召回，不仅报告准确率。"),
        ("FR-MDL-005", "模型解释与误差分析", "P0", "提供线性系数或置换重要性、分组误差、典型错误和限制条件。", "解释方法与模型兼容；明确相关/预测解释不等于因果。", "评估 Artifact 有效。", "高基数或隐私字段的样例需脱敏；不输出个体决策建议。"),
        ("FR-MDL-006", "模型使用限制", "P0", "报告训练数据范围、适用人群、时间范围、泄露风险、公平性观察、性能不确定性和禁止用途。", "限制作为报告必填区块；存在高风险未处理问题时阻断“可用于决策”的表述。", "准备发布模型报告。", "MVP 不部署在线预测服务。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.8 证据、结论与验证", level=2)
    reqs = [
        ("FR-EVD-001", "Artifact 持久化", "P0", "统计量、表格、图表、模型、指标和运行日志均保存为带类型、生产者、参数、版本和校验信息的 Artifact。", "Artifact ID 唯一；可从 Run 和 DatasetVersion 双向检索；文件完整性可校验。", "确定性工具成功执行。", "写入失败时对应步骤不得标记 succeeded。"),
        ("FR-EVD-002", "Claim 分级", "P0", "Claim 分为直接事实、统计推断、模型解释、业务推测、行动建议五级，并记录文本、证据、版本、限制和验证状态。", "所有 Claim 具有级别；数字性 Claim 至少关联一个 Artifact。", "生成叙述。", "业务推测和建议不得伪装为统计事实。"),
        ("FR-EVD-003", "数字注入与核对", "P0", "正文数字由程序从 Artifact 模板化注入；Validator 重新解析并核对数值、单位、方向和版本。", "不存在未验证数字；舍入规则一致；差值和百分点表述正确。", "Claim 草稿和 Artifact 可用。", "核对失败则 validation_failed，不进入正式报告。"),
        ("FR-EVD-004", "字段与证据有效性验证", "P0", "验证 Claim 字段存在、Artifact 属于同一数据版本、依赖步骤成功、证据未过期。", "跨版本混用被阻断或显式标注比较关系。", "Claim 准备发布。", "当前版本切换不会自动改写历史 Claim 的绑定。"),
        ("FR-EVD-005", "证据查看器", "P0", "用户可从结论展开查看原始计算结果、图表/表格、工具、参数、代码片段、运行日志摘要和数据版本。", "从报告到证据的导航不超过两次操作；无权限内容按规则脱敏。", "Claim 已生成。", "代码或日志含密钥/路径时先清理再展示。"),
        ("FR-EVD-006", "拒答与降级", "P0", "证据不足、质量过差、样本不足、统计假设不满足或执行失败时，返回明确原因、已完成事实和下一步建议。", "不得用模糊措辞掩盖失败；拒答事件可审计。", "验证器或执行器触发阻断条件。", "可降级为描述统计时需明确说明范围变化。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.9 报告、Notebook 与重跑", level=2)
    reqs = [
        ("FR-RPT-001", "报告编排", "P0", "生成含执行摘要、数据说明、质量、方法、结果、证据、限制和附录的 HTML 报告；用户可选择/排序已通过 Claim。", "正式区块仅包含 passed Claim；目录和证据链接有效。", "存在有效 Artifact/Claim。", "草稿内容需显式标识，不与正式结论混排。"),
        ("FR-RPT-002", "Notebook 导出", "P0", "导出按步骤组织的 Notebook，包含加载、清洗、分析、图表、建模和验证代码，以及必要的参数与说明。", "在受支持环境中可从指定输入重跑；不得包含密钥和不可访问的绝对路径。", "AnalysisRun=succeeded。", "受限执行生成的内部代码若不可导出，应提供等价可读代码。"),
        ("FR-RPT-003", "清洗数据与 Manifest 导出", "P0", "可导出当前清洗数据和机器可读 Manifest，记录数据哈希、版本链、步骤、参数、Artifact、依赖和环境摘要。", "导出包中文件校验通过；用户能识别所对应版本。", "用户有导出权限。", "敏感字段导出遵循项目权限与掩码策略。"),
        ("FR-RPT-004", "重新执行", "P0", "用户可在相同或新数据版本上复制 AnalysisSpec 并重跑；系统先检查 Schema 兼容性。", "新 Run 独立保存；字段缺失或类型变化时生成兼容性报告并阻断不安全步骤。", "已有可重跑的 AnalysisRun。", "不得覆写历史结果；随机过程固定种子。"),
        ("FR-RPT-005", "运行比较", "P1", "比较两个 Run 的输入版本、参数、质量、关键指标、Claim 和失败步骤。", "差异来源可追溯；不将不同口径指标直接比较。", "两个 Run 属于同一项目且有兼容任务。", "不可比项标注原因。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("7.10 系统管理与运行", level=2)
    reqs = [
        ("FR-SYS-001", "Tool Registry", "P0", "维护工具名称、版本、输入/输出 Schema、权限、资源限制和适用任务；Agent 只能调用注册且启用的工具。", "不存在任意工具名调用；参数校验失败不进入执行器。", "系统已加载工具配置。", "工具下线后历史 Run 仍保留版本信息。"),
        ("FR-SYS-002", "任务队列与进度", "P0", "长任务异步执行，显示排队、步骤、耗时和可取消状态；刷新页面不丢失进度。", "状态与后端一致；完成或失败均有终态和时间。", "用户启动执行。", "Worker 重启后可识别遗留 running 并恢复或标记失败。"),
        ("FR-SYS-003", "错误信息与恢复", "P0", "向用户展示可理解错误、影响范围、建议动作和错误编号；技术堆栈仅进入受限日志。", "错误可关联 Run/Step；常见解析、资源、Schema 错误有针对性提示。", "发生异常。", "不得暴露密钥、系统路径或其他用户数据。"),
        ("FR-SYS-004", "配置与密钥", "P0", "LLM、存储、执行器和资源限制通过环境/配置管理；密钥不写入数据库、日志、报告或 Notebook。", "密钥扫描无明文；缺失配置阻断相关功能并可诊断。", "系统启动或调用外部提供商。", "MVP 可配置为无 LLM 模式，核心确定性分析仍可运行。"),
    ]
    for r in reqs:
        add_requirement(doc, *r)

    doc.add_heading("8. 页面与交互需求", level=1)
    pages = [
        ("Overview", "当前项目、当前数据版本、质量评分、最近运行、核心发现、待确认事项", "从待办进入具体问题；切换当前版本；查看最近运行"),
        ("Data", "上传、Sheet 选择、预览、Schema、类型覆盖、版本链和差异", "上传与解析、确认低置信度字段、版本回滚/分支"),
        ("Quality", "问题筛选、指标、样例、风险解释、建议、清洗预览和审批", "逐项确认、忽略并填写原因、批量低风险审批"),
        ("Explore", "自动 EDA、图表、分组统计、自然语言提问和分析计划", "切换证据口径、导出图表数据、确认计划"),
        ("Model", "目标、特征、拆分、baseline、评估、误差、解释和限制", "确认 AnalysisSpec、运行模型、比较 Dummy"),
        ("Report", "结论编辑、证据抽屉、代码、限制、导出和重跑", "选择 passed Claim、查看证据、导出 HTML/Notebook"),
    ]
    add_table(doc, ["页面", "核心内容", "关键操作"], pages, [1300, 4460, 3600], font_size=8.5)
    doc.add_heading("8.1 通用交互规则", level=2)
    for text in [
        "任何会改变数据或分析定义的操作均显示影响范围，并要求显式确认。",
        "页面顶部持续显示当前项目、数据集和版本；历史证据展示其原绑定版本。",
        "风险、警告、失败和信息提示使用不同视觉语义，不能只依赖颜色。",
        "表格支持分页、搜索、筛选与列说明；默认不一次渲染全量数据。",
        "耗时操作提供进度、当前步骤、预计不可用时的说明、取消和错误恢复入口。",
        "证据、代码和日志采用渐进披露，避免非技术用户被实现细节淹没。",
    ]:
        add_doc_bullet(doc, text)

    doc.add_heading("9. 数据与对象模型", level=1)
    doc.add_paragraph("核心关系：Project → Dataset → DatasetVersion → ColumnSchema；项目同时包含 QualityIssue、CleaningPlan、AnalysisSpec、AnalysisRun、Artifact、Claim、ValidationResult、UserDecision 与 ConversationSummary。")
    add_table(
        doc,
        ["实体", "关键字段", "关键约束"],
        [
            ("Project", "project_id, name, owner_id, timezone, status", "项目为数据隔离边界；删除为归档。"),
            ("Dataset", "dataset_id, project_id, name, source_type", "一个逻辑数据集可拥有多个版本。"),
            ("DatasetVersion", "version_id, hash, storage_path, parent_id, status, row_count", "ready 后不可修改；父版本可空且仅 raw 为空。"),
            ("ColumnSchema", "version_id, column, physical_type, semantic_type, role, confidence", "列名在版本内唯一；覆盖记录来源。"),
            ("QualityIssue", "issue_id, version_id, type, severity, metrics, status", "metrics 必须结构化；状态迁移受控。"),
            ("CleaningPlan", "plan_id, source_version, operations, approval, result_version", "仅 approved 可执行；成功后 result_version 必填。"),
            ("AnalysisSpec", "spec_id, revision, task, target, split, metrics", "不可原地改写已被 Run 引用的修订。"),
            ("AnalysisRun", "run_id, version_id, spec_id, status, seed, environment", "绑定单一输入版本；步骤与终态可审计。"),
            ("Artifact", "artifact_id, run_id, type, producer, uri, checksum, metadata", "文件或结果必须可校验；与 Run 同生命周期归档。"),
            ("Claim", "claim_id, text, level, evidence_ids, version_id, limitations, status", "published 前 validation_status=passed。"),
            ("UserDecision", "decision_id, user_id, object_type/id, action, reason, timestamp", "确认、忽略、覆盖等关键决定不可静默覆盖。"),
        ],
        [1500, 4080, 3780],
        font_size=8.1,
    )
    doc.add_heading("9.1 数据保留与过期", level=2)
    doc.add_paragraph(
        "MVP 默认不自动删除项目数据。管理员应可配置保留期；达到保留期后先归档、再按审批流程清除。"
        "任何删除均需覆盖元数据、Parquet、Artifact、报告、临时文件和缓存，并保留不含敏感内容的删除审计。"
    )

    doc.add_heading("10. 系统架构与接口边界", level=1)
    doc.add_paragraph(
        "建议采用 Streamlit UI + 应用服务层 + Agent Orchestrator + Tool Registry + 分析引擎 + SQLite/Parquet 的模块化单体架构。"
        "DuckDB 用于 P1 的大数据查询。LLM Provider 通过适配器隔离；核心确定性能力在无 LLM 时仍可运行。"
    )
    add_table(
        doc,
        ["模块", "职责", "不得承担"],
        [
            ("UI", "输入、预览、确认、进度、证据和导出", "不得直接修改数据文件或计算正式指标"),
            ("应用服务层", "鉴权、事务、对象生命周期、任务提交", "不得把业务规则散落在页面回调"),
            ("Agent Orchestrator", "计划、上下文、工具选择、叙述", "不得直接计算数字或绕过 Tool Registry"),
            ("分析引擎", "加载、画像、质量、清洗、统计、绘图、建模", "不得依赖自然语言输出作为事实输入"),
            ("执行器/沙箱", "运行受控代码、资源限制、日志", "不得联网、访问任意路径或执行系统命令"),
            ("Validator", "Schema、字段、证据、数字、版本和发布校验", "不得修改原始 Artifact 来“修正”结论"),
            ("Storage", "元数据事务、不可变文件、校验和、仓储接口", "不得将密钥或完整敏感样本写入日志"),
        ],
        [1700, 3900, 3760],
        font_size=8.5,
    )
    doc.add_heading("10.1 内部服务接口（建议）", level=2)
    for text in [
        "IngestionService.create_dataset_version(upload, parse_options) → DatasetVersion",
        "SchemaService.profile_and_infer(version_id) → ColumnSchema[]",
        "QualityService.scan(version_id, analysis_spec?) → QualityIssue[]",
        "CleaningService.preview/execute(plan_id) → Preview | DatasetVersion",
        "AnalysisService.plan/run(spec_id, version_id) → AnalysisRun",
        "EvidenceService.create_artifact/validate_claim → Artifact | ValidationResult",
        "ReportService.render/export(run_id, selection) → ExportArtifact",
    ]:
        add_doc_bullet(doc, text)
    add_callout(doc, "接口约束", "所有写操作必须携带项目和用户上下文；所有结果对象必须返回稳定 ID、状态、创建时间与错误编号。正式 API 形式在详细设计阶段冻结。")

    doc.add_heading("11. 非功能需求", level=1)
    nfr_rows = [
        ("NFR-PERF-01", "性能", "10 万行×30 列以内，质量摘要与基础 EDA P50≤60 秒、P95≤180 秒（建议基线）", "固定硬件和基准数据集压测"),
        ("NFR-PERF-02", "交互", "普通页面 P95 首次可交互≤3 秒；分页预览 P95≤2 秒", "前端与接口监控"),
        ("NFR-SCALE-01", "容量", "MVP 单文件建议上限 500MB、行数 500 万；超限在上传前后均明确提示", "边界文件测试；最终值经预研冻结"),
        ("NFR-REL-01", "可靠性", "成功提交的 ready 版本不可因进程重启丢失；失败任务具有终态", "故障注入与恢复测试"),
        ("NFR-REP-01", "可复现", "相同输入、参数、代码/工具版本和种子下，确定性结果一致；浮点容差预定义", "回归快照与哈希核对"),
        ("NFR-SEC-01", "隔离", "项目数据、路径、日志和导出不可跨项目访问", "越权和路径穿越测试"),
        ("NFR-PRV-01", "隐私", "模型上下文不包含完整数据；PII 默认只传统计摘要或脱敏样例", "提示词/调用载荷审计"),
        ("NFR-AUD-01", "审计", "上传、版本、清洗审批、Schema 覆盖、运行、发布和导出均留痕", "审计事件完整性测试"),
        ("NFR-OBS-01", "可观测", "任务成功率、阶段耗时、失败类型、资源和 LLM/工具调用可度量", "仪表盘与告警演练"),
        ("NFR-UX-01", "可用性", "核心旅程无需编程；阻断错误包含原因和下一步", "5 名目标用户可用性测试"),
        ("NFR-A11Y-01", "可访问性", "键盘可操作；状态不只用颜色；关键控件有可读标签", "自动扫描+人工抽检"),
        ("NFR-MNT-01", "可维护", "核心模块类型检查通过；数据转换覆盖≥90%、质量≥85%、Schema≥80%、编排≥70%", "CI 覆盖率门禁"),
        ("NFR-COMP-01", "兼容", "支持近两年主流 Chrome/Edge；导出 Notebook 兼容约定 Python 环境", "兼容矩阵回归"),
        ("NFR-I18N-01", "语言与时区", "MVP 中文界面；时间以项目时区显示，存储使用 UTC", "跨时区与夏令时用例"),
    ]
    add_table(doc, ["编号", "属性", "要求", "验证方式"], nfr_rows, [1500, 1100, 4700, 2060], font_size=7.9)
    doc.add_heading("11.1 可维护性与工程质量", level=2)
    doc.add_paragraph("建议工具链：Ruff、Mypy、Pytest、Coverage、Bandit、Pre-commit、GitHub Actions。数据操作应优先采用纯函数和显式参数；产品代码与 AI 临时代码必须隔离。")

    doc.add_heading("12. 安全、隐私与合规要求", level=1)
    doc.add_heading("12.1 受控执行", level=2)
    for text in [
        "run_python 在独立容器或受限进程运行，默认无网络，限制 CPU、内存、运行时间、进程数和可写目录。",
        "仅允许白名单库；执行前 AST 检查；禁止 eval、exec、os.system、subprocess、socket、requests 和任意文件路径访问。",
        "代码、参数、环境摘要、stdout/stderr、退出码和资源使用必须记录；日志在展示前清理敏感信息。",
        "临时目录按 Run 隔离并在终态清理；Artifact 通过受控存储 API 写入。",
    ]:
        add_doc_bullet(doc, text)
    doc.add_heading("12.2 敏感数据", level=2)
    doc.add_paragraph("系统应识别邮箱、手机号、身份证号、地址、姓名等敏感字段。默认数据最小化：模型只接收 Schema、统计摘要、必要的脱敏样例、用户决定和相关证据。")
    doc.add_heading("12.3 权限模型（MVP）", level=2)
    add_table(
        doc,
        ["能力", "项目所有者/编辑者", "只读查看者", "系统管理员"],
        [
            ("上传与创建版本", "允许", "禁止", "按项目授权"),
            ("修改 Schema/审批清洗", "允许", "禁止", "默认禁止"),
            ("运行分析与建模", "允许", "禁止", "按项目授权"),
            ("查看数据明细", "允许；受敏感策略约束", "按项目配置", "默认无内容权限"),
            ("查看证据/报告", "允许", "允许；受项目配置", "按项目授权"),
            ("配置全局资源与提供商", "禁止", "禁止", "允许"),
        ],
        [2600, 2400, 2100, 2260],
        font_size=8.5,
    )
    add_callout(doc, "安全边界", "本说明书不将 MVP 定义为满足特定行业合规认证。若处理医疗、金融、未成年人或其他受监管数据，须另行开展合规评估与数据处理协议设计。", fill="FDE9E7", color=RED)

    doc.add_heading("13. 日志、监控与审计", level=1)
    doc.add_heading("13.1 审计事件", level=2)
    doc.add_paragraph("至少记录：登录/授权结果、项目创建归档、上传、版本创建、Schema 覆盖、质量处置、清洗审批与执行、AnalysisSpec 确认、Run 状态、Claim 发布/撤回、报告/数据导出和管理员配置变化。")
    doc.add_heading("13.2 运行监控", level=2)
    for text in [
        "按阶段统计成功率、P50/P95 耗时、错误码、重试、取消和资源使用。",
        "监控 Artifact 写入失败、遗留 running 任务、磁盘阈值、队列积压和 LLM/工具 Schema 失败。",
        "错误日志包含 request_id、project_id、run_id、step_id 和 tool_version，但不包含原始敏感值。",
        "告警阈值和响应人应在部署设计阶段配置并演练。",
    ]:
        add_doc_bullet(doc, text)

    doc.add_heading("14. 验收策略与测试要求", level=1)
    doc.add_heading("14.1 上线准入条件", level=2)
    criteria = [
        "所有 P0 功能需求通过，P0 阻断缺陷为 0；P1/P2 未完成项不影响核心证据链。",
        "三个固定 Demo 完成端到端验收：房价、客户流失、电商订单。",
        "正式报告数字可追溯率 100%，不存在无证据数字和不存在字段引用。",
        "原始版本不可覆盖；所有已批准清洗生成新版本并可回滚。",
        "分类/回归预处理和数据拆分通过泄露专项测试。",
        "沙箱逃逸、路径穿越、跨项目访问、密钥泄露等高风险安全用例通过。",
        "文档、HTML、Notebook、清洗数据和 Manifest 导出通过重跑与完整性检查。",
        "关键 NFR 经约定硬件基线验证；不达标项有书面豁免和风险接受。",
    ]
    for c in criteria:
        add_doc_bullet(doc, c)
    doc.add_heading("14.2 测试层级", level=2)
    add_table(
        doc,
        ["层级", "重点"],
        [
            ("单元测试", "解析、类型推断、质量规则、清洗纯函数、指标、数字注入、状态机"),
            ("边界测试", "空表、单列、混合类型、极端缺失、高基数、时区、超长文本、超限文件"),
            ("集成测试", "上传→版本→质量→清洗→EDA/模型→Claim→导出"),
            ("统计方法测试", "拆分、预处理拟合范围、指标口径、显著性条件、浮点容差"),
            ("LLM 行为测试", "字段幻觉、工具幻觉、证据不足拒答、结构化输出、提示注入"),
            ("安全测试", "AST 绕过、路径穿越、联网、资源耗尽、越权、日志和导出泄密"),
            ("回归测试", "固定数据与 Artifact/Claim 快照；版本升级兼容性"),
            ("可用性测试", "目标用户能否在无代码情况下完成核心旅程并理解风险提示"),
        ],
        [1800, 7560],
    )
    doc.add_heading("14.3 Demo 验收脚本摘要", level=2)
    add_numbered_list(doc, [
        "房价：上传→识别邮编为类别→发现缺失/泄露→确认清洗→回归 baseline→证据化特征解释→导出。",
        "客户流失：确认预测时点→排除事后字段→时间拆分→不平衡分类指标→分组误差→限制说明。",
        "电商订单：重复订单检测→金额对账→清洗预览与版本→时间趋势→HTML/Notebook 重跑。",
    ])

    doc.add_heading("15. 开发路线与里程碑", level=1)
    roadmap = [
        ("M1 项目基础", "1 周", "目录、配置、SQLite、上传、格式加载、DatasetVersion、Parquet", "原始版本不可覆盖；哈希与重载通过"),
        ("M2 Schema", "1 周", "画像、物理/语义/角色推断、置信度、用户覆盖", "邮编等编码识别；覆盖持久化"),
        ("M3 数据质量", "1–2 周", "质量规则、严重程度、结构化报告", "无 LLM 可运行；指标与样例正确"),
        ("M4 清洗与版本", "1 周", "计划、预览、审批、执行、差异、回滚", "每次操作新版本；不变量验证"),
        ("M5 EDA 与图表", "1–2 周", "自动 EDA、Chart Planner、Plotly、Artifact", "图表绑定版本；配置可重跑"),
        ("M6 建模", "1–2 周", "AnalysisSpec、拆分、Pipeline、baseline、评价与解释", "无泄露；与 Dummy 对比"),
        ("M7 Agent 与 NLQ", "1–2 周", "Registry、Planner、Context、结构化输出、决策记忆", "工具/字段幻觉被阻断"),
        ("M8 证据与报告", "1 周", "Artifact、Claim、Validator、HTML、Notebook、Manifest", "结论有证据；Notebook 可重跑"),
        ("M9 安全与质量", "持续", "沙箱、AST、CI、覆盖率、安全扫描、幻觉测试", "上线准入条件满足"),
    ]
    add_table(doc, ["阶段", "工期", "主要交付", "阶段门"], roadmap, [1500, 900, 4200, 2760], font_size=8.2)
    doc.add_paragraph("按顺序串行估算约 10–14 周，不含需求冻结、资源等待、上线审批与 P1 扩展；可在架构稳定后并行推进 UI、规则和测试。")

    doc.add_heading("16. 风险、依赖与应对", level=1)
    risks = [
        ("R-01 LLM 幻觉", "高", "错误字段、工具或解释进入结果", "结构化输出、Registry、Artifact、Claim Validator、拒答"),
        ("R-02 数据泄露", "高", "模型指标虚高并误导决策", "预测时点、拆分规则、Pipeline、泄露扫描与专项测试"),
        ("R-03 沙箱不充分", "高", "文件/网络/主机风险", "独立隔离、无网络、白名单、AST、资源限制与安全测试"),
        ("R-04 Schema 误判", "中高", "错误统计、清洗与建模", "置信度、证据、用户确认、变更影响分析"),
        ("R-05 大文件性能", "中", "超时、内存溢出、体验差", "Parquet、分块、抽样、DuckDB P1、明确容量上限"),
        ("R-06 证据链过重", "中", "存储增长与交互复杂", "Artifact 分层、按需展示、生命周期和压缩策略"),
        ("R-07 统计误用", "高", "将相关当因果、样本不足", "任务边界、假设检查、Claim 分级与限制模板"),
        ("R-08 Notebook 环境漂移", "中", "导出后不可重跑", "Manifest、依赖锁定、版本记录和固定回归环境"),
        ("R-09 敏感数据外发", "高", "隐私与合规风险", "最小上下文、脱敏、提供商配置、调用载荷审计"),
    ]
    add_table(doc, ["风险", "等级", "影响", "主要应对"], risks, [1900, 800, 2700, 3960], font_size=8.2)
    doc.add_heading("16.1 外部依赖", level=2)
    doc.add_paragraph("Python 数据栈、LLM Provider、SQLite/Parquet 文件系统、Plotly、scikit-learn、Jinja2、nbformat 及部署环境资源限制。关键依赖应锁定版本并建立兼容性回归。")

    doc.add_heading("17. 数据分析与产品埋点", level=1)
    add_table(
        doc,
        ["事件", "关键属性", "用途"],
        [
            ("project_created", "project_id, source", "项目漏斗"),
            ("dataset_uploaded", "format, size_bucket, result, error_code", "接入成功率与容量规划"),
            ("schema_override", "semantic_type, role, confidence_bucket", "推断质量优化"),
            ("quality_issue_action", "type, severity, action", "规则价值与用户信任"),
            ("cleaning_plan_executed", "operation, affected_ratio, result", "清洗成功率与风险"),
            ("analysis_run_finished", "task, status, duration, failed_step", "核心成功率与性能"),
            ("claim_validation", "level, result, failure_reason", "证据链质量"),
            ("export_completed", "type, result, run_id", "价值实现与导出可靠性"),
            ("rerun_completed", "source_run, new_version, compatibility_result", "复现与复用"),
        ],
        [2400, 4200, 2760],
        font_size=8.4,
    )
    doc.add_paragraph("埋点不得包含原始字段值、用户问题全文、敏感列名或导出内容。分析用户问题需单独取得许可并先去标识化。")

    doc.add_heading("18. 假设、待确认事项与决策记录", level=1)
    doc.add_heading("18.1 当前假设", level=2)
    for text in [
        "MVP 为单组织或轻量项目权限场景，不承诺企业级多租户与实时协作。",
        "首个部署形态以本地/单机或受控服务器为主，存储采用 SQLite + 文件系统 Parquet。",
        "单次分析以单表为主；多表关联属于 P2。",
        "用户对上传数据拥有合法处理权，产品仍需提供隐私提醒与最小化处理。",
        "复杂合规、在线模型部署和自动业务决策不属于 MVP。",
    ]:
        add_doc_bullet(doc, text)
    doc.add_heading("18.2 上线前必须确认", level=2)
    open_items = [
        ("Q-01", "部署模式与目标硬件基线", "影响容量、性能 SLA、沙箱和文件存储"),
        ("Q-02", "单文件/项目/用户存储上限", "影响上传、资源配额和清理策略"),
        ("Q-03", "身份认证方式及角色模型", "影响项目隔离、审计和导出权限"),
        ("Q-04", "LLM 提供商、数据驻留与保留政策", "影响隐私、合规和无 LLM 降级"),
        ("Q-05", "敏感数据明文查看与导出政策", "影响 UI 掩码、权限和报告"),
        ("Q-06", "统计检验与最低样本阈值", "影响拒答和 Claim Validator"),
        ("Q-07", "报告品牌、语言与导出模板", "影响 HTML/Notebook 呈现"),
        ("Q-08", "数据与日志保留期", "影响删除、备份和成本"),
        ("Q-09", "是否在 MVP 纳入 P1 的自然语言分析", "影响工期、验收和 LLM 依赖"),
    ]
    add_table(doc, ["编号", "事项", "影响"], open_items, [1000, 3900, 4460], font_size=8.5)

    doc.add_heading("附录 A：需求追踪矩阵", level=1)
    trace = [
        ("上传与不可变版本", "FR-ING-001～007", "UT/IT/E2E-ING", "M1"),
        ("Schema 三层推断", "FR-SCH-001～006", "UT/IT-SCH", "M2"),
        ("确定性质量检测", "FR-QLT-001～005", "UT/STAT/E2E-QLT", "M3"),
        ("清洗审批与回滚", "FR-CLN-001～006", "UT/IT/E2E-CLN", "M4"),
        ("分析定义与计划", "FR-ANA-001～005", "IT/LLM/E2E-ANA", "M6/M7"),
        ("EDA/图表/NLQ", "FR-EDA-001～004；FR-NLQ-001～002", "UT/IT/LLM", "M5/M7"),
        ("Baseline 建模", "FR-MDL-001～006", "STAT/IT/E2E-MDL", "M6"),
        ("证据与验证", "FR-EVD-001～006", "UT/REG/LLM/E2E-EVD", "M8"),
        ("报告与重跑", "FR-RPT-001～005", "IT/REG/E2E-RPT", "M8"),
        ("系统运行", "FR-SYS-001～004", "IT/SEC/CHAOS", "M1/M7/M9"),
    ]
    add_table(doc, ["业务能力", "需求编号", "测试包", "里程碑"], trace, [2500, 3000, 2360, 1500], font_size=8.4)

    doc.add_heading("附录 B：关键结构示例", level=1)
    doc.add_heading("B.1 DatasetVersion", level=2)
    p = doc.add_paragraph()
    r = p.add_run(
        '{\n  "dataset_id": "ds_sales",\n  "version": "v1",\n  "source_file": "sales.xlsx",\n'
        '  "storage_path": "datasets/ds_sales/v1/data.parquet",\n  "file_hash": "sha256:...",\n'
        '  "row_count": 82310,\n  "column_count": 18,\n  "sheet": "Orders",\n'
        '  "status": "raw",\n  "parent_version": null\n}'
    )
    r.font.name = "Courier New"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(8.5)
    p.paragraph_format.left_indent = Inches(0.25)
    set_cell = None
    doc.add_heading("B.2 AnalysisSpec", level=2)
    p = doc.add_paragraph()
    r = p.add_run(
        "task: classification\n"
        "target: churn_30d\n"
        "entity_key: customer_id\n"
        "time_column: observation_date\n"
        "split_strategy: temporal\n"
        "metrics: [pr_auc, recall]\n"
        "excluded_columns: [cancel_date, churn_reason]"
    )
    r.font.name = "Courier New"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(8.5)
    p.paragraph_format.left_indent = Inches(0.25)
    doc.add_heading("B.3 发布条件", level=2)
    p = doc.add_paragraph()
    r = p.add_run(
        "can_publish = evidence_ids 非空\n"
        "  AND validation_status == passed\n"
        "  AND dataset_version 非空\n"
        "  AND contains_unverified_numbers == false"
    )
    r.font.name = "Courier New"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    r.font.size = Pt(8.5)
    p.paragraph_format.left_indent = Inches(0.25)

    doc.add_heading("附录 C：MVP 完成定义（Definition of Done）", level=1)
    for text in [
        "需求：对应 P0 需求编号、设计稿/交互说明、验收用例和负责人齐全。",
        "实现：代码评审通过，类型检查与静态扫描无阻断问题，配置与迁移可重复。",
        "测试：单元、集成、统计、安全和端到端测试通过，覆盖率达到模块门槛。",
        "证据：关键数字、图表、模型指标和 Claim 可追溯、可验证、可重跑。",
        "安全：沙箱、权限、脱敏、日志与导出策略验证通过，无高危未接受风险。",
        "运维：监控、错误码、告警、备份/恢复和故障处理说明可用。",
        "文档：用户说明、部署说明、限制条件、已知问题和版本变更记录更新。",
    ]:
        add_doc_bullet(doc, text)


def final_document_settings(doc):
    settings = doc.settings._element
    update = settings.find(qn("w:updateFields"))
    if update is None:
        update = OxmlElement("w:updateFields")
        settings.append(update)
    update.set(qn("w:val"), "true")
    compat = settings.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings.append(compat)
    doc.core_properties.title = "AI Data Analyst Agent 产品需求规格说明书"
    doc.core_properties.subject = "PRD / SRS"
    doc.core_properties.author = "AI Data Analyst Agent 项目组"
    doc.core_properties.keywords = "AI Data Analyst, PRD, SRS, 数据分析, 可复现, 证据链"
    doc.core_properties.comments = "依据项目总设计编制的 V1.0 评审稿"


def main():
    doc = Document()
    configure_page(doc)
    configure_styles(doc)
    add_cover(doc)
    add_front_matter(doc)
    add_sections(doc)
    configure_headers(doc)
    final_document_settings(doc)
    doc.save(OUT)
    print(OUT.resolve())


if __name__ == "__main__":
    main()
