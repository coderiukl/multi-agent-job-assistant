# Kiến trúc hệ thống hiện tại – As-is Architecture

Tài liệu này mô tả kiến trúc đã được triển khai trên nhánh `main` của hệ thống
Multi-Agent Job Assistant.

Những thành phần chưa triển khai như authentication, Redis, MinIO,
Interview Agent và Human-in-the-loop không thuộc kiến trúc As-is.

## 1. Kiến trúc tổng thể

```mermaid
flowchart TD
    USER["Người dùng"] --> FE["Frontend<br/>HTML, CSS, JavaScript"]
    FE --> API["FastAPI REST API"]

    API --> CVAPI["CV API"]
    API --> JOBAPI["Job Search API"]
    API --> CONVAPI["Conversation API"]

    CVAPI --> CVP["CV Processing Service"]
    CVP --> PDF["PDF Inspector<br/>Native Text và PaddleOCR"]
    PDF --> PARSER["CV Parser Agent"]
    PARSER --> CVSTORE[("Local CV Profile Storage")]

    JOBAPI --> SEARCH["Hybrid Job Search Service"]

    CONVAPI --> GRAPH["LangGraph Conversation Workflow"]
    GRAPH --> MEMORY[("LangGraph Checkpoint")]

    GRAPH --> INTENT["Intent Analyzer"]
    GRAPH --> CVA["CV Analysis Agent"]
    GRAPH --> JSA["Job Search Agent"]
    GRAPH --> JMA["Job Matching Agent"]
    GRAPH --> CAA["Career Advice Agent"]
    GRAPH --> CLA["Cover Letter Agent"]

    JSA --> SEARCH
    SEARCH --> PG[("PostgreSQL Jobs")]
    SEARCH --> QD[("Qdrant Job Embeddings")]

    INTENT --> LLM["LLM Factory"]
    PARSER --> LLM
    CVA --> LLM
    JSA --> LLM
    JMA --> LLM
    CAA --> LLM
    CLA --> LLM

    LLM --> PROVIDER{"LLM Provider"}
    PROVIDER --> OPENAI["OpenAI"]
    PROVIDER --> ROUTER["9Router"]

    AF["Airflow Crawling Pipeline"] --> RAW[("Raw JSONL và Metrics")]
    AF --> PG
    PG --> INDEX["BAAI/bge-m3 Embedding"]
    INDEX --> QD
```

## 2. Các tầng kiến trúc

```mermaid
flowchart TD
    L1["Presentation Layer<br/>HTML, CSS, JavaScript"]
    L2["API Layer<br/>FastAPI Routers và Schemas"]
    L3["Workflow Layer<br/>LangGraph State và Routing"]
    L4["Agent Layer<br/>Sáu Agent chuyên biệt"]
    L5["Service Layer<br/>Nghiệp vụ và tính toán xác định"]
    L6["Repository Layer<br/>Truy cập dữ liệu"]
    L7["Data Layer<br/>PostgreSQL, Qdrant và Local Storage"]

    L1 --> L2
    L2 --> L3
    L2 --> L5
    L3 --> L4
    L4 --> L5
    L5 --> L6
    L6 --> L7
```

### Presentation Layer

Frontend sử dụng:

- HTML.
- CSS.
- Vanilla JavaScript.
- Fetch API.
- Vite.

Frontend chịu trách nhiệm:

- Tải CV.
- Nhập câu hỏi.
- Nhập Job Description.
- Hiển thị danh sách việc làm.
- Hiển thị kết quả CV Analysis.
- Hiển thị Job Matching.
- Hiển thị Career Advice và Cover Letter.
- Quản lý danh sách cuộc hội thoại trên trình duyệt.

Mã nguồn chính:

```text
frontend/index.html
frontend/src/main.js
frontend/src/api/
frontend/src/features/
frontend/src/css/
```

### API Layer

FastAPI cung cấp các nhóm API:

| API | Trách nhiệm |
|---|---|
| Health API | Kiểm tra trạng thái FastAPI |
| CV API | Upload, kiểm tra và xử lý CV |
| Job API | Tìm kiếm việc làm |
| Conversation API | Điều phối hội thoại và lấy lịch sử |

Mã nguồn chính:

```text
backend/app/main.py
backend/app/api/router.py
backend/app/api/v1/router.py
backend/app/api/v1/endpoints/
```

