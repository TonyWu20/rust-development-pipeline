#!/usr/bin/env python3
"""Generate 1080x1440 cards from INTRODUCTION-zh.md with clean typography."""

from PIL import Image, ImageDraw, ImageFont
import textwrap
import os
import re

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = SCRIPT_DIR
NOTO_CJK = "/Library/Fonts/Nix Fonts/xsvgxlrih9120rbj2vh7qbrvg1bsvv96-noto-fonts-cjk-sans-2.004/share/fonts/opentype/noto-cjk/NotoSansCJK-VF.otf.ttc"
NOTO_MONO = "/Library/Fonts/Nix Fonts/xsvgxlrih9120rbj2vh7qbrvg1bsvv96-noto-fonts-cjk-sans-2.004/share/fonts/opentype/noto-cjk/NotoSansMonoCJK-VF.otf.ttc"
SOURCE_SANS_REGULAR = "/Library/Fonts/Nix Fonts/2sbrq4vj0fzg3kda0jxnbkbphdynw28y-source-sans-pro-3.006/share/fonts/truetype/SourceSansPro-Regular.ttf"
SOURCE_SANS_BOLD = "/Library/Fonts/Nix Fonts/2sbrq4vj0fzg3kda0jxnbkbphdynw28y-source-sans-pro-3.006/share/fonts/truetype/SourceSansPro-Bold.ttf"
SOURCE_SANS_LIGHT = "/Library/Fonts/Nix Fonts/2sbrq4vj0fzg3kda0jxnbkbphdynw28y-source-sans-pro-3.006/share/fonts/truetype/SourceSansPro-Light.ttf"

# ── Canvas ────────────────────────────────────────────────────────────────────
W, H = 1080, 1440
MARGIN_X = 80
MARGIN_TOP = 100
MARGIN_BOTTOM = 80
CONTENT_W = W - 2 * MARGIN_X

# ── Palette: Catppuccin Latte ─────────────────────────────────────────────────
BG = (239, 241, 245)  # Base       #eff1f5
FG = (76, 79, 105)  # Text       #4c4f69
ACCENT = (136, 57, 239)  # Mauve      #8839ef
MUTED = (172, 176, 190)  # Overlay1   #acb0be
CODE_BG = (230, 233, 239)  # Mantle     #e6e9ef
CODE_FG = (64, 160, 43)  # Green      #40a02b
SURFACE1 = (204, 208, 218)  # Surface1   #ccd0da
SAPPHIRE = (32, 159, 181)  # Sapphire   #209fb5
PEACH = (254, 100, 11)  # Peach      #fe640b

# ── Font sizes ────────────────────────────────────────────────────────────────
SZ_H1 = 52
SZ_H2 = 36
SZ_BODY = 30
SZ_CODE = 24
SZ_SMALL = 22
LINE_H = {SZ_H1: 70, SZ_H2: 52, SZ_BODY: 46, SZ_CODE: 36, SZ_SMALL: 34}


