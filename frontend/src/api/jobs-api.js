import { requestJson } from "./http-client.js";
import { normalizeJobSearchResult } from "./normalizers.js";

const JOB_SEARCH_ENDPOINT = "/api/v1/jobs/search";

export async function searchJobs({
  query,
  filters = {},
  sort = "relevance",
  page = 1,
  pageSize = 10,
}) {
  const responseBody = await requestJson(
    JOB_SEARCH_ENDPOINT,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query,
        filters,
        sort,
        page,
        page_size: pageSize,
      }),
    },
    "Không thể kết nối với dịch vụ tìm kiếm việc làm.",
  );

  const data = responseBody?.data ?? responseBody;

  return normalizeJobSearchResult(data);
}