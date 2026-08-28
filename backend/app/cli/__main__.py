import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from app.crawlers.registry import DEFAULT_JOB_SOURCE_REGISTRY

SUPPORTED_SOURCES = frozenset(DEFAULT_JOB_SOURCE_REGISTRY.names)

def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "date must use YYYY-MM-DD format"
        ) from error


def positive_int(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "limit must be an integer"
        ) from error

    if limit < 1:
        raise argparse.ArgumentTypeError(
            "limit must be greater than zero"
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
        type=positive_int,
        default=20,
        help=(
            "Number of jobs to fetch. "
            "Each source may define a lower maximum."
        ),
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

    import_parser = subparsers.add_parser(
        "import-jsonl-jobs",
        help=(
            "Import normalized JSONL jobs "
            "into PostgreSQL"
        ),
    )

    import_parser.add_argument(
        "--date",
        dest="target_date",
        type=iso_date,
        required=True,
        help="Crawl date using YYYY-MM-DD",
    )
    import_parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/jobs"),
        help="Job JSONL data directory",
    )
    import_parser.add_argument(
        "--timezone",
        default="Asia/Ho_Chi_Minh",
        help="Timezone used to interpret crawl date",
    )
    import_parser.add_argument(
        "--source",
        choices=sorted(SUPPORTED_SOURCES),
        default=None,
        help="Only import one source",
    )

    index_parser = subparsers.add_parser(
        "index-jobs",
        help="Synchronize PostgreSQL jobs to Qdrant."
    )

    index_parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=100,
        help=(
            "Number of PostgreSQL jobs scanned "
            "per batch."
        ),
    )
    return parser


async def execute(args: argparse.Namespace) -> int:
    if args.command == "crawl-jobs":
        from app.cli.crawl_jobs import crawl_jobs, print_result
        

        result = await crawl_jobs(
            source_name=args.source,
            limit=args.limit,
            cursor=args.cursor,
            data_dir=args.data_dir,
            timeout_seconds=args.timeout,
        )

        print_result(result)
        return 0

    if args.command == "import-jsonl-jobs":
        from app.cli.crawl_jobs import print_result
        from app.cli.import_jsonl_jobs import import_jsonl_jobs

        result = await import_jsonl_jobs(
            target_date=args.target_date,
            data_dir=args.data_dir,
            timezone_name=args.timezone,
            source=args.source,
        )

        print_result(result)
        return 0

    if args.command == "index-jobs":
        from app.cli.crawl_jobs import print_result
        from app.cli.index_jobs import sync_job_index

        result = await sync_job_index(scan_batch_size=args.batch_size)

        print_result
        return 0

    raise ValueError(
        f"Unsupported command: {args.command}"
    )


def print_error(error: Exception) -> None:
    payload = {
        "status": "failed",
        "error_type": type(error).__name__,
        "message": str(error),
    }

    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return asyncio.run(execute(args))
    except KeyboardInterrupt:
        print_error(RuntimeError("Command interrupted by user"))
        return 130
    except Exception as error:  # noqa: BLE001 - CLI boundary logs failures.
        print_error(error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
