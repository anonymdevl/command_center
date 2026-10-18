"""Make the PDF's fonts from the Manrope the app already bundles.

    python3 scripts/build_pdf_fonts.py      (needs fonttools and brotli)

The app ships Manrope as one variable woff2. Frappe's PDF engine (wkhtmltopdf) reads
neither woff2 nor variable fonts, so on the server every PDF fell back to DejaVu Sans:
wide, heavy, nothing like the screen. This writes three static TrueType weights --
regular, semibold, bold -- that export.py embeds in the PDF itself, so no font has to be
installed on the server. Run again only if the bundled Manrope changes.
"""
import glob
import os
import sys

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = sorted(glob.glob(os.path.join(ROOT, "command_center", "public", "command-center",
                                    "manrope-latin-wght-normal.*.woff2")))
if not src:
    sys.exit("No bundled Manrope found; build the frontend first.")
out_dir = os.path.join(ROOT, "command_center", "api", "fonts")
os.makedirs(out_dir, exist_ok=True)
# The names matter as much as the outlines: the first build left every weight called
# "Manrope ExtraLight", and the server's PDF engine ignored the fonts and used DejaVu.
for weight, name, style in ((400, "regular", "Regular"), (600, "semibold", "SemiBold"),
                            (700, "bold", "Bold")):
    font = TTFont(src[0])
    font.flavor = None
    static = instantiateVariableFont(font, {"wght": weight})
    for t in ("STAT", "fvar", "avar", "gvar", "HVAR", "MVAR"):
        if t in static:
            del static[t]
    names = static["name"]
    names.names = [n for n in names.names if n.nameID not in (1, 2, 3, 4, 6, 16, 17)]
    for nid, value in ((1, "Manrope"), (2, style if style in ("Regular", "Bold") else "Regular"),
                       (3, f"Manrope-{style};AI Business Intelligence"), (4, f"Manrope {style}"),
                       (6, f"Manrope-{style}"), (16, "Manrope"), (17, style)):
        names.setName(value, nid, 3, 1, 0x409)
        names.setName(value, nid, 1, 0, 0)
    if style == "SemiBold":  # its own family for apps that only know Regular and Bold
        names.setName("Manrope SemiBold", 1, 3, 1, 0x409)
        names.setName("Manrope SemiBold", 1, 1, 0, 0)
    os2 = static["OS/2"]
    os2.usWeightClass = weight
    os2.fsSelection = (os2.fsSelection & ~0b1100001) | (0b100000 if style == "Bold" else 0b1000000)
    static["head"].macStyle = 1 if style == "Bold" else 0
    path = os.path.join(out_dir, f"manrope-{name}.ttf")
    static.save(path)
    print(f"{path}  {os.path.getsize(path):,} bytes")
