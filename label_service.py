"""
label_service.py — ZPL / TSPL generation, TCP printing, HTML preview, QR redirect logic.

Printer protocol reference
  ZPL II  : Zebra Technologies — default port 9100
  TSPL    : TSC / Elgin / Argox — default port 9100

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
    Return a TSPL command string ready to send to an Elgin/Argox/TSC printer.
    TSPL accepts SIZE in mm but TEXT/QRCODE positions in dots (203 DPI).
    Line endings MUST be CRLF — Elgin L42 Pro firmware requires it.
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
    # Elgin L42 Pro exige CRLF entre comandos
    return "\r\n".join(lines) + "\r\n"


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


def send_to_printer(ip: str, port: int, command: str, encoding: str = "utf-8") -> tuple[bool, str]:
    """
    Envia os comandos TSPL/ZPL para a impressora.

    `encoding` MUST match the charset the command string was built for:
    - ZPL   → "utf-8"   (generate_zpl sets ^CI28, i.e. UTF-8 mode on the printer)
    - TSPL  → "cp1252"  (generate_tspl sets CODEPAGE 1252; TSPL has no UTF-8 mode,
                          so multi-byte UTF-8 would render accented chars as garbage)

    Lógica de detecção:
    - ip sem pontos/dois-pontos → fila CUPS (impressora USB local)
      Tentativas: (1) escrita direta em /dev/usb/lp*  (2) lpr -l  (3) lp -o raw
    - ip com pontos → impressora de rede via TCP socket (porta 9100)
    """
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
