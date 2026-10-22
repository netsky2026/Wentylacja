"""PDF sheet with one controller's connection data for the PLC technician (no password)."""
import io
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

ASSETS = Path(__file__).parent / "assets"
GREEN = colors.HexColor("#09894C")
for name, f in (("DV", "DejaVuSans.ttf"), ("DV-B", "DejaVuSans-Bold.ttf"), ("DV-M", "DejaVuSansMono.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(ASSETS / "fonts" / f)))

ST = {
    "h1": ParagraphStyle("h1", fontName="DV-B", fontSize=15, textColor=GREEN, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName="DV-B", fontSize=11.5, textColor=GREEN, spaceBefore=10, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="DV", fontSize=9.5, leading=13),
    "small": ParagraphStyle("s", fontName="DV", fontSize=8, leading=10.5, textColor=colors.HexColor("#555555")),
    "cell": ParagraphStyle("c", fontName="DV", fontSize=9, leading=11.5),
    "mono": ParagraphStyle("m", fontName="DV-M", fontSize=8.8, leading=11.5),
    "code": ParagraphStyle("code", fontName="DV-M", fontSize=7.6, leading=9.6, backColor=colors.HexColor("#F4F6F5"),
                           borderColor=colors.HexColor("#DDE3E0"), borderWidth=0.5, borderPadding=5),
}


def _table(rows, widths, mono_col=None):
    data = [[Paragraph(str(v), ST["mono"] if i == mono_col and r else ST["cell"]) for i, v in enumerate(row)]
            for r, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF5EF")),
                           ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CFD8D3")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def sample_state(n: int) -> str:
    ch = [{"id": i, "on": True, "heating": False, "mode": "auto", "temp": 21.5, "setpoint": 22.0, "humidity": 65.0,
           "co2": 1200, "curtain_left": 40, "curtain_right": 40, "chimney": 30, "water_lpm": 3.2, "water_total_l": 15432.0}
          for i in range(n)]
    body = json.dumps({"model": "Fatek M", "ack": "", "chambers": ch[:1],
                       "plant": {"power_kw": 4.1, "power_kwh": 12345.6, "water_lpm": 20.0, "water_total_l": 99999.0}},
                      ensure_ascii=False, indent=2)
    if n > 1:
        body = body.replace('"water_total_l": 15432.0\n    }', f'"water_total_l": 15432.0\n    }},\n    ... (komory id 1–{n - 1} – te same pola)')
    return body


def build(dev: dict, chamber_names: list, broker: dict, username: str, topics: tuple, site_url: str, generated: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"Sterownik {dev['device_id']} – dane dla technika", author="Marco Polo Wentylacja")
    logo = Image(str(ASSETS / "marco-polo.png"), width=46 * mm, height=46 * mm * 514 / 1248)
    head = Table([[logo, Paragraph(f"{site_url}<br/>wygenerowano: {generated}", ST["small"])]], colWidths=[100 * mm, 78 * mm])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                              ("LINEBELOW", (0, 0), (-1, 0), 2, GREEN), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    W = 178 * mm
    n = dev["chambers"]
    story = [head, Spacer(1, 8),
             Paragraph(f"Dane sterownika dla technika PLC – {dev['client_name']}", ST["h1"]),
             Paragraph(f"Sterownik: <b>{dev['name']}</b> · ID: <b>{dev['device_id']}</b> · liczba komór: <b>{n}</b>", ST["p"]),
             Paragraph("1. Połączenie MQTT", ST["h2"]),
             _table([["Parametr", "Wartość"],
                     ["Broker (host)", broker["host"]],
                     ["Port", f"{broker['port']}" + (" – TLS (certyfikat Let's Encrypt, CA: ISRG Root X1)" if broker["tls"] else "")],
                     ["Login MQTT", username],
                     ["Hasło MQTT", "przekazywane osobno: ______________________________"],
                     ["Client ID", f"fatek-{dev['device_id']}"],
                     ["Temat stanu (publikuje sterownik)", topics[0]],
                     ["Temat poleceń (subskrybuje sterownik)", topics[1]],
                     ["QoS / Retain / Keep-alive", "1 / nie / 30–60 s"],
                     ["Publikacja stanu", "co 2–5 s (brak danych > 10 s = offline)"]], [62 * mm, W - 62 * mm], mono_col=1),
             Paragraph("2. Komory tego sterownika", ST["h2"]),
             _table([["id w JSON", "Nazwa w panelu"]] + [[str(i), nm] for i, nm in enumerate(chamber_names)], [30 * mm, W - 30 * mm]),
             Paragraph(f"Lista <b>chambers</b> musi zawierać dokładnie <b>{n}</b> element(y) o id 0–{n - 1}.", ST["small"]),
             KeepTogether([Paragraph("3. Przykładowa wiadomość stanu (temat stanu)", ST["h2"]),
                           Preformatted(sample_state(n), ST["code"])]),
             Paragraph("Kurtyny i komin w % <b>otwarcia</b> 0–100. Liczniki <b>water_total_l</b> i <b>power_kwh</b> narastające – "
                       "nie mogą się zerować po zaniku zasilania. Liczby jako liczby JSON, kodowanie UTF-8.", ST["small"]),
             KeepTogether([Paragraph("4. Polecenia (temat poleceń)", ST["h2"]),
                           _table([["type", "value", "Działanie"],
                                   ["set_setpoint", "liczba 5–35 °C", "nowa nastawa temperatury komory (pole chamber)"],
                                   ["set_mode", '"auto" / "manual"', "zmiana trybu komory"],
                                   ["set_vent", "{curtain_left, curtain_right, chimney} 0–100 % otwarcia", "pozycje w trybie ręcznym (1–3 pola)"],
                                   ["ping", "– (request_id)", 'wpisać request_id do pola "ack" i od razu wysłać stan']],
                                  [28 * mm, 62 * mm, W - 90 * mm])]),
             KeepTogether([Paragraph("5. Test uruchomienia", ST["h2"]),
                           Paragraph("1) Wpisz dane z punktu 1 i uruchom publikację stanu. "
                                     "2) Marco Polo otwiera w panelu <b>Podgląd MQTT</b> – wiadomość musi mieć status „Przyjęta”. "
                                     "3) <b>Wyślij test</b> – panel pokaże „Sterownik potwierdził odbiór”. "
                                     "4) Zmień nastawę i tryb ręczny z panelu – sprawdź reakcję sterownika. "
                                     "5) Odłącz internet na 1 min – sterownik ma sam wrócić online.", ST["p"]),
                           Spacer(1, 6),
                           Paragraph(f"Pełna instrukcja: {site_url}/instrukcja-plc.pdf", ST["small"])]),
             ]
    doc.build(story)
    return buf.getvalue()
