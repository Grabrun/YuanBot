"""python -m yuanbot.tui 入口"""

import argparse

from yuanbot.tui.app import run_tui


def main():
    parser = argparse.ArgumentParser(description="🌸 缘·Bot TUI 终端聊天界面")
    parser.add_argument("--host", default="http://localhost:8000", help="后端地址")
    parser.add_argument("--token", default=None, help="JWT Token")
    parser.add_argument("--api-key", default=None, help="API Key")
    args = parser.parse_args()

    run_tui(host=args.host, token=args.token, api_key=args.api_key)


if __name__ == "__main__":
    main()
