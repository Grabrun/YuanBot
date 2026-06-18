#!/usr/bin/env python3
"""Update CHANGELOG release date from 'Unreleased' to today's date"""

import re
import sys


def main():
    if len(sys.argv) < 3:
        print("error: Usage: update_changelog_date.py <version> <date>", file=sys.stderr)
        sys.exit(1)

    version = sys.argv[1]
    today = sys.argv[2]

    with open("CHANGELOG.md") as f:
        content = f.read()

    pattern = r'^## \[' + re.escape(version) + r'\]\s*-\s*(\S+)'
    match = re.search(pattern, content, re.MULTILINE)

    if match:
        date = match.group(1)
        if date == "Unreleased":
            old = f"## [{version}] - Unreleased"
            new = f"## [{version}] - {today}"
            content = content.replace(old, new)
            with open("CHANGELOG.md", "w") as f:
                f.write(content)
            print(f"Updated release date for v{version} to {today}")


if __name__ == "__main__":
    main()
