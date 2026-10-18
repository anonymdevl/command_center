# -*- coding: utf-8 -*-
"""The sign-in page and the access page: /command-center-login, /management-only.

Both load the app's own stylesheet, so they share its palette, type, accents and
light/dark with the Command Center itself; these are the few rules only they need.
"""

AUTH_CSS = """
/* ============ SIGN-IN AND ACCESS PAGES (auth.py) ============ */
body.cc-auth{overflow:auto;min-height:100vh;background:var(--bg);display:grid;place-items:center;padding:24px}
.auth{width:min(960px,100%);display:grid;grid-template-columns:1fr 1fr;background:var(--surface);
 border-radius:28px;box-shadow:var(--shadow2);overflow:hidden;min-height:540px}
.auth.single{width:min(520px,100%);grid-template-columns:1fr;min-height:0}
.auth-brand{background:var(--t3);padding:44px 40px;display:flex;flex-direction:column;gap:26px}
.auth-brand b{display:block;font-size:var(--fs-2xl);font-weight:var(--fw-semibold);letter-spacing:-.025em;
 color:var(--ink);margin-top:14px}
.auth-brand p{color:var(--ink2);font-size:var(--fs-md);margin-top:6px;max-width:320px}
.auth-brand ul{list-style:none;margin-top:auto;display:flex;flex-direction:column;gap:12px}
.auth-brand li{position:relative;padding-left:26px;color:var(--ink2);font-size:var(--fs-sm);line-height:1.5}
.auth-brand li::before{content:"";position:absolute;left:2px;top:5px;width:12px;height:12px;border-radius:50%;
 background:var(--accent);box-shadow:inset 0 0 0 3px var(--t3)}
.auth-mark{width:44px;height:44px;border-radius:13px;background:var(--ink);display:grid;place-items:center}
.auth-mark i{width:18px;height:18px;border-radius:50%;border:3.5px solid var(--accent);display:block;
 box-shadow:7px 0 0 -1px var(--t3)}
.auth-card{padding:48px 44px;display:flex;flex-direction:column;justify-content:center}
.auth-card h1{font-size:var(--fs-3xl);font-weight:var(--fw-semibold);letter-spacing:-.03em;line-height:1.15;color:var(--ink)}
.auth-sub{color:var(--mut);font-size:var(--fs-md);margin-top:8px;line-height:1.55}
.auth form{display:flex;flex-direction:column;margin-top:28px}
.auth label{font-size:var(--fs-sm);font-weight:var(--fw-semibold);color:var(--ink2);margin:14px 0 6px}
.auth input{height:48px;border:1px solid var(--line2);border-radius:var(--r-sm);background:var(--surface);
 color:var(--ink);font:var(--fw-regular) var(--fs-md) var(--sans);padding:0 14px;width:100%;
 transition:border-color .15s,box-shadow .15s}
.auth input:focus{outline:0;border-color:var(--accent);box-shadow:0 0 0 4px var(--accent-bg)}
.auth-pw{position:relative}
.auth-pw input{padding-right:70px}
.auth-pw button{position:absolute;right:6px;top:6px;height:36px;padding:0 12px;border:0;border-radius:var(--r-xs);
 background:var(--raised);color:var(--ink2);font:var(--fw-semibold) var(--fs-xs) var(--sans);cursor:pointer}
.auth-msg{display:none;margin-top:14px;background:var(--crit-bg);color:var(--crit);border-radius:var(--r-sm);
 padding:10px 12px;font-size:var(--fs-sm)}
.auth-msg.on{display:block}
.auth-go{display:inline-flex;align-items:center;justify-content:center;height:48px;margin-top:22px;border:0;
 border-radius:var(--r-pill);background:var(--accent);color:var(--on-accent);text-decoration:none;
 font:var(--fw-semibold) var(--fs-md) var(--sans);cursor:pointer;padding:0 24px;transition:filter .15s}
.auth-go:hover{filter:brightness(1.07)}
.auth-go:disabled{opacity:.7;cursor:default;filter:none}
.auth-go:focus-visible,.auth-alt:focus-visible,.auth-pw button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.auth-foot{display:flex;flex-direction:column;gap:6px;margin-top:22px;font-size:var(--fs-xs);color:var(--mut)}
.auth-foot a{color:var(--accent);font-weight:var(--fw-semibold);text-decoration:none}
.auth-lock{width:48px;height:48px;border-radius:14px;background:var(--accent-bg);color:var(--accent);
 display:grid;place-items:center;margin-bottom:18px}
.auth-eyebrow{font-size:var(--fs-xs);font-weight:var(--fw-semibold);color:var(--mut);margin-bottom:6px}
.auth-acts{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:8px}
.auth-acts .auth-go{margin-top:18px}
.auth-alt{height:48px;margin-top:18px;padding:0 20px;border:1px solid var(--line2);border-radius:var(--r-pill);
 background:var(--surface);color:var(--ink);font:var(--fw-semibold) var(--fs-md) var(--sans);cursor:pointer}
.auth-alt:hover{border-color:var(--ink2)}
.auth-who{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);font-size:var(--fs-sm);color:var(--mut);
 line-height:1.55}
.auth-who b{color:var(--ink);font-weight:var(--fw-semibold)}
@media(max-width:820px){
 .auth{grid-template-columns:1fr;min-height:0}
 .auth-brand{padding:28px 26px;gap:16px}
 .auth-brand ul{display:none}
 .auth-card{padding:32px 26px}
}
"""
