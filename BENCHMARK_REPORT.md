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

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
