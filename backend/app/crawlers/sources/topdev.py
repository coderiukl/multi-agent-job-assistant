from app.crawlers.sources.structured_job_board import (
    StructuredJobBoardSource,
)


class TopDevJobSource(StructuredJobBoardSource):
    source_name = "topdev"
    attribution = "TopDev"
    listing_url = "https://topdev.vn/viec-lam/tim-kiem"
    detail_path_prefix = "/viec-lam/"
    detail_path_pattern = r"/viec-lam/.+-\d+"
    allowed_hosts = frozenset({"topdev.vn", "www.topdev.vn"})
    _MAX_LIMIT = 15
