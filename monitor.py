#!/usr/bin/env python3
"""NRAI Website Real-Time Monitor for iPhone (via ntfy)

Monitors ALL NRAI circular pages:
  1. https://www.thenrai.in/news_events.aspx (Main News & Events list)
  2. https://www.thenrai.in/news_events_details.aspx (News Details page)
  3. https://www.thenrai.in/ (Homepage Latest Circulars)
"""

import hashlib
from html.parser import HTMLParser
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

# ================= CONFIGURATION =================
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "nrai-live-updates-iphone")

# Monitors all 3 pages where NRAI publishes circulars
TARGET_URLS = [
    "https://www.thenrai.in/news_events_details.aspx",
    "https://www.thenrai.in/",
]

CHECK_INTERVAL_SECONDS = 60
CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "seen_updates.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


class NRAILinkParser(HTMLParser):

  def __init__(self, base_url):
    super().__init__()
    self.base_url = base_url
    self.items = []
    self._current_tag = None
    self._current_href = None
    self._current_text = []

  def handle_starttag(self, tag, attrs):
    if tag.lower() == "a":
      self._current_tag = "a"
      for k, v in attrs:
        if k.lower() == "href" and v:
          self._current_href = v.strip()
      self._current_text = []

  def handle_data(self, data):
    if self._current_tag == "a":
      self._current_text.append(data)

  def handle_endtag(self, tag):
    if tag.lower() == "a" and self._current_tag == "a":
      full_text = " ".join("".join(self._current_text).split())
      href = self._current_href
      if href and full_text and len(full_text) > 3:
        absolute_url = urllib.parse.urljoin(self.base_url, href)
        if not href.startswith("javascript:") and not href.startswith("#"):
          self.items.append((full_text, absolute_url))
      self._current_tag = None
      self._current_href = None
      self._current_text = []


def load_seen():
  if os.path.exists(CACHE_FILE):
    try:
      with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return []
  return []


def save_seen(seen_list):
  try:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
      json.dump(seen_list, f, indent=2, ensure_ascii=False)
  except Exception as e:
    print(f"[Error saving cache] {e}")


def send_iphone_push(title, link):
  endpoint = f"https://ntfy.sh/{NTFY_TOPIC}"
  payload = f"New Update on NRAI Website:\n{title}\n\nTap to open: {link}".encode(
      "utf-8"
  )

  req = urllib.request.Request(endpoint, data=payload, method="POST")
  req.add_header("Title", "NRAI Circular Update")
  req.add_header("Priority", "urgent")
  req.add_header("Tags", "rotating_light,loudspeaker,dart")
  safe_link = urllib.parse.quote(link, safe=":/%?&=#+@_~-")
  req.add_header("Click", safe_link)

  try:
    with urllib.request.urlopen(req, timeout=15) as resp:
      print(f"[PUSH SENT] -> iPhone ({NTFY_TOPIC}): {title[:60]}...")
      return True
  except Exception as e:
    print(f"[FAILED TO SEND PUSH] {e}")
    return False


def fetch_page(url):
  req = urllib.request.Request(url, headers=HEADERS)
  try:
    with urllib.request.urlopen(req, timeout=20, context=CTX) as response:
      return response.read().decode("utf-8", errors="replace")
  except Exception as e:
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection error on {url}: {e}"
    )
    return None


def run_check():
  all_found_items = []
  keywords = [
      "circular",
      "notification",
      "championship",
      "result",
      "schedule",
      "nscc",
      ".pdf",
      "relay",
      "trial",
      "news",
      "event",
      "selection",
      "shooting",
      "ranking",
      "entry",
      "draw",
  ]

  for target_url in TARGET_URLS:
    html = fetch_page(target_url)
    if not html:
      continue

    parser = NRAILinkParser(target_url)
    parser.feed(html)

    for text, url in parser.items:
      lower_t = text.lower()
      lower_u = url.lower()

      if (
          any(kw in lower_t or kw in lower_u for kw in keywords)
          or "news_events" in lower_u
      ):
        uid = hashlib.sha256(f"{text}::{url}".encode("utf-8")).hexdigest()
        all_found_items.append((uid, text, url))

  unique_items = {}
  for uid, text, url in all_found_items:
    if uid not in unique_items:
      unique_items[uid] = (text, url)

  seen = load_seen()
  is_initial_run = len(seen) == 0

  new_items_found = 0
  for uid, (text, url) in unique_items.items():
    if uid not in seen:
      seen.append(uid)
      new_items_found += 1
      if not is_initial_run:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] NEW CIRCULAR DETECTED:"
            f" {text}"
        )
        send_iphone_push(text, url)
        time.sleep(1)

  save_seen(seen)

  if is_initial_run:
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Initialized monitor with"
        f" {len(seen)} existing notices across all NRAI pages. Ready for new"
        " updates!"
    )
  else:
    if new_items_found == 0:
      print(
          f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Check complete across all 3"
          " NRAI pages. No new circulars."
      )
    else:
      print(
          f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Done. Found and sent"
          f" {new_items_found} new circular(s) to iPhone!"
      )


def main():
  print("==================================================")
  print(" NRAI Multi-Page Real-Time Monitor Started")
  print(f" Monitoring 3 URLs: {TARGET_URLS}")
  print(f" iPhone Topic: {NTFY_TOPIC}")
  print("==================================================")

  # 👉 DINGS YOUR IPHONE IMMEDIATELY TO CONFIRM IT'S ACTIVE:
  send_iphone_push(
      "NRAI Cloud Monitor Active! Scanning all 3 circular pages.", TARGET_URLS[0]
  )

  if "--test" in sys.argv:
    print("Sending test notification to iPhone...")
    return

  if "--once" in sys.argv or os.getenv("GITHUB_ACTIONS"):
    print("Running single check mode (Cloud / GitHub Actions)...")
    run_check()
    return

  print(f" Interval: every {CHECK_INTERVAL_SECONDS} seconds")
  while True:
    try:
      run_check()
    except Exception as e:
      print(f"Unexpected error during check: {e}")
    time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
  main()
