# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Đỗ Tuấn Anh (2A202603465)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11, WSL2 Ubuntu (Python 3.12), Docker Desktop; agent chạy local bằng `python app.py`, mock LLM (không gọi API thật)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM trả lời khoảng 150–230 ms khi bình thường (p95 ≈ 222 ms ở tải thấp), nên 500 ms cho dư địa gấp đôi mà người dùng vẫn thấy nhanh; chặt hơn sẽ báo động giả khi có vài request chậm. |
| Error rate `/ask` | < 2 % | Mock LLM cố ý trả lỗi 503 ở mức khoảng 1–2% để giả lập lỗi upstream; đặt 2% là mức tối thiểu chấp nhận được, dưới mức đó người dùng thử lại là xong. |
| Accuracy trên golden dataset | ≥ 85 % | Dùng cho quality gate trong CI (Exercise 7.3): dưới 85% thì chặn merge, vì khi đó agent trả lời sai quá nhiều câu trong bộ 23 câu. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.54 | 191.1 | 221.6 | 1679.9 | 1.00% | ✅ PASS |
| 10 | 40.27 | 194.3 | 221.9 | 1673.8 | 1.33% | ✅ PASS |
| 50 | 109.0 | 197.6 | 287.8 | 1722.5 | 0.33% | ✅ PASS |
| 100 | 140.41 | 265.0 | 1115.0 | 1723.0 | 1.00% | ❌ FAIL (p95) |

(Nguồn: `develop/reports/load_v2_c1.json`, `_c10`, `_c50`, `_c100`; mỗi mức 300 request.)

**Nhận xét:** RPS tăng gần tuyến tính ở mức thấp: từ 1 lên 10 concurrency RPS tăng 8.9 lần (4.54 → 40.27) vì mỗi request chủ yếu chờ mock LLM (I/O, không tốn CPU) nên chạy song song được. Từ 10 lên 50 chỉ tăng 2.7 lần, và từ 50 lên 100 chỉ tăng 1.3 lần (109 → 140): agent bắt đầu bão hoà (một process, event loop và ngưỡng số request song song). Dấu hiệu rõ nhất là p95 tăng vọt từ 288 ms lên 1115 ms ở concurrency 100 và vi phạm SLO, trong khi p50 chỉ tăng nhẹ (198 → 265 ms): request xếp hàng chờ nhau nên đuôi phân bố dài ra. Ở concurrency 1 và 10, p99 (khoảng 1.7 s) không đến từ tải mà do 3% request bị mock làm chậm có chủ ý.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 193.0 | 221.9 | 231.4 |
| 0.03 (mặc định) | 230.4 | 221.8 | 1702.2 |
| 0.1 | 296.5 | 1683.9 | 1712.0 |

(Nguồn: `develop/reports/load_v2_slow_0.json`, `_0.03`, `_0.1`; mỗi lần 300 request, concurrency 20.)

**Nhận xét:** Nhạy nhất là p99, rồi đến p95. Khi tỉ lệ request chậm đi từ 0 lên 3%, avg chỉ tăng từ 193 lên 230 ms (+19%) và p95 gần như không đổi (222 ms), nhưng p99 nhảy từ 231 lên 1702 ms (gấp 7 lần). Khi lên 10%, số request chậm vượt 5% tổng nên p95 cũng nhảy lên 1684 ms và SLO p95 bị vi phạm, trong khi avg mới 296 ms, vẫn trông ổn. Trung bình bị hàng trăm request nhanh làm loãng đi nên che mất vấn đề: cứ 100 người thì có 3–10 người chờ hơn 1.7 giây mà avg không báo gì. Vì vậy SLO phải đặt theo percentile (p95/p99), vì nó phản ánh trải nghiệm của người dùng xấu số nhất.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.7 | 108.8 | 113.7 |
| Tổng cost (USD) | 0.000399 | 0.000758 | 0.000790 |
| Cost / câu đúng (USD) | 0.00039855 | 0.00003607 | 0.00003436 |
| Quality gate | FAIL (ngưỡng 80%) | PASS (ngưỡng 80%, 0 regression) | PASS (ngưỡng 100%, 0 regression) |

