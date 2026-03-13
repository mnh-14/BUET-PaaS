#!/usr/bin/env python3
import argparse
import sys
import time

try:
    import requests
except Exception:
    requests = None
    import urllib.request
    import urllib.error


def http_get(url, timeout=5):
    if requests:
        r = requests.get(url, timeout=timeout)
        return r.status_code, r.text
    else:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                return resp.getcode(), resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8") if getattr(e, 'fp', None) else ""
            return e.code, body
        except Exception:
            raise


def check_endpoint(base, path, timeout):
    url = base.rstrip("/") + path
    try:
        code, body = http_get(url, timeout=timeout)
        ok = (200 <= code < 400)
        return ok, code, url
    except Exception:
        return False, None, url


def main():
    p = argparse.ArgumentParser(description="Check backend health endpoints")
    p.add_argument("--host", default="127.0.0.1", help="Backend host (default: 127.0.0.1)")
    p.add_argument("--port", default=8000, type=int, help="Backend port (default: 8000)")
    p.add_argument("--retries", default=3, type=int, help="Number of retries (default: 3)")
    p.add_argument("--delay", default=2.0, type=float, help="Delay between retries seconds (default: 2)")
    p.add_argument("--timeout", default=5.0, type=float, help="HTTP timeout seconds (default: 5)")
    args = p.parse_args()

    base = f"http://{args.host}:{args.port}"
    endpoints = ["/", "/health"]

    all_ok = True
    for path in endpoints:
        ok = False
        for attempt in range(1, args.retries + 1):
            passed, code, url = check_endpoint(base, path, timeout=args.timeout)
            if passed:
                print(f" {url} -> {code}")
                ok = True
                break
            else:
                print(f"✗ {url} (attempt {attempt}/{args.retries}) -> {code}")
                if attempt < args.retries:
                    time.sleep(args.delay)

        if not ok:
            all_ok = False

    if all_ok:
        print("All checks passed")
        sys.exit(0)
    else:
        print("One or more checks failed")
        sys.exit(2)


if __name__ == "__main__":
    main()
