import glob
import json
import os
from backend.services.results_card import build_results_card

def main():
    # Clear existing results cache
    for f in glob.glob('cache/results/*.json'):
        try:
            os.remove(f)
        except Exception:
            pass

    with open('cache/announcements/_classified_2026-11-02.json', encoding='utf-8') as f:
        items = json.load(f)

    url_to_item = {it.get('attachment_url'): it for it in items if it.get('attachment_url')}
    with open('cache/filings/_url_map.json', encoding='utf-8') as f:
        url_map = json.load(f)

    print('Building results cards for mapped filings...')
    for url, sha in url_map.items():
        it = url_to_item.get(url)
        if it:
            res = build_results_card(
                ticker=it.get('ticker', ''),
                filing_url=url,
                news_id=it.get('news_id'),
                headline=it.get('headline', ''),
                allow_download=True,
            )
            print(f"{it.get('ticker')}: status={res.get('status')}, period={res.get('period_current')}, basis={res.get('basis')}, is_bank={res.get('is_bank')}")

if __name__ == '__main__':
    main()