### Workflow Layer

LangGraph chịu trách nhiệm:

- Lưu Conversation State.
- Khôi phục conversation context.
- Phân tích ý định.
- Kiểm tra dữ liệu còn thiếu.
- Lập kế hoạch workflow.
- Điều hướng đến Agent.
- Chạy multi-agent workflow.
- Lưu checkpoint và lịch sử hội thoại.

Mã nguồn chính:

```text
backend/app/graphs/conversation/state.py
backend/app/graphs/conversation/builder.py
backend/app/graphs/conversation/routing.py
backend/app/graphs/conversation/planning.py
backend/app/graphs/conversation/nodes.py
backend/app/graphs/conversation/workflow.py
```

### Agent Layer

Hệ thống hiện có sáu Agent:

| Agent | Input chính | Output chính |
|---|---|---|
| CV Parser Agent | Nội dung CV | CVProfile |
| CV Analysis Agent | CVProfile | CVAnalysisResult |
| Job Search Agent | Truy vấn và CV context | JobSearchPlan |
| Job Matching Agent | CVProfile và Job | JobMatchingAssessment |
| Career Advice Agent | CV và matching evidence | CareerAdviceResult |
| Cover Letter Agent | CV và Job Description | CoverLetterResult |

Mã nguồn:

```text
backend/app/agents/
backend/app/prompts/
backend/app/schemas/
```

Mỗi Agent chỉ thực hiện một trách nhiệm và sử dụng structured output thay vì
trả dữ liệu tự do cho Agent khác.

### Service Layer

Service Layer chứa nghiệp vụ không nên đặt trực tiếp trong Agent hoặc API.

Các trách nhiệm chính:

- Xử lý file CV.
- Hợp nhất native text và OCR.
- Tính điểm Job Matching.
- Tìm kiếm và xếp hạng việc làm.
- Điều phối conversation.
- Thu thập và chuẩn hóa job.

Mã nguồn:

```text
backend/app/services/
```

### Repository Layer

Repository Layer tách nghiệp vụ khỏi cách lưu trữ dữ liệu.

Mã nguồn:

```text
backend/app/repositories/
```

Các repository hiện tại chịu trách nhiệm:

- Lưu và đọc CVProfile.
- Lưu dữ liệu job dạng JSONL.
- Upsert job vào PostgreSQL.
- Truy vấn ứng viên việc làm.
- Đọc job phục vụ quá trình indexing.

### Data Layer

| Thành phần | Dữ liệu |
|---|---|
| PostgreSQL | Job đã chuẩn hóa |
| PostgreSQL Checkpoint | Trạng thái và lịch sử LangGraph |
| Qdrant | Vector embedding của việc làm |
| Local Storage | Tệp CV PDF và CVProfile |
| JSONL | Dữ liệu job thô |
| Metrics JSON | Kết quả crawl theo batch và theo ngày |

## 3. Luồng Conversation Workflow

```mermaid
flowchart TD
    START["Người dùng gửi yêu cầu"] --> PREP["Prepare Turn"]
    PREP --> RESOLVE["Resolve Context"]
    RESOLVE --> INTENT["Analyze Intent"]

    INTENT --> REQUIRED{"Thiếu CV, JD hoặc<br/>ý định chưa rõ?"}

    REQUIRED -- "Có" --> CLARIFY["Clarification"]
    REQUIRED -- "Không" --> PLAN["Plan Workflow"]

    PLAN --> TYPE{"Workflow Type"}

    TYPE -- "Single Agent" --> DISPATCH["Single Agent Dispatch"]
    TYPE -- "Multi-Agent" --> MULTI["Thực hiện các bước trong WorkflowPlan"]

    DISPATCH --> SINGLE{"Primary Intent"}
    SINGLE --> SMALL["Small Talk"]
    SINGLE --> GENERAL["General Question"]
    SINGLE --> OUT["Out of Scope"]
    SINGLE --> CVA["CV Analysis"]
    SINGLE --> SEARCH["Job Search"]
    SINGLE --> MATCH["Job Matching"]
    SINGLE --> ADVICE["Career Advice"]
    SINGLE --> COVER["Cover Letter"]

    MULTI --> STEP{"Current Step"}
    STEP --> MCV["Workflow CV Analysis"]
    STEP --> MSEARCH["Workflow Job Search"]
    STEP --> MMATCH["Workflow Job Matching"]
    STEP --> MADVICE["Workflow Career Advice"]
    STEP --> MCOVER["Workflow Cover Letter"]

    MCV --> NEXT["Advance Workflow"]
    MSEARCH --> NEXT
    MMATCH --> NEXT
    MADVICE --> NEXT
    MCOVER --> NEXT

    NEXT --> DONE{"Hoàn thành tất cả bước?"}
    DONE -- "Chưa" --> STEP
    DONE -- "Rồi" --> SUMMARY["Build Workflow Response"]

    CLARIFY --> RECORD["Record Assistant Message"]
    SMALL --> RECORD
    GENERAL --> RECORD
    OUT --> RECORD
    CVA --> RECORD
    SEARCH --> RECORD
    MATCH --> RECORD
    ADVICE --> RECORD
    COVER --> RECORD
    SUMMARY --> RECORD

    RECORD --> CHECKPOINT["Lưu Checkpoint"]
    CHECKPOINT --> END["Trả phản hồi"]
```

