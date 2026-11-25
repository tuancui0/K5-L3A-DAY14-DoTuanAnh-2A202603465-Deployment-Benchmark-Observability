# Day 14 — Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1 — Anti-patterns trong `01-localhost-vs-production/develop/app.py`

1. **API key hardcode** (dòng 17: `OPENAI_API_KEY = "sk-hardcoded-..."`) — push lên GitHub là lộ key ngay.
2. **Database URL kèm mật khẩu hardcode** (dòng 18: `DATABASE_URL = "postgresql://admin:password123@..."`).
3. **Không có config management** (dòng 21–22: `DEBUG = True`, `MAX_TOKENS = 500` cứng trong code, không đọc từ env).
4. **Dùng `print()` thay vì logging có cấu trúc** (dòng 33, 36, 38), không có level, khó parse trong log aggregator.
5. **Log ra secret** (dòng 34: `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`).
6. **Không có health check** (`/health`, `/ready`): platform không biết khi agent crash để restart.
7. **Host `localhost`** (dòng 51): chỉ nhận kết nối từ chính máy, không chạy được trong container.
8. **Port cố định 8000** (dòng 52): Railway/Render inject `PORT` qua env var.
9. **`reload=True`** (dòng 53): chế độ debug reload không dùng cho production.
10. **Không xử lý SIGTERM / graceful shutdown**: tắt đột ngột sẽ cắt ngang request đang chạy.

### Exercise 1.2 — Kết quả chạy bản develop

curl.exe -i -X POST "http://localhost:8000/ask?question=Hello"

HTTP/1.1 200 OK

date: Wed, 25 Nov 2026 08:28:42 GMT

server: uvicorn

content-length: 103

content-type: application/json

{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}

### Exercise 1.3 — So sánh develop vs production

Kết quả chạy bản production (`python app.py` trong `production/`):

- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":44.0,"version":"1.0.0","environment":"development",...}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` (body `{"question":"Hello"}`) → `200 OK`: `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) ...","model":"gpt-4o-mini"}`
- Lưu ý: lần đầu gửi JSON bị PowerShell làm mất dấu `"` nên app trả `500 Internal Server Error`. Bản production chưa bắt JSON sai (`await request.json()` không có try/except), nên đây là một điểm có thể cải thiện.

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode trong code (`DEBUG = True`, `MAX_TOKENS = 500`) | Đọc từ env vars qua `config.py` (`settings`) | Cùng một image chạy được ở dev/staging/prod, chỉ đổi env; không phải sửa code khi đổi môi trường |
| Secrets | `OPENAI_API_KEY = "sk-..."` trong source | `os.getenv(...)`, `.env` không commit (có `.env.example`) | Tránh lộ key khi push repo; đổi/rotate key không cần deploy lại code |
| Port / Host | `localhost:8000` cố định | `settings.host` (0.0.0.0) và `settings.port` từ `PORT` | Container và PaaS cần bind 0.0.0.0 và dùng port do platform cấp |
| Health check | Không có | `GET /health` (liveness) và `GET /ready` (readiness) | Platform biết khi nào restart container, load balancer biết khi nào được route traffic |
| Logging | `print()` text, có cả secret | JSON log (`logger.info(json.dumps({...}))`), không log secret | Parse/lọc được trong Datadog/Loki; không rò rỉ thông tin nhạy cảm |
| Shutdown | Tắt đột ngột | `lifespan` + handler SIGTERM, cho request hiện tại hoàn thành | Deploy/scale-down không làm rớt request của người dùng |
| Debug reload | `reload=True` luôn bật | `reload=settings.debug` | Reload tốn tài nguyên và không an toàn ở production |
| Input | `question: str` qua query string | Body JSON, validate rỗng → 422 | API rõ ràng, lỗi đầu vào trả mã đúng |


## Part 2: Docker

