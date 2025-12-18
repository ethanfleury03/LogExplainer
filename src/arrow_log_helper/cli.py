from __future__ import absolute_import, print_function

import argparse
import sys


def build_parser():
    parser = argparse.ArgumentParser(
        prog="arrow_log_helper",
        description="Arrow Log Helper (GUI wiring + stub analyzer; no scanning yet).",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        default=False,
        help="Launch the Tkinter GUI.",
    )
    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    args = build_parser().parse_args(argv)

    if args.gui:
        from arrow_log_helper import gui

        return gui.main([])

    print("Not implemented yet (use --gui for the UI).")
    return 2


if __name__ == "__main__":
    sys.exit(main())


