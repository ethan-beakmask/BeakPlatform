#!/usr/bin/env python3
import json
import sys


data = json.load(sys.stdin)
for item in data.get("nftables", []):
    s = item.get("set")
    if not s or not s.get("elem"):
        continue
    for e in s["elem"]:
        if isinstance(e, dict) and "elem" in e:
            v = e["elem"]
            val = v.get("val")
            exp = v.get("expires")
            if isinstance(val, dict):
                val = "%s/%s" % (val["prefix"]["addr"], val["prefix"]["len"])
            print("%s timeout %ds" % (val, int(exp)) if exp else val)
        else:
            print(e)
