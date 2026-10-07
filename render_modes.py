"""Render desktop, mobile, or both from either source layout."""
import argparse
from pathlib import Path
from mcp_tools import create_comic_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", default="comic.png")
    parser.add_argument("--mode", choices=["desktop", "mobile", "both"], default="both")
    parser.add_argument("--output-dir", default="output")
    args = parser.parse_args()
    modes = ["desktop", "mobile"] if args.mode == "both" else [args.mode]
    for mode in modes:
        directory = Path(args.output_dir) / mode
        result = create_comic_video(args.image, format=mode, output_dir=str(directory),
            output=str(directory / "comic_video.mp4"))
        print(result, flush=True)


if __name__ == "__main__":
    main()
