"""Quick test to find the right mermaid.ink encoding."""
import httpx
import base64
import json
import zlib

code = "graph TD\n    A-->B\n    B-->C"

# Method 1: plain base64 via /img/ route
b64 = base64.urlsafe_b64encode(code.encode("utf-8")).decode("ascii")
url1 = f"https://mermaid.ink/img/{b64}"
print(f"Method 1 (plain b64 /img/): {url1[:80]}...")
try:
    resp = httpx.get(url1, timeout=15, follow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"  Status: {resp.status_code}, CT: {ct}, Size: {len(resp.content)}")
except Exception as e:
    print(f"  Error: {e}")

# Method 2: JSON object base64 
obj = {"code": code, "mermaid": {"theme": "default"}}
j = json.dumps(obj)
b64j = base64.urlsafe_b64encode(j.encode("utf-8")).decode("ascii")
url2 = f"https://mermaid.ink/img/{b64j}"
print(f"\nMethod 2 (json b64 /img/): {url2[:80]}...")
try:
    resp = httpx.get(url2, timeout=15, follow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"  Status: {resp.status_code}, CT: {ct}, Size: {len(resp.content)}")
except Exception as e:
    print(f"  Error: {e}")

# Method 3: pako via deflateRaw (wbits=-15)
compress_raw = zlib.compressobj(level=9, wbits=-15)
raw_data = compress_raw.compress(code.encode("utf-8"))
raw_data += compress_raw.flush()
b64r = base64.urlsafe_b64encode(raw_data).decode("ascii")
url3 = f"https://mermaid.ink/img/pako:{b64r}"
print(f"\nMethod 3 (pako deflateRaw): {url3[:80]}...")
try:
    resp = httpx.get(url3, timeout=15, follow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"  Status: {resp.status_code}, CT: {ct}, Size: {len(resp.content)}")
except Exception as e:
    print(f"  Error: {e}")

# Method 4: Full zlib via /img/pako: route
full = zlib.compress(code.encode("utf-8"), level=9)
b64f = base64.urlsafe_b64encode(full).decode("ascii")
url4 = f"https://mermaid.ink/img/pako:{b64f}"
print(f"\nMethod 4 (pako full zlib): {url4[:80]}...")
try:
    resp = httpx.get(url4, timeout=15, follow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"  Status: {resp.status_code}, CT: {ct}, Size: {len(resp.content)}")
except Exception as e:
    print(f"  Error: {e}")

# Method 5: standard base64 (not URL-safe)
b64s = base64.b64encode(code.encode("utf-8")).decode("ascii")
url5 = f"https://mermaid.ink/img/{b64s}"
print(f"\nMethod 5 (std b64 /img/): {url5[:80]}...")
try:
    resp = httpx.get(url5, timeout=15, follow_redirects=True)
    ct = resp.headers.get("content-type", "")
    print(f"  Status: {resp.status_code}, CT: {ct}, Size: {len(resp.content)}")
except Exception as e:
    print(f"  Error: {e}")
