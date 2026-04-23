"""
main.py — Interfaz de línea de comandos (CLI) del Agente de Auditoría ISO 27001.

Comandos disponibles:
  audit start     — Inicia o reanuda una sesión de auditoría
  audit status    — Muestra el progreso actual
  audit report    — Genera informes TXT y PDF
  audit load-doc  — Carga un documento ISO al Knowledge Base
  audit reset     — Borra el estado y empieza de cero

Uso:
  python main.py start
  python main.py start --controls A.5.1,A.5.2,A.8.1
  python main.py load-doc ruta/al/iso27001.pdf
  python main.py report
  python main.py status
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich import print as rprint

from config import Config, setup_logging
from knowledge_base import KnowledgeBase
from llm_router import LLMRouter, LLMConnectionError, LLMAPIError
from memory_manager import MemoryManager
from audit_engine import AuditEngine, ANNEX_A_CONTROLS
from report_generator import ReportGenerator

# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────

setup_logging()
logger = logging.getLogger(__name__)

app = typer.Typer(
    name="iso27001-agent",
    help="🔒 Agente IA para Auditorías de Cumplimiento ISO 27001:2022",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

BANNER = """
[bold blue]╔══════════════════════════════════════════════════════════════╗[/bold blue]
[bold blue]║[/bold blue]  [bold white]🔒 AGENTE IA — AUDITORÍA ISO 27001:2022[/bold white]              [bold blue]║[/bold blue]
[bold blue]║[/bold blue]  [dim]Powered by LLM | Arquitectura multi-modelo[/dim]               [bold blue]║[/bold blue]
[bold blue]╚══════════════════════════════════════════════════════════════╝[/bold blue]
"""


def _print_banner() -> None:
    console.print(BANNER)


def _init_components() -> tuple[LLMRouter, KnowledgeBase, MemoryManager]:
    """Inicializa y valida todos los componentes del sistema."""
    try:
        Config.validate()
    except ValueError as exc:
        console.print(f"[red]❌ Error de configuración: {exc}[/red]")
        raise typer.Exit(1)

    # Knowledge Base
    kb = KnowledgeBase()
    docs_loaded = kb.load_directory()
    if docs_loaded == 0:
        console.print(
            "[yellow]⚠️  No se encontraron documentos ISO en el directorio 'knowledge/'.\n"
            "   El agente usará su base de conocimiento interna.\n"
            "   Para mayor precisión, usa: [bold]python main.py load-doc ruta/iso.pdf[/bold][/yellow]"
        )
    else:
        console.print(f"[green]✅ {kb.get_summary()}[/green]")

    # LLM
    console.print(f"[dim]Conectando con backend: {Config.LLM_BACKEND.upper()}...[/dim]")
    try:
        llm = LLMRouter()
    except (LLMConnectionError, LLMAPIError) as exc:
        console.print(f"[red]❌ Error de IA: {exc}[/red]")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red]❌ Error inesperado iniciando IA: {exc}[/red]")
        logger.exception("Error iniciando LLM")
        raise typer.Exit(1)

    # Memory
    memory = MemoryManager()

    return llm, kb, memory


def _ask_audit_setup(memory: MemoryManager) -> bool:
    """
    Pregunta al usuario si quiere reanudar o iniciar nueva auditoría.
    Retorna True si se inicia nueva, False si se reanuda.
    """
    existing = memory.load()
    if existing:
        stats = memory.get_statistics()
        console.print(
            f"\n[green]📂 Auditoría existente encontrada:[/green]\n"
            f"   Organización: [bold]{memory.state.organization}[/bold]\n"
            f"   Inicio: {memory.state.start_date}\n"
            f"   Progreso: {sum(v for k,v in stats.items() if k!='Pendiente')} evaluados | "
            f"{stats['Pendiente']} pendientes\n"
        )
        resume = typer.confirm("¿Desea reanudar esta auditoría?", default=True)
        if resume:
            return False

    # Nueva auditoría
    console.print("\n[bold]📋 CONFIGURACIÓN DE NUEVA AUDITORÍA[/bold]")
    org = typer.prompt("  Nombre de la organización", default=Config.ORGANIZATION_NAME)
    auditor = typer.prompt("  Nombre del auditor", default=Config.AUDITOR_NAME)
    scope = typer.prompt(
        "  Alcance de la auditoría (ej: 'Departamento TI - Sede Madrid')",
        default="SGSI Corporativo"
    )
    memory.initialize_new_audit(organization=org, auditor=auditor, scope_notes=scope)
    return True


# ──────────────────────────────────────────────────────────────────────────────
# Comandos CLI
# ──────────────────────────────────────────────────────────────────────────────

@app.command()
def start(
    controls: Optional[str] = typer.Option(
        None,
        "--controls", "-c",
        help="Lista de controles a auditar separados por coma (ej: A.5.1,A.5.2,A.8.1). "
             "Si no se especifica, audita todos.",
    ),
    skip_done: bool = typer.Option(
        True,
        "--skip-done/--no-skip-done",
        help="Saltar controles ya evaluados al reanudar.",
    ),
) -> None:
    """
    🚀 [bold]Iniciar o reanudar una sesión de auditoría ISO 27001[/bold].

    El agente guiará el proceso control por control, formulando preguntas
    específicas y evaluando las respuestas con IA.
    """
    _print_banner()
    llm, kb, memory = _init_components()

    _ask_audit_setup(memory)

    engine = AuditEngine(llm=llm, kb=kb, memory=memory)

    # Determinar lista de controles a auditar
    if controls:
        control_list = [c.strip().upper() for c in controls.split(",")]
        console.print(f"\n[cyan]🎯 Auditando {len(control_list)} controles específicos.[/cyan]")
    else:
        control_list = engine.get_controls_to_audit()
        console.print(f"\n[cyan]📋 Auditando todos los controles ({len(control_list)} en total).[/cyan]")

    # Filtrar ya evaluados si se reanuda
    if skip_done:
        pending = [c for c in control_list if not memory.is_control_done(c)]
        skipped = len(control_list) - len(pending)
        if skipped > 0:
            console.print(f"[dim]  → {skipped} controles ya evaluados serán omitidos.[/dim]")
        control_list = pending

    memory.set_pending_controls(control_list)

    if not control_list:
        console.print("\n[green]✅ ¡Todos los controles ya han sido evaluados![/green]")
        console.print("   Usa [bold]python main.py report[/bold] para generar el informe.")
        raise typer.Exit()

    console.print(
        f"\n[bold yellow]⚡ Iniciando auditoría: {len(control_list)} controles por evaluar[/bold yellow]"
    )
    console.print("[dim]  Presione Ctrl+C en cualquier momento para pausar. El progreso se guarda automáticamente.[/dim]\n")

    completed = 0
    try:
        for i, control_id in enumerate(control_list, 1):
            console.print(f"\n[dim]Progreso: {i}/{len(control_list)} | Completados: {completed}[/dim]")
            finding = engine.run_control_audit(control_id)
            if finding:
                completed += 1

            # Preguntar si continuar cada 5 controles
            if i % 5 == 0 and i < len(control_list):
                if not typer.confirm(
                    f"\n  ¿Continuar con los siguientes controles? ({len(control_list)-i} restantes)",
                    default=True,
                ):
                    console.print("[yellow]Sesión pausada. El progreso ha sido guardado.[/yellow]")
                    break

    except KeyboardInterrupt:
        console.print("\n\n[yellow]⏸️  Sesión pausada por el usuario. Progreso guardado en estado_auditoria.md[/yellow]")

    # Resumen final de sesión
    stats = memory.get_statistics()
    console.print(f"\n[green]📊 Sesión finalizada:[/green]")
    console.print(f"   ✅ Conformes: {stats['Conforme']}")
    console.print(f"   ❌ No Conformes: {stats['No Conforme']}")
    console.print(f"   ⚠️  Observaciones: {stats['Observación']}")
    console.print(f"   🕐 Pendientes: {stats['Pendiente']}")

    if typer.confirm("\n¿Generar informe ahora?", default=True):
        _run_report(memory)


@app.command()
def status() -> None:
    """
    📊 [bold]Mostrar el estado actual de la auditoría[/bold].
    """
    _print_banner()
    memory = MemoryManager()
    loaded = memory.load()

    if not loaded and not memory.state.findings:
        console.print("[yellow]No hay ninguna auditoría en curso.[/yellow]")
        console.print("Inicia una con: [bold]python main.py start[/bold]")
        return

    stats = memory.get_statistics()
    total = sum(v for k, v in stats.items() if k != "Pendiente")
    conformance = (stats["Conforme"] / total * 100) if total > 0 else 0

    # Panel de estado
    console.print(Panel(
        f"[bold]Organización:[/bold] {memory.state.organization}\n"
        f"[bold]Auditor:[/bold] {memory.state.auditor}\n"
        f"[bold]Inicio:[/bold] {memory.state.start_date}\n"
        f"[bold]Alcance:[/bold] {memory.state.scope_notes}",
        title="📋 Información de la Auditoría",
        border_style="blue",
    ))

    # Tabla de estadísticas
    table = Table(title="📊 Estadísticas de Cumplimiento", show_header=True)
    table.add_column("Estado", style="bold")
    table.add_column("Cantidad", justify="right")
    table.add_column("Indicador")
    table.add_row("✅ Conformes", str(stats["Conforme"]), "[green]" + "█" * stats["Conforme"] + "[/green]")
    table.add_row("❌ No Conformidades", str(stats["No Conforme"]), "[red]" + "█" * stats["No Conforme"] + "[/red]")
    table.add_row("⚠️ Observaciones", str(stats["Observación"]), "[yellow]" + "█" * stats["Observación"] + "[/yellow]")
    table.add_row("➖ No Aplicables", str(stats["No Aplicable"]), "[dim]" + "█" * stats["No Aplicable"] + "[/dim]")
    table.add_row("🕐 Pendientes", str(stats["Pendiente"]), "[cyan]" + "█" * min(stats["Pendiente"], 20) + "[/cyan]")
    table.add_row("[bold]Tasa de Conformidad[/bold]", f"[bold]{conformance:.1f}%[/bold]", "")
    console.print(table)

    # No conformidades destacadas
    nc = memory.get_non_conformities()
    if nc:
        console.print(f"\n[red bold]❌ No Conformidades ({len(nc)}):[/red bold]")
        for f in nc:
            console.print(f"  • [red]{f.control_id}[/red] — {f.title}")
            console.print(f"    [dim]{f.hallazgo[:120]}...[/dim]")


@app.command()
def report(
    format: str = typer.Option(
        "all", "--format", "-f",
        help="Formato de salida: 'txt', 'pdf' o 'all'",
    ),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Ruta de salida del informe (sin extensión)",
    ),
) -> None:
    """
    📄 [bold]Generar informe de auditoría en TXT y/o PDF[/bold].
    """
    _print_banner()
    memory = MemoryManager()
    if not memory.load():
        console.print("[yellow]No hay auditoría cargada. Inicia con: python main.py start[/yellow]")
        raise typer.Exit(1)

    _run_report(memory, format=format, output=output)


def _run_report(
    memory: MemoryManager,
    format: str = "all",
    output: Optional[Path] = None,
) -> None:
    """Función interna para generar informes."""
    gen = ReportGenerator(memory)
    Config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        if format in ("txt", "all"):
            progress.add_task("Generando informe TXT...", total=None)
            path = gen.export_txt(output.with_suffix(".txt") if output else None)
            console.print(f"[green]✅ Informe TXT: [bold]{path}[/bold][/green]")

        if format in ("pdf", "all"):
            progress.add_task("Generando informe PDF...", total=None)
            try:
                path = gen.export_pdf(output.with_suffix(".pdf") if output else None)
                console.print(f"[green]✅ Informe PDF: [bold]{path}[/bold][/green]")
            except RuntimeError as exc:
                console.print(f"[red]❌ Error generando PDF: {exc}[/red]")


@app.command("load-doc")
def load_doc(
    file_path: Path = typer.Argument(
        ...,
        help="Ruta al archivo de documentación ISO (.pdf, .txt, .md)",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    copy_to_knowledge: bool = typer.Option(
        True,
        "--copy/--no-copy",
        help="Copiar el archivo al directorio knowledge/ para uso futuro.",
    ),
) -> None:
    """
    📚 [bold]Cargar un documento ISO 27001 al Knowledge Base[/bold].

    El agente usará este documento para extraer el texto exacto de cada
    control durante la auditoría (inyección de contexto inteligente).
    """
    _print_banner()
    Config.validate()
    kb = KnowledgeBase()

    console.print(f"[cyan]📂 Cargando: {file_path.name}...[/cyan]")

    try:
        kb.load_file(file_path)

        if copy_to_knowledge:
            dest = Config.KNOWLEDGE_DIR / file_path.name
            if not dest.exists():
                import shutil
                shutil.copy2(file_path, dest)
                console.print(f"[green]  ✅ Copiado a knowledge/{file_path.name}[/green]")

        controls = kb.get_all_control_ids()
        console.print(f"[green]✅ Documento cargado exitosamente.[/green]")
        console.print(f"   Controles indexados: {len(controls)}")
        if controls:
            console.print(f"   Muestra: {', '.join(controls[:8])}{'...' if len(controls) > 8 else ''}")

    except Exception as exc:
        console.print(f"[red]❌ Error cargando documento: {exc}[/red]")
        logger.exception("Error en load-doc")
        raise typer.Exit(1)


@app.command()
def reset(
    confirm: bool = typer.Option(
        False, "--yes", "-y",
        help="Confirmar borrado sin preguntar",
    ),
) -> None:
    """
    🗑️  [bold red]Borrar el estado actual de la auditoría[/bold red] y comenzar de cero.
    """
    if not confirm:
        if not typer.confirm(
            "⚠️  Esto borrará TODO el progreso de la auditoría. ¿Continuar?",
            default=False,
        ):
            console.print("[yellow]Operación cancelada.[/yellow]")
            raise typer.Exit()

    state_file = Config.STATE_FILE
    if state_file.exists():
        state_file.unlink()
        console.print(f"[green]✅ Estado borrado: {state_file}[/green]")
    else:
        console.print("[dim]No había estado previo que borrar.[/dim]")


@app.command()
def list_controls() -> None:
    """
    📋 [bold]Listar todos los controles del Anexo A de ISO 27001:2022[/bold].
    """
    _print_banner()
    table = Table(title="Controles del Anexo A — ISO 27001:2022", show_header=True)
    table.add_column("Control ID", style="cyan bold", width=12)
    table.add_column("Título", style="white")
    table.add_column("Cláusula", style="dim", width=14)

    clause_map = {
        "A.5": "Organizacional",
        "A.6": "Personas",
        "A.7": "Físico",
        "A.8": "Tecnológico",
    }

    for ctrl_id, title in ANNEX_A_CONTROLS.items():
        clause_key = ".".join(ctrl_id.split(".")[:2])
        clause = clause_map.get(clause_key, "")
        table.add_row(ctrl_id, title, clause)

    console.print(table)
    console.print(f"\n[dim]Total: {len(ANNEX_A_CONTROLS)} controles[/dim]")


# ──────────────────────────────────────────────────────────────────────────────
# Punto de entrada
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
