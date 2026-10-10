"""Build the phone-friendly wallet page that shows every prop full-width."""

from html import escape

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Specimen Wallet</title>
<style>
  :root {{ --bg:#0a0a0a; --card:#161616; --text:#f2f2f2; --muted:#9a9a9a; --accent:#e0592a; }}
  @media (prefers-color-scheme: light) {{
    :root {{ --bg:#f5f0e8; --card:#fff; --text:#111; --muted:#666; }}
  }}
  body {{ margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,sans-serif; }}
  header {{ padding:16px; position:sticky; top:0; background:var(--bg); z-index:2; }}
  h1 {{ margin:0; font-size:20px; }}
  .note {{ color:var(--muted); font-size:13px; }}
  nav {{ display:flex; gap:8px; padding:0 16px 12px; overflow-x:auto; }}
  nav a {{ color:var(--text); border:1px solid var(--muted); border-radius:999px;
          padding:6px 14px; text-decoration:none; white-space:nowrap; }}
  section {{ padding:16px; }}
  .story {{ color:var(--muted); margin:4px 0 12px; }}
  .strip {{ display:flex; gap:12px; overflow-x:auto; scroll-snap-type:x mandatory; }}
  .strip a {{ flex:0 0 92%; scroll-snap-align:center; background:var(--card);
             border-radius:12px; padding:6px; }}
  .strip img {{ width:100%; display:block; border-radius:8px; }}
</style>
</head>
<body>
<header>
  <h1>Specimen Wallet</h1>
  <div class="note">Fictional props for a hackathon demo. Not real documents.
  Max screen brightness helps scanners.</div>
</header>
<nav>{nav}</nav>
{sections}
</body>
</html>
"""

SECTION = """<section id="{key}">
  <h2>{title}</h2>
  <p class="story">{story}</p>
  <div class="strip">{images}</div>
</section>"""

FILES = ("role_card", "boarding_pass", "passport", "return_ticket", "hotel_booking")


def build_wallet(personas) -> str:
    nav = "".join(f'<a href="#{p.key}">{escape(p.given_names.split()[0].title())}</a>' for p in personas)
    sections = []
    for p in personas:
        images = "".join(
            f'<a href="{p.key}/{name}.png"><img src="{p.key}/{name}.png" alt="{name}"></a>'
            for name in FILES
        )
        title = f"{p.given_names.title()} {p.surname.title()}"
        sections.append(
            SECTION.format(key=p.key, title=escape(title), story=escape(p.story), images=images)
        )
    return PAGE.format(nav=nav, sections="\n".join(sections))
