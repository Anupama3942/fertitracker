# -*- coding: utf-8 -*-
"""
Enhanced Script to generate the Complete, Professional Official Government User Manual & System Report
in Sinhala for the FertiTracker System as a Microsoft Word (.docx) document.
"""

import os
import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls

def set_cell_background(cell, fill_hex):
    """Sets background color of a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=130, right=130):
    """Sets cell padding (in dxa: 20 dxa = 1 pt)."""
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        f'</w:tcMar>'
    )
    tc_pr.append(tc_mar)

def set_table_borders(table, color="D1D5DB", sz="4", val="single"):
    """Sets clean, subtle horizontal borders for a table."""
    tblPr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:left w:val="none"/>'
        f'<w:right w:val="none"/>'
        f'<w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>'
        f'<w:insideV w:val="none"/>'
        f'</w:tblBorders>'
    )
    tblPr.append(borders)

def add_callout(doc, text, title="වැදගත් නිල සටහන (Official Note)", alert_type="note"):
    """Adds an official callout box with a colored left border."""
    border_color = "1E3A8A" if alert_type == "note" else ("059669" if alert_type == "success" else "DC2626")
    bg_color = "EFF6FF" if alert_type == "note" else ("ECFDF5" if alert_type == "success" else "FEF2F2")
    
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    
    cell = table.cell(0, 0)
    cell.width = Inches(6.5)
    set_cell_background(cell, bg_color)
    set_cell_margins(cell, top=140, bottom=140, left=180, right=180)
    
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = parse_xml(
        f'<w:tcBorders {nsdecls("w")}>'
        f'<w:top w:val="none"/>'
        f'<w:bottom w:val="none"/>'
        f'<w:left w:val="single" w:sz="36" w:space="0" w:color="{border_color}"/>'
        f'<w:right w:val="none"/>'
        f'</w:tcBorders>'
    )
    tc_pr.append(borders)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.15
    
    r_title = p.add_run(f"📌 {title}\n")
    r_title.bold = True
    r_title.font.name = "Nirmala UI"
    r_title.font.size = Pt(10.5)
    r_title.font.color.rgb = RGBColor(30, 58, 138) if alert_type == "note" else (RGBColor(5, 150, 105) if alert_type == "success" else RGBColor(220, 38, 38))
    
    r_text = p.add_run(text)
    r_text.font.name = "Nirmala UI"
    r_text.font.size = Pt(10)
    r_text.font.color.rgb = RGBColor(31, 41, 55)
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

def format_run(run, font_name="Nirmala UI", size_pt=10.5, bold=False, italic=False, color_rgb=None):
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color_rgb:
        run.font.color.rgb = color_rgb

def create_manual_document(output_path):
    doc = Document()
    
    # Page setup - Margins (1 inch all around)
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
        
        # Header & Footer
        header = section.header
        hp = header.paragraphs[0]
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hrun = hp.add_run("FertiTracker | ජාතික පොහොර බෙදාහැරීමේ පද්ධති අත්පොත (Government Manual)")
        format_run(hrun, size_pt=8.5, color_rgb=RGBColor(107, 114, 128))
        
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        frun = fp.add_run("කෘෂිකර්ම අමාත්‍යාංශය සහ ගොවිජන සංවර්ධන දෙපාර්තමේන්තුව — නිල රාජ්‍ය ලේඛනයකි")
        format_run(frun, size_pt=8.5, color_rgb=RGBColor(156, 163, 175))

    # Palette
    PRIMARY = RGBColor(30, 58, 138)     # Navy #1E3A8A
    SECONDARY = RGBColor(5, 150, 105)   # Emerald #059669
    DARK_TEXT = RGBColor(31, 41, 55)    # Charcoal #1F2937
    MUTED_TEXT = RGBColor(75, 85, 99)   # Gray #4B5563

    # Section Heading Helpers
    def add_section_h1(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(title)
        format_run(r, size_pt=14.5, bold=True, color_rgb=PRIMARY)

    def add_section_h2(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(13)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(title)
        format_run(r, size_pt=12, bold=True, color_rgb=SECONDARY)

    def add_section_h3(title):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(9)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.keep_with_next = True
        r = p.add_run(title)
        format_run(r, size_pt=11, bold=True, color_rgb=DARK_TEXT)

    def add_para(text, bold_prefix="", space_after=6):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(space_after)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            format_run(r_pre, size_pt=10.5, bold=True, color_rgb=DARK_TEXT)
        r_body = p.add_run(text)
        format_run(r_body, size_pt=10.5, color_rgb=DARK_TEXT)
        return p

    def add_bullet(text, bold_prefix=""):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.15
        if bold_prefix:
            r_pre = p.add_run(bold_prefix)
            format_run(r_pre, size_pt=10, bold=True, color_rgb=DARK_TEXT)
        r_body = p.add_run(text)
        format_run(r_body, size_pt=10, color_rgb=DARK_TEXT)
        return p

    # ==========================================
    # COVER / HEADER
    # ==========================================
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(10)
    p_title.paragraph_format.space_after = Pt(4)
    run_emblem = p_title.add_run("ශ්‍රී ලංකා ප්‍රජාතාන්ත්‍රික සමාජවාදී ජනරජය\n")
    format_run(run_emblem, size_pt=13, bold=True, color_rgb=MUTED_TEXT)
    run_dept = p_title.add_run("කෘෂිකර්ම අමාත්‍යාංශය | ගොවිජන සංවර්ධන දෙපාර්තමේන්තුව\n")
    format_run(run_dept, size_pt=14, bold=True, color_rgb=PRIMARY)
    
    p_main = doc.add_paragraph()
    p_main.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_main.paragraph_format.space_before = Pt(8)
    p_main.paragraph_format.space_after = Pt(6)
    run_sys = p_main.add_run("FertiTracker (ෆර්ටිට්‍රැකර්)\n")
    format_run(run_sys, size_pt=24, bold=True, color_rgb=PRIMARY)
    run_sub = p_main.add_run("ජාතික පොහොර තොග සහ ගොවි සහනාධාර බෙදාහැරීමේ විනිවිදභාවය තහවුරු කිරීමේ ඩිජිටල් පද්ධතිය\n")
    format_run(run_sub, size_pt=13.5, bold=True, color_rgb=SECONDARY)
    run_eng = p_main.add_run("National Fertilizer Stock & Farmer Distribution Traceability System\n")
    format_run(run_eng, size_pt=11, italic=True, color_rgb=MUTED_TEXT)

    p_doc_type = doc.add_paragraph()
    p_doc_type.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_doc_type.paragraph_format.space_before = Pt(6)
    p_doc_type.paragraph_format.space_after = Pt(16)
    run_badge = p_doc_type.add_run("පරිපූර්ණ රාජ්‍ය මෙහෙයුම්, පරිපාලන සහ තාක්ෂණික පද්ධති අත්පොත\n(Comprehensive Government Operational Manual & System Handover Report)")
    format_run(run_badge, size_pt=12, bold=True, color_rgb=PRIMARY)

    # Document Metadata Table
    meta_table = doc.add_table(rows=5, cols=2)
    meta_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(meta_table)
    meta_data = [
        ("ලේඛන අංකය (Document Reference)", "AGR/FT/GOM/2026/V1.0"),
        ("අදාළ ආයතන (Target Scope)", "ගොවිජන සංවර්ධන දෙපාර්තමේන්තුව, සියලුම ගොවිජන සේවා මධ්‍යස්ථාන (ASCs 560+), මධ්‍යම පොහොර ගබඩා, රජයේ විගණකාධිපති දෙපාර්තමේන්තුව"),
        ("පද්ධති අනුවාදය (System Version)", "FertiTracker Core v2.0 (Tri-Lingual: Sinhala, Tamil, English)"),
        ("තාක්ෂණික පදනම & සංවර්ධනය", "මෘදුකාංග ඉංජිනේරු අංශය, තාක්ෂණ අධ්‍යයන පීඨය, වව්නියාව විශ්වවිද්‍යාලය (University of Vavuniya) — TICT3153"),
        ("ක්‍රියාත්මක දිනය (Effective Date)", "2026 නොවැම්බර් 09 වන දින සිට බලාත්මකයි"),
    ]
    for idx, (label, val) in enumerate(meta_data):
        row = meta_table.rows[idx]
        cell_lbl, cell_val = row.cells[0], row.cells[1]
        cell_lbl.width = Inches(2.5)
        cell_val.width = Inches(4.0)
        set_cell_background(cell_lbl, "F3F4F6")
        set_cell_margins(cell_lbl, top=70, bottom=70, left=90, right=90)
        set_cell_margins(cell_val, top=70, bottom=70, left=90, right=90)
        
        p0 = cell_lbl.paragraphs[0]
        r0 = p0.add_run(label)
        format_run(r0, size_pt=9.5, bold=True, color_rgb=DARK_TEXT)
        
        p1 = cell_val.paragraphs[0]
        r1 = p1.add_run(val)
        format_run(r1, size_pt=9.5, color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # ==========================================
    # 1. EXECUTIVE SUMMARY & BACKGROUND
    # ==========================================
    add_section_h1("1. විධායක සාරාංශය සහ ආයතනික අරමුණ (Executive Summary & Purpose)")
    
    add_para(
        "ශ්‍රී ලංකාවේ ජාතික ආහාර සුරක්ෂිතතාව තහවුරු කිරීමෙහිලා කෘෂිකර්ම අමාත්‍යාංශය සහ ගොවිජන සංවර්ධන දෙපාර්තමේන්තුව "
        "හරහා ක්‍රියාත්මක කරනු ලබන රසායනික පොහොර සහනාධාර වැඩසටහන ප්‍රමුඛතම රාජ්‍ය ආයෝජනයකි. දිවයින පුරා විසිරී ඇති "
        "ගොවිජන සේවා මධ්‍යස්ථාන 560 කට අධික සංඛ්‍යාවක් හරහා වාර්ෂිකව රුපියල් බිලියන ගණනක පොහොර ගොවි ජනතාව වෙත බෙදාහරිනු ලැබේ. "
        "කෙසේ වෙතත්, දශක ගණනාවක් තිස්සේ මෙම ක්‍රියාවලිය සඳහා භෞතික කඩදාසි ලේඛන (Paper Registers) භාවිත කිරීම හේතුවෙන් "
        "බරපතල අක්‍රමිකතා, රාජ්‍ය මූල්‍ය කාන්දුවීම් සහ පරිපාලනමය දුර්වලතා රැසක් නිර්මාණය වී තිබේ."
    )

    add_section_h2("1.1 පවතින කඩදාසි ක්‍රමයේ ප්‍රධාන ගැටලු සහ මෙහෙයුම් අවදානම්:")
    add_bullet("මධ්‍යම පොහොර ගබඩා (Warehouses), ගොවිජන සේවා මධ්‍යස්ථාන (ASCs) සහ ගොවි කෝටා ලේඛන අතර කිසිදු ඩිජිටල් සබඳතාවක් නොමැතිවීම. ප්‍රවාහනයේදී සිදුවන කාන්දුවීම් හෝ තොග අතුරුදහන්වීම් සොයාගත නොහැක.", "• විසන්ධි වූ තොග දාමය (Disconnected Custody): ")
    add_bullet("එක් ගොවියෙකුගේ කූපන් පතක් හෝ නම වෙනත් පුද්ගලයින් විසින් ඉදිරිපත් කර අසල්වැසි මධ්‍යස්ථාන කිහිපයකින් වංචනිකව පොහොර ලබාගැනීම වැළැක්වීමට ක්ෂණික පද්ධතියක් නොමැතිකම.", "• ද්විත්ව නිකුත් කිරීම් සහ වංචා (Duplicate Issuances): ")
    add_bullet("ගබඩාවේ පිටුපස ඇති පැරණි තොග තිබියදී අලුතින් ලැබෙන තොග මුලින් නිකුත් කිරීම නිසා පොහොර කැට ගැසී, තෙතමනය උරාගෙන කල් ඉකුත්වී විනාශ වීම (FEFO ක්‍රමය නොමැතිකම).", "• කල් ඉකුත්වීමේ නාස්තිය (Expiry Wastage): ")
    add_bullet("පවතින ඇතැම් ඩිජිටල් ක්‍රමවේද ස්මාර්ට්ෆෝන් සඳහා පමණක් සීමා වීම නිසා, සාමාන්‍ය කීපෑඩ් (Keypad) දුරකථන හිමි වැඩිහිටි ගොවි ජනතාව සහ දුරකථන නොමැති ගොවීන් සහනාධාර අයිතියෙන් කොන්වීම.", "• ඩිජිටල් පරතරය (Exclusion of Marginalized Farmers): ")
    add_bullet("කඩදාසි පොත් විනාශ වීම, ගංවතුරට හසුවීම හෝ ගිනිගැනීම නිසා රජයේ විගණකාධිපති දෙපාර්තමේන්තුවේ විමර්ශන සඳහා විධිමත් සාක්ෂි නොමැතිවීම.", "• විගණන සාක්ෂි නොමැතිකම (Missing Audit Trail): ")

    add_section_h2("1.2 FertiTracker මඟින් ලබාදෙන ජාතික විසඳුම:")
    add_para(
        "FertiTracker පද්ධතිය මඟින් මධ්‍යම ගබඩාවේ සිට ගොවියාගේ කුඹුරට පොහොර ලැබෙන තෙක් සම්පූර්ණ ජීවන චක්‍රයම "
        "තනි ඩිජිටල් වේදිකාවක් ඔස්සේ නිරීක්ෂණය කරන අතර, ශ්‍රී ලංකා රාජ්‍ය භාෂා ප්‍රතිපත්තියට අනුකූලව සිංහල, දෙමළ සහ ඉංග්‍රීසි "
        "යන ත්‍රිභාෂාවෙන්ම සජීවීව ක්‍රියාත්මක වේ. පද්ධතිය සතු ප්‍රධාන ශක්තීන් පහත පරිදි වේ:"
    )
    add_bullet("පොහොර කාණ්ඩයක් නිෂ්පාදනය කළ දිනයේ සිට ප්‍රවාහනය, ගොවිජන මධ්‍යස්ථානයට ලැබීම සහ ගොවියා ලබාගන්නා තෙක් 100% ක පූර්ණ නිරීක්ෂණය.", "1. කණ්ඩායම් අනුව පූර්ණ ගවේෂණය (End-to-End Batch Traceability): ");
    add_bullet("පළමුව කල් ඉකුත්වන කාණ්ඩයෙන් ස්වයංක්‍රීයව පොහොර නිකුත් කිරීම. එක් කාණ්ඩයක් මදි වූ විට ඊළඟ කාණ්ඩයෙන් බෙදා වෙන්කිරීම (Multi-Batch Splitting). කල් ඉකුත් වූ තොග නිකුත් කිරීම 100% අවහිර කිරීම.", "2. ස්වයංක්‍රීය FEFO තොග එන්ජිම (FEFO Stock Allocation): ");
    add_bullet("ස්මාර්ට්ෆෝන් හිමි ගොවීන්ට තත්පර 60 ක ආරක්ෂිත QR කේතය; සාමාන්‍ය කීපෑඩ් දුරකථන හිමි ගොවීන්ට 6-ඉලක්කම් SMS රහස් අංකය; දුරකථන නොමැති ගොවීන්ට ද්වි-නිලධාරී අනුමැති ක්‍රමය (Two-Officer Rule).", "3. සියලු ගොවීන් ඇතුළත් කරගැනීමේ ත්‍රිත්ව ක්‍රමවේදය (Inclusion by Design): ");
    add_bullet("PostgreSQL පේළි මට්ටමේ අගුලු දැමීම (SELECT ... FOR UPDATE) මඟින් එකම කෝටාව හෝ තොගය නිලධාරීන් දෙදෙනෙකු විසින් එකවර නිකුත් කිරීම මුළුමනින්ම වැළැක්වීම.", "4. සමගාමී ගනුදෙනු අගුල (PostgreSQL Row-Level Locking): ");
    add_bullet("කිසිදු නිලධාරියෙකුට හෝ පරිපාලකයෙකුට මකාදැමීමට හෝ වෙනස් කිරීමට නොහැකි සංවෘත විගණන ලේඛනයක් පවත්වා ගැනීම.", "5. වෙනස් කළ නොහැකි විගණන ලේඛනය (Append-Only Immutable Audit Log): ");

    add_callout(
        doc,
        "FertiTracker පද්ධතිය මඟින් රජයේ පොහොර සහනාධාර අරමුදල්වලින් 100% ක පූර්ණ වගවීමක් තහවුරු කෙරෙන අතර, "
        "එක් ශතයක හෝ එක් පොහොර බෑගයක හෝ අක්‍රමිකතාවක් ක්ෂණිකව විගණන වාර්තාවලින් හඳුනාගත හැකිය.",
        "රාජ්‍ය මූල්‍ය විනිවිදභාවය (Financial Transparency Guarantee)",
        alert_type="success"
    )

    # ==========================================
    # 2. USER ROLES & ACCESS CONTROL
    # ==========================================
    add_section_h1("2. පද්ධතියේ පරිශීලක භූමිකාවන් සහ වගකීම් (Role-Based Access Control - RBAC)")
    add_para(
        "රාජකාරිමය බෙදීම (Separation of Duties) සහ දූෂණ වැළැක්වීමේ මූලධර්ම මත පදනම්ව, පද්ධතිය තුළ නිශ්චිත පරිශීලක භූමිකාවන් "
        "6 ක් ක්‍රියාත්මක වේ. සෑම නිලධාරියෙකුටම ප්‍රවේශ විය හැක්කේ තම නිල බලප්‍රදේශයට අදාළ දත්ත සඳහා පමණි:"
    )

    roles_table = doc.add_table(rows=7, cols=3)
    roles_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(roles_table)
    
    headers = ["පරිශීලක භූමිකාව (Role)", "පද්ධති අවසරයන් (Permissions)", "ප්‍රධාන මෙහෙයුම් වගකීම් (Operational Scope)"]
    hdr_row = roles_table.rows[0]
    for idx, heading in enumerate(headers):
        cell = hdr_row.cells[idx]
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=90, bottom=90, left=110, right=110)
        p = cell.paragraphs[0]
        r = p.add_run(heading)
        format_run(r, size_pt=9.5, bold=True, color_rgb=RGBColor(255, 255, 255))
        
    roles_info = [
        ("පද්ධති පරිපාලක\n(System Administrator)", "පද්ධතිමය පූර්ණ ප්‍රවේශය (Full System Admin)", "නිලධාරී ගිණුම් සෑදීම, තාවකාලික මුරපද නිකුත් කිරීම, වගා කන්න (Maha/Yala) සක්‍රීය/අක්‍රිය කිරීම, ගොවිජන සේවා මධ්‍යස්ථාන සහ ගබඩා ලියාපදිංචිය."),
        ("මධ්‍යම ගබඩා නිලධාරී\n(Warehouse Officer)", "මධ්‍යම ගබඩා මට්ටම (Warehouse Scope)", "නව පොහොර කාණ්ඩ (Batches) ඇතුළත් කිරීම, කල් ඉකුත්වීමේ දිනයන් සටහන් කිරීම, ගොවිජන සේවා මධ්‍යස්ථාන වෙත ලොරි රථ මඟින් තොග පිටත් කිරීම (Dispatches)."),
        ("ගොවිජන සේවා කවුන්ටර නිලධාරී\n(ASC Counter Officer)", "මධ්‍යස්ථාන මට්ටම (ASC Counter Scope)", "පිටත් කළ තොග භාරගැනීම සහ විෂමතා සටහන් කිරීම, ගොවීන් ලියාපදිංචිය, QR කේත ස්කෑන් කිරීම, SMS රහස් අංක තහවුරු කිරීම, පොහොර නිකුත් කිරීම."),
        ("ගොවිජන සේවා මධ්‍යස්ථාන ප්‍රධානී\n(ASC Head / In-Charge)", "අනුමැති සහ අධීක්ෂණ මට්ටම (Approval Scope)", "කවුන්ටර මෙහෙයුම්වලට අමතරව: දුරකථන නොමැති ගොවීන් වෙනුවෙන් ඉදිරිපත් වන ඉල්ලීම් අනුමත කිරීම (Two-Officer Rule), කල් ඉකුත් වූ තොග ඉවත් කිරීම (Write-Off) අනුමත කිරීම."),
        ("රජයේ ස්වාධීන විගණක\n(Government Auditor)", "කියවීමට පමණක් අවසර (Read-Only Audit)", "සංශෝධනය කළ නොහැකි විගණන ලේඛනය (Audit Log), ප්‍රවාහන හානි සහ විෂමතා වාර්තා, නිලධාරී මැදිහත්වීම් අනුපාත පරීක්ෂාව, කණ්ඩායම් විමර්ශනය."),
        ("ලියාපදිංචි ගොවි මහතුන්\n(Registered Farmers)", "පුද්ගලික ගොවි ගිණුම (Farmer Portal)", "තමන්ට හිමි සහනාධාර කෝටාව සහ ඉතිරි ප්‍රමාණය පරීක්ෂා කිරීම, තත්පර 60 ක වලංගුතාව සහිත ආරක්ෂිත QR කේතයක් ජනනය කිරීම, ලැබීම් ඉතිහාසය බැලීම.")
    ]
    
    for row_idx, data in enumerate(roles_info, start=1):
        row = roles_table.rows[row_idx]
        bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx in range(3):
            cell = row.cells[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            r = p.add_run(data[col_idx])
            format_run(r, size_pt=9, bold=(col_idx==0), color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================================
    # 3. END-TO-END OPERATIONAL WORKFLOWS
    # ==========================================
    add_section_h1("3. ප්‍රධාන මෙහෙයුම් ක්‍රියාදාමයන් — පියවරෙන් පියවර මාර්ගෝපදේශය (Operational Workflows)")
    
    # Workflow 1: Season Setup
    add_section_h2("3.1 ක්‍රියාදාමය 1: වගා කන්න (Maha/Yala) සැකසීම සහ තනි සක්‍රීය කන්න නීතිය")
    add_para(
        "ශ්‍රී ලංකාවේ වගා කන්න ක්‍රමය අනුව සහනාධාර නිකුත් කෙරේ. පද්ධතිය තුළ එකවර සක්‍රීය විය හැක්කේ "
        "එක් වගා කන්නයක් පමණි (Single Active Season Invariant). මෙය පරිපාලක උපකරණ පුවරුවෙන් පාලනය වේ:"
    )
    add_bullet("පද්ධති පරිපාලක /accounts/dashboard/ වෙත පිවිස 'කන්න කළමනාකරණය' යටතේ නව කන්නයක් (උදා: Maha 2026/2027) සාදා 'සක්‍රීය කරන්න (ACTIVE)' බොත්තම ක්ලික් කරයි.", "පියවර 1 (කන්නය සක්‍රීය කිරීම): ");
    add_bullet("එක් කන්නයක් සක්‍රීය කළ විගස, පද්ධතිය ස්වයංක්‍රීයවම පෙර පැවති අනෙකුත් සියලු කන්න 'අවසන් (CLOSED)' තත්ත්වයට පත් කරයි.", "පියවර 2 (තනි සක්‍රීය කන්න නීතිය): ");
    add_bullet("කන්නයක් අවසන් (CLOSED) වූ පසු, කිසිදු නිලධාරියෙකුට හෝ මධ්‍යස්ථානයකට එම කන්නය යටතේ පොහොර නිකුත් කළ නොහැක. කවුන්ටරයෙන් ඉල්ලීමක් ඉදිරිපත් කළද, මධ්‍යම දත්ත සමුදාය මට්ටමින් එය ප්‍රතික්ෂේප වේ.", "පියවර 3 (අක්‍රිය කන්න ආරක්ෂාව): ");

    # Workflow 2: Farmer Registration & Quota Import
    add_section_h2("3.2 ක්‍රියාදාමය 2: ගොවීන් ලියාපදිංචිය සහ සහනාධාර කෝටා ඇතුළත් කිරීම (Two-Phase CSV)")
    add_para(
        "ගොවි හැඳුනුම්පත් ව්‍යාජ ලෙස යොදාගැනීම සහ දත්ත දූෂණය වැළැක්වීම සඳහා පියවර දෙකක දැඩි ක්‍රමවේදයක් ක්‍රියාත්මක වේ:"
    )
    add_bullet("කවුන්ටර නිලධාරියා ගොවියාගේ මුල් ජාතික හැඳුනුම්පත (පැරණි 9 ඉලක්කම් + V/X හෝ නව 12 ඉලක්කම්) පරීක්ෂා කර පද්ධතියට ඇතුළත් කරයි. දුරකථන අංකය ශ්‍රී ලංකා ජංගම ආකෘතියට (07XXXXXXXX) වලංගු කෙරේ.", "ගොවි ලියාපදිංචිය: ");
    add_bullet("ලියාපදිංචි වූ වහාම ගොවි ගිණුම 'අක්‍රිය (INACTIVE)' තත්ත්වයේ පවතී. ගොවියාගේ දුරකථනයට ලැබෙන 6-ඉලක්කම් රහස් OTP කේතය තහවුරු කළ පසු පමණක් ගිණුම සක්‍රීය වේ.", "OTP සක්‍රීය කිරීම: ");
    add_bullet("ගොවිජන සංවර්ධන කොමසාරිස් ජනරාල් කාර්යාලයෙන් දිස්ත්‍රික්කයට ලැබෙන කෝටා ලේඛනය (/distributions/entitlements/csv-preview/) වෙත උඩුගත කෙරේ. මෙහිදී UTF-8 BOM සහිත සහ රහිත Excel ගොනු දෙවර්ගයම ගැටලුවකින් තොරව හඳුනාගනී.", "කෝටා CSV උඩුගත කිරීම: ");
    add_bullet("පද්ධතිය උඩුගත කළ ගොනුවේ සියලු පේළි පරීක්ෂා කර පූර්ව නිරීක්ෂණයක් ලබාදේ. නොපවතින ගොවි හැඳුනුම්පත් හෝ වැරදි අගයන් රතු පැහැයෙන් පෙන්වන අතර, සියලු වැරදි නිවැරදි වන තුරු දත්ත සමුදායට එක්කිරීම සම්පූර්ණයෙන්ම අවහිර කරයි (All-or-Nothing Atomic Import).", "දෙපියවර පූර්ව නිරීක්ෂණය: ");

    # Workflow 3: Central Warehouse Dispatch
    add_section_h2("3.3 ක්‍රියාදාමය 3: මධ්‍යම ගබඩාවෙන් තොග නිකුත් කිරීම සහ ප්‍රවාහන පාලනය (Warehouse Dispatch)")
    add_para(
        "මධ්‍යම පොහොර ගබඩාවලින් (Colombo Central Hub / Lakphohora) දිස්ත්‍රික්කයේ ගොවිජන සේවා මධ්‍යස්ථාන වෙත "
        "පොහොර පිටත් කිරීම මෙම ක්‍රියාවලිය මඟින් පාලනය වේ:"
    )
    add_bullet("මධ්‍යම ගබඩා නිලධාරී /inventory/dispatches/create/ වෙත පිවිස, පොහොර කාණ්ඩ අංකය (Batch No), පොහොර වර්ගය, නිෂ්පාදිත දිනය සහ කල් ඉකුත්වීමේ දිනය (Expiry Date) ඇතුළත් කරයි.", "පියවර 1 (කාණ්ඩ නිර්මාණය): ");
    add_bullet("ලබන්නා වන ගොවිජන සේවා මධ්‍යස්ථානය (ASC), ප්‍රවාහන ලොරි රථ අංකය, රියදුරු නම සහ පිටත් කරන බෑග් ප්‍රමාණය ඇතුළත් කර පිටත් කිරීම තහවුරු කරයි.", "පියවර 2 (ප්‍රවාහන සටහන): ");
    add_bullet("පිටත් කිරීම තහවුරු කළ විගස, තොගය 'ප්‍රවාහනයේ පවතී (IN_TRANSIT)' තත්ත්වයට පත්වන අතර, අදාළ ගොවිජන සේවා මධ්‍යස්ථානයේ උපකරණ පුවරුවේ ක්ෂණිකව දිස්වේ.", "පියවර 3 (සජීවී නිරීක්ෂණය): ");

    # Workflow 4: ASC Receiving & Discrepancies
    add_section_h2("3.4 ක්‍රියාදාමය 4: ගොවිජන සේවා මධ්‍යස්ථානයේදී තොග භාරගැනීම සහ විෂමතා සමථකරණය")
    add_para(
        "ලොරි රථය ගොවිජන සේවා මධ්‍යස්ථානයට ළඟා වූ පසු, භෞතිකව බෑග් පරීක්ෂා කර පද්ධතියට ඇතුළත් කිරීමේ නීති:"
    )
    add_bullet("නිලධාරියා තම මධ්‍යස්ථානයේ පැමිණි තොගය තෝරාගෙන 'තොග භාරගන්න (Receive Dispatch)' ක්ලික් කරයි.", "පියවර 1 (තොග පරීක්ෂාව): ");
    add_bullet("හොඳ තත්ත්වයේ බෑග් (Good Bags), ප්‍රවාහනයේදී තෙමී හෝ ඉරී හානි වූ බෑග් (Damaged Bags) සහ අඩු බෑග් (Missing Bags) ගණන වෙන වෙනම සටහන් කරයි.", "පියවර 2 (වර්ගීකරණය): ");
    add_bullet("හානි හෝ අඩු බෑග් ඇත්නම්, ඒ සඳහා අනිවාර්ය සාධාරණීකරණ සටහනක් (Mandatory Justification Note - උදා: 'වැසි ජලය කාන්දු වීම නිසා බෑග් 2 ක් තෙමී ඇත, රියදුරු පිළිගන්නා ලදී') ඇතුළත් කළ යුතු අතර, ලොරි රියදුරුගේ අත්සන සහිත බිල්පත ලේඛනගත කළ යුතුය.", "පියවර 3 (අනිවාර්ය සටහන): ");
    add_bullet("පද්ධතිය ගණිතමය වශයෙන් තහවුරු කරයි: පිටත් කළ බෑග් = හොඳ බෑග් + හානි බෑග් + අඩු බෑග්. හොඳ බෑග් පමණක් මධ්‍යස්ථානයේ බෙදාහැරිය හැකි තොගයට එකතු වන අතර, හානි සහ අඩු බෑග් ස්වයංක්‍රීයව 'විෂමතා ලේඛනයට (Discrepancy Log)' ඇතුළත් වේ.", "පියවර 4 (විෂමතා තහවුරුව): ");

    # Workflow 5: 3-Tier Verification
    add_section_h2("3.5 ක්‍රියාදාමය 5: සියලු ගොවීන් ඇතුළත් කරගැනීමේ ත්‍රිත්ව සත්‍යාපන ක්‍රමවේදය (Inclusion by Design)")
    add_para(
        "FertiTracker හි සුවිශේෂීම මානුෂීය සහ තාක්ෂණික ලක්ෂණය වන්නේ කිසිදු ගොවියෙකු කොන් නොවන පරිදි ක්‍රියාත්මක වන සත්‍යාපන ක්‍රම 3 යි:"
    )

    methods_table = doc.add_table(rows=4, cols=3)
    methods_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(methods_table)
    
    m_hdrs = ["නිකුත් කිරීමේ ක්‍රමවේදය", "ඉලක්කගත ගොවි ප්‍රජාව", "ආරක්ෂක යාන්ත්‍රණය සහ මෙහෙයුම් පියවර"]
    m_row0 = methods_table.rows[0]
    for idx, heading in enumerate(m_hdrs):
        cell = m_row0.cells[idx]
        set_cell_background(cell, "059669")
        set_cell_margins(cell, top=90, bottom=90, left=110, right=110)
        p = cell.paragraphs[0]
        r = p.add_run(heading)
        format_run(r, size_pt=9.5, bold=True, color_rgb=RGBColor(255, 255, 255))
        
    methods_data = [
        ("ක්‍රමය 1: ඩිජිටල් QR කේතය\n(Dynamic Browser QR)", "ස්මාර්ට්ෆෝන් භාවිත කරන ගොවි මහතුන් සඳහා", "ගොවියා තම දුරකථනයෙන් පද්ධතියට පිවිස QR කේතය පෙන්වයි. මෙය තත්පර 60 කින් කල් ඉකුත්වන, එක්වරක් පමණක් භාවිත කළ හැකි ගුප්තකේතන ටෝකනයකි. නිලධාරියා වෙබ් කැමරාවෙන් එය ස්කෑන් කර පරීක්ෂා කරයි."),
        ("ක්‍රමය 2: SMS රහස් අංකය\n(6-Digit Keypad SMS Backup)", "සාමාන්‍ය කීපෑඩ් (Button) දුරකථන හිමි ගොවීන්", "ගොවියා කවුන්ටරයට පැමිණි විට, නිලධාරියා ගොවියාගේ ජංගම දුරකථනයට 6-ඉලක්කම් SMS රහස් අංකයක් යවයි. අංකය HMAC-SHA256 මඟින් ආරක්ෂා කර ඇති අතර, අදාළ මධ්‍යස්ථානයට පමණක් සීමා වේ. වැරදි උත්සාහයන් 5 කදී අවහිර වේ."),
        ("ක්‍රමය 3: නිලධාරී මැදිහත්වීම\n(Two-Officer Rule Assisted Issue)", "දුරකථන නොමැති, වැඩිහිටි හෝ අසරණ ගොවීන්", "කවුන්ටර නිලධාරියා ගොවියාගේ හැඳුනුම්පත පරීක්ෂා කර හේතුව සමඟ ඉල්ලීමක් යොමු කරයි. මධ්‍යස්ථාන ප්‍රධානියා (ASC Head) එය අනුමත කළ යුතුය. තමන් දැමූ ඉල්ලීම තමන්ටම අනුමත කළ නොහැක (ද්වි-නිලධාරී රීතිය).")
    ]
    
    for row_idx, data in enumerate(methods_data, start=1):
        row = methods_table.rows[row_idx]
        bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx in range(3):
            cell = row.cells[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            r = p.add_run(data[col_idx])
            format_run(r, size_pt=9, bold=(col_idx==0), color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    add_callout(
        doc,
        "ද්වි-නිලධාරී නීතිය (Two-Officer Rule) මඟින් ව්‍යාජ ගොවීන් පෙන්වා පොහොර ලබාගැනීමේ වංචාවන් 100% ක් වළක්වයි. "
        "කවුන්ටර නිලධාරියා සහ මධ්‍යස්ථාන ප්‍රධානියා යන දෙදෙනාම ගනුදෙනුව සඳහා ඩිජිටල් ලෙස වගකිව යුතුය.",
        "වංචා වැළැක්වීමේ මූලධර්මය (Anti-Collusion Governance)",
        alert_type="note"
    )

    # Workflow 6: Atomic Issue & FEFO
    add_section_h2("3.6 ක්‍රියාදාමය 6: පරමාණුක නිකුත් කිරීමේ ගනුදෙනුව සහ FEFO එන්ජිම (Atomic Issue & FEFO)")
    add_para(
        "කවුන්ටරයේදී පොහොර නිකුත් කිරීම තහවුරු කළ විට, පද්ධතිය තනි පරිගණක ගනුදෙනුවක් (Atomic Transaction) ලෙස "
        "පහත සියලු පියවර ක්ෂණිකව ක්‍රියාත්මක කරයි:"
    )
    add_bullet("PostgreSQL දත්ත සමුදායේ අදාළ තොග පේළි වෙනත් කිසිදු පරිගණකයකට වෙනස් කළ නොහැකි ලෙස අගුලු දමයි (SELECT ... FOR UPDATE).", "1. පේළි මට්ටමේ අගුල: ");
    add_bullet("වගා කන්නය සක්‍රීයද (ACTIVE) සහ ගොවියාගේ ඉතිරි කෝටාව ප්‍රමාණවත්දැයි පරීක්ෂා කරයි.", "2. කෝටා සහ කන්න පරීක්ෂාව: ");
    add_bullet("මධ්‍යස්ථානයේ ඇති කල් ඉකුත් නොවූ තොග අතරින් ආසන්නතම කල් ඉකුත්වීමේ දිනය සහිත කාණ්ඩයෙන් (Earliest Expiry) පොහොර වෙන්කරයි.", "3. FEFO ස්වයංක්‍රීය වෙන්කිරීම: ");
    add_bullet("ගොවියාට අවශ්‍ය ප්‍රමාණය මුල් කාණ්ඩයේ ඉතිරි ප්‍රමාණයට වඩා වැඩි නම්, මුල් කාණ්ඩයෙන් ඉතිරි සියල්ල ලබාගෙන, ඉතිරි කොටස ඊළඟ කාණ්ඩයෙන් ස්වයංක්‍රීයව අඩුකරයි (Multi-Batch Splitting).", "4. කාණ්ඩ බෙදී යාම: ");
    add_bullet("වෙන්කළ සෑම කාණ්ඩයකටම වෙන වෙනම නිකුත් කිරීමේ තොග චලන වාර්තාවක් (StockMovement) නිර්මාණය කරයි. ගොවියාගේ ඉතිරි කෝටාව අඩු කරයි. ටෝකනය 'භාවිතා කරන ලදී (USED)' ලෙස සටහන් කරයි.", "5. චලන සටහන් සහ කෝටා අඩුකිරීම: ");
    add_bullet("නිල ඩිජිටල් රිසිට්පතක් (Digital Receipt) තිරය මත ජනනය කර, සංශෝධනය කළ නොහැකි විගණන ලේඛනයට (AuditLog) ඇතුළත් කරයි.", "6. රිසිට්පත සහ විගණන මුද්‍රාව: ");

    # Workflow 7: Low Stock & Write-Off
    add_section_h2("3.7 ක්‍රියාදාමය 7: අවම තොග අනතුරු ඇඟවීම් සහ කල් ඉකුත් වූ තොග බැහැර කිරීම (Write-Off)")
    add_para(
        "ගොවිජන සේවා මධ්‍යස්ථාන උපකරණ පුවරුවේ තොග තත්ත්වය පිළිබඳ සජීවී ලාංඡන (Real-time Badges) දිස්වේ:"
    )
    add_bullet("තොග ප්‍රමාණවත් වන අතර කල් ඉකුත්වීමට දින 60 කට වඩා ඇත.", "• නිරෝගී තොග (HEALTHY - කොළ පැහැය): ");
    add_bullet("මධ්‍යස්ථානයේ පවතින තොගය අවම සීමාවට (Default 10 bags) වඩා අඩුවී ඇත. වහාම මධ්‍යම ගබඩාවෙන් ඉල්ලුම් කළ යුතුය.", "• අඩු තොග (LOW STOCK - කහ පැහැය): ");
    add_bullet("ඉදිරි දින 60 ඇතුළත කල් ඉකුත්වන කාණ්ඩ පවතී. FEFO එන්ජිම මඟින් මෙම තොග මුලින්ම නිකුත් කෙරේ.", "• කල් ඉකුත්වීමට ආසන්න (NEAR EXPIRY - තැඹිලි පැහැය): ");
    add_bullet("කල් ඉකුත් වූ තොග. මේවා කිසිදු ගොවියෙකුට නිකුත් කිරීමට පද්ධතිය ඉඩ නොදේ (100% අවහිර කෙරේ).", "• කල් ඉකුත් වූ තොග (EXPIRED - රතු පැහැය): ");
    add_bullet("කල් ඉකුත් වූ තොගයක් ඉවත් කිරීමට (Write-Off) හැක්කේ මධ්‍යස්ථාන ප්‍රධානියාට (ASC Head) පමණි. ඒ සඳහා අමාත්‍යාංශ නියෝගය හෝ පරීක්ෂණ වාර්තාව සහිත අනිවාර්ය සාධාරණීකරණ හේතුවක් සැපයිය යුතුය. මෙහිදී කිසිදු දත්තයක් මකා නොදමන අතර 'අපතේ දැමීම (WRITE_OFF)' ලෙස ස්ථිරව සටහන් වේ.", "• නීත්‍යානුකූල බැහැර කිරීමේ පටිපාටිය: ");

    # Workflow 8: Batch Traceability Explorer
    add_section_h2("3.8 ක්‍රියාදාමය 8: කණ්ඩායම් අනුව සජීවී සොයායාමේ හැකියාව (End-to-End Batch Traceability)")
    add_para(
        "අමාත්‍යාංශයට හෝ විගණකවරුන්ට ඕනෑම අවස්ථාවක /distributions/reports/batch-trace/ වෙත පිවිස පොහොර කාණ්ඩ "
        "අංකයක් (උදා: UREA-2026-B01) ඇතුළත් කිරීමෙන් සම්පූර්ණ ජීවන චක්‍රය තත්පරයකින් දැකගත හැක:"
    )
    add_bullet("මධ්‍යම ගබඩාවේ තොරතුරු: නිෂ්පාදිත හෝ ආනයනික ගබඩාව, නිෂ්පාදිත දිනය සහ කල් ඉකුත්වීමේ දිනය.", "1. මධ්‍යම ගබඩාව: ");
    add_bullet("ප්‍රවාහන වාර්තා: පිටත් කළ සියලුම ලොරි රථ අංක, රියදුරන්, පිටත් කළ දිනයන් සහ ගමනාන්ත මධ්‍යස්ථාන.", "2. ප්‍රවාහනය: ");
    add_bullet("භාරගැනීම් සහ විෂමතා: එක් එක් මධ්‍යස්ථානයේදී භාරගත් හොඳ බෑග්, හානි වූ බෑග් සහ අඩු බෑග් ගණන.", "3. භාරගැනීම: ");
    add_bullet("වර්තමාන තොග ශේෂය: මෙම කාණ්ඩයෙන් දිවයිනේ කුමන මධ්‍යස්ථානවල බෑග් කීයක් ඉතිරිව පවතීද යන්න.", "4. තොග ශේෂය: ");
    add_bullet("ප්‍රතිලාභී ගොවි ලේඛනය: මෙම කාණ්ඩයෙන් පොහොර ලබාගත් සියලුම ගොවීන්ගේ ලැයිස්තුව, ලැබුණු දිනය, ප්‍රමාණය සහ රිසිට්පත් අංකය.", "5. ගොවි ලේඛනය: ");
    add_bullet("ගණිතමය සමීකරණය: පිටත් කළ බෑග් = භාරගත් හොඳ බෑග් + හානි බෑග් + අඩු බෑග් + ප්‍රවාහනයේ පවතින බෑග්.", "6. විගණන සමීකරණය: ");

    # ==========================================
    # 4. ANTI-FRAUD, PRIVACY & SECURITY
    # ==========================================
    add_section_h1("4. වංචා වැළැක්වීම, දත්ත රහස්‍යතාව සහ ආරක්ෂණ ක්‍රමවේදය (Security & Privacy Architecture)")
    
    add_section_h2("4.1 පුරවැසි දත්ත රහස්‍යතාව (Citizen Privacy & Masking)")
    add_para(
        "ශ්‍රී ලංකා පෞද්ගලික දත්ත ආරක්ෂණ පනතේ (Personal Data Protection Act) මූලධර්මවලට අනුකූලව, "
        "ගොවි ජනතාවගේ සංවේදී තොරතුරු ආරක්ෂා කර ඇත:"
    )
    add_bullet("තිරය මත, මුද්‍රිත වාර්තාවල සහ විගණන ලේඛනවල ජාතික හැඳුනුම්පත් අංක මැද ඉලක්කම් ආවරණය කර (Masked - උදා: 1985****5678) පෙන්වයි.", "• හැඳුනුම්පත් ආවරණය: ");
    add_bullet("දුරකථන අංක ආවරණය කර (උදා: 077****501) පෙන්වයි.", "• දුරකථන ආවරණය: ");
    add_bullet("ගොවියෙකුගේ දුරකථන අංකය වෙනස් කිරීමට අවශ්‍ය නම්, නිලධාරියා මුල් ජාතික හැඳුනුම්පත පෞද්ගලිකව පරීක්ෂා කර 'මම මුල් හැඳුනුම්පත පරීක්ෂා කළෙමි' යන ප්‍රතිඥාව දිය යුතුය. පැරණි සහ නව අංක දෙකම ආවරණය කර විගණන ලේඛනයට ස්ථිරව ඇතුළත් වේ.", "• දුරකථන අංක වෙනස් කිරීමේ විගණනය: ");

    add_section_h2("4.2 සංශෝධනය කළ නොහැකි ස්ථිර විගණන ලේඛනය (Append-Only Immutable Audit Log)")
    add_bullet("පද්ධතියේ කිසිදු විගණන වාර්තාවක් මකාදැමීමට හෝ සංස්කරණය කිරීමට නොහැකි වන පරිදි මෘදුකාංග කේතය (Model .save() සහ .delete()) මට්ටමින් අගුලු දමා ඇත.", "• මකාදැමීම් විරෝධී ආරක්ෂාව: ");
    add_bullet("Django Admin තුළින් පවා විගණන සටහන් මකාදැමීම හෝ වෙනස් කිරීමේ අවසරයන් මුළුමනින්ම අක්‍රිය කර ඇත (has_add_permission=False, has_change_permission=False, has_delete_permission=False).", "• පරිපාලන අගුල: ");
    add_bullet("සියලුම විගණන සටහන් ශ්‍රී ලංකා සම්මත වේලාවෙන් (Asia/Colombo UTC+5:30) සහ පරිශීලකයාගේ IP ලිපිනය සහිතව සටහන් වේ.", "• කාල මුද්‍රාව: ");

    add_section_h2("4.3 ගුප්තකේතන ආරක්ෂාව සහ සැසි පාලනය")
    add_bullet("ගොවීන්ගේ 6-ඉලක්කම් රහස් අංක සහ OTP සාමාන්‍ය අංක ලෙස ගබඩා නොකර, සේවාදායකයේ රහස් යතුරක් (Server Secret) සහිතව HMAC-SHA256 ක්‍රමයට ගුප්තකේතනය කර සුරකියි.", "• HMAC-SHA256 ගුප්තකේතනය: ");
    add_bullet("නිලධාරියෙකු තම පරිගණකය විවෘතව තබා මධ්‍යස්ථානයෙන් බැහැරව ගියහොත්, විනාඩි 30 ක අක්‍රියතාවයෙන් පසු පද්ධතිය ස්වයංක්‍රීයව ලොග් අවුට් වේ.", "• විනාඩි 30 ක අක්‍රියතා අගුල (Session Timeout): ");
    add_bullet("පරිපාලක විසින් සාදන නිලධාරී ගිණුම් සඳහා තාවකාලික මුරපදයක් ලබාදෙන අතර, මුල් ලොග් වීමේදීම නව මුරපදයක් සෑදීම අනිවාර්ය වේ (must_change_password=True).", "• අනිවාර්ය මුල් මුරපද වෙනස: ");

    # ==========================================
    # 5. FIELD INFRASTRUCTURE & OFFLINE RESILIENCE
    # ==========================================
    add_section_h1("5. ක්ෂේත්‍ර යටිතල පහසුකම්, දෘඩාංග සහ අන්තර්ජාලය දුර්වල ප්‍රදේශ සඳහා විසඳුම්")
    
    add_section_h2("5.1 ගොවිජන සේවා මධ්‍යස්ථාන සඳහා අවශ්‍ය අවම දෘඩාංග:")
    add_bullet("සාමාන්‍ය පරිගණකයක් හෝ ලැප්ටොප් පරිගණකයක් (Intel Core i3 හෝ ඊට සමාන, 4GB RAM, Windows 10/11 හෝ Ubuntu Linux).", "• පරිගණක උපාංග: ");
    add_bullet("QR කේත ස්කෑන් කිරීම සඳහා පරිගණකයට සම්බන්ධ කළ හැකි සාමාන්‍ය USB වෙබ් කැමරාවක් (උදා: Logitech C270) හෝ ලැප්ටොප් කැමරාව.", "• ස්කෑනර් කැමරා: ");
    add_bullet("රිසිට්පත් මුද්‍රණය සඳහා සාමාන්‍ය POS රිසිට්පත් මුද්‍රණ යන්ත්‍රයක් (Thermal Receipt Printer) හෝ A4 මුද්‍රණ යන්ත්‍රයක්.", "• මුද්‍රණ යන්ත්‍ර: ");
    add_bullet("ග්‍රාමීය ප්‍රදේශවල විදුලි බිඳවැටීම්වලදී අඛණ්ඩව සේවය දීමට 650VA හෝ ඊට වැඩි UPS බැටරි ඒකකයක්.", "• අඛණ්ඩ විදුලි සැපයුම (UPS): ");

    add_section_h2("5.2 අන්තර්ජාලය දුර්වල ප්‍රදේශ සඳහා විසඳුම් (Offline LAN & Low Bandwidth):")
    add_bullet("පද්ධතියේ සියලුම මෝස්තර (Tailwind CSS) සහ ජාවාස්ක්‍රිප්ට් පුස්තකාල (html5-qrcode, qrcode.min.js) බාහිර අන්තර්ජාල සේවාදායකයන්ගෙන් තොරව 100% ක්ම අභ්‍යන්තර ගොනු ලෙස (Local Static Files) ධාවනය වේ. එබැවින් මධ්‍යස්ථානයේ අභ්‍යන්තර ජාලයක් (Local Wi-Fi / LAN) තුළ අන්තර්ජාලය නොමැතිව වුවද ධාවනය කළ හැක.", "• 100% දේශීය ස්ථිතික ගොනු: ");
    add_bullet("ජංගම දුරකථන කැමරා මඟින් QR ස්කෑන් කිරීමට HTTPS අවශ්‍ය වන බැවින්, Cloudflare Tunnel (cloudflared tunnel --url http://127.0.0.1:8000) භාවිතයෙන් ක්ෂණික ආරක්ෂිත HTTPS සබඳතාවක් ගොඩනගාගත හැක.", "• Cloudflare Tunnel තාක්ෂණය: ");
    add_bullet("පද්ධතියේ පවතින විවෘත SMS Backend එක හරහා රජයේ නිල SMS Gateway (Mobitel m-Space, Dialog IdeaMart, Gov SMS) සෘජුවම සම්බන්ධ කළ හැක.", "• ප්ලගීන කළ හැකි SMS ගේට්වේ (Pluggable SMS Gateway): ");

    # ==========================================
    # 6. EMERGENCY PROCEDURES & TROUBLESHOOTING
    # ==========================================
    add_section_h1("6. ක්ෂේත්‍ර හදිසි මෙහෙයුම් සහ ගැටලු නිරාකරණ මාර්ගෝපදේශය (Troubleshooting Guide)")
    add_para(
        "ගොවිජන සේවා මධ්‍යස්ථාන කවුන්ටරවලදී මතුවිය හැකි ප්‍රායෝගික ගැටලු සහ ඊට අදාළ ක්ෂණික නිල විසඳුම්:"
    )

    trouble_table = doc.add_table(rows=7, cols=3)
    trouble_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(trouble_table)
    
    tr_hdrs = ["මතුවන ගැටලුව / සිදුවීම", "මූලික හේතුව (Root Cause)", "ක්ෂේත්‍ර නිලධාරියා ගතයුතු ක්ෂණික පියවර (Field Action)"]
    tr_row0 = trouble_table.rows[0]
    for idx, heading in enumerate(tr_hdrs):
        cell = tr_row0.cells[idx]
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=90, bottom=90, left=110, right=110)
        p = cell.paragraphs[0]
        r = p.add_run(heading)
        format_run(r, size_pt=9.5, bold=True, color_rgb=RGBColor(255, 255, 255))
        
    trouble_data = [
        ("ගොවියාගේ ස්මාර්ට්ෆෝන් තිරය කැඩී ඇත / QR කේතය ස්කෑන් නොවේ", "දුරකථන තිරයේ සීරීම් හෝ ආලෝක පරාවර්තනය.", "කවුන්ටරයේ 'SMS Backup Code' ක්ලික් කර ගොවියාගේ දුරකථනයට 6-ඉලක්කම් කේතය යවා එය ඇතුළත් කරන්න. එසේත් නැත්නම් නිලධාරී මැදිහත්වීමේ (Assisted Issue) ක්‍රමය භාවිත කරන්න."),
        ("ගොවියා ළඟ දුරකථනයක් නොමැත / සිම්පත නැතිවී ඇත", "දුරකථනය නිවසේ අමතක වීම හෝ නොමැතිකම.", "නිලධාරී මැදිහත්වීමේ ක්‍රමය (/distributions/counter/assisted/) තෝරා, ගොවියාගේ මුල් ජාතික හැඳුනුම්පත පරීක්ෂා කර හේතුව සටහන් කරන්න. මධ්‍යස්ථාන ප්‍රධානියා (ASC Head) තම තිරයෙන් අනුමත කළ යුතුය."),
        ("පැමිණි ලොරි රථයේ බෑග් තෙමී හෝ ඉරී ඇත", "ප්‍රවාහනයේදී වැසි ජලය කාන්දු වීම හෝ හැසිරවීමේ දෝෂ.", "හොඳ බෑග් 'හොඳ (Good)' ලෙසත්, හානි වූ බෑග් 'හානි (Damaged)' ලෙසත් ඇතුළත් කරන්න. අනිවාර්ය හේතුව සටහන් කර ලොරි රියදුරුගේ අත්සන භෞතික බිල්පතට ලබාගන්න."),
        ("ගොවියාගේ කෝටා ප්‍රමාණය වැරදි බව ගොවියා පවසයි", "ගොවිජන ලියාපදිංචි ලේඛනයේ මූලික දත්ත දෝෂයක්.", "ප්‍රාදේශීය ගොවිජන සංවර්ධන නිලධාරී දැනුවත් කර, /distributions/entitlements/<id>/edit/ වෙතින් කෝටාව සංශෝධනය කරන්න. පැරණි සහ නව අගයන් විගණන ලේඛනයේ සටහන් වේ."),
        ("නිලධාරියා මුරපදය අමතක වීම නිසා ගිණුම අගුලු වැටී ඇත", "5 වතාවක් වැරදි මුරපදය ඇතුළත් කිරීම.", "පද්ධති පරිපාලක විසින් /accounts/officers/ වෙතින් මුරපදය යළි සකසයි (Reset). ලැබෙන තාවකාලික මුරපදයෙන් ලොග් වී නව මුරපදයක් සකස් කළ යුතුය."),
        ("පොහොර නිකුත් කරමින් සිටියදී විදුලිය හෝ අන්තර්ජාලය ඇණහිටීම", "ජාතික විදුලි බිඳවැටීම හෝ රැහැන් කැඩී යාම.", "PostgreSQL පරමාණුක ගනුදෙනු (ACID) නිසා අඩක් නිමවූ ගනුදෙනු ස්වයංක්‍රීයව අවලංගු (Rollback) වේ. විදුලිය ලැබුණු පසු නැවත QR ස්කෑන් කරන්න. කිසිදු දත්ත දූෂණයක් සිදු නොවේ.")
    ]
    
    for row_idx, data in enumerate(trouble_data, start=1):
        row = trouble_table.rows[row_idx]
        bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx in range(3):
            cell = row.cells[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=70, bottom=70, left=90, right=90)
            p = cell.paragraphs[0]
            r = p.add_run(data[col_idx])
            format_run(r, size_pt=9, bold=(col_idx==0), color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================================
    # 7. SCREEN DIRECTORY & DEMO ACCOUNTS
    # ==========================================
    add_section_h1("7. පද්ධති තිර නාමාවලිය සහ නිරූපණ ගිණුම් (Screen Directory & Credentials)")
    
    add_section_h2("7.1 පූර්ව-වින්‍යාසගත නිරූපණ ගිණුම් (DEMO ONLY Accounts):")
    add_para(
        "විශ්වවිද්‍යාල සහ අමාත්‍යාංශ ඇගයීම් සඳහා පහත ගිණුම් සකස් කර ඇත. සියලුම ගිණුම්වල මුරපදය Password123! වේ:"
    )

    acc_table = doc.add_table(rows=7, cols=5)
    acc_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(acc_table)
    
    a_hdrs = ["භූමිකාව (Role)", "පරිශීලක නාමය", "මුරපදය", "පවරා ඇති ස්ථානය", "ක්‍රියාකාරී වපසරිය"]
    a_row0 = acc_table.rows[0]
    for idx, heading in enumerate(a_hdrs):
        cell = a_row0.cells[idx]
        set_cell_background(cell, "1E3A8A")
        set_cell_margins(cell, top=80, bottom=80, left=90, right=90)
        p = cell.paragraphs[0]
        r = p.add_run(heading)
        format_run(r, size_pt=9, bold=True, color_rgb=RGBColor(255, 255, 255))
        
    acc_data = [
        ("පද්ධති පරිපාලක", "admin", "Password123!", "අමාත්‍යාංශ ප්‍රධාන කාර්යාලය", "පරිශීලකයින්, කන්න, සමස්ත පද්ධති විගණනය"),
        ("මධ්‍යම ගබඩා නිලධාරී", "wh_officer", "Password123!", "උතුරු පළාත් මධ්‍යම ගබඩාව", "කාණ්ඩ සෑදීම, තොග පිටත් කිරීම්"),
        ("ගොවිජන සේවා නිලධාරී", "asc_officer", "Password123!", "වව්නියාව දකුණ ASC මධ්‍යස්ථානය", "QR ස්කෑන් කිරීම, තොග භාරගැනීම, පොහොර නිකුත් කිරීම"),
        ("මධ්‍යස්ථාන ප්‍රධානී", "asc_head", "Password123!", "වව්නියාව දකුණ ASC මධ්‍යස්ථානය", "මැදිහත්වීම් අනුමත කිරීම, තොග ඉවත් කිරීම් අනුමැතිය"),
        ("රජයේ විගණක", "auditor", "Password123!", "විගණකාධිපති දෙපාර්තමේන්තුව", "කියවීමට පමණක් අවසර: විගණන ලේඛන, විෂමතා වාර්තා"),
        ("ලියාපදිංචි ගොවියා", "farmer1", "Password123!", "වව්නියාව දකුණ ASC", "ගොවි පෝටලය, QR උත්පාදනය, ඉතිහාසය පරීක්ෂාව")
    ]
    
    for row_idx, data in enumerate(acc_data, start=1):
        row = acc_table.rows[row_idx]
        bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx in range(5):
            cell = row.cells[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
            p = cell.paragraphs[0]
            r = p.add_run(data[col_idx])
            format_run(r, size_pt=8.5, bold=(col_idx==0), color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    add_section_h2("7.2 ප්‍රධාන පද්ධති තිර නාමාවලිය (URL Navigation Directory):")
    
    url_table = doc.add_table(rows=16, cols=3)
    url_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(url_table)
    
    u_hdrs = ["පද්ධති තිරය (Screen Name)", "URL ලිපිනය (URL Path)", "අවසර ලත් පරිශීලක භූමිකාවන්"]
    u_row0 = url_table.rows[0]
    for idx, heading in enumerate(u_hdrs):
        cell = u_row0.cells[idx]
        set_cell_background(cell, "059669")
        set_cell_margins(cell, top=80, bottom=80, left=100, right=100)
        p = cell.paragraphs[0]
        r = p.add_run(heading)
        format_run(r, size_pt=9, bold=True, color_rgb=RGBColor(255, 255, 255))
        
    url_data = [
        ("පද්ධතියට පිවිසීම (Login)", "/login/", "සියලුම පරිශීලකයින්"),
        ("පරිශීලක උපකරණ පුවරුව (Dashboard)", "/accounts/dashboard/", "භූමිකාවට අදාළ අතුරුමුහුණත"),
        ("නිලධාරී කළමනාකරණය", "/accounts/officers/", "පද්ධති පරිපාලක පමණි"),
        ("ගොවීන් ලියාපදිංචිය සහ කළමනාකරණය", "/distributions/farmers/manage/", "කවුන්ටර නිලධාරී, පරිපාලක"),
        ("දෙපියවර කෝටා CSV පූර්ව නිරීක්ෂණය", "/distributions/entitlements/csv-preview/", "කවුන්ටර නිලධාරී, පරිපාලක"),
        ("ආදර්ශ කෝටා CSV බාගත කිරීම", "/distributions/entitlements/csv-sample/", "කවුන්ටර නිලධාරී, පරිපාලක"),
        ("මධ්‍යම ගබඩා තොග පිටත් කිරීම", "/inventory/dispatches/create/", "ගබඩා නිලධාරී, පරිපාලක"),
        ("ගොවිජන මධ්‍යස්ථානයේදී තොග භාරගැනීම", "/inventory/receiving/", "කවුන්ටර නිලධාරී, මධ්‍යස්ථාන ප්‍රධානී"),
        ("ඩිජිටල් QR කේත ස්කෑනරය", "/distributions/counter/scan/", "කවුන්ටර නිලධාරී, මධ්‍යස්ථාන ප්‍රධානී"),
        ("SMS 6-ඉලක්කම් රහස් අංක තහවුරුව", "/distributions/counter/sms-code/", "කවුන්ටර නිලධාරී, මධ්‍යස්ථාන ප්‍රධානී"),
        ("දුරකථන නොමැති ගොවීන්ගේ ඉල්ලීම්", "/distributions/counter/assisted/", "කවුන්ටර නිලධාරී (ඉල්ලීමට), ප්‍රධානී (අනුමත කිරීමට)"),
        ("කල් ඉකුත් වූ තොග ඉවත් කිරීම (Write-Off)", "/inventory/write-off/", "මධ්‍යස්ථාන ප්‍රධානී, පරිපාලක"),
        ("කණ්ඩායම් අනුව ජීවන චක්‍ර ගවේෂණය", "/distributions/reports/batch-trace/", "විගණක, පරිපාලක, මධ්‍යස්ථාන ප්‍රධානී"),
        ("ප්‍රවාහන හානි සහ විෂමතා වාර්තාව", "/inventory/discrepancies/", "විගණක, පරිපාලක, මධ්‍යස්ථාන ප්‍රධානී"),
        ("වෙනස් කළ නොහැකි විගණන ලේඛනය", "/distributions/audit/logs/", "විගණක, පරිපාලක"),
    ]
    
    for row_idx, data in enumerate(url_data, start=1):
        row = url_table.rows[row_idx]
        bg = "F9FAFB" if row_idx % 2 == 1 else "FFFFFF"
        for col_idx in range(3):
            cell = row.cells[col_idx]
            set_cell_background(cell, bg)
            set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
            p = cell.paragraphs[0]
            r = p.add_run(data[col_idx])
            format_run(r, size_pt=8.5, bold=(col_idx==0), color_rgb=DARK_TEXT)

    doc.add_paragraph().paragraph_format.space_after = Pt(8)

    # ==========================================
    # 8. TEST CERTIFICATION & CONCLUSION
    # ==========================================
    add_section_h1("8. පද්ධති සහතිකකරණය, නිගමනය සහ අනුමැතිය (Certification & Sign-Off)")
    
    add_section_h2("8.1 ස්වයංක්‍රීය පරීක්ෂණ සහතිකකරණය (PostgreSQL Automated Test Certification):")
    add_para(
        "FertiTracker පද්ධතියේ සියලුම ගනුදෙනු, ආරක්ෂණ විධිවිධාන, සමගාමී අගුලු දැමීම් සහ දත්ත වෙනස් කළ නොහැකි බව "
        "PostgreSQL 16 සජීවී දත්ත සමුදාය මත පදනම් වූ ස්වයංක්‍රීය පරීක්ෂණ 60 ක් (60 Test Cases) මඟින් 100% ක් පරික්ෂා කර සහතික කර ඇත:"
    )
    add_bullet("ගිණුම් ආරක්ෂාව, OTP සීමා කිරීම්, අනිවාර්ය මුරපද වෙනස් කිරීම්, තනි සක්‍රීය කන්න නීතිය.", "• Accounts & Security Tests (TC-01 සිට TC-14): ");
    add_bullet("තොග පිටත් කිරීම්, භාරගැනීම්, විෂමතා සටහන් කිරීම් සහ බහු-නූල් (Multi-threaded) සමගාමී පරීක්ෂණ.", "• Inventory & Dispatches Tests (TC-15 සිට TC-21): ");
    add_bullet("තත්පර 60 QR ටෝකන, HMAC-SHA256 SMS රහස් අංක, ද්වි-නිලධාරී අනුමැති සහ එකවර ගනුදෙනු අගුල.", "• Distributions & Counter Tests (TC-22 සිට TC-38): ");
    add_bullet("FEFO කාණ්ඩ වෙන්කිරීම, කල් ඉකුත් වූ තොග නිකුත් කිරීම වැළැක්වීම, බැහැර කිරීම් (Write-offs).", "• FEFO & Expiry Tests (TC-39 සිට TC-42): ");
    add_bullet("AuditLog කිසිදු ආකාරයකින් සංස්කරණය හෝ මකාදැමිය නොහැකි බව තහවුරු කිරීම.", "• AuditLog Immutability Tests (TC-43 සිට TC-46): ");
    add_bullet("ගොවි ජාතික හැඳුනුම්පත් වලංගු කිරීම, දුරකථන ආවරණය කිරීම, දෙපියවර CSV පූර්ව නිරීක්ෂණය සහ UTF-8 BOM.", "• Citizen Security & CSV Tests (TC-47 සිට TC-60): ");
    add_bullet("පරීක්ෂණ 60 න් 60 ම සාර්ථකයි (Ran 60 tests in 69.9s — 100% OK).", "• සමස්ත පරීක්ෂණ ප්‍රතිඵලය: ");

    add_section_h2("8.2 නිගමනය (Conclusion):")
    add_para(
        "FertiTracker පද්ධතිය යනු ශ්‍රී ලංකාවේ කෘෂිකාර්මික සැපයුම් දාමය සහ ගොවි සහනාධාර බෙදාහැරීමේ ක්‍රියාවලිය "
        "නවීන ඩිජිටල් යුගයට ගැළපෙන පරිදි පරිවර්තනය කරන ප්‍රබල, විශ්වාසනීය සහ පූර්ණ විනිවිදභාවයකින් යුතු රාජ්‍ය මට්ටමේ විසඳුමකි. "
        "එය කඩදාසි භාවිතය අවසන් කර, රාජ්‍ය සම්පත් නාස්තිය සහ පොහොර වංචා අවම කරමින්, ශ්‍රී ලාංකේය ගොවි ප්‍රජාවගේ අයිතිවාසිකම් "
        "සුරක්ෂිත කර රටේ ආහාර සුරක්ෂිතතාව ශක්තිමත් කිරීමට සෘජුවම දායක වනු ඇත."
    )

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # Official Sign-Off Box
    sign_table = doc.add_table(rows=2, cols=2)
    sign_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(sign_table)
    
    c0 = sign_table.cell(0, 0)
    c1 = sign_table.cell(0, 1)
    set_cell_background(c0, "F9FAFB")
    set_cell_background(c1, "F9FAFB")
    set_cell_margins(c0, top=120, bottom=120, left=140, right=140)
    set_cell_margins(c1, top=120, bottom=120, left=140, right=140)
    
    p_c0 = c0.paragraphs[0]
    p_c0.add_run("පද්ධති සංවර්ධනය සහ තාක්ෂණික සහතිකකරණය:\n\n").bold = True
    p_c0.add_run(".......................................................\n")
    p_c0.add_run("මෘදුකාංග ඉංජිනේරු අංශය\nතාක්ෂණ අධ්‍යයන පීඨය, වව්නියාව විශ්වවිද්‍යාලය\n(TICT3153 — Software Engineering Project)\nදිනය: 2026/11/09\n")
    
    p_c1 = c1.paragraphs[0]
    p_c1.add_run("රාජ්‍ය මෙහෙයුම් පිළිගැනීම සහ අනුමැතිය:\n\n").bold = True
    p_c1.add_run(".......................................................\n")
    p_c1.add_run("ගොවිජන සංවර්ධන කොමසාරිස් ජනරාල් / නියෝජ්‍ය කොමසාරිස්\nගොවිජන සංවර්ධන දෙපාර්තමේන්තුව\nකෘෂිකර්ම අමාත්‍යාංශය\nදිනය: .......................................\n")

    # Save document
    doc.save(output_path)
    print(f"Successfully generated comprehensive government user manual: {output_path}")

if __name__ == "__main__":
    out_dir = os.path.join(os.getcwd(), "docs")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "FertiTracker_Government_User_Manual_Sinhala.docx")
    create_manual_document(out_file)
