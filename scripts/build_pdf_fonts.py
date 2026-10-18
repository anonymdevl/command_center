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
for weight, name in ((400, "regular"), (600, "semibold"), (700, "bold")):
    font = TTFont(src[0])
    font.flavor = None
    static = instantiateVariableFont(font, {"wght": weight}, updateFontNames=True)
    path = os.path.join(out_dir, f"manrope-{name}.ttf")
    static.save(path)
    print(f"{path}  {os.path.getsize(path):,} bytes")