### Exercise 2.1 — Dockerfile cơ bản (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản đầy đủ, khoảng 1 GB).
2. **Working directory:** `/app` (`WORKDIR /app`).
3. **Vì sao COPY `requirements.txt` trước:** Docker cache theo từng layer. Requirements ít đổi nên layer `pip install` được dùng lại từ cache; chỉ khi `requirements.txt` đổi mới cài lại. Nếu `COPY . .` đứng trước thì chỉ cần sửa 1 dòng code là mất cache và phải cài lại toàn bộ dependencies.
4. **CMD vs ENTRYPOINT:** `CMD` là lệnh mặc định, dễ bị ghi đè khi `docker run <image> <lệnh khác>`. `ENTRYPOINT` là chương trình cố định của container, tham số truyền khi `docker run` được nối thêm vào sau nó. Hai cái hay dùng cùng nhau: ENTRYPOINT là chương trình, CMD là tham số mặc định.

### Exercise 2.2 — Build và chạy bản develop

Chạy `docker run -d -p 8000:8000 --name agent-dev my-agent:develop`:

- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":7.0,"container":true}`
- `POST /ask?question=What+is+Docker` → `200 OK`: `{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}`

### Exercise 2.3 — Multi-stage build

- **Stage 1 (builder):** `python:3.11-slim` + `gcc`, `libpq-dev`, chạy `pip install --user` để cài dependencies vào `/root/.local`.
- **Stage 2 (runtime):** `python:3.11-slim` sạch, tạo user không phải root (`appuser`), chỉ `COPY --from=builder /root/.local` cùng `main.py` và `utils/mock_llm.py`, có `HEALTHCHECK`, chạy `uvicorn` với 2 workers.
- **Vì sao nhỏ hơn:** image cuối không chứa gcc, apt cache, build tools; base là `-slim` thay vì bản đầy đủ.

Kích thước đo bằng `docker images my-agent`:

| Image | Disk usage | Content size |
|-------|-----------:|-------------:|
| `my-agent:develop` (single-stage, `python:3.11`) | 1.67 GB | 426 MB |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | 240 MB | 57.4 MB |

Chênh lệch: **giảm khoảng 85.6%** theo disk usage ((1670 − 240) / 1670), khoảng 86.5% theo content size ((426 − 57.4) / 426).

### Exercise 2.4 — Docker Compose stack

**Các service** (`docker compose ps`): `agent`, `redis`, `qdrant`, `nginx`. Cả bốn cùng nằm trong network `internal` (bridge). Chỉ Nginx publish port ra host (80, 443); agent, redis, qdrant không expose port ra ngoài.

```
Client ──HTTP :80──> nginx ──proxy_pass──> agent:8000 ──> redis:6379  (session / rate limit)
                     (load balancer)                  └─> qdrant:6333 (vector DB)
```

- Thứ tự khởi động: `redis` và `qdrant` phải `healthy` trước (`depends_on: condition: service_healthy`), sau đó mới tới `agent`, rồi `nginx`.
- Giao tiếp giữa các service qua tên service trong network `internal` (`redis://redis:6379/0`, `http://qdrant:6333`), nhờ DNS nội bộ của Docker.
- Dữ liệu redis và qdrant nằm trong volume (`redis_data`, `qdrant_data`) nên không mất khi container bị tạo lại.

Kết quả test qua Nginx (`curl.exe -i http://localhost/health`) → `200 OK`:
`{"status":"ok","uptime_seconds":9.3,"version":"2.0.0",...}`, kèm header bảo mật `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` do Nginx thêm vào.

`POST http://localhost/ask` (body `{"question":"Explain microservices"}`) qua Nginx → `200 OK`: `{"answer":"Đây là câu trả lời từ AI agent (mock). ..."}`

## Part 3: Cloud Deployment

Theo CHECKPOINTS.md, mình deploy agent của Part 6 (`06-lab-complete/`) thay vì app mẫu trong `03-cloud-deployment/`.

