import argparse
import asyncio
from pathlib import Path
from typing import Sequence

from app.cli.crawl_jobs import (
    SUPPORTED_SOURCES,
    crawl_jobs,
    print_error,
    print_result,
)


def job_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "limit must be an integer"
        ) from error

    if limit < 1 or limit > 20:
        raise argparse.ArgumentTypeError(
            "limit must be between 1 and 20"
        )

    return limit


def positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "value must be a number"
        ) from error

    if number <= 0:
        raise argparse.ArgumentTypeError(
            "value must be greater than zero"
        )

    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Multi Agent Job Assistant commands",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    crawl_parser = subparsers.add_parser(
        "crawl-jobs",
        help="Crawl and normalize jobs from a configured source",
    )

    crawl_parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES),
        default="himalayas",
        help="Job source name",
    )
    crawl_parser.add_argument(
        "--limit",
        type=job_limit,
        default=20,
        help="Number of jobs to fetch, from 1 to 20",
    )
    crawl_parser.add_argument(
        "--cursor",
        default=None,
        help="Pagination cursor returned by the previous crawl",
    )
    crawl_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/jobs"),
        help="Directory used by the local JSONL repository",
    )
    crawl_parser.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="HTTP timeout in seconds",
    )

    return parser


async def execute(args: argparse.Namespace) -> int:
    if args.command != "crawl-jobs":
        raise ValueError(f"Unsupported command: {args.command}")

    result = await crawl_jobs(
        source_name=args.source,
        limit=args.limit,
        cursor=args.cursor,
        data_dir=args.data_dir,
        timeout_seconds=args.timeout,
    )

    print_result(result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return asyncio.run(execute(args))
    except KeyboardInterrupt:
        print_error(RuntimeError("Command interrupted by user"))
        return 130
    except Exception as error:
        print_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())