"""Deploy-time JSON integrity gate. Every named file must parse as JSON and carry
an `asof` key. Fails (exit 1) on a truncated/corrupt/empty file - the data-side
analogue of tools/check-scripts.mjs, closing the truncation hole the audit found."""
import json
import sys

bad = 0
for f in sys.argv[1:]:
    try:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        assert d.get("asof"), "missing asof"
        print("OK %s (asof %s)" % (f, d.get("asof")))
    except FileNotFoundError:
        print("::warning::%s not present - skipped" % f)
    except Exception as e:
        print("::error::%s failed JSON integrity: %s" % (f, e))
        bad += 1
sys.exit(1 if bad else 0)
