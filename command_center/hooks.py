app_name = "command_center"
app_title = "Intelligent Command Center"
app_publisher = "Michael Appiah-Kubi"
app_description = "An executive intelligence layer over ERPNext."
app_email = "ai4powersoft@gmail.com"
app_license = "Proprietary"

# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
# The SPA is built into command_center/public/frontend by the `build` script in
# package.json, and served at /command-center. Until that build exists the route
# renders the placeholder in www/command-center.html. The file name must match
# to_route, and the bare path needs its own rule or it 404s.
website_route_rules = [
    {"from_route": "/command-center/<path:app_path>", "to_route": "command-center"},
    {"from_route": "/command-center", "to_route": "command-center"},
]

# ---------------------------------------------------------------------------
# Roles and fixtures
# ---------------------------------------------------------------------------
# Access is management-only. There is deliberately no general staff role.
fixtures = [
    {"dt": "Role", "filters": [["role_name", "in", ["Command Center Manager"]]]},
    {"dt": "Custom Field", "filters": [["name", "like", "%-icc_%"]]},
]

after_install = "command_center.install.after_install"

# A credential belongs to one person. Enforced by query condition, not by
# remembering to filter in every read.
permission_query_conditions = {
    "Command Center Site Credential":
        "command_center.api.credentials.credential_query_conditions",
}
has_permission = {
    "Command Center Site Credential":
        "command_center.api.credentials.has_credential_permission",
}

# ---------------------------------------------------------------------------
# Change feed
# ---------------------------------------------------------------------------
# Every tracked transaction writes one Command Center Change Event row. The sync
# worker — local or on a peer site — consumes the feed rather than polling tables.
#
# Failure here must never block a business transaction, so the handler swallows
# and logs. A missed event is recoverable on the next full sweep; a blocked
# invoice is not.
TRACKED_DOCTYPES = [
    "Sales Invoice",
    "Sales Order",
    "Delivery Note",
    "Purchase Invoice",
    "Purchase Order",
    "Purchase Receipt",
    "Payment Entry",
    "Journal Entry",
    "Stock Entry",
    "Stock Reconciliation",
    "Project",
    "Task",
    "Issue",
    "Employee",
]

doc_events = {
    "*": {
        "after_insert": "command_center.api.changes.record_event",
        "on_submit": "command_center.api.changes.record_event",
        "on_update_after_submit": "command_center.api.changes.record_event",
        "on_cancel": "command_center.api.changes.record_event",
    }
}

scheduler_events = {
    "cron": {
        # Peer refresh. Reads only: each site computes its own figures, peers
        # read the conclusions. See connectors/remote.py.
        "*/15 * * * *": ["command_center.api.changes.refresh_peers"],
    },
    "daily": [
        "command_center.api.changes.prune_consumed_events",
    ],
}
