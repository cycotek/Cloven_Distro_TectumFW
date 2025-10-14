import requests
import time, sys

print("[scraper] starting… Scraper running...")
try:
    while True:
        time.sleep(10)
        print("[scraper] heartbeat")
except KeyboardInterrupt:
    sys.exit(0)