def load(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except Exception:
        return ImageFont.load_default()


# Font cache
_fcache = {}


def font(role, size):
    key = (role, size)
    if key not in _fcache:
        if role == "h1":
            # Bold CJK for headings
            _fcache[key] = load(NOTO_CJK, size, index=3)  # Medium weight index
        elif role == "h2":
            _fcache[key] = load(NOTO_CJK, size, index=3)
        elif role == "body":
            _fcache[key] = load(NOTO_CJK, size, index=0)
        elif role == "code":
            _fcache[key] = load(NOTO_MONO, size, index=0)
        elif role == "label":
            _fcache[key] = load(SOURCE_SANS_BOLD, size)
        else:
            _fcache[key] = load(NOTO_CJK, size, index=0)
    return _fcache[key]


# ── Markdown parser → segments ────────────────────────────────────────────────
# Each segment: dict with type and text


def parse_md(text):
    """Parse markdown into a list of block segments."""
    segments = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # H1
        if line.startswith("# "):
            segments.append({"type": "h1", "text": line[2:].strip()})
            i += 1

        # H2
        elif line.startswith("## "):
            segments.append({"type": "h2", "text": line[3:].strip()})
            i += 1

        # Fenced code block
        elif line.strip().startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # closing ```
            segments.append({"type": "code", "text": "\n".join(code_lines)})

        # Blank line
        elif line.strip() == "":
            segments.append({"type": "blank"})
            i += 1

        # Horizontal rule
        elif line.strip() == "---":
            segments.append({"type": "rule"})
            i += 1

        # Table
        elif line.strip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i]
                if re.match(r"^\|[-| :]+\|$", row.strip()):
                    i += 1
                    continue
                cells = [c.strip() for c in row.strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            segments.append({"type": "table", "rows": rows})

        # Bullet
        elif re.match(r"^[-*] ", line):
            segments.append({"type": "bullet", "text": line[2:].strip()})
            i += 1

        # Numbered list
        elif re.match(r"^\d+\. ", line):
            segments.append({"type": "numbered", "text": re.sub(r"^\d+\. ", "", line)})
            i += 1

        # Paragraph
        else:
            segments.append({"type": "para", "text": line.strip()})
            i += 1

    return segments


# ── Text wrapping that respects CJK ──────────────────────────────────────────


def wrap_text(draw, text, fnt, max_width):
    """Wrap text to fit max_width, returning list of lines."""
    # Remove inline markdown (bold, code, backtick)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)

    words = list(text)  # character-level for CJK
    lines = []
    current = ""
    for ch in words:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=fnt)
        if bbox[2] > max_width and current:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines


# ── Card renderer ─────────────────────────────────────────────────────────────


def render_card(page_segments, page_num, total_pages):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Subtle top gradient bar
    for y in range(6):
        alpha = int(255 * (1 - y / 6))
        draw.line([(0, y), (W, y)], fill=ACCENT)

    y = MARGIN_TOP

    for seg in page_segments:
        if y > H - MARGIN_BOTTOM - 60:
            break

        stype = seg["type"]

        if stype == "blank":
            y += 12
            continue

        if stype == "rule":
            draw.line(
                [(MARGIN_X, y + 8), (W - MARGIN_X, y + 8)], fill=SURFACE1, width=1
            )
            y += 24
            continue

        if stype == "h1":
            fnt = font("h1", SZ_H1)
            lines = wrap_text(draw, seg["text"], fnt, CONTENT_W)
            for line in lines:
                draw.text(
                    (MARGIN_X, y), line, font=fnt, fill=ACCENT, language="简体中文"
                )
                y += LINE_H[SZ_H1]
            y += 12
            continue

        if stype == "h2":
            fnt = font("h2", SZ_H2)
            lines = wrap_text(draw, seg["text"], fnt, CONTENT_W)
            # Accent left border
            draw.rectangle(
                [(MARGIN_X, y + 4), (MARGIN_X + 4, y + SZ_H2 + 4)], fill=ACCENT
            )
            for line in lines:
                draw.text(
                    (MARGIN_X + 18, y), line, font=fnt, fill=FG, language="简体中文"
                )
                y += LINE_H[SZ_H2]
            y += 8
            continue

        if stype == "para":
            if not seg["text"]:
                y += 12
                continue
            fnt = font("body", SZ_BODY)
            lines = wrap_text(draw, seg["text"], fnt, CONTENT_W)
            for line in lines:
                draw.text((MARGIN_X, y), line, font=fnt, fill=FG, language="简体中文")
                y += LINE_H[SZ_BODY]
            y += 4
            continue

        if stype == "bullet":
            fnt = font("body", SZ_BODY)
            bullet_x = MARGIN_X + 28
            lines = wrap_text(draw, seg["text"], fnt, CONTENT_W - 28)
            # Draw bullet dot
            draw.ellipse([(MARGIN_X + 2, y + 16), (MARGIN_X + 12, y + 26)], fill=ACCENT)
            for k, line in enumerate(lines):
                draw.text((bullet_x, y), line, font=fnt, fill=FG, language="简体中文")
                y += LINE_H[SZ_BODY]
            y += 2
            continue

        if stype == "numbered":
            fnt = font("body", SZ_BODY)
            lines = wrap_text(draw, seg["text"], fnt, CONTENT_W - 32)
            # number handled outside; just indent
            for line in lines:
                draw.text(
                    (MARGIN_X + 32, y), line, font=fnt, fill=FG, language="简体中文"
                )
                y += LINE_H[SZ_BODY]
            y += 2
            continue

        if stype == "code":
            fnt = font("code", SZ_CODE)
            code_lines = seg["text"].split("\n")
            pad = 16
            block_h = len(code_lines) * LINE_H[SZ_CODE] + pad * 2
            # Background rect
            draw.rectangle(
                [(MARGIN_X, y), (W - MARGIN_X, y + block_h)],
                fill=CODE_BG,
                outline=SURFACE1,
            )
            cy = y + pad
            for cl in code_lines:
                draw.text((MARGIN_X + pad, cy), cl, font=fnt, fill=CODE_FG)
                cy += LINE_H[SZ_CODE]
            y += block_h + 12
            continue

        if stype == "table":
            fnt = font("body", SZ_SMALL)
            rows = seg["rows"]
            if not rows:
                continue
            col_w = CONTENT_W // max(len(rows[0]), 1)
            row_h = LINE_H[SZ_SMALL] + 12
            for ri, row in enumerate(rows):
                row_y = y + ri * row_h
                if ri == 0:
                    draw.rectangle(
                        [(MARGIN_X, row_y), (W - MARGIN_X, row_y + row_h)],
                        fill=SURFACE1,
                    )
                for ci, cell in enumerate(row):
                    cx = MARGIN_X + ci * col_w + 8
                    color = SAPPHIRE if ri == 0 else FG
                    draw.text(
                        (cx, row_y + 6), cell, font=fnt, fill=color, language="简体中文"
                    )
            y += len(rows) * row_h + 12
            continue

    # Page number
    pg_fnt = font("label", 22)
    pg_text = f"{page_num} / {total_pages}"
    bbox = draw.textbbox((0, 0), pg_text, font=pg_fnt)
    pg_x = (W - (bbox[2] - bbox[0])) // 2
    draw.text((pg_x, H - 50), pg_text, font=pg_fnt, fill=MUTED)

    return img


