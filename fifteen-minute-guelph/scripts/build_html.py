import os
css = open("/mnt/user-data/uploads/City of Guelph Data/_testdata/leaflet.min.css").read()
src = open("/home/claude/guelph/src/index.src.html").read().replace("/*LEAFLET_CSS*/", css)
open("/home/claude/guelph/app/index.html", "w").write(src)
# website build: realtime decoder + config load before the app
web = "/home/claude/guelph/web/"; os.makedirs(web, exist_ok=True)
tag = '<script src="leaflet.min.js"></script>'
assert tag in src
open(web + "index.html", "w").write(
    "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
    "<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}</style>\n</head><body>\n"
    + src.replace(tag, '<script src="gtfsrt.js"></script>\n<script src="config.js"></script>\n' + tag) + "\n</body></html>\n")
print("ok")
