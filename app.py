# noqa
# coding=utf-8
from __future__ import print_function

import atexit
import copy
import logging
import sys

from marblecutter.web import app

logging.basicConfig(level=logging.INFO)


def module_dumper():
    modules = copy.copy(sys.modules.values())
    files = set([v.__file__ for v in modules if hasattr(v, "__file__")])
    files = sorted([f.split("site-packages")[1][1:] for f in files if "site-packages" in f])

    print("Files in site-packages/ loaded:")
    print()
    print("\n".join(files))


if __name__ == "__main__":
    atexit.register(module_dumper)
    app.run(host="0.0.0.0", port=8000, debug=True)
