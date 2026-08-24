from app.crawlers.sources.structured_job_board import (
    StructuredJobBoardSource,
)


class ItViecJobSource(StructuredJobBoardSource):
    source_name = "itviec"
    attribution = "ITviec"
    listing_url = "https://itviec.com/it-jobs"
    detail_path_prefix = "/it-jobs/"
    detail_path_pattern = r"/it-jobs/.+-\d+"
    allowed_hosts = frozenset({"itviec.com", "www.itviec.com"})
