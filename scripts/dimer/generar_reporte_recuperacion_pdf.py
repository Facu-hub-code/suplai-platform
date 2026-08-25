#!/usr/bin/env python3
"""Genera el informe comercial de recuperación WhatsApp para Dimer."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "implementacion" / "dimer" / "outputs" / "Dimer-informe-recuperacion-WhatsApp-ago2026.pdf"

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
NAVY = (18, 42, 74)
ICE = (0, 112, 148)
SLATE = (55, 65, 80)
MUTED = (110, 118, 130)
LINE = (220, 226, 232)
PAPER = (248, 250, 252)
WHITE = (255, 255, 255)
QUOTE_BG = (241, 246, 249)


def clp(n: int) -> str:
    return f"${n:,}".replace(",", ".")


class DimerReport(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4", unit="mm")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_left_margin(16)
        self.set_right_margin(16)
        self.add_font("Arial", "", str(FONT_DIR / "Arial.ttf"))
        self.add_font("Arial", "B", str(FONT_DIR / "Arial Bold.ttf"))
        self.add_font("Arial", "I", str(FONT_DIR / "Arial Italic.ttf"))
        self.add_font("Arial", "BI", str(FONT_DIR / "Arial Bold Italic.ttf"))
        self.set_text_color(*SLATE)

    def header(self) -> None:
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 12, "F")
        self.set_xy(16, 3.2)
        self.set_font("Arial", "", 8)
        self.set_text_color(*WHITE)
        self.cell(118, 6, "Distribuidora Dimer  ·  Informe comercial de recuperación", align="L")
        self.cell(60, 6, "WhatsApp  ·  agosto 2026", align="R")
        self.set_text_color(*SLATE)
        self.set_xy(self.l_margin, 18)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_draw_color(*LINE)
        self.line(16, self.get_y(), 194, self.get_y())
        self.set_y(-12)
        self.set_font("Arial", "", 7.5)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "Uso interno Dimer · sin teléfonos ni datos de contacto  ·  página " + str(self.page_no()), align="C")
        self.set_text_color(*SLATE)

    def h1(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 18)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*SLATE)

    def kicker(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "B", 8)
        self.set_text_color(*ICE)
        self.cell(0, 5, text.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*SLATE)

    def h2(self, text: str) -> None:
        self.set_x(self.l_margin)
        self.ln(2)
        self.set_font("Arial", "B", 12)
        self.set_text_color(*NAVY)
        self.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ICE)
        y = self.get_y()
        self.set_line_width(0.5)
        self.line(16, y, 52, y)
        self.set_line_width(0.2)
        self.ln(3)
        self.set_text_color(*SLATE)

    def body(self, text: str, size: float = 10) -> None:
        self.set_x(self.l_margin)
        self.set_font("Arial", "", size)
        self.set_text_color(*SLATE)
        self.multi_cell(0, 5.2, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1.2)

    def quote(self, text: str, who: str) -> None:
        x = self.l_margin
        y = self.get_y()
        usable = 178
        inner_w = usable - 8
        quoted = f"«{text}»"
        self.set_font("Arial", "I", 9)
        quote_h = self.multi_cell(inner_w, 4.6, quoted, dry_run=True, output="HEIGHT")
        height = 2.5 + quote_h + 4.2 + 3
        self.set_fill_color(*QUOTE_BG)
        self.set_draw_color(*ICE)
        self.set_line_width(0.8)
        self.rect(x, y, usable, height, "F")
        self.line(x, y, x, y + height)
        self.set_line_width(0.2)
        self.set_xy(x + 4, y + 2.5)
        self.set_font("Arial", "I", 9)
        self.set_text_color(*SLATE)
        self.multi_cell(inner_w, 4.6, quoted, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Arial", "", 8)
        self.set_text_color(*MUTED)
        self.set_x(x + 4)
        self.cell(inner_w, 4.2, who, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_xy(self.l_margin, y + height + 2)
        self.set_text_color(*SLATE)

    def ensure(self, mm: float) -> None:
        if self.get_y() + mm > 279:
            self.add_page()

    def case(self, tag: str, title: str, virtue: str, body: str, quote: str, who: str) -> None:
        self.ensure(48)
        self.set_font("Arial", "B", 8)
        self.set_text_color(*ICE)
        self.cell(0, 5, tag.upper(), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Arial", "B", 11)
        self.set_text_color(*NAVY)
        self.cell(0, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font("Arial", "I", 9)
        self.set_text_color(*ICE)
        self.cell(0, 5, virtue, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(0.5)
        self.body(body, size=9.5)
        self.quote(quote, who)


def draw_kpis(pdf: DimerReport) -> None:
    items = [
        ("80", "Mensajes enviados"),
        ("23%", "Tasa de respuesta"),
        ("1", "Pedido confirmado"),
        (clp(104360), "Venta asociada"),
    ]
    y = pdf.get_y()
    w, h, gap = 42.25, 24, 3
    for i, (value, label) in enumerate(items):
        x = 16 + i * (w + gap)
        pdf.set_fill_color(*PAPER)
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.2)
        pdf.rect(x, y, w, h, "FD")
        pdf.set_xy(x, y + 4)
        pdf.set_font("Arial", "B", 16)
        pdf.set_text_color(*NAVY)
        pdf.cell(w, 9, value, align="C")
        pdf.set_xy(x, y + 14)
        pdf.set_font("Arial", "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(w, 6, label, align="C")
    pdf.set_y(y + h + 6)
    pdf.set_x(pdf.l_margin)
    pdf.set_text_color(*SLATE)


def draw_table(pdf: DimerReport) -> None:
    headers = ["", "Grupo 1 · 18/08", "Grupo 2 · 25/08", "Total"]
    rows = [
        ["Enviados y entregados", "30 / 30", "50 / 50", "80 / 80"],
        ["Respondieron", "6 (20%)", "12 (24%)", "18 (23%)"],
        ["Pedido confirmado", "1", "0", "1"],
        ["Monto", clp(104360), "—", clp(104360)],
        ["Horario de envío", "10:00 Chile*", "10:00 Chile", "Puntual"],
    ]
    col_w = [52, 42, 42, 42]
    x0 = 16
    y = pdf.get_y()
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Arial", "B", 8)
    x = x0
    for w, h in zip(col_w, headers):
        pdf.set_xy(x, y)
        pdf.rect(x, y, w, 8, "F")
        pdf.cell(w, 8, h, align="C")
        x += w
    y += 8
    for i, row in enumerate(rows):
        fill = PAPER if i % 2 == 0 else WHITE
        pdf.set_fill_color(*fill)
        x = x0
        for j, (w, cell) in enumerate(zip(col_w, row)):
            pdf.set_xy(x, y)
            pdf.set_draw_color(*LINE)
            pdf.rect(x, y, w, 8, "FD")
            if j == 0:
                pdf.set_font("Arial", "B", 8)
                pdf.set_text_color(*NAVY)
                align = "L"
            else:
                pdf.set_font("Arial", "", 8)
                pdf.set_text_color(*SLATE)
                align = "C"
            pdf.set_xy(x + (1.5 if j == 0 else 0), y)
            pdf.cell(w - (1.5 if j == 0 else 0), 8, cell, align=align)
            x += w
        y += 8
    pdf.set_y(y + 4)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        4,
        "* El envío del 18/08 quedó registrado a las 10:00 del reloj operacional del sistema (Argentina) y salió alrededor de las 09:00 de Chile. El del 25/08 se ajustó para las 10:00 Chile.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_text_color(*SLATE)
    pdf.ln(1)


def build() -> Path:
    pdf = DimerReport()
    pdf.add_page()

    pdf.kicker("Campaña piloto · papas congeladas")
    pdf.h1("Recuperación de clientes por WhatsApp")
    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 6, "Resultados de dos envíos personalizados · 18 y 25 de agosto de 2026", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    draw_kpis(pdf)

    pdf.body(
        "Se contactó a 80 clientes personas naturales de Dimer, con nombre de pila y teléfono móvil chileno válido, "
        "usando un mensaje humano para entender por qué habían dejado de pedir papas. El agente Luis continúa la "
        "conversación: se presenta como equipo de ventas de Dimer, cotiza, respeta al vendedor asignado y deriva a la tienda cuando hace falta."
    )
    pdf.set_fill_color(*QUOTE_BG)
    pdf.set_draw_color(*ICE)
    y = pdf.get_y()
    pdf.rect(16, y, 178, 16, "F")
    pdf.set_xy(20, y + 3)
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(*SLATE)
    pdf.multi_cell(
        170,
        5,
        "«Hola [Nombre], cómo estás? Nos dimos cuenta que hace un tiempo no nos pides Papas, quería saber qué pasó, tuviste algún problema?»",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_y(y + 18)
    pdf.set_x(pdf.l_margin)

    pdf.h2("Resultado de los dos grupos")
    draw_table(pdf)
    pdf.body(
        "Grupo 1: 30 clientes el lunes 18 de agosto. Grupo 2: 50 clientes nuevos el martes 25 de agosto, sin repetir a los del primer envío. "
        "Los 80 mensajes fueron aceptados por WhatsApp. El pedido confirmado es de Cristian (Grupo 1): 4 cajas de Papa One Fry tradicional 9 mm por "
        f"{clp(104360)}, el mismo día del contacto, a través del catálogo."
    )

    pdf.add_page()
    pdf.h2("Cómo conversó el agente")
    pdf.body(
        "Estos casos muestran lo que el canal puede hacer después del primer mensaje: identificar a Dimer, entender el motivo real "
        "(precio, vendedor, sucursal, cierre del local) y avanzar sin pelearse con la fuerza de ventas."
    )

    pdf.case(
        "Grupo 1 · pedido del mismo día",
        "Cristian — de un saludo a 4 cajas",
        "Reconoce el producto, cotiza el formato comercial y cierra en catálogo.",
        "Respondió «buenos días», pidió ver precios y nombró Papa One Fry tradicional de 9 mm. El agente encontró el SKU "
        "(caja 6×2,5 kg), cotizó $26.090 la caja y, cuando pidió 4 cajas, lo dejó en el catálogo. El pedido quedó confirmado: "
        f"4 × One Fry 9 mm = {clp(104360)}.",
        "Si me gustaría ver precios.  /  Papas one fry tradicional de 9 mm.  /  4 cajas.",
        "Cristian · 18 de agosto",
    )
    pdf.case(
        "Grupo 2 · intención de compra",
        "Álvaro — empatía y cotización sin apurar",
        "Acompaña un local cerrado por enfermedad y deja precios listos para cuando reabra.",
        "Avisó que está enfermo, tiene el local cerrado unos días y que pronto va a pedir aceite y papas. El agente saludó, "
        "pasó valores de papas congeladas por caja y esperó: no forzó el pedido. Quedó como el mejor caso comercial del segundo envío.",
        "Estoy enfermo y tengo cerrado, por unos días. Pronto haré un pedido de aceite y papas. Me mandas valores, gracias.",
        "Álvaro · 25 de agosto",
    )
    pdf.case(
        "Grupo 2 · cliente activo",
        "Carlos — no asume que se fue",
        "Corrige el diagnóstico de «perdido» y sigue la conversación por el producto que sí le interesa.",
        "No era un abandono de papas: había comprado 2 cajas McCain la semana pasada, junto con otras cosas. El cambio de proveedor "
        "fue solo en pizza, porque espera ofertas. El agente reconoció que siguen activos con McCain y le mandó el catálogo.",
        "Compré la semana pasada 2 cajas McCain junto con varias otras cosas. Esperando ofertas especialmente pizza. Porque ahí sí cambié de proveedor.",
        "Carlos · 25 de agosto",
    )

    pdf.add_page()
    pdf.case(
        "Grupo 2 · objeción de precio",
        "Pamela — respeta a su vendedora y ataca el precio",
        "Deja el pedido a Fernanda y abre la conversación de papas versus Ariztía.",
        "Pidió identidad, aclaró que le compra a Fernanda y que las papas las saca a Ariztía. Cuando dijo que compra por precio, "
        "el agente no discutió la vendedora: ofreció ver alternativas y el catálogo. Confirma la hipótesis de abandono por precio.",
        "Le pido a Fernanda. Pero las papas las compro a Ariztía.  /  Generalmente compro por precio.",
        "Pamela · 25 de agosto",
    )
    pdf.case(
        "Grupo 1 · cambio de negocio",
        "Daniel — entiende el contexto y deja la puerta abierta",
        "Traduce un cierre de carro de comida en una oportunidad para el arrendatario.",
        "Explicó que el carro de comida estaba lento, que su yerno se fue a Santiago y que decidió arrendarlo en Quintay, Casablanca. "
        "El agente empatizó, pidió datos del punto y le mandó el catálogo para que se lo haga llegar a quien lo tome. También trabaja helados con Dimer.",
        "Lo que pasa es que ahora arrendé el carro de comida. Estaba muy lento todo y mi yerno se fue a Santiago a trabajar.",
        "Daniel · 18 de agosto",
    )
    pdf.case(
        "Grupo 1 · continuidad familiar",
        "David — conversación larga, honesta y útil",
        "Escucha el cambio de titularidad y deja la sucursal en manos del vendedor.",
        "Cerró su local hace más de tres meses; el RUT sigue activo en la sucursal de su señora, más fuerte en plásticos y envases, "
        "con congelados mezclados (papas Dimer, Minuto Verde y otros proveedores). El agente entendió el mapa de compra, recibió el contacto "
        "de ella y se ofreció como apoyo de catálogo y promos, sin reemplazar al vendedor.",
        "Ella sí le compra a Dimer la papa en ciertos calibres y Minuto Verde; los otros artículos los compra en otro lado.",
        "David · 18 de agosto",
    )
    pdf.case(
        "Ambos grupos · no pelea el canal",
        "Cecilia y Christian — ceden al vendedor o a la sucursal",
        "El agente se presenta, aclara quién es Dimer y no disputa la relación humana.",
        "Cecilia (Grupo 2) ya pide a Dimer Belloto: el agente reconoció que es la misma distribuidora y la dejó con su sucursal. "
        "Christian (Grupo 1) dijo que pide seguido y que su vendedor es Gonzalo: el agente se disculpó por el encuadre de «perdido», "
        "confirmó que Gonzalo sigue siendo el vendedor y ofreció cotizar o armar pedido para que él lo vea en el sistema.",
        "Hola, pido a Dimer Belloto.  /  Ya tengo asignado un vendedor, es Gonzalo.",
        "Cecilia · 25 de agosto  ·  Christian · 18 de agosto",
    )

    pdf.ensure(100)
    pdf.h2("Señales para el equipo comercial")
    pdf.body(
        "Además del pedido de Cristian, el agente dejó conversaciones que el equipo de Dimer puede retomar esta semana:"
    )
    bullets = [
        "Cristian ya convirtió: 4 cajas One Fry 9 mm por " + clp(104360) + ".",
        "Álvaro reabre en unos días y pidió valores de aceite y papas: conviene un follow-up humano.",
        "Pamela compra papas a Ariztía por precio; Fernanda sigue siendo su vendedora Dimer.",
        "Carlos sigue en McCain y espera ofertas de pizza.",
        "Alejandra (Grupo 2) avisó que no ha pasado el vendedor.",
        "Cecilia ya está cubierta por Dimer Belloto; no era una pérdida.",
        "Varios del padrón «perdido» siguen comprando o tienen vendedora: sirve para afinar la lista.",
    ]
    pdf.set_font("Arial", "", 9.5)
    for item in bullets:
        pdf.set_x(18)
        pdf.set_text_color(*ICE)
        pdf.cell(4, 5.6, "•")
        pdf.set_text_color(*SLATE)
        pdf.multi_cell(0, 5.6, item, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)
    y = pdf.get_y()
    pdf.set_fill_color(*NAVY)
    pdf.rect(16, y, 178, 28, "F")
    pdf.set_xy(20, y + 3)
    pdf.set_font("Arial", "B", 9)
    pdf.set_text_color(*WHITE)
    pdf.cell(170, 5, "Sugerencia de seguimiento", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_x(20)
    pdf.set_font("Arial", "", 8.5)
    pdf.multi_cell(
        170,
        4.5,
        "Priorizar esta semana a Álvaro (pedido de aceite y papas), Pamela (precio vs Ariztía, con Fernanda), "
        "Alejandra (visita de vendedor) y Carlos (oferta de pizza). El canal WhatsApp ya abrió la conversación; el cierre queda en el equipo comercial.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.set_y(y + 32)
    pdf.set_font("Arial", "I", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        4.8,
        "Fuente: dos envíos WhatsApp a Grupo 1 (18/08) y Grupo 2 (25/08), conversaciones del agente Luis y pedido confirmado en tienda Dimer. "
        "Informe preparado por Suplai el 25 de agosto de 2026.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT))
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(path)
    print(f"bytes={path.stat().st_size}")
