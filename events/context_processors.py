import re

from django.conf import settings

_GA_ID_PATTERN = re.compile(r"^(G-[A-Z0-9]{4,20}|UA-\d{4,12}-\d{1,4})$")


def analytics(request):
    raw = getattr(settings, "GOOGLE_ANALYTICS_ID", "") or ""
    ga_id = raw.strip()
    if not _GA_ID_PATTERN.match(ga_id):
        ga_id = ""
    return {"GOOGLE_ANALYTICS_ID": ga_id}
