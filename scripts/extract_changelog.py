#!/usr/bin/env python3
"""Extract release notes for a version from CHANGELOG.md"""

import os
import sys


def main():
    version = os.environ.get("VERSION", "")
    if not version:
        print("error: VERSION env var is required", file=sys.stderr)
        sys.exit(1)

    prefix = f"## [{version}]"
    in_block = False

    with open("CHANGELOG.md") as f:
        for line in f:
            if line.startswith(prefix):
                in_block = True
                continue
            if in_block:
                if line.startswith("## ["):
                    break
                sys.stdout.write(line)


if __name__ == "__main__":
    main()
