import frappe


def after_install():
    """Runs once, on `bench install-app`.

    Everything the app needs on a fresh site belongs here — *not* in a patch.
    Frappe records every entry in patches.txt as already-applied when an app is
    installed, on the reasonable assumption that a new install is at current
    schema. A patch therefore never executes on the site it was written for, and
    the failure is silent: the Patch Log says it ran.

    That bug cost one install. It is worth the comment.
    """
    create_manager_role()
    seed_local_business()
    frappe.db.commit()


def create_manager_role():
    """The only role this app ships.

    The platform is for management. There is no general staff role, because a
    staff member's view of the business is ERPNext itself — this app exists to
    answer questions staff are not asked.
    """
    if frappe.db.exists("Role", "Command Center Manager"):
        return
    frappe.get_doc({
        "doctype": "Role",
        "role_name": "Command Center Manager",
        "desk_access": 1,
    }).insert(ignore_permissions=True)


def seed_local_business():
    """Register the host site as connector number one.

    The app must never treat the site it is installed on as a special case. It is
    simply the Connected Business flagged `is_local`. Every engine above that
    layer sees N businesses and never asks which one it is living inside — which
    is what makes moving the platform to another site a configuration change
    rather than a rewrite.

    Idempotent, because this is called from install and from the upgrade patch.
    """
    if frappe.db.exists("Connected Business", {"is_local": 1}):
        return None

    company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
    if not company:
        # No Company yet. Registration happens on first use instead of failing
        # the install of an app that is perfectly installable.
        return None

    doc = frappe.get_doc({
        "doctype": "Connected Business",
        "business_name": company,
        "business_code": frappe.scrub(company)[:40],
        "is_local": 1,
        "erpnext_company": company,
        "currency": frappe.db.get_value("Company", company, "default_currency"),
        "timezone": frappe.db.get_single_value("System Settings", "time_zone"),
        "status": "Active",
    }).insert(ignore_permissions=True)
    return doc.name


def install_pdf_fonts(quiet: bool = False):
    """Put Manrope where the server's PDF engine finds fonts.

    wkhtmltopdf (0.12.6, patched Qt, on Biomed) ignores fonts embedded in the page, and
    reads only the fonts fontconfig knows. The first version installed them under
    ~/.local/share/fonts, which Biomed's fontconfig does not search: the files were there
    and `fc-list` still had no Manrope. ~/.fonts is searched by every fontconfig setup, so
    they go there, and the cache is refreshed. Runs after every migrate, and before a PDF
    if the fonts are not in place, so a pull and a restart are enough. Nothing outside
    that folder is touched; without fontconfig the PDF keeps its fallback font.
    """
    import os
    import shutil
    import subprocess

    src = os.path.join(os.path.dirname(__file__), "api", "fonts")
    home = os.path.expanduser("~")
    dest = os.path.join(home, ".fonts", "command_center")
    try:
        os.makedirs(dest, exist_ok=True)
        changed = False
        for name in sorted(os.listdir(src)):
            if not name.endswith(".ttf"):
                continue
            a, b = os.path.join(src, name), os.path.join(dest, name)
            if not os.path.exists(b) or open(a, "rb").read() != open(b, "rb").read():
                shutil.copyfile(a, b)
                changed = True
        # The folder the first version used, which nothing searched.
        old = os.path.join(home, ".local", "share", "fonts", "command_center")
        if os.path.isdir(old):
            shutil.rmtree(old, ignore_errors=True)
        if changed and shutil.which("fc-cache"):
            subprocess.run(["fc-cache", "-f"], check=False, timeout=120,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not quiet:
            print(f"Command Center: PDF fonts {'installed' if changed else 'already in place'} in {dest}")
        return changed
    except Exception as e:  # never stop a migrate, or a PDF, over a typeface
        if not quiet:
            print(f"Command Center: could not install the PDF fonts ({e}); PDFs keep the fallback font")
        return False
