"""
label_service.py — ZPL / TSPL generation, TCP printing, HTML preview, QR redirect logic.

Printer protocol reference
  ZPL II  : Zebra Technologies — default port 9100
  TSPL    : TSC / Elgin / Argox — default port 9100

Coordinate system used in fields_config: millimetres from top-left corner.
At print time, mm values are converted to dots (203 DPI = ~8 dots/mm).
"""

import json
import socket
from datetime import datetime, timedelta
from io import BytesIO

# segno is a pure-Python QR code generator (pip install segno)
try:
    import segno
    _HAS_SEGNO = True
except ImportError:  # pragma: no cover
    _HAS_SEGNO = False

# ── Constants ─────────────────────────────────────────────────────────────────

DPI = 203                        # Standard thermal-printer DPI
DOTS_PER_MM: float = DPI / 25.4  # ≈ 8.0 dots/mm

# Promote-before-expiry window (days): within this window the promo URL is served
PROMO_DAYS_BEFORE_EXPIRY = 3

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mm(mm: float) -> int:
    """Convert millimetres to dots (203 DPI)."""
    return int(mm * DOTS_PER_MM)


def _build_print_data(template_data: dict, batch_data: dict, base_url: str) -> dict:
    """
    Merge template defaults with batch-specific values and inject the dynamic
    QR URL so every field name used in fields_config resolves to a string.
    """
    batch_id = batch_data.get("id", 0)
    data = {
        "product_name": batch_data.get("product_name", "[Produto]"),
        "batch_number": batch_data.get("batch_number", "[Lote]"),
        "production_date": _fmt_date(batch_data.get("production_date")),
        "expiry_date": _fmt_date(batch_data.get("expiry_date")),
        "weight": f'{batch_data.get("weight_kg", 0.0):.3f} kg',
        "ingredients_summary": batch_data.get("ingredients_summary", ""),
        "qr_url": f"{base_url.rstrip('/')}/qr/{batch_id}",
    }
    return data


def _fmt_date(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)


# ── Default fields_config ─────────────────────────────────────────────────────

DEFAULT_FIELDS_CONFIG = json.dumps([
    {"field": "product_name",       "x": 2,  "y": 3,  "font_size_mm": 4.5, "bold": True},
    {"field": "batch_number",       "x": 2,  "y": 10, "font_size_mm": 3,   "bold": False, "label": "Lote"},
    {"field": "production_date",    "x": 2,  "y": 16, "font_size_mm": 3,   "bold": False, "label": "Fab"},
    {"field": "expiry_date",        "x": 2,  "y": 22, "font_size_mm": 3,   "bold": False, "label": "Val"},
    {"field": "weight",             "x": 2,  "y": 28, "font_size_mm": 3,   "bold": False, "label": "Peso"},
    {"field": "ingredients_summary","x": 2,  "y": 34, "font_size_mm": 2.5, "bold": False},
    {"field": "qr_code",            "x": 44, "y": 6,  "size": 28},
], indent=None)


# ── ZPL (Zebra) ───────────────────────────────────────────────────────────────

def generate_zpl(template_data: dict, print_data: dict) -> str:
    """
    Return a ZPL II command string ready to send to a Zebra printer.

    template_data keys: width_mm, height_mm, fields_config (JSON string)
    print_data keys   : product_name, batch_number, expiry_date, weight,
                        ingredients_summary, qr_url, …
    """
    w = _mm(template_data["width_mm"])
    h = _mm(template_data["height_mm"])

    lines = [
        "^XA",
        f"^PW{w}",      # label width
        f"^LL{h}",      # label length
        "^LH0,0",       # label home origin
        "^CI28",        # UTF-8 encoding
    ]

    fields = json.loads(template_data.get("fields_config") or "[]")

    for field in fields:
        x = _mm(field.get("x", 0))
        y = _mm(field.get("y", 0))
        fname = field.get("field", "")

        if fname == "qr_code":
            qr_url = print_data.get("qr_url", "")
            # magnification: size_mm / approx module count → clamp 2-10
            mag = max(2, min(10, int(field.get("size", 25) * DOTS_PER_MM / 30)))
            lines += [
                f"^FO{x},{y}",
                f"^BQN,2,{mag}",
                f"^FDQA,{qr_url}^FS",
            ]
        else:
            text = str(print_data.get(fname, ""))
            label = field.get("label", "")
            if label:
                text = f"{label}: {text}"
            h_dots = _mm(field.get("font_size_mm", 3))
            lines += [
                f"^FO{x},{y}",
                f"^A0N,{h_dots},{h_dots}",
                f"^FD{text}^FS",
            ]

    lines.append("^XZ")
    return "\n".join(lines)


# ── TSPL (Elgin / Argox / TSC) ────────────────────────────────────────────────

