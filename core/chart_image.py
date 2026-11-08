"""Trade chart snapshot (PNG): candles + entry / stop-loss / take-profit zones.

Needs Pillow (optional: ``pkg install python-pillow`` on Termux). Without it,
``render_trade_chart`` returns None and notifications go out as text only.
"""
import io

try:
    from PIL import Image, ImageDraw
except Exception:  # pragma: no cover - optional dependency
    Image = ImageDraw = None

BG = (13, 17, 23)
GRID = (33, 38, 45)
TEXT = (201, 209, 217)
UP = (38, 166, 154)
DOWN = (239, 83, 80)
ENTRY = (66, 135, 245)


def render_trade_chart(candles, direction, entry, stop_loss, take_profit,
                       symbol="", width=900, height=560, exit_price=None,
                       timeframe="5m", opened_at=None, closed_at=None):
    """candles: list of dicts with open/high/low/close. Returns PNG bytes or None."""
    if Image is None or not candles:
        return None
    candles = candles[-90:]
    levels = [float(entry), float(stop_loss), float(take_profit)]
    if exit_price is not None:
        levels.append(float(exit_price))
    lo = min(min(float(c["low"]) for c in candles), *levels)
    hi = max(max(float(c["high"]) for c in candles), *levels)
    pad = (hi - lo) * 0.06 or 1.0
    lo, hi = lo - pad, hi + pad

    left, right, top, bottom = 10, 110, 40, 20
    plot_w, plot_h = width - left - right, height - top - bottom

    def y(price):
        return top + (hi - float(price)) / (hi - lo) * plot_h

    img = Image.new("RGBA", (width, height), BG + (255,))
    draw = ImageDraw.Draw(img)
    for i in range(6):
        gy = top + plot_h * i / 5
        draw.line([(left, gy), (left + plot_w, gy)], fill=GRID)
        draw.text((left + plot_w + 6, gy - 5), f"{hi - (hi - lo) * i / 5:.6g}", fill=TEXT)

    # translucent zones
    zones = Image.new("RGBA", img.size, (0, 0, 0, 0))
    zd = ImageDraw.Draw(zones)
    zd.rectangle([left, y(max(entry, stop_loss)), left + plot_w, y(min(entry, stop_loss))],
                 fill=DOWN + (45,))
    zd.rectangle([left, y(max(entry, take_profit)), left + plot_w, y(min(entry, take_profit))],
                 fill=UP + (45,))
    img = Image.alpha_composite(img, zones)
    draw = ImageDraw.Draw(img)

    step = plot_w / len(candles)
    body = max(1.0, step * 0.6)
    for i, c in enumerate(candles):
        x = left + step * i + step / 2
        o, h, l, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
        color = UP if cl >= o else DOWN
        draw.line([(x, y(h)), (x, y(l))], fill=color)
        top_y, bot_y = sorted((y(o), y(cl)))
        draw.rectangle([x - body / 2, top_y, x + body / 2, max(bot_y, top_y + 1)], fill=color)

    chart_levels = [("TP", take_profit, UP), ("ENTRY", entry, ENTRY),
                    ("SL", stop_loss, DOWN)]
    if exit_price is not None:
        chart_levels.append(("EXIT", exit_price, (245, 166, 35)))
    for name, price, color in chart_levels:
        py = y(price)
        draw.line([(left, py), (left + plot_w, py)], fill=color, width=2)
        draw.rectangle([left + plot_w + 2, py - 8, width - 4, py + 8], fill=color)
        draw.text((left + plot_w + 6, py - 5), f"{name} {float(price):.6g}", fill=(255, 255, 255))

    draw.text((left + 6, 12),
              f"{symbol}  {str(direction).upper()}  {timeframe}  DEMO",
              fill=TEXT)
    if opened_at:
        draw.text((left + 6, height - 16),
                  f"OPEN {opened_at}  |  CLOSE {closed_at or '—'}",
                  fill=TEXT)
    out = io.BytesIO()
    img.convert("RGB").save(out, format="PNG")
    return out.getvalue()
