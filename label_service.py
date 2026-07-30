"""
label_service.py — ZPL / TSPL / PPLB generation, TCP printing, HTML preview, QR redirect logic.

Printer protocol reference
  ZPL II  : Zebra Technologies — default port 9100
  TSPL    : TSC / Elgin / Argox — default port 9100 (NOT officially listed by Elgin
            for the L42 Pro Full — its spec sheet says "EPL ZPL PPLA PPLB" only;
            if a printer just echoes the raw command text as label content
            instead of executing it, that printer doesn't understand TSPL —
            use PPLB instead, which IS Elgin's documented factory language)
  PPLB    : Elgin's native Eltron/EPL-style language (factory default on the L42).
            No native QR symbology (only PDF417/MaxiCode), and its internal
            fonts (1-5 + integer H/V multiplier) have no documented mm size —
            on-printer testing (2026-07-30, L42 Pro Full) showed the "A" text
            command's multiplier scaling badly overshoots width relative to
            height (font_size_mm=6 measured 7mm tall but wide enough to
            overrun an adjacent field 51mm away). So both QR *and* text are
            rendered as raster bitmaps and sent via the GW image command —
            this makes printed size a direct mm→pixel calculation instead of
            a guess about the printer's internal font metrics.

Coordinate system used in fields_config: millimetres from top-left corner.
At print time, mm values are converted to dots (203 DPI = ~8 dots/mm).
"""

import glob
import json
import os
import socket
import subprocess
import shutil
from datetime import datetime, timedelta
from io import BytesIO

# segno is a pure-Python QR code generator (pip install segno)
try:
    import segno
    _HAS_SEGNO = True
except ImportError:  # pragma: no cover
    _HAS_SEGNO = False

# Pillow is used only by the PPLB path, to raster text at an exact mm size
# (see the PPLB note above for why we don't trust the printer's own fonts)
try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False

# ── Constants ─────────────────────────────────────────────────────────────────

DPI = 203                        # Standard thermal-printer DPI
DOTS_PER_MM: float = DPI / 25.4  # ≈ 8.0 dots/mm

# Promote-before-expiry window (days): within this window the promo URL is served
PROMO_DAYS_BEFORE_EXPIRY = 3

# ── Helpers ───────────────────────────────────────────────────────────────────

def _mm(mm: float) -> int:
    """Convert millimetres to dots (203 DPI)."""
    return int(mm * DOTS_PER_MM)