- **Platform:** Railway
- **Public URL:** https://agent-production-cfcee077.up.railway.app
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`; chi tiết lệnh test xem `DEPLOYMENT.md`

### Exercise 3.1/3.2 — So sánh `railway.toml` với `render.yaml`

| | `railway.toml` | `render.yaml` |
|---|---|---|
| Phạm vi | Chỉ cấu hình build và deploy của một service; biến môi trường đặt bằng CLI (`railway variables set`) hoặc dashboard | Blueprint (IaC) khai báo cả nhiều service (web + redis/keyvalue) và danh sách biến môi trường |
| Build | `builder = "DOCKERFILE"` (hoặc NIXPACKS tự nhận diện) | `runtime: docker` hoặc `runtime: python` kèm `buildCommand` |
| Health check | `healthcheckPath`, `healthcheckTimeout` | `healthCheckPath` |
| Restart | `restartPolicyType`, `restartPolicyMaxRetries` | Render tự restart khi health check fail, không khai báo trong file |
| Secret | Không ghi vào file, đặt bằng CLI/dashboard | `generateValue: true` (tự sinh) hoặc `sync: false` (nhập tay trên dashboard) |
| Redis | Thêm Redis từ dashboard rồi trỏ `REDIS_URL` | Khai báo ngay trong file bằng `type: keyvalue` + `fromService` |
| Deploy | `railway up` đẩy code từ máy | Push GitHub, Render đọc Blueprint, `autoDeploy` |

### Exercise 3.3 — Pipeline Cloud Run (`cloudbuild.yaml` + `service.yaml`, chỉ đọc)

`cloudbuild.yaml` là pipeline CI/CD chạy mỗi lần push lên `main`: (1) chạy `pytest`, (2) build Docker image gắn tag `$COMMIT_SHA` và `latest` có `--cache-from` để dùng lại layer, (3) push image lên Container Registry, (4) `gcloud run deploy` lên Cloud Run (min 1, max 10 instance, 512Mi RAM, secret lấy từ Secret Manager). Mỗi bước dùng `waitFor` nên test lỗi thì không build và không deploy. `service.yaml` là bản mô tả service dạng IaC (kiểu Knative) cho cùng cấu hình: autoscaling `minScale: 1` tránh cold start, `maxScale: 10`, tối đa 80 request đồng thời mỗi instance, giới hạn CPU/RAM, cổng 8000 và env.

## Part 4: API Security

### Exercise 4.1 — API key (`04-api-gateway/develop/app.py`)

- **Check ở đâu:** hàm dependency `verify_api_key` (đọc header `X-API-Key` bằng `APIKeyHeader`), gắn vào `/ask` qua `Depends(verify_api_key)`. Key đúng lấy từ biến môi trường `AGENT_API_KEY`.
- **Sai key thì sao:** thiếu key → `401`; có key nhưng sai → `403`.
- **Rotate key:** đặt `AGENT_API_KEY` mới trên môi trường rồi restart; key cũ lập tức không còn hiệu lực. Không cần sửa code vì key không hardcode.

```
$ curl.exe -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" --data-binary "@body.json"
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

$ curl.exe -i ... -H "X-API-Key: wrong" ...
HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