# ── Pagination ────────────────────────────────────────────────────────────────


def estimate_height(draw, seg):
    """Rough height estimate for a segment without rendering."""
    stype = seg.get("type")
    if stype == "blank":
        return 12
    if stype == "rule":
        return 24
    if stype == "h1":
        fnt = font("h1", SZ_H1)
        n = max(1, len(seg["text"]) // 16)
        return n * LINE_H[SZ_H1] + 12
    if stype == "h2":
        fnt = font("h2", SZ_H2)
        n = max(1, len(seg["text"]) // 22)
        return n * LINE_H[SZ_H2] + 8
    if stype in ("para", "bullet", "numbered"):
        n = max(1, len(seg.get("text", "")) // 20)
        return n * LINE_H[SZ_BODY] + 4
    if stype == "code":
        lines = seg["text"].split("\n")
        return len(lines) * LINE_H[SZ_CODE] + 44
    if stype == "table":
        rows = seg.get("rows", [])
        return len(rows) * (LINE_H[SZ_SMALL] + 12) + 12
    return 0


def paginate(segments):
    """Split segments into pages fitting H - MARGIN_TOP - MARGIN_BOTTOM."""
    avail = (
        H - MARGIN_TOP - MARGIN_BOTTOM - 60 + 80
    )  # extra room to reduce orphan pages
    # Use a temp draw for measurement
    tmp = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(tmp)

    pages = []
    current = []
    used = 0

    for seg in segments:
        h = estimate_height(draw, seg)
        if used + h > avail and current:
            pages.append(current)
            current = []
            used = 0
        current.append(seg)
        used += h

    if current:
        pages.append(current)

    return pages


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    md_path = os.path.join(os.path.dirname(SCRIPT_DIR), "INTRODUCTION-zh.md")
    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    segments = parse_md(text)
    pages = paginate(segments)
    total = len(pages)

    print(f"Generating {total} cards…")

    for i, page_segs in enumerate(pages, 1):
        img = render_card(page_segs, i, total)
        out_path = os.path.join(OUT_DIR, f"slide_{i:02d}.png")
        img.save(out_path, "PNG")
        print(f"  Saved {out_path}")

    print("Done.")


if __name__ == "__main__":
    main()