def _build_print_data(batch_data: dict, base_url: str) -> dict:
    """
    Build the print data dict from batch values and inject the dynamic QR URL
    so every field name used in fields_config resolves to a string.
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


# ── QR sizing ─────────────────────────────────────────────────────────────────
# QR "size" in fields_config is the desired physical side length in mm. The
# printer (and segno, for the on-screen preview) picks the module count from
# the payload + error-correction level, so we simulate that with segno to
# convert "size in mm" into the printer's real dots-per-module / preview's
# pixels-per-module — keeping ZPL, TSPL and the preview all at the same
# physical size instead of each using its own ad-hoc scaling formula.

QR_ECC_SEGNO = "q"   # segno's error param (lowercase) — mirrors TSPL "Q" / ZPL "QA," below
_QR_FALLBACK_MODULES = 33  # used only if segno isn't installed


def _qr_module_count(data: str) -> int:
    """Modules per side of the QR symbol segno/the printer will generate for `data`."""
    if _HAS_SEGNO:
        try:
            qr = segno.make(data, micro=False, error=QR_ECC_SEGNO)
            return qr.symbol_size(border=0)[0]
        except Exception:
            pass
    return _QR_FALLBACK_MODULES


# ── ZPL (Zebra) ───────────────────────────────────────────────────────────────

def generate_zpl(template_data: dict, print_data: dict, quantity: int = 1) -> str:
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
            size_mm = field.get("size", 25)
            modules = _qr_module_count(qr_url)
            mag = max(2, min(10, round(size_mm * DOTS_PER_MM / modules)))
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

    lines.append(f"^PQ{max(1, quantity)}")
    lines.append("^XZ")
    return "\n".join(lines)


# ── TSPL (Elgin / Argox / TSC) ────────────────────────────────────────────────

def generate_tspl(template_data: dict, print_data: dict, quantity: int = 1) -> str:
    """
    Return a TSPL command string ready to send to a TSC/Argox printer (or an
    Elgin unit whose firmware has real TSPL2 compatibility).
    TSPL accepts SIZE in mm but TEXT/QRCODE positions in dots (203 DPI).
    Line endings use CRLF per the TSPL2 spec.

    NOTE: Elgin's official spec sheet for the L42 Pro Full lists only
    "EPL ZPL PPLA PPLB" as supported languages — TSPL is not on that list.
    If the printer prints the command text itself as label content instead of
    executing it, that means it doesn't understand TSPL — use generate_pplb()
    instead, which targets Elgin's documented native language.
    """
    w = template_data["width_mm"]
    h = template_data["height_mm"]

    lines = [
        f"SIZE {w} mm, {h} mm",
        "GAP 2 mm, 0 mm",
        "CODEPAGE 1252",   # Windows-1252 (Latin1) — required for á/ç/ã/õ etc; must
                           # match the encoding used when the command is sent (see
                           # send_to_printer's `encoding` argument).
        "CLS",
    ]

    fields = json.loads(template_data.get("fields_config") or "[]")

    for field in fields:
        x = _mm(field.get("x", 0))
        y = _mm(field.get("y", 0))
        fname = field.get("field", "")

        if fname == "qr_code":
            qr_url = print_data.get("qr_url", "").replace('"', "")
            size_mm = field.get("size", 25)
            modules = _qr_module_count(qr_url)
            cell_width = max(2, min(10, round(size_mm * DOTS_PER_MM / modules)))
            lines.append(f'QRCODE {x},{y},Q,{cell_width},A,0,M2,"{qr_url}"')
        else:
            text = str(print_data.get(fname, "")).replace('"', "'")
            label = field.get("label", "")
            if label:
                text = f"{label}: {text}"
            scale = max(1, int(field.get("font_size_mm", 3) / 2))
            lines.append(f'TEXT {x},{y},"0",0,{scale},{scale},"{text}"')

    lines.append(f"PRINT {max(1, quantity)},1")
    return "\r\n".join(lines) + "\r\n"


# ── PPLB (Elgin's native factory language, Eltron/EPL-style) ──────────────────
# Source: Elgin L42 "Manual de Programação" v3.0 (BPLB command set). Every
# command line ends in a bare LF (not CRLF). Params are comma-separated with
# NO spaces. Coordinates are in dots (8 dots/mm @ 203dpi), same as TSPL/ZPL.
#
# Text is rendered as a raster bitmap (via Pillow) and sent through the same
# GW image command used for the QR code, rather than the native "A" text
# command — see the module docstring for why: the internal fonts' mm size
# isn't documented, and on-printer testing showed the multiplier scaling
# overshoots width badly relative to height.

_PPLB_ENCODING = "cp850"  # DOS850/Latin1 — "I8,1,001" below, documented as the
                          # common choice for Brazilian Portuguese on this printer

_pplb_font_cache: dict[int, "ImageFont.FreeTypeFont"] = {}


def _pplb_font(px: int) -> "ImageFont.FreeTypeFont":
    font = _pplb_font_cache.get(px)
    if font is None:
        font = ImageFont.load_default(size=px)
        _pplb_font_cache[px] = font
    return font


def _text_raster_pplb(text: str, font_size_mm: float, bold: bool = False) -> tuple[bytes, int, int, int]:
    """
    Render `text` as a 1-bit raster bitmap at an exact physical height (mm),
    for PPLB's GW (binary image) command — see module docstring for why we
    don't use PPLB's native "A" text command.

    Returns (packed_bytes, bytes_per_row, width_px, height_px); (b"", 0, 0, 0)
    if Pillow isn't installed or the text is empty (caller skips the field).
    """
    if not _HAS_PIL or not text:
        return b"", 0, 0, 0

    px = max(6, round(font_size_mm * DOTS_PER_MM))
    font = _pplb_font(px)

    probe = ImageDraw.Draw(Image.new("1", (1, 1), 1))
    bbox = probe.textbbox((0, 0), text, font=font)
    w = max(1, bbox[2] - bbox[0]) + (1 if bold else 0)  # +1px slack for the synthetic-bold pass
    h = max(1, bbox[3] - bbox[1])

    img = Image.new("1", (w, h), 1)  # white background
    draw = ImageDraw.Draw(img)
    draw.text((-bbox[0], -bbox[1]), text, font=font, fill=0)
    if bold:
        draw.text((-bbox[0] + 1, -bbox[1]), text, font=font, fill=0)  # synthetic bold: redraw offset 1px

    bytes_per_row = (w + 7) // 8
    raster = bytearray(bytes_per_row * h)
    pixels = img.load()
    for py in range(h):
        row_offset = py * bytes_per_row
        for px_ in range(w):
            if pixels[px_, py] == 0:  # 0 = black
                raster[row_offset + (px_ // 8)] |= (0x80 >> (px_ % 8))

    return bytes(raster), bytes_per_row, w, h


def _qr_raster_pplb(data: str, size_mm: float) -> tuple[bytes, int, int]:
    """
    Render `data` as a 1-bit QR raster bitmap for PPLB's GW (binary image) command.
    PPLB has no native QR symbology (only PDF417/MaxiCode — see the 'b' command),
    so the QR has to be drawn as pixels here rather than generated by the printer.

    Returns (packed_bytes, bytes_per_row, side_px); (b"", 0, 0) if segno isn't
    installed — the caller skips the QR field rather than failing the whole label.
    """
    if not _HAS_SEGNO:
        return b"", 0, 0
    try:
        qr = segno.make(data, micro=False, error=QR_ECC_SEGNO)
    except Exception:
        return b"", 0, 0

    modules = qr.symbol_size(border=0)[0]
    matrix = qr.matrix  # sequence of rows; each row supports bool/int indexing per module
    dots_per_module = max(1, round(size_mm * DOTS_PER_MM / modules))
    border_modules = 2  # quiet zone required for reliable scanning
    side_px = (modules + 2 * border_modules) * dots_per_module
    bytes_per_row = (side_px + 7) // 8

    raster = bytearray(bytes_per_row * side_px)
    for py in range(side_px):
        module_row = py // dots_per_module - border_modules
        if not (0 <= module_row < modules):
            continue  # quiet zone / out of bounds → stays white (0)
        row = matrix[module_row]
        row_offset = py * bytes_per_row
        for px in range(side_px):
            module_col = px // dots_per_module - border_modules
            if 0 <= module_col < modules and row[module_col]:
                raster[row_offset + (px // 8)] |= (0x80 >> (px % 8))

    return bytes(raster), bytes_per_row, side_px


def generate_pplb(template_data: dict, print_data: dict, quantity: int = 1) -> bytes:
    """
    Return raw PPLB bytes ready to send to an Elgin printer's native (factory
    default) language. Returns bytes rather than str because the QR field is
    embedded as inline binary raster data (see _qr_raster_pplb) — arbitrary
    binary can't safely round-trip through a text encoding.
    """
    w = _mm(template_data["width_mm"])
    h = _mm(template_data["height_mm"])

    def line(s: str) -> bytes:
        return (s + "\n").encode(_PPLB_ENCODING, errors="replace")

    out = bytearray()
    out += line("N")            # clear print buffer — start of a new label
    out += line("I8,1,001")     # code page 850 (Latin1) — most common in Brazil
    out += line(f"Q{h},24")     # label height + ~3mm gap between labels
    out += line(f"q{w}")        # total print width
    out += line("ZT")           # print head-first (top-down)
    out += line("S2")           # 2 in/s — conservative default speed
    out += line("D8")           # mid-range heat/density

    fields = json.loads(template_data.get("fields_config") or "[]")

    for field in fields:
        x = _mm(field.get("x", 0))
        y = _mm(field.get("y", 0))
        fname = field.get("field", "")

        if fname == "qr_code":
            qr_url = print_data.get("qr_url", "")
            size_mm = field.get("size", 25)
            raster, bytes_per_row, side_px = _qr_raster_pplb(qr_url, size_mm)
            if raster:
                out += f"GW{x},{y},{bytes_per_row},{side_px}".encode(_PPLB_ENCODING) + b"\n"
                out += raster
                out += b"\n"
        else:
            text = str(print_data.get(fname, ""))
            label = field.get("label", "")
            if label:
                text = f"{label}: {text}"
            font_size_mm = field.get("font_size_mm", 3)
            bold = bool(field.get("bold"))

            raster, bytes_per_row, w_px, h_px = _text_raster_pplb(text, font_size_mm, bold)
            if raster:
                out += f"GW{x},{y},{bytes_per_row},{h_px}".encode(_PPLB_ENCODING) + b"\n"
                out += raster
                out += b"\n"
            elif text:
                # Fallback if Pillow isn't installed: PPLB's native "A" text command.
                # mult calibrated from an on-printer measurement (2026-07-30, L42 Pro
                # Full, internal font 2): height_mm ≈ 1.5*mult + 1 → mult = (h-1)/1.5.
                # This still won't match width precisely (see module docstring) —
                # install Pillow for accurate WYSIWYG sizing.
                mult = max(1, min(8, round((font_size_mm - 1) / 1.5)))
                safe_text = text.replace('"', "'")
                out += line(f'A{x},{y},0,2,{mult},{mult},N,"{safe_text}"')

    out += line(f"P1,{max(1, quantity)}")
    return bytes(out)


# ── USB / CUPS / TCP printing ─────────────────────────────────────────────────

def _find_usb_device() -> str | None:
    """Return the first available USB printer device file (/dev/usb/lp* or /dev/lp*)."""
    candidates = sorted(glob.glob("/dev/usb/lp*")) + sorted(glob.glob("/dev/lp*"))
    for dev in candidates:
        if os.path.exists(dev):
            return dev
    return None


def _print_usb_direct(data: bytes) -> tuple[bool, str]:
    """Write raw bytes directly to the USB printer device, bypassing CUPS filters."""
    dev = _find_usb_device()
    if not dev:
        return False, "Dispositivo USB não encontrado em /dev/usb/lp* ou /dev/lp*."
    try:
        with open(dev, "wb") as f:
            f.write(data)
        return True, f"Enviado diretamente para {dev} (USB raw)."
    except PermissionError:
        return False, (
            f"Sem permissão para escrever em {dev}. "
            "Execute: sudo usermod -aG lp smartfood && sudo systemctl restart smartfood"
        )
    except OSError as exc:
        return False, f"Erro ao escrever em {dev}: {exc}"


def _print_via_lpr(queue: str, data: bytes) -> tuple[bool, str]:
    """Send raw bytes via lpr -l (literal mode — bypasses CUPS driver filters)."""
    if not shutil.which("lpr"):
        return False, "Comando 'lpr' não encontrado."
    try:
        p = subprocess.Popen(
            ["lpr", "-P", queue, "-l"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        _, stderr = p.communicate(input=data, timeout=10)
        if p.returncode == 0:
            return True, f"Enviado para fila CUPS '{queue}' (modo literal)."
        err = stderr.decode("utf-8", errors="replace").strip()
        return False, f"lpr erro: {err}"
    except Exception as exc:
        return False, f"lpr exceção: {exc}"


def send_to_printer(ip: str, port: int, command: "str | bytes", encoding: str = "utf-8") -> tuple[bool, str]:
    """
    Envia os comandos TSPL/ZPL/PPLB para a impressora.

    `command` may be str (ZPL/TSPL — encoded here using `encoding`) or bytes
    (PPLB — already encoded by generate_pplb, since it embeds a binary QR
    raster that can't safely round-trip through a text encoding).

    `encoding` MUST match the charset the command string was built for:
    - ZPL   → "utf-8"   (generate_zpl sets ^CI28, i.e. UTF-8 mode on the printer)
    - TSPL  → "cp1252"  (generate_tspl sets CODEPAGE 1252; TSPL has no UTF-8 mode,
                          so multi-byte UTF-8 would render accented chars as garbage)

    Lógica de detecção:
    - ip sem pontos/dois-pontos → fila CUPS (impressora USB local)
      Tentativas: (1) escrita direta em /dev/usb/lp*  (2) lpr -l  (3) lp -o raw
    - ip com pontos → impressora de rede via TCP socket (porta 9100)
    """
    if isinstance(command, bytes):
        data = command
    else:
        try:
            data = command.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            data = command.encode(encoding, errors="replace")

    is_local_queue = ip and not any(c in ip for c in (".", ":"))

    if is_local_queue:
        # 1. Fila CUPS raw — método mais confiável quando a fila está em modo raw
        if shutil.which("lp"):
            try:
                p = subprocess.Popen(
                    ["lp", "-d", ip],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                _, stderr = p.communicate(input=data, timeout=10)
                if p.returncode == 0:
                    return True, f"Enviado para fila CUPS '{ip}'."
            except Exception:
                pass
            # Se lp falhou, tenta lpr -l
            ok, msg = _print_via_lpr(ip, data)
            if ok:
                return ok, msg

        # 2. Escrita direta no dispositivo USB (fallback)
        ok, msg = _print_usb_direct(data)
        if ok:
            return ok, msg

        return False, f"Falha ao imprimir em '{ip}'. Verifique: lpstat -v | grep {ip}"

    # ── TCP socket para impressoras de rede ───────────────────────────────────
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(8)
            sock.connect((ip, int(port)))
            sock.sendall(data)
            sock.shutdown(socket.SHUT_WR)
            try:
                sock.recv(256)
            except Exception:
                pass
        return True, f"Enviado para {ip}:{port} com sucesso."
    except socket.timeout:
        return False, f"Timeout em {ip}:{port}. Impressora fora da rede."
    except ConnectionRefusedError:
        return False, f"Conexão recusada em {ip}:{port}. Impressora desligada ou IP errado."
    except OSError as exc:
        return False, f"Erro de rede: {exc}"


def enviar_teste_impressora(ip: str, port: int = 9100) -> tuple[bool, str]:
    """Envia um print de teste mínimo (TSPL) para verificar conectividade."""
    cmd = "\r\n".join([
        "SIZE 100 mm, 50 mm",
        "GAP 2 mm, 0 mm",
        "CODEPAGE 1252",
        "CLS",
        'TEXT 16,8,"0",0,2,2,"SmartFood Ops 360"',
        'TEXT 16,60,"0",0,1,1,"Teste de impressao OK"',
        'TEXT 16,90,"0",0,1,1,"Elgin L42 Pro"',
        "PRINT 1,1",
    ]) + "\r\n"
    return send_to_printer(ip, port, cmd, encoding="cp1252")


# ── QR SVG generation ─────────────────────────────────────────────────────────

def _qr_svg(data: str, size_mm: float, px_per_mm: float, module_scale_px: int) -> str:
    """Return an inline SVG string for the given QR data, sized to size_mm at px_per_mm."""
    if _HAS_SEGNO:
        try:
            qr = segno.make(data, micro=False, error=QR_ECC_SEGNO)
            buf = BytesIO()
            qr.save(buf, kind="svg", scale=max(1, module_scale_px), border=1,
                    dark="black", light="white")
            svg = buf.getvalue().decode("utf-8")
            start = svg.find("<svg")
            return svg[start:] if start >= 0 else svg
        except Exception:
            pass  # fall through to placeholder

    # Fallback placeholder
    px = int(size_mm * px_per_mm)
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
            modules = _qr_module_count(qr_url)
            module_scale_px = round(size_mm * scale / modules)
            svg = _qr_svg(qr_url, size_mm, scale, module_scale_px)
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
        f'font-family:\'Courier New\',Courier,monospace;overflow:visible;'
        f'box-shadow:3px 3px 8px rgba(0,0,0,.5);">'
        f'{inner}</div>'
    )


# ── QR redirect logic ─────────────────────────────────────────────────────────

def resolve_qr_url(
    expiry_date: datetime,
    tutorial_url: str,
    promo_url: str,
    batch_id: int | None = None,
) -> str:
    """Return the URL that a QR code scan should redirect to.

    Within PROMO_DAYS_BEFORE_EXPIRY days of expiry → promo_url.
    Otherwise → tutorial_url. Falls back to /produto/{batch_id} if no tutorial_url.
    """
    now = datetime.utcnow()
    cutoff = expiry_date - timedelta(days=PROMO_DAYS_BEFORE_EXPIRY)
    use_promo = (now >= cutoff) and bool(promo_url)
    if use_promo:
        return promo_url
    if not tutorial_url and batch_id:
        return f"/produto/{batch_id}"
    return tutorial_url or "/"
