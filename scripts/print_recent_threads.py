import json
from backend.routers.push import thread_announcements

with open("cache/announcements/_classified_2026-11-02.json") as f:
    items = json.load(f)

items_sorted = sorted(items, key=lambda x: str(x.get("date", "")), reverse=True)
threaded = thread_announcements(items_sorted)

def reason_for(item):
    cat = item.get("category", "")
    h = item.get("headline", "").lower()
    if cat == "results":
        return "Quarterly/half-yearly financial results keyword"
    if cat == "management_change":
        return "Matches appointment/resignation/director/CFO pattern"
    if cat == "earnings_call":
        return "Earnings call transcript or concall audio/recording"
    if cat == "investor_meetings":
        return "Analyst / Institutional investor meet schedule/outcome"
    if cat == "press_release":
        return "Explicit press release or media release publication"
    if cat == "postal_ballot":
        return "Postal ballot or EGM voting outcome/notice"
    if cat == "litigation":
        return "Tax / statutory / dispute order or legal penalty"
    if cat == "unclassified":
        if "loss of share" in h:
            return "Routine loss of share certificate disclosure"
        if "newspaper" in h:
            return "Newspaper publication clipping"
        if "presentation" in h:
            return "Investor presentation slide deck"
        return "Routine compliance/general intimation"
    return f"Matched keyword pattern for {cat}"

print(f"Total threads: {len(threaded)}")
for i, t in enumerate(threaded[:20]):
    sub_cnt = t.get("thread_count", 1)
    suffix = f" [Thread of {sub_cnt}]" if sub_cnt > 1 else ""
    tick = t.get("ticker", "")
    cat = t.get("category", "").upper()
    tier = t.get("priority_tier", "").upper()
    date_val = t.get("date", "")
    head = t.get("headline", "")[:95]
    r = reason_for(t)
    print(f"{i+1}. [{tick}] {cat} ({tier}){suffix}")
    print(f"   Date: {date_val}")
    print(f"   Headline: {head}")
    print(f"   Reason: {r}")
