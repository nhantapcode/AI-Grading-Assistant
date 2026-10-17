"""Internal extraction subprocess; uploaded code is never executed."""
import argparse
from pathlib import Path

from app.services.extraction import manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('filename')
    parser.add_argument('destination',type=Path)
    args = parser.parse_args()
    try:
        manifest(args.source,args.filename,args.destination)
    except Exception as error:
        args.destination.mkdir(parents=True,exist_ok=True)
        (args.destination/'error.txt').write_text(str(error)[:300])
        raise SystemExit(2)


if __name__=='__main__':
    main()