def generate_tspl(template_data: dict, print_data: dict) -> str:
    """
    Return a TSPL command string ready to send to an Elgin/Argox/TSC printer.
    TSPL accepts SIZE in mm but TEXT/QRCODE positions in dots (203 DPI).
    """
    w = template_data["width_mm"]
    h = template_data["height_mm"]

    lines = [
        f"SIZE {w} mm, {h} mm",
        "GAP 2 mm, 0 mm",
        "CLS",
    ]

    fields = json.loads(template_data.get("fields_config") or "[]")

    for field in fields:
        x = _mm(field.get("x", 0))
        y = _mm(field.get("y", 0))
        fname = field.get("field", "")

        if fname == "qr_code":
            qr_url = print_data.get("qr_url", "").replace('"', "")
            cell_width = max(1, min(10, int(field.get("size", 25) / 6)))
            lines.append(f'QRCODE {x},{y},L,{cell_width},A,0,"{qr_url}"')
        else:
            text = str(print_data.get(fname, "")).replace('"', "'")
            label = field.get("label", "")
            if label:
                text = f"{label}: {text}"
            scale = max(1, int(field.get("font_size_mm", 3) / 2))
            lines.append(f'TEXT {x},{y},"0",0,{scale},{scale},"{text}"')

    lines.append("PRINT 1,1")
    return "\n".join(lines)


# ── TCP socket send ───────────────────────────────────────────────────────────

def send_to_printer(ip: str, port: int, command: str) -> tuple[bool, str]:
    """
    Open a TCP connection to the printer, send the command string, close.
    Returns (success: bool, message: str).
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(5)
            sock.connect((ip, int(port)))
            sock.sendall(command.encode("utf-8"))
        return True, f"Enviado para {ip}:{port} com sucesso."
    except socket.timeout:
        return False, f"Timeout ao conectar em {ip}:{port}."
    except ConnectionRefusedError:
        return False, f"Conexão recusada em {ip}:{port}. Verifique se a impressora está ligada."
    except OSError as exc:
        return False, f"Erro de rede: {exc}"


# ── QR SVG generation ─────────────────────────────────────────────────────────

def _qr_svg(data: str, size_mm: float, scale: int) -> str:
    """Return an inline SVG string for the given QR data."""
    if _HAS_SEGNO:
        try:
            qr = segno.make(data, micro=False, error="m")
            buf = BytesIO()
            qr.save(buf, kind="svg", scale=scale, border=1,
                    dark="black", light="white")
            svg = buf.getvalue().decode("utf-8")
            start = svg.find("<svg")
            return svg[start:] if start >= 0 else svg
        except Exception:
            pass  # fall through to placeholder

    # Fallback placeholder
    px = int(size_mm * scale)
    return (
        f'<svg width="{px}" height="{px}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{px}" height="{px}" fill="white" stroke="black" stroke-width="1.5"/>'
        f'<text x="50%" y="50%" font-size="9" text-anchor="middle" dy=".35em" '
        f'font-family="monospace">QR</text></svg>'
    )


# ── HTML preview ──────────────────────────────────────────────────────────────

def generate_preview_html(template_data: dict, print_data: dict) -> str:
    """
    Return an HTML fragment (a single <div>) that visually simulates the
    physical thermal label: white background, black text, monospace font,
    proportional to the configured dimensions.

    Scale: 3.8 px/mm  → a 62 × 40 mm label renders as 236 × 152 px.
    """
    scale = 3.8  # px per mm
    w_px = int(template_data["width_mm"] * scale)
    h_px = int(template_data["height_mm"] * scale)

    fields = json.loads(template_data.get("fields_config") or "[]")
    elements: list[str] = []

    for field in fields:
        x_px = int(field.get("x", 0) * scale)
        y_px = int(field.get("y", 0) * scale)
        fname = field.get("field", "")

        if fname == "qr_code":
            qr_url = print_data.get("qr_url", "https://smartfood.app/qr/0")
            size_mm = field.get("size", 25)
            svg = _qr_svg(qr_url, size_mm, scale=int(scale))
            elements.append(
                f'<div style="position:absolute;left:{x_px}px;top:{y_px}px;'
                f'line-height:0">{svg}</div>'
            )
        else:
            text = str(print_data.get(fname, f"[{fname}]"))
            label = field.get("label", "")
            if label:
                text = f"{label}: {text}"
            fs_px = max(7, int(field.get("font_size_mm", 3) * scale * 0.65))
            bold = "font-weight:bold;" if field.get("bold") else ""
            elements.append(
                f'<span style="position:absolute;left:{x_px}px;top:{y_px}px;'
                f'font-size:{fs_px}px;{bold}white-space:nowrap;color:black;">'
                f'{text}</span>'
            )

    inner = "\n".join(elements)
    return (
        f'<div style="width:{w_px}px;height:{h_px}px;background:white;'
        f'border:2px solid #111;position:relative;'
        f'font-family:\'Courier New\',Courier,monospace;overflow:hidden;'
        f'box-shadow:3px 3px 8px rgba(0,0,0,.5);">'
        f'{inner}</div>'
    )


# ── QR redirect logic ─────────────────────────────────────────────────────────

def resolve_qr_url(expiry_date: datetime, tutorial_url: str, promo_url: str) -> str:
    """
    Return the URL that a QR code scan should redirect to.

    Logic:
      • If expiry_date is within PROMO_DAYS_BEFORE_EXPIRY days (or already past):
          → return promo_url  (e.g. a discount/clearance page)
      • Otherwise:
          → return tutorial_url  (e.g. a recipe/preparation video)

    Falls back to tutorial_url if either URL is empty.
    """
    now = datetime.utcnow()
    cutoff = expiry_date - timedelta(days=PROMO_DAYS_BEFORE_EXPIRY)
    use_promo = (now >= cutoff) and bool(promo_url)
    return promo_url if use_promo else (tutorial_url or "/")
