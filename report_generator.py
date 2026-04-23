"""
report_generator.py — Generación de informes de auditoría en TXT y PDF.

Usa:
  - Texto plano estructurado para .txt
  - ReportLab para .pdf (con fallback a FPDF2 si ReportLab no está disponible)
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List

from config import Config
from memory_manager import AuditState, Finding, MemoryManager

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _separator(char: str = "═", width: int = 70) -> str:
    return char * width


def _header_block(title: str, state: AuditState) -> List[str]:
    """Bloque de cabecera para el informe."""
    return [
        _separator(),
        f"  INFORME DE AUDITORÍA ISO 27001:2022",
        _separator(),
        f"  Organización: {state.organization}",
        f"  Auditor:      {state.auditor}",
        f"  Inicio:       {state.start_date}",
        f"  Generado:     {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        _separator(),
        "",
    ]


def _stats_block(memory: MemoryManager) -> List[str]:
    """Bloque de estadísticas."""
    stats = memory.get_statistics()
    total = sum(v for k, v in stats.items() if k != "Pendiente")
    conformance = (stats["Conforme"] / total * 100) if total > 0 else 0
    lines = [
        "RESUMEN EJECUTIVO",
        _separator("─"),
        f"  ✅ Controles Conformes:     {stats['Conforme']:>4}",
        f"  ❌ No Conformidades:        {stats['No Conforme']:>4}",
        f"  ⚠️  Observaciones:           {stats['Observación']:>4}",
        f"  ➖ No Aplicables:           {stats['No Aplicable']:>4}",
        f"  🕐 Pendientes:              {stats['Pendiente']:>4}",
        _separator("─"),
        f"  Tasa de Conformidad:       {conformance:.1f}%",
        "",
    ]
    return lines


def _findings_block(findings: List[Finding], filter_state: str = None) -> List[str]:
    """Bloque de hallazgos (todos o filtrados por estado)."""
    filtered = [f for f in findings if filter_state is None or f.estado == filter_state]
    if not filtered:
        return [f"  (Ningún hallazgo de tipo '{filter_state}')", ""]

    lines = []
    for f in sorted(filtered, key=lambda x: x.control_id):
        emoji = {"Conforme": "[OK]", "No Conforme": "[NC]",
                 "Observación": "[OBS]", "No Aplicable": "[NA]"}.get(f.estado, "[?]")
        lines += [
            f"{emoji} {f.control_id} — {f.title}",
            f"    Fecha:              {f.fecha}",
            f"    Estado:             {f.estado}",
            f"    Hallazgo:           {f.hallazgo}",
            f"    Evidencia req.:     {f.evidencia_requerida}",
            f"    Brecha encontrada:  {f.brecha_encontrada}",
            f"    Respuesta auditado: {f.respuesta_usuario[:200]}{'...' if len(f.respuesta_usuario)>200 else ''}",
            "",
        ]
    return lines


# ──────────────────────────────────────────────────────────────────────────────
# Generador TXT
# ──────────────────────────────────────────────────────────────────────────────

def generate_txt_report(memory: MemoryManager, output_path: Path = None) -> Path:
    """
    Genera el informe completo en texto plano estructurado.
    Retorna la ruta del archivo generado.
    """
    if output_path is None:
        filename = f"informe_iso27001_{_timestamp()}.txt"
        output_path = Config.REPORTS_DIR / filename

    state = memory.state
    findings = memory.get_all_findings()

    lines: List[str] = []
    lines += _header_block("INFORME DE AUDITORÍA ISO 27001:2022", state)
    lines += _stats_block(memory)

    # No conformidades primero (las más críticas)
    nc = memory.get_non_conformities()
    if nc:
        lines += [
            "NO CONFORMIDADES DETECTADAS",
            _separator("─"),
            "",
        ]
        lines += _findings_block(nc, "No Conforme")

    # Observaciones
    obs = memory.get_observations()
    if obs:
        lines += [
            "OBSERVACIONES",
            _separator("─"),
            "",
        ]
        lines += _findings_block(obs, "Observación")

    # Controles conformes
    conf = [f for f in findings if f.estado == "Conforme"]
    if conf:
        lines += [
            "CONTROLES CONFORMES",
            _separator("─"),
            "",
        ]
        lines += _findings_block(conf, "Conforme")

    # No aplicables
    na = [f for f in findings if f.estado == "No Aplicable"]
    if na:
        lines += [
            "CONTROLES NO APLICABLES",
            _separator("─"),
            "",
        ]
        lines += _findings_block(na, "No Aplicable")

    # Pendientes
    if state.pending_controls:
        lines += [
            "CONTROLES PENDIENTES DE AUDITAR",
            _separator("─"),
        ]
        for ctrl in state.pending_controls:
            lines.append(f"  - {ctrl}")
        lines.append("")

    lines += [
        _separator(),
        "  Fin del Informe de Auditoría ISO 27001:2022",
        _separator(),
    ]

    content = "\n".join(lines)
    output_path.write_text(content, encoding="utf-8")
    logger.info("Informe TXT generado: %s", output_path)
    return output_path


# ──────────────────────────────────────────────────────────────────────────────
# Generador PDF (ReportLab)
# ──────────────────────────────────────────────────────────────────────────────

def _generate_pdf_reportlab(memory: MemoryManager, output_path: Path) -> Path:
    """Genera PDF usando ReportLab."""
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import A4  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
    from reportlab.lib.units import cm  # type: ignore
    from reportlab.platypus import (  # type: ignore
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )

    state = memory.state
    findings = memory.get_all_findings()
    stats = memory.get_statistics()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=18, spaceAfter=12, textColor=colors.HexColor("#1a1a2e"),
    )
    style_h1 = ParagraphStyle(
        "H1", parent=styles["Heading1"],
        fontSize=14, spaceAfter=8, textColor=colors.HexColor("#16213e"),
        borderPad=4,
    )
    style_h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=12, spaceAfter=6, textColor=colors.HexColor("#0f3460"),
    )
    style_body = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=13, spaceAfter=4,
    )
    style_nc = ParagraphStyle(
        "NC", parent=style_body, textColor=colors.red,
    )
    style_conf = ParagraphStyle(
        "Conf", parent=style_body, textColor=colors.green,
    )

    story = []

    # ── Portada ──
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("INFORME DE AUDITORÍA ISO 27001:2022", style_title))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e")))
    story.append(Spacer(1, 0.5 * cm))

    meta_data = [
        ["Organización:", state.organization],
        ["Auditor:", state.auditor],
        ["Fecha de inicio:", state.start_date],
        ["Fecha de informe:", datetime.now().strftime("%Y-%m-%d %H:%M")],
        ["Alcance:", state.scope_notes or "No especificado"],
    ]
    meta_table = Table(meta_data, colWidths=[4 * cm, 12 * cm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1a1a2e")),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 1 * cm))

    # ── Resumen ejecutivo ──
    story.append(Paragraph("RESUMEN EJECUTIVO", style_h1))

    total = sum(v for k, v in stats.items() if k != "Pendiente")
    conformance = (stats["Conforme"] / total * 100) if total > 0 else 0

    summary_data = [
        ["Estado", "Cantidad", ""],
        ["✅ Conformes", str(stats["Conforme"]), ""],
        ["❌ No Conformidades", str(stats["No Conforme"]), ""],
        ["⚠️ Observaciones", str(stats["Observación"]), ""],
        ["➖ No Aplicables", str(stats["No Aplicable"]), ""],
        ["🕐 Pendientes", str(stats["Pendiente"]), ""],
        ["Tasa de Conformidad", f"{conformance:.1f}%", ""],
    ]

    summary_table = Table(summary_data, colWidths=[8 * cm, 4 * cm, 4 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#f0f4f8"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 1 * cm))

    # ── Función auxiliar para sección de hallazgos ──
    def add_findings_section(title: str, finding_list: List[Finding], txt_style) -> None:
        if not finding_list:
            return
        story.append(Paragraph(title, style_h1))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.3 * cm))

        for f in sorted(finding_list, key=lambda x: x.control_id):
            story.append(Paragraph(
                f"<b>{f.control_id} — {f.title}</b>", style_h2
            ))
            details = [
                ("Estado:", f.estado),
                ("Fecha:", f.fecha),
                ("Hallazgo:", f.hallazgo),
                ("Evidencia requerida:", f.evidencia_requerida),
                ("Brecha encontrada:", f.brecha_encontrada),
                ("Respuesta auditado:", f.respuesta_usuario[:300] + ("..." if len(f.respuesta_usuario) > 300 else "")),
            ]
            for label, value in details:
                story.append(Paragraph(
                    f"<b>{label}</b> {value}", style_body
                ))
            story.append(Spacer(1, 0.4 * cm))

    add_findings_section("NO CONFORMIDADES", memory.get_non_conformities(), style_nc)
    add_findings_section("OBSERVACIONES", memory.get_observations(), style_body)
    add_findings_section(
        "CONTROLES CONFORMES",
        [f for f in findings if f.estado == "Conforme"],
        style_conf,
    )
    add_findings_section(
        "CONTROLES NO APLICABLES",
        [f for f in findings if f.estado == "No Aplicable"],
        style_body,
    )

    # Pendientes
    if state.pending_controls:
        story.append(Paragraph("CONTROLES PENDIENTES", style_h1))
        for ctrl in state.pending_controls:
            story.append(Paragraph(f"• {ctrl}", style_body))
        story.append(Spacer(1, 0.5 * cm))

    doc.build(story)
    logger.info("Informe PDF (ReportLab) generado: %s", output_path)
    return output_path


def _generate_pdf_fpdf(memory: MemoryManager, output_path: Path) -> Path:
    """Fallback: genera PDF usando FPDF2."""
    from fpdf import FPDF  # type: ignore

    state = memory.state
    findings = memory.get_all_findings()
    stats = memory.get_statistics()

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Título
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "INFORME DE AUDITORIA ISO 27001:2022", ln=True, align="C")
    pdf.ln(5)

    # Metadatos
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Organizacion: {state.organization}", ln=True)
    pdf.cell(0, 7, f"Auditor: {state.auditor}", ln=True)
    pdf.cell(0, 7, f"Inicio: {state.start_date}", ln=True)
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True)
    pdf.ln(5)

    # Resumen
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "RESUMEN", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 7, f"Conformes: {stats['Conforme']}", ln=True)
    pdf.cell(0, 7, f"No Conformidades: {stats['No Conforme']}", ln=True)
    pdf.cell(0, 7, f"Observaciones: {stats['Observacion']}", ln=True)
    pdf.cell(0, 7, f"Pendientes: {stats['Pendiente']}", ln=True)
    pdf.ln(5)

    # Hallazgos
    for f in sorted(findings, key=lambda x: x.control_id):
        pdf.set_font("Helvetica", "B", 11)
        title = f"{f.control_id} - {f.title[:50]}"
        pdf.cell(0, 8, title.encode("latin-1", "replace").decode("latin-1"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        for label, value in [
            ("Estado:", f.estado),
            ("Hallazgo:", f.hallazgo[:200]),
            ("Brecha:", f.brecha_encontrada[:150]),
        ]:
            text = f"{label} {value}"
            pdf.multi_cell(0, 6, text.encode("latin-1", "replace").decode("latin-1"))
        pdf.ln(3)

    pdf.output(str(output_path))
    logger.info("Informe PDF (FPDF) generado: %s", output_path)
    return output_path


def generate_pdf_report(memory: MemoryManager, output_path: Path = None) -> Path:
    """
    Genera el informe en PDF.
    Intenta ReportLab primero, luego FPDF2 como fallback.
    """
    if output_path is None:
        filename = f"informe_iso27001_{_timestamp()}.pdf"
        output_path = Config.REPORTS_DIR / filename

    try:
        return _generate_pdf_reportlab(memory, output_path)
    except ImportError:
        logger.warning("ReportLab no disponible, usando FPDF2...")
    try:
        return _generate_pdf_fpdf(memory, output_path)
    except ImportError as exc:
        raise RuntimeError(
            "No se encontró ReportLab ni FPDF2. "
            "Ejecuta: pip install reportlab fpdf2"
        ) from exc


# ──────────────────────────────────────────────────────────────────────────────
# Interfaz pública
# ──────────────────────────────────────────────────────────────────────────────

class ReportGenerator:
    """Wrapper de conveniencia para generar informes desde main.py."""

    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def export_txt(self, path: Path = None) -> Path:
        return generate_txt_report(self.memory, path)

    def export_pdf(self, path: Path = None) -> Path:
        return generate_pdf_report(self.memory, path)

    def export_all(self) -> dict:
        """Genera ambos formatos y retorna las rutas."""
        ts = _timestamp()
        return {
            "txt": generate_txt_report(
                self.memory, Config.REPORTS_DIR / f"informe_iso27001_{ts}.txt"
            ),
            "pdf": generate_pdf_report(
                self.memory, Config.REPORTS_DIR / f"informe_iso27001_{ts}.pdf"
            ),
        }
