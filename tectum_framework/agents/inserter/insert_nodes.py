import time, sys
print("[inserter] starting… (stub) never gonna say goodbye")
try:
    while True:
        time.sleep(10)
        print("[inserter] heartbeat")
except KeyboardInterrupt:
    sys.exit(0)