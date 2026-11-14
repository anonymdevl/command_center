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


def prepare_hosted_site(time_zone: str = "Africa/Accra", country: str = "Ghana",
                        currency: str = "GHS", language: str = "en"):
    """A plain Frappe site that hosts the platform for businesses on other sites.

    It has no ERPNext and no business of its own -- every business is reached over its
    API -- so the setup wizard has nothing to set up. Marked complete here, with the
    site's time zone and currency, so the desk opens for the administrator instead of
    asking about a company that does not exist. Run once by host.sh.
    """
    create_manager_role()
    for field, value in (("time_zone", time_zone), ("country", country),
                         ("currency", currency), ("language", language)):
        try:
            frappe.db.set_single_value("System Settings", field, value)
        except Exception:
            pass
    try:
        frappe.db.set_single_value("System Settings", "setup_complete", 1)
    except Exception:
        pass
    try:  # v15+: setup state is per installed app
        frappe.db.set_value("Installed Application", {"app_name": "frappe"},
                            "is_setup_complete", 1)
    except Exception:
        pass
    frappe.defaults.set_global_default("currency", currency)
    frappe.db.commit()
    return {"ok": True, "time_zone": time_zone, "currency": currency}


def register_business(business_name: str, site_url: str, api_key: str, api_secret: str,
                      erpnext_company: str | None = None, business_code: str | None = None,
                      currency: str | None = None, timezone: str | None = None,
                      overdue_after_days: int = 90):
    """Add (or update) a business reached over its API: its URL and the key and secret
    of its read-only ERPNext user. The company and currency are read from that site
    when not given. Then the connection is tried, so a wrong URL or key is found here
    rather than at the first load. Run by host.sh; safe to rerun.
    """
    name = frappe.db.get_value("Connected Business", {"business_name": business_name})
    doc = frappe.get_doc("Connected Business", name) if name else frappe.new_doc("Connected Business")
    doc.update({"business_name": business_name,
                "business_code": business_code or doc.business_code or frappe.scrub(business_name)[:40],
                "is_local": 0, "status": "Active", "site_url": site_url,
                "api_key": api_key, "api_secret": api_secret,
                "overdue_after_days": doc.overdue_after_days or overdue_after_days})
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Tried with the read-only account, as every load will be (api/ingest.probe).
    from command_center.api.ingest import probe
    who, companies = probe(doc.business_code)
    company = erpnext_company or doc.erpnext_company
    if not company and companies:
        company = companies[0]["name"]
    if company and not currency:
        currency = next((c.get("default_currency") for c in companies if c["name"] == company), None)
    doc.reload()
    doc.update({"erpnext_company": company, "currency": currency or doc.currency,
                "timezone": timezone or doc.timezone})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"business": doc.name, "code": doc.business_code, "reads_as": who,
            "company": company, "currency": doc.currency}


def register_from_env():
    """register_business with the secret read from the environment (host.sh), so the
    key and secret never appear in a command line, the shell history or `ps`."""
    import os
    out = register_business(
        business_name=os.environ["CC_BUSINESS_NAME"], site_url=os.environ["CC_SITE_URL"],
        api_key=os.environ["CC_API_KEY"], api_secret=os.environ["CC_API_SECRET"],
        erpnext_company=os.environ.get("CC_COMPANY") or None)
    print(f"registered {out['business']} ({out['code']}): reads as {out['reads_as']}, "
          f"company {out['company']}, currency {out['currency']}")
    return out


def set_secret_from_env(key: str, env: str):
    """A site_config value from the environment (host.sh), never from a command line."""
    import os

    from frappe.installer import update_site_config
    value = os.environ.get(env)
    if not value:
        print(f"{key}: not set (nothing in {env})")
        return False
    update_site_config(key, value)
    print(f"{key}: set")
    return True


def add_manager(email: str, full_name: str):
    """A person who may use the platform: a System User holding Command Center Manager
    and nothing else. No email is sent; they set their password from the reset link
    an administrator sends from the desk, or one given to them."""
    create_manager_role()
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        first, _, last = (full_name or email).partition(" ")
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": first,
                               "last_name": last, "user_type": "System User",
                               "send_welcome_email": 0})
        user.flags.no_welcome_mail = True
        user.insert(ignore_permissions=True)
    user.add_roles("Command Center Manager")
    frappe.db.commit()
    link = user.reset_password(send_email=False)
    print(f"{email}: Command Center Manager. Password link (valid for a limited time): {link}")
    return {"user": email, "reset_link": link}


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