## 4. Luồng CV Processing

```mermaid
flowchart TD
    UPLOAD["Upload CV PDF"] --> META["Kiểm tra metadata"]
    META --> FILE{"Tệp hợp lệ?"}

    FILE -- "Không" --> ERROR["Trả lỗi validation"]
    FILE -- "Có" --> STORE["Lưu PDF"]

    STORE --> INSPECT["Kiểm tra PDF"]
    INSPECT --> NATIVE["Native Text Extraction"]
    NATIVE --> OCRCHECK{"Có trang cần OCR?"}

    OCRCHECK -- "Có" --> OCR["PaddleOCR"]
    OCRCHECK -- "Không" --> MERGE["Text Merger"]
    OCR --> MERGE

    MERGE --> PARSER["CV Parser Agent"]
    PARSER --> PROFILE["CVProfile"]
    PROFILE --> SAVE["Lưu JSON Profile"]
    SAVE --> RESULT["Trả kết quả upload"]
```

## 5. Luồng Hybrid Job Search

```mermaid
flowchart TD
    QUERY["Job Search Request"] --> AGENT["Job Search Agent"]
    AGENT --> PLAN["JobSearchPlan"]
    AGENT -- "LLM lỗi" --> DIRECT["Direct Search Plan"]
    DIRECT --> PLAN

    PLAN --> PARALLEL{"Tìm kiếm song song"}
    PARALLEL --> SQL["PostgreSQL Search"]
    PARALLEL --> VECTOR["Qdrant Metadata Filter + Semantic Search"]

    VECTOR --> AVAILABLE{"Qdrant thành công?"}
    AVAILABLE -- "Không" --> FALLBACK["PostgreSQL Fallback"]
    AVAILABLE -- "Có" --> LOAD["Đọc chi tiết Job từ PostgreSQL"]

    SQL --> MERGE["Hợp nhất theo job_id"]
    LOAD --> MERGE
    FALLBACK --> MERGE

    MERGE --> SCORE["Tính Hybrid Score"]
    SCORE --> DEDUP["Deduplicate"]
    DEDUP --> SORT["Sort"]
    SORT --> PAGE["Pagination"]
    PAGE --> RESULT["JobSearchResult<br/>retrieved_count, has_more"]
```

Qdrant áp dụng metadata filter trước semantic top-K. PostgreSQL xác nhận lại
filter khi tải source record. Hai tầng dùng cùng quy tắc salary currency và
salary period; không có quy đổi ngầm giữa tháng và năm. Location trên Qdrant
dùng `location_keys` đã chuẩn hóa, còn PostgreSQL mở rộng các alias phổ biến
trước khi tạo điều kiện `ILIKE`.

`total` chỉ là số job deduplicate trong cửa sổ ứng viên đã truy xuất.
`retrieved_count` là số source record sau khi hợp nhất và `has_more` thể hiện
khả năng còn trang tiếp theo; API không mô tả `total` như tổng chính xác của
toàn bộ database.

Công thức:

```text
Final Score =
    0.60 × Semantic Score
  + 0.30 × Keyword Score
  + 0.10 × Freshness Score
```

## 6. Luồng Job Matching

