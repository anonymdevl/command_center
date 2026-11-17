"""Keep everyone's access when client separation arrives (17 Nov 2026).

Client separation (plans.visible_codes) lets a person on no customer see only the
businesses that are on no customer. On a platform with exactly one customer that holds
every connected business -- one client, as in production today -- a manager who was
added by hand before customers mattered is on no customer, and would lose every business
the moment this deploys.

So, only in that one unambiguous case: every active manager who is not an administrator
and is on no customer is added to the one customer, as a User (not an Account Manager),
which is exactly the access they had. With two or more customers, or a business on no
customer, nothing is done: who belongs where is then the administrator's decision
(Settings -> Customers). Running it twice changes nothing.
"""

from django.db import migrations

MANAGER = "Insights Dashboard Manager"


def keep_access(apps, schema_editor):
    ClientAccount = apps.get_model("core", "ClientAccount")
    ClientBusiness = apps.get_model("core", "ClientBusiness")
    ClientMember = apps.get_model("core", "ClientMember")
    ConnectedBusiness = apps.get_model("core", "ConnectedBusiness")
    User = apps.get_model("auth", "User")

    clients = list(ClientAccount.objects.all()[:2])
    if len(clients) != 1:
        return
    client = clients[0]
    held = set(ClientBusiness.objects.filter(client=client).values_list("business_code", flat=True))
    every = set(ConnectedBusiness.objects.values_list("business_code", flat=True))
    if not every or not every <= held:
        return  # a business on no customer: the old rule still serves those managers
    on_a_customer = {u.lower() for u in ClientMember.objects.values_list("username", flat=True)}
    managers = User.objects.filter(is_active=True, is_superuser=False, groups__name=MANAGER)
    for u in managers.distinct():
        if u.username.lower() in on_a_customer:
            continue
        ClientMember.objects.get_or_create(client=client, username=u.username,
                                           defaults={"role": "user"})


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_plansnapshot"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(keep_access, migrations.RunPython.noop),
    ]
