#!/usr/bin/env python3
"""NRAI Website Real-Time Monitor for iPhone (via ntfy)
Monitors: https://www.thenrai.in/news_events_details.aspx
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
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "nrai-live-updates-iphone")
TARGET_URL = "https://www.thenrai.in/news_events_details.aspx"
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
  req.add_header("Title", "NRAI Website Update")
  req.add_header("Priority", "urgent")
  req.add_header("Tags", "rotating_light,loudspeaker")
  safe_link = urllib.parse.quote(link, safe=":/%?&=#+@_~-")
  req.add_header("Click", safe_link)
  try:
    with urllib.request.urlopen(req, timeout=15) as resp:
      print(f"[PUSH SENT] -> iPhone ({NTFY_TOPIC}): {title[:60]}...")
      return True
  except Exception as e:
    print(f"[FAILED TO SEND PUSH] {e}")
    return False
def fetch_page():
  req = urllib.request.Request(TARGET_URL, headers=HEADERS)
  try:
    with urllib.request.urlopen(req, timeout=20, context=CTX) as response:
      return response.read().decode("utf-8", errors="replace")
  except Exception as e:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Connection error: {e}")
    return None
def run_check():
  html = fetch_page()
  if not html:
    return
  parser = NRAILinkParser(TARGET_URL)
  parser.feed(html)
  relevant_items = []
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
  ]
  for text, url in parser.items:
    lower_t = text.lower()
    lower_u = url.lower()
    if (
        any(kw in lower_t or kw in lower_u for kw in keywords)
        or "news_events" in lower_u
    ):
      uid = hashlib.sha256(f"{text}::{url}".encode("utf-8")).hexdigest()
      relevant_items.append((uid, text, url))
  if len(relevant_items) < 3:
    for text, url in parser.items:
      if not any(
          nav in text.lower()
          for nav in ["home", "about us", "contact", "gallery", "committee"]
      ):
        uid = hashlib.sha256(f"{text}::{url}".encode("utf-8")).hexdigest()
        relevant_items.append((uid, text, url))
  seen = load_seen()
  is_initial_run = len(seen) == 0
  new_items_found = 0
  for uid, text, url in relevant_items:
    if uid not in seen:
      seen.append(uid)
      new_items_found += 1
      if not is_initial_run:
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] NEW ITEM DETECTED: {text}"
        )
        send_iphone_push(text, url)
        time.sleep(1)
  save_seen(seen)
  if is_initial_run:
    print(
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Initialized monitor with"
        f" {len(seen)} existing notices. Ready for new updates!"
    )
  else:
    if new_items_found == 0:
      print(
          f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Check done. No new updates."
      )
def main():
  print("==================================================")
  print(" NRAI Real-Time Monitor Started")
  print(f" Target: {TARGET_URL}")
  print(f" iPhone Topic: {NTFY_TOPIC}")
  print("==================================================")
  if "--test" in sys.argv:
    print("Sending test notification to iPhone...")
    send_iphone_push(
        "TEST ALERT: NRAI Monitor connected to iPhone successfully!", TARGET_URL
    )
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