(Nguồn: `develop/reports/eval_v1.json`, `eval_v2.json`, `eval_v2_fixed.json`.)

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` (JWT khác gì API key?) | `token`, `hết hạn`, `chữ ký` | Thêm vào cuối `KNOWLEDGE_BASE` (`develop/utils/mock_llm.py`) một tài liệu với từ khoá `["jwt", "api key"]`, giải thích API key cố định không hết hạn còn JWT là token có chữ ký, chứa thông tin user và thời điểm hết hạn. Dùng cả `api key` để tài liệu này thắng tài liệu API key cũ khi câu hỏi nhắc cả hai. |
| `scaling-03` (HPA scale dựa trên chỉ số nào?) | `cpu`, `memory`, `custom metrics` | Thêm tài liệu với từ khoá `["hpa", "kubernetes", "autoscal"]`: HPA scale số pod theo CPU, memory hoặc custom metrics như RPS, độ dài hàng đợi. |

Sau khi sửa: 23/23 đúng, 2 câu được cải thiện, **0 regression** so với `eval_v2.json`; các từ khoá mới chỉ khớp câu hỏi của chính chúng nên không làm đổi kết quả câu khác.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 có thêm bước retrieval nên prompt dài hơn: số token trung bình tăng từ 56.7 lên 108.8 (+92%) và tổng chi phí tăng từ $0.000399 lên $0.000758 (+90%). Đổi lại accuracy tăng từ 4.3% lên 91.3%. So theo "cost / câu đúng" thì v2 rẻ hơn v1 hơn 11 lần ($0.0000361 so với $0.000399), vì v1 trả lời sai gần như mọi câu nên tiền bỏ ra gần như phí. Nếu chỉ nhìn "cost / câu" (v2 đắt gấp đôi) sẽ chọn nhầm v1. Về latency, p95 trong eval của v1 là 333.9 ms (do 1 request chậm trong 23 câu) và của v2 là 220.5 ms; mẫu 23 câu quá nhỏ để kết luận về latency, cần dựa vào load test (mục 2).

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** — `screenshots/prometheus-alert-firing.png` (cả 2 alert cùng firing) và `screenshots/prometheus-alert-details.png`

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (critical) firing, giá trị 16.6% so với ngưỡng 5% | Trang Alerts hiện `Active Since 3m 3s` tại lúc chụp (đã qua `for: 1m`); mình không ghi lại giờ đổi cấu hình nên chưa có số chính xác cho khoảng thời gian từ lúc đổi đến lúc firing | Panel Error rate (đỏ) và Requests/s theo status code (503 tăng) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (warning) firing, p95 = 1.90 s so với ngưỡng 1 s | `Active Since 3m 12s` tại lúc chụp (đã qua `for: 2m`); cũng chưa ghi giờ đổi cấu hình | Panel Latency p50/p95/p99 (p95, p99 tăng vọt trong khi p50 gần như không đổi) |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (warning, ngưỡng $2/giờ) | 150 s (đổi lúc 11:15:39, firing lúc 11:18:09; đo bằng script poll `/api/v1/alerts` mỗi 5 s) | Panel Cost burn rate (USD/giờ) và LLM cost (1h) |
| D | `docker pause` 1 instance | `AgentInstanceDown` (critical, `for: 30s`) | 40 s (pause lúc 11:19:13, firing lúc 11:19:53) | Panel Instances up (từ 2 xuống 1) |
| E | `AGENT_VERSION=v1` | Không có alert mới do thí nghiệm này gây ra. Lúc kiểm tra (150 s sau khi đổi) chỉ còn `LLMCostBurnRateHigh` đang firing, đó là tàn dư của thí nghiệm C vì alert dùng cửa sổ `rate(...[5m])` nên chưa kịp hạ xuống dưới $2/giờ | Không áp dụng (không có alert). Dấu hiệu thấy được trên dashboard: Retrieval hit ratio mất, Tokens/s giảm, bảng version đổi sang v1 |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Chuyển nhầm sang v1 không làm hạ tầng hỏng: request vẫn trả 200, latency còn nhanh hơn, chi phí còn rẻ hơn (token ít hơn), nên cả bốn alert hạ tầng đều im lặng, trong khi chất lượng tụt từ 91–100% xuống 4.3% (mục 3). Cách phát hiện: (1) chạy **eval định kỳ** (hoặc sau mỗi deploy) trên golden dataset với quality gate và cảnh báo khi accuracy giảm; (2) theo dõi **metric chất lượng** như tỉ lệ retrieval tìm được tài liệu (retrieval hit ratio) và alert khi tụt mạnh; (3) alert khi metric `agent_info` (version/model) **khác phiên bản kỳ vọng** sau deploy; (4) triển khai **canary** và so sánh chất lượng trước khi chuyển hết traffic; (5) thu thập phản hồi của người dùng hoặc chấm mẫu traffic thật bằng LLM-as-judge.

Ghi chú về cách đo C và D: thời gian tính từ lúc đổi cấu hình đến lúc Prometheus báo `firing`, đã bao gồm `for` của rule (C: 2 phút, D: 30 giây), thời gian container khởi động lại và chu kỳ scrape; riêng C còn phải chờ cửa sổ `rate(...[5m])` tích luỹ đủ chi phí của model lớn.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: `971ef23548084e5f4284b7f997b9eb13`
- Tổng thời gian: 1721.7 ms (log `http_request`; Jaeger hiển thị 1.7 s)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1694.6 ms, 98.4% tổng thời gian). Các span còn lại: `agent.retrieve_context` 25 ms, `agent.run` bao trùm cả hai. Kết luận: request chậm vì lời gọi LLM (upstream), không phải do code của agent hay bước retrieval.
- Ảnh: `screenshots/jaeger-slow-trace.png`
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep "971ef23"`):