```mermaid
flowchart TD
    INPUT["CVProfile và Job"] --> AGENT["Job Matching Agent"]
    AGENT --> ASSESS["JobMatchingAssessment"]

    ASSESS --> TS["Technical Skills: 40%"]
    ASSESS --> EX["Experience: 25%"]
    ASSESS --> PR["Projects: 15%"]
    ASSESS --> ED["Education: 10%"]
    ASSESS --> LC["Languages và Certifications: 10%"]

    TS --> SCORE["Weighted Score"]
    EX --> SCORE
    PR --> SCORE
    ED --> SCORE
    LC --> SCORE

    SCORE --> NORMALIZE["Chuẩn hóa tiêu chí áp dụng"]
    NORMALIZE --> LEVEL{"Phân loại kết quả"}

    LEVEL --> STRONG["Strong Match: từ 85"]
    LEVEL --> GOOD["Good Match: từ 70"]
    LEVEL --> PARTIAL["Partial Match: từ 50"]
    LEVEL --> LOW["Low Match: dưới 50"]

    STRONG --> RESULT["JobMatchingResult"]
    GOOD --> RESULT
    PARTIAL --> RESULT
    LOW --> RESULT
```

## 7. Luồng Job Crawling và Indexing

```mermaid
flowchart TD
    SCHEDULE["Airflow Scheduler"] --> SOURCE["Chạy DAG theo từng nguồn"]
    SOURCE --> CURSOR["Đọc pagination cursor"]
    CURSOR --> FETCH["Fetch Job Source"]
    FETCH --> RAW["Lưu RawJob thành JSONL"]

    RAW --> MAP["Map thành JobCandidate"]
    MAP --> NORMALIZE["Chuẩn hóa thành NormalizedJob"]
    NORMALIZE --> VALID{"Dữ liệu hợp lệ?"}

    VALID -- "Không" --> FAILURE["Ghi nhận lỗi"]
    VALID -- "Có" --> UPSERT["Upsert PostgreSQL"]

    FAILURE --> METRICS["Tổng hợp Crawl Metrics"]
    UPSERT --> METRICS

    METRICS --> QUALITY{"Batch đạt chất lượng?"}
    QUALITY -- "Không" --> RETRY["Retry hoặc failure callback"]
    QUALITY -- "Có" --> COMMIT["Lưu cursor mới"]

    COMMIT --> RECORD["Lưu Metrics JSON"]
    RECORD --> READ["Đọc Job theo từng batch từ PostgreSQL"]
    READ --> ID["Tạo point ID ổn định từ job_id"]
    ID --> HASH["Kiểm tra content_hash và embedding versions"]

    HASH --> REQUIRED{"Cần index?"}
    REQUIRED -- "Không" --> SKIP["Bỏ qua"]
    REQUIRED -- "Có" --> EMBED["BAAI/bge-m3 Embedding"]

    EMBED --> QDRANT["Upsert Qdrant"]
    SKIP --> SUMMARY["Indexing Summary"]
    QDRANT --> SUMMARY
    SUMMARY --> END["Hoàn thành DAG"]
```

Qdrant lưu riêng từng source record bằng point ID được dẫn xuất ổn định từ
`job_id`. Chữ ký quyết định reindex gồm `content_hash`,
`embedding_model_version` và `embedding_text_version`. Deduplicate liên nguồn
được thực hiện trên kết quả tìm kiếm, không thực hiện bằng cách cho các nguồn
dùng chung một Qdrant point.

Khi chuyển từ collection `jobs_bge_m3_v1` sang `jobs_bge_m3_v2`, chạy full
sync bằng `python -m app.cli index-jobs --batch-size 100`. Các DAG sau đó tiếp
tục index tăng dần theo `job_ids` của từng batch crawl.

Khi `index_payload_version` thay đổi, cũng cần chạy full sync để các point cũ
có đủ metadata filter và payload index tương ứng.

## 8. Thành phần chưa được triển khai

Các thành phần sau thuộc định hướng tương lai, không phải kiến trúc As-is:

- Authentication và JWT.
- Phân quyền người dùng.
- Redis hoặc Celery.
- MinIO hoặc S3.
- Interview Preparation Agent.
- Result Synthesis Agent độc lập.
- Human-in-the-loop hoàn chỉnh.
- Rate limiting.
- Qdrant collection dành riêng cho CV.
- Production deployment hoàn chỉnh.
- LangSmith evaluation dataset.

Các thành phần này chỉ nên xuất hiện trong phần kiến trúc đề xuất hoặc hướng
phát triển của báo cáo.