$ curl.exe -i ... -H "X-API-Key: secret-key-123" ...
HTTP/1.1 200 OK
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). ..."}
```

### Exercise 4.2 — JWT (`04-api-gateway/production`)

Lấy token bằng `POST /auth/token` với `student` / `demo123` (token đã che):

```
{"access_token":"eyJhbGciOiJIUzI1NiIs...<đã che>","token_type":"bearer","expires_in_minutes":60}
```

Dùng token (`Authorization: Bearer <token>`):

```
HTTP/1.1 200 OK
{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. ...","usage":{"requests_remaining":9,"budget_remaining_usd":1.8e-05}}
```

Token JWT chứa `sub`, `role`, `iat`, `exp` và được ký bằng `JWT_SECRET`, nên server không cần tra DB ở mỗi request.

### Exercise 4.3 — Rate limiting

- **Algorithm:** Sliding Window Counter (mỗi user một `deque` timestamp, bỏ các timestamp cũ hơn 60 giây).
- **Limit:** user (role `user`) 10 request/phút; admin 100 request/phút.
- **Bypass cho admin:** không bypass hoàn toàn mà dùng limiter khác theo role (`rate_limiter_admin` nếu `role == "admin"`, tài khoản `teacher`).

Vòng lặp 15 request liên tiếp: request 1–9 trả `200`, từ request 10 trở đi trả `429` (request đầu tiên với token đã dùng 1 lượt nên tổng 10 lượt đầu được chấp nhận). Output `curl -i` khi bị chặn:

```
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795597004
retry-after: 50

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":50}}
```

### Exercise 4.4 — Cost guard

`cost_guard.py` giữ một `UsageRecord` cho mỗi user theo ngày (input/output token, số request) và tính chi phí theo giá GPT-4o-mini. Trước khi gọi LLM, `check_budget` kiểm tra hai ngưỡng: budget theo user ($1/ngày) và budget toàn hệ thống ($10/ngày); vượt thì trả `402`, đạt 80% thì ghi cảnh báo. Sau khi gọi, `record_usage` cộng token đã dùng. Record tự reset khi sang ngày mới (so sánh chuỗi ngày).

Bản mẫu dùng RAM nên mất khi restart và không chia sẻ giữa nhiều instance. Bản Redis theo đề bài dùng key `budget:{user_id}:{YYYY-MM}`, cộng dồn bằng `INCRBYFLOAT` và đặt TTL khoảng 32 ngày, nên dữ liệu bền qua restart và dùng chung được cho mọi instance. Vì budget tính bằng tiền nên cần chặn cả khi request đã nằm trong rate limit.

**Vì sao cần cả hai:** rate limit bảo vệ tốc độ (chống spam, quá tải); cost guard bảo vệ tiền (một user gọi chậm nhưng prompt rất dài vẫn có thể đốt hết budget mà không bị rate limit chặn).

## Part 5: Scaling & Reliability

### Exercise 5.1 — Health checks (`05-scaling-reliability/develop/app.py`)

- **`/health` (liveness):** trả `200` miễn là process còn sống, kèm uptime và các check phụ. Kết quả thực tế: `200 OK`, `{"status":"degraded", ..., "checks":{"memory":{"status":"degraded","used_percent":92.6}}}`. RAM máy đang cao nên báo `degraded`, nhưng vẫn là 200 nên platform không restart container.
- **`/ready` (readiness):** trả `200 {"ready":true,"in_flight_requests":1}` khi agent đã khởi động xong; trả `503` khi chưa sẵn sàng hoặc đang shutdown (biến `_is_ready`), để load balancer ngừng gửi traffic vào.
- **Khác nhau:** liveness trả lời "có cần restart không?", readiness trả lời "có nên gửi request vào không?". Chưa ready thì chờ, không restart; chết hẳn (health fail) thì restart.

### Exercise 5.2 — Graceful shutdown

Khi tắt server (Ctrl+C, gửi SIGINT; trên Linux/container là SIGTERM), log ghi:

```
INFO:     Finished server process [24908]
2026-11-25 16:00:35,037 INFO Received signal 2 — uvicorn will handle graceful shutdown
```

Cơ chế: handler `handle_sigterm` log lại tín hiệu, còn uvicorn tự dừng nhận kết nối mới và chạy phần shutdown của `lifespan`. Ở đó `_is_ready = False` (readiness trả 503 để không nhận thêm traffic), vòng lặp chờ tối đa 30 giây cho `_in_flight_requests` về 0, rồi mới thoát; `timeout_graceful_shutdown=30` cho uvicorn đợi tương ứng. Nhờ vậy request đang chạy được hoàn thành thay vì bị cắt ngang.

### Exercise 5.3 — Stateless design

Bản production không giữ `conversation_history` trong RAM mà lưu session (kèm history, tối đa 20 message) vào Redis với key `session:{session_id}` và TTL. Mỗi request đọc session từ Redis, thêm message, ghi lại. Vì vậy instance nào cũng phục vụ được bất kỳ session nào. Nếu để trong RAM, mỗi instance có một dictionary riêng: request thứ 2 rơi vào instance khác sẽ không thấy history của request đầu.

### Exercise 5.4 — Load balancing

`docker compose -p k5-day14-scaling up -d --build --scale agent=3` khởi động 3 agent (`agent-1`, `agent-2`, `agent-3`), 1 Redis và 1 Nginx (cổng 8080). Nginx phân tán request theo vòng tròn: 6 request liên tiếp có `served_by` lần lượt `instance-f53e98`, `instance-54f5e1`, `instance-624fc0`, rồi lặp lại; trường `storage` luôn là `redis`. Log `docker compose logs agent` cho thấy cả 3 instance đều nhận `POST /chat`, và health check nội bộ `GET /health` đều trả 200.

### Exercise 5.5 — Test stateless

`python test_stateless.py` gửi 5 câu trong cùng một session `096ae989-...`:

```
Request 1: [instance-f53e98]   Request 2: [instance-54f5e1]   Request 3: [instance-624fc0]
Request 4: [instance-f53e98]   Request 5: [instance-54f5e1]
Instances used: {'instance-624fc0', 'instance-f53e98', 'instance-54f5e1'}
Total messages: 10   -> ✅ Session history preserved across all instances via Redis!
```

Cả 5 request đi qua 3 instance khác nhau, vậy mà history đọc lại đủ 10 message (5 user + 5 assistant): chứng minh state nằm ở Redis chứ không ở từng instance. Lưu ý script không tự tắt instance nào; việc "một instance chết thì traffic chuyển sang instance khác" được suy ra từ cấu hình Nginx và Redis dùng chung, không được kiểm chứng bằng cách tắt thật trong bài này.

## Part 6: Final Project (`06-lab-complete/`)

`python check_production_ready.py` (chạy trong WSL2 Ubuntu, Python 3.12, Docker Desktop): **PASS 12/12**, 43/43 checks đạt. Image 63 MB; `docker stop` tắt êm, exit code 0 trong 0.6s.

📋 Checklist Deliverable
- ✅ Dockerfile (multi-stage, < 500 MB)
- ✅ docker-compose.yml (agent + redis)
- ✅ .dockerignore
- ✅ Health check endpoint (GET /health)
- ✅ Readiness endpoint (GET /ready)
- ✅ API Key authentication
- ✅ Rate limiting
- ✅ Cost guard
- ✅ Config từ environment variables
- ✅ Structured logging
- ✅ Graceful shutdown
- ✅ Public URL ready (Railway / Render config)

Result: 12/12 tiêu chí đạt · 43/43 checks passed — 🎉 PASS 12/12 — PRODUCTION READY!

## Part 7: Benchmark & Observability

### Exercise 7.1 — Metrics của agent (v2, cổng 8002)

Sau 1 request `POST /ask`, `GET /metrics` cho thấy:

| Loại | Ví dụ trong output | Ý nghĩa |
|---|---|---|
| **Counter** (chỉ tăng) | `http_requests_total{method="POST",route="/ask",status="200"} 1.0`; `llm_tokens_total{...type="input"} 91.0`; `llm_cost_usd_total{...} 4.66e-05` | Tổng số request, token, chi phí tích luỹ từ lúc process chạy |
| **Gauge** (lên xuống) | `agent_in_flight_requests 0.0`; `agent_info{model="mock-llm-small",version="v2"} 1.0` | Giá trị tại thời điểm hiện tại: số request đang xử lý, phiên bản đang chạy |
| **Histogram** (phân bố) | `http_request_duration_seconds_bucket{le="0.2",...} 1.0` kèm `_count` và `_sum` (0.189s); `llm_request_duration_seconds_*` | Đếm số quan sát rơi vào từng bucket để tính p50/p95/p99 bằng `histogram_quantile` |

**Vì sao label `route` dùng route template (`route.path`), không dùng `request.url.path`:** mỗi giá trị khác nhau của một label tạo ra một chuỗi thời gian (time series) riêng. Nếu dùng URL thật, bot quét hàng nghìn URL lạ (`/wp-admin`, `/.env`, `/a1b2c3`...) sẽ tạo hàng nghìn series mới cho mỗi metric (nhân thêm với method, status, bucket của histogram). Đó là cardinality explosion: Prometheus ngốn RAM và disk, query chậm, có thể sập, và kẻ tấn công còn có thể chủ động làm vậy. Dùng template (`/ask`, hoặc `unmatched` cho URL không khớp route nào) giữ số series cố định.

**Metric tự thêm:** `agent_question_length_chars` (Histogram, bucket 20/50/100/200/500/1000/2000) trong `develop/app.py`, được `observe(len(body.question))` trong endpoint `/ask`. Kết quả với câu hỏi mẫu: `agent_question_length_chars_sum 40.0`, `_count 1.0`, nằm trong bucket `le="50.0"`. Dùng Histogram thay vì label `length=...` vì độ dài có vô số giá trị, làm label sẽ gây cardinality bùng nổ.

### Exercise 7.2 — Load test & SLO

Kết quả đầy đủ (4 mức concurrency, 3 mức `MOCK_SLOW_RATE`) ở `BENCHMARK_REPORT.md` mục 2. Tóm tắt: concurrency 1 → 100 cho RPS 4.54 → 140.41, p95 222 → 1115 ms (vi phạm SLO p95 ≤ 500 ms ở mức 100).

**Vì sao avg chỉ tăng nhẹ mà p99 tăng vọt? SLO nên đặt theo chỉ số nào?** Khi 3% request bị chậm (khoảng 1.7 s) còn 97% chỉ mất khoảng 190 ms, avg chỉ tăng từ 193 lên 230 ms vì bị hàng trăm request nhanh làm loãng, nhưng p99 rơi đúng vào nhóm request chậm nên nhảy từ 231 lên 1702 ms. SLO nên đặt theo percentile (p95/p99) vì nó phản ánh trải nghiệm của người dùng bị chậm nhất, thứ mà trung bình che mất.

### Exercise 7.3 — Eval & quality gate

- v1: 4.3% (1/23), gate FAIL. v2: 91.3% (21/23), gate PASS, cải thiện 20 câu, 0 regression.
- v2 sai 2 câu (`security-02`, `scaling-03`); sau khi thêm 2 tài liệu vào `KNOWLEDGE_BASE`: **100% (23/23)**, 2 câu cải thiện, 0 regression, `Quality gate (accuracy ≥ 100%, không regression): PASS` (`reports/eval_v2_fixed.json`).
- **Job CI** (`.github/workflows/eval.yml`): chạy mỗi pull request, bật agent v2 với `MOCK_ERROR_RATE=0`, rồi `python eval/run_eval.py --min-accuracy 0.85`. `run_eval.py` trả exit code 1 khi accuracy dưới ngưỡng hoặc có regression, nên bước này fail, job fail, và nếu bật branch protection yêu cầu check `quality-gate` pass thì PR không thể merge.

# AI LOG

Trong quá trình thực hiện bài lab, tôi có sử dụng Claude Code (trợ lý AI tích hợp trong VS Code) như một công cụ hỗ trợ phát triển. Tuy nhiên, tôi là người chủ động thực hiện các công việc chính, bao gồm nghiên cứu yêu cầu, phân tích mã nguồn, lựa chọn phương án triển khai, chạy thử nghiệm, kiểm tra kết quả và hoàn thiện báo cáo. AI chủ yếu được sử dụng để tham khảo, giải thích vấn đề và hỗ trợ xử lý những phần kỹ thuật cần thiết.

## 1. Các công việc tôi trực tiếp thực hiện

| Phần | Công việc tôi thực hiện |
|---|---|
| Part 1 | Đọc và phân tích mã nguồn, xác định các anti-pattern, đối chiếu sự khác biệt giữa môi trường development và production. |
| Part 2, 4, 5 | Nghiên cứu cấu trúc Dockerfile, Docker Compose, JWT, Rate Limiter, Cost Guard, Health Check và Stateless. Tự đối chiếu với code thực tế để hoàn thiện câu trả lời. |
| Part 6 | Phân tích các TODO, xác định những thành phần còn thiếu và triển khai các chức năng để đáp ứng yêu cầu production-ready. Bao gồm config, authentication, rate limiter, cost guard, Redis, main application và các file cấu hình triển khai. |
| Part 7 | Kiểm tra stack observability, phân tích nguyên nhân container bị crash, bổ sung metric, cập nhật Knowledge Base và xây dựng quy trình CI. |
| Báo cáo | Tổng hợp kết quả thực nghiệm, đối chiếu dữ liệu, phân tích kết quả và hoàn thiện các tài liệu MISSION_ANSWERS.md, BENCHMARK_REPORT.md, DEPLOYMENT.md. |

## 2. Vai trò của AI trong quá trình thực hiện

Tôi sử dụng Claude Code như một công cụ hỗ trợ trong các công việc sau:

- Hỗ trợ giải thích các thành phần kỹ thuật như JWT, Redis, Rate Limiter, Docker và Observability.
- Gợi ý cách phát hiện anti-pattern và các vấn đề có thể phát sinh khi triển khai production.
- Đề xuất hướng xử lý đối với các TODO và lỗi phát sinh trong quá trình triển khai.
- Hỗ trợ viết hoặc điều chỉnh một số đoạn code, file cấu hình và tài liệu.
- Hỗ trợ phân tích output từ các lệnh kiểm thử để tôi có thêm cơ sở đối chiếu.

Các đề xuất từ AI đều được tôi xem xét, điều chỉnh và kiểm tra lại trong môi trường thực tế trước khi sử dụng. Tôi không sử dụng kết quả AI đưa ra như một kết quả kiểm chứng độc lập.

## 3. Quá trình triển khai và kiểm thử thực tế

Toàn bộ quá trình thiết lập môi trường và thực nghiệm được tôi trực tiếp thực hiện trên máy cá nhân:

- Cài đặt và cấu hình Python, Docker Desktop, WSL2 Ubuntu, Python 3.12 thông qua uv và Railway CLI.
- Tự thực hiện các lệnh build image, chạy container, Docker Compose, curl, load test, evaluation và Locust headless.
- Tự thiết lập tài khoản Railway, tạo project, cấu hình Redis và thiết lập AGENT_API_KEY. Các thông tin nhạy cảm không được đưa vào repository.
- Trực tiếp triển khai ứng dụng lên Railway bằng lệnh railway up.
- Tự thay đổi file .env để thực hiện các thí nghiệm A–E.
- Thực hiện benchmark với quy mô 1 và 3 instance.
- Chụp ảnh minh chứng, lưu output và tổng hợp dữ liệu vào các thư mục screenshots/, reports/ và benchmark-results/.

Các số liệu trong báo cáo như kích thước image, RPS, p50/p95/p99, accuracy, cost và thời gian alert firing đều được lấy từ kết quả chạy thực tế. Tôi trực tiếp tổng hợp và đối chiếu dữ liệu từ các file JSON/CSV trước khi đưa vào báo cáo.

## 4. Những lỗi gặp phải và cách tôi xử lý

| Vấn đề | Cách tôi xử lý |
|---|---|
| Docker Hub trả lỗi 429 khi pull image | Đăng nhập Docker Hub bằng docker login và thực hiện build lại. |
| Docker Compose báo thiếu .env.local | Kiểm tra cấu hình và tạo file .env.local rỗng để đáp ứng yêu cầu của compose. |
| pydantic-core không build được trên Python 3.14/3.15 | Kiểm tra tính tương thích và chuyển sang Python 3.12 để chạy script kiểm thử. |
| Graceful shutdown không đạt trên Windows | Xác định vấn đề liên quan đến cách xử lý SIGTERM trên Windows và chuyển sang WSL2 Ubuntu để kiểm tra lại. |
| Container agent của stack observability bị crash với ModuleNotFoundError: uvicorn | Kiểm tra log container, xác định vấn đề liên quan đến PYTHONPATH và điều chỉnh Dockerfile. |
| Alert chưa firing sau khi thay đổi .env | Kiểm tra trạng thái Locust, xác nhận hệ thống vẫn đang nhận tải và chờ đủ khoảng thời gian cấu hình trong điều kiện alert. |

Trong các tình huống trên, tôi chủ động kiểm tra log, xác định nguyên nhân và thử nghiệm phương án xử lý. AI được sử dụng để hỗ trợ giải thích lỗi và tham khảo hướng khắc phục khi cần thiết.

## 5. Kết quả kiểm chứng

Sau khi hoàn thành triển khai, tôi trực tiếp thực hiện lại các bước kiểm tra để xác nhận kết quả:

- Chạy lại `python check_production_ready.py` với Docker trong WSL2 Ubuntu và đạt kết quả PASS 12/12.
- Gọi trực tiếp URL Railway bằng curl:
  - `/health` trả về HTTP 200.
  - `/ready` trả về HTTP 200.
  - `/ask` không có API key trả về HTTP 401.
  - `/ask` có API key hợp lệ trả về HTTP 200.
- Chạy lại evaluation sau khi điều chỉnh KNOWLEDGE_BASE, đạt 100% (23/23) và không có regression theo file `reports/eval_v2_fixed.json`.
- Đối chiếu các số liệu trong BENCHMARK_REPORT.md với dữ liệu gốc từ JSON và CSV.
- Kiểm tra lại các ảnh minh chứng và tài liệu triển khai trước khi hoàn thiện bài nộp.

## 6. Hạn chế và những điểm cần lưu ý

Trong quá trình thực hiện, tôi ghi nhận một số hạn chế:

- Không lưu lại chính xác thời điểm thay đổi cấu hình của thí nghiệm A và B, do đó bảng 4.2 chỉ có thông tin Active Since, chưa thể xác định chính xác khoảng thời gian từ lúc thay đổi cấu hình đến khi alert firing.
- Ảnh `screenshots/test.png` được chụp trong phiên chưa thiết lập biến `$KEY`, nên lệnh thứ tư trả về HTTP 401. Tuy nhiên, tôi đã kiểm tra lại trong phiên có API key và xác nhận endpoint trả về HTTP 200. Thông tin này được ghi chú trong DEPLOYMENT.md.

## 7. Đánh giá mức độ sử dụng AI

AI đóng vai trò là công cụ hỗ trợ trong quá trình thực hiện bài lab, tương tự một trợ lý lập trình giúp giải thích kiến thức, gợi ý phương án và hỗ trợ xử lý một số công việc kỹ thuật.

Tôi là người trực tiếp nghiên cứu yêu cầu, triển khai môi trường, thực hiện các thí nghiệm, kiểm tra lỗi, chạy benchmark, xác minh kết quả và chịu trách nhiệm về nội dung báo cáo cuối cùng.

Việc sử dụng AI giúp tiết kiệm thời gian tra cứu và xử lý vấn đề, nhưng các kết quả được đưa vào bài nộp đều được đối chiếu với quá trình thực nghiệm thực tế của tôi.