```json
{"ts": "2026-11-25T10:40:25.335612+00:00", "level": "INFO", "service": "observable-agent", "instance": "88334406e4a2", "event": "llm_call", "trace_id": "971ef23548084e5f4284b7f997b9eb13", "span_id": "a308f8c9ed69dc82", "request_id": "00718135bcff", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 74, "output_tokens": 37, "cost_usd": 3.3e-05, "llm_ms": 1694.6}
{"ts": "2026-11-25T10:40:25.336323+00:00", "level": "INFO", "service": "observable-agent", "instance": "88334406e4a2", "event": "http_request", "trace_id": "971ef23548084e5f4284b7f997b9eb13", "span_id": "a308f8c9ed69dc82", "request_id": "00718135bcff", "method": "POST", "route": "/ask", "status": 200, "ms": 1721.7}
```

Hai dòng log cùng `trace_id` với trace trong Jaeger: `llm_call` cho thấy `llm_ms` = 1694.6 khớp với span `chat mock-llm-small`, và `http_request` cho thấy tổng thời gian của cả request.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58.4 | 200 | 550 | 1700 | 84 / 6970 (1.21%) |
| 3 | 59.0 | 200 | 440 | 1700 | 72 / 7042 (1.02%) |

(Nguồn: dòng `POST /ask` trong `production/benchmark-results/scale_1_stats.csv` và `scale_3_stats.csv`. Tính cả `GET /health` thì tổng là 64.1 RPS với 1 instance và 65.2 RPS với 3 instance, p95 510 ms và 410 ms. Locust headless 100 users, ramp-up 10 user/s, 2 phút.)

**Giải thích kết quả:** Scale từ 1 lên 3 instance **cải thiện p95 một chút** (550 → 440 ms, giảm khoảng 20%; tính chung cả `/health` là 510 → 410 ms) nhưng **RPS gần như không đổi** (58.4 → 59.0) và p99 vẫn 1700 ms. Lý do: nút thắt không nằm ở agent mà ở chính bài test. `locustfile.py` đặt `wait_time = between(0.5, 2)`, tức mỗi user nghỉ trung bình 1.25 giây giữa hai request, nên 100 user chỉ sinh ra khoảng 100 / (1.25 + 0.25) ≈ 66 request/giây dù agent nhanh hay chậm. Với tải đó một instance chưa bị bão hoà (ở mục 2.1, một process chịu được 140 RPS khi gọi liên tục không nghỉ), nên thêm instance không làm tăng thông lượng; lợi ích thấy được chỉ là giảm xếp hàng nên p95 giảm. Còn p99 giữ nguyên 1700 ms vì nó do ~3% request bị mock LLM làm chậm có chủ ý (độ trễ của lời gọi LLM), việc thêm instance không rút ngắn được một lời gọi LLM chậm. Muốn thấy scale tăng RPS thật, phải tăng tải vượt khả năng của 1 instance (nhiều user hơn hoặc bỏ `wait_time`); khi đó nút thắt mới là CPU/event loop của agent, và scale ngang mới có tác dụng. Lỗi 1.0–1.2% là lỗi giả lập có chủ ý của mock LLM (`MOCK_ERROR_RATE=0.01`).

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đo bằng percentile, không bằng trung bình.** Khi 3% request bị chậm, avg chỉ tăng 193 → 230 ms nhưng p99 tăng 231 → 1702 ms (mục 2.2); trong Locust 100 user p99 vẫn là 1700 ms dù scale lên 3 instance (mục 5). SLO và alert phải đặt theo p95/p99.
  2. **Hiểu bài test đo cái gì trước khi kết luận.** Scale từ 1 lên 3 instance gần như không đổi RPS (58.4 → 59.0) vì `wait_time` của Locust giới hạn tải ở khoảng 66 req/s, không phải vì scale vô ích. Kết quả benchmark phản ánh cả công cụ đo chứ không chỉ hệ thống bị đo.
  3. **Ba trụ cột bổ sung cho nhau.** Dashboard (metrics) báo p95 tăng và 2 alert firing; Jaeger chỉ ra chậm ở span `chat mock-llm-small` (98.4% thời gian); log JSON có cùng `trace_id` xác nhận chi tiết (`llm_ms` 1694.6). Và "cost / câu đúng" cho thấy v2 rẻ hơn v1 hơn 11 lần dù cost / câu đắt gấp đôi: số đo sai chỉ số dễ dẫn đến chọn sai phiên bản.
- Nếu đưa agent này lên production thật, sẽ thêm:
  - Alert theo tỉ lệ lỗi và độ trễ **ở tầng Nginx/load balancer** hoặc synthetic check từ bên ngoài, vì lỗi 504 do instance treo không xuất hiện trong metric của chính agent.
  - Metric/alert **chất lượng** (accuracy theo eval định kỳ trên traffic thật, tỉ lệ retrieval không tìm thấy tài liệu), vì lỗi chất lượng (ví dụ chạy nhầm v1) không làm metric hạ tầng nào đỏ.
  - Alert **budget theo ngày/tháng** và theo user (hiện chỉ có burn rate theo giờ), cùng alert cho saturation (`agent_in_flight_requests` kéo dài ở mức cao) và tỉ lệ 429 của rate limiter.
