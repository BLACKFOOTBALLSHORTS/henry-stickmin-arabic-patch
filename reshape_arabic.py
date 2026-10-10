"""
Reshape Arabic text in key=value translation files for games
(like Henry Stickmin) that cannot join/reverse Arabic letters by themselves.

Usage:
    pip install arabic-reshaper python-bidi
    python reshape_arabic.py btb_plain_ar.txt btb_english.txt
    python reshape_arabic.py btb_plain_ar.txt btb_english.txt --no-bidi

Keep your readable Arabic in the *_plain_ar.txt file and edit only that one.
The output file is the one you copy into the game folder.
"""
import argparse
import sys

import arabic_reshaper

try:
    from bidi import get_display          # python-bidi >= 0.5
except ImportError:
    from bidi.algorithm import get_display  # older versions

reshaper = arabic_reshaper.ArabicReshaper(configuration={
    "delete_harakat": True,     # most Flash fonts cannot draw tashkeel
    "support_ligatures": True,  # lam-alef etc.
})


# The game draws the string left-to-right exactly as stored, so paired
# punctuation must be flipped back after the bidi reordering.
MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")


def convert(text: str, use_bidi: bool) -> str:
    shaped = reshaper.reshape(text)
    if not use_bidi:
        return shaped
    return get_display(shaped).translate(MIRROR)


def convert_value(value: str, use_bidi: bool, pad: str) -> str:
    # The game turns the two literal characters \n into a line break.
    # Each line is converted on its own so the lines stay in top-to-bottom order.
    parts = value.split("\\n")
    return "\\n".join(convert(p.strip(), use_bidi) + pad if p.strip() else p for p in parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--no-bidi", action="store_true",
                    help="join letters only, do not reverse direction")
    ap.add_argument("--pad", type=int, default=0,
                    help="number of padding chars appended to the end of every line")
    ap.add_argument("--pad-char", choices=["space", "nbsp"], default="space",
                    help="padding char: normal space or non-breaking space (U+00A0)")
    args = ap.parse_args()

    pad = (" " if args.pad_char == "space" else "\u00a0") * args.pad
    out = []
    with open(args.src, encoding="utf-8-sig") as f:
        for line in f.read().splitlines():
            if "=" not in line or not line.strip():
                out.append(line)
                continue
            key, value = line.split("=", 1)   # split on the FIRST '=' only
            out.append(f"{key}={convert_value(value, not args.no_bidi, pad)}")

    with open(args.dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    print(f"done: {len(out)} lines -> {args.dst}")


if __name__ == "__main__":
    sys.exit(main())
