# Deployment Information

## Public URL
https://agent-production-cfcee077.up.railway.app

## Platform
Railway (build từ `06-lab-complete/Dockerfile`, health check `/health`) + Railway Redis.

## Test Commands

### Health Check
```bash
curl https://agent-production-cfcee077.up.railway.app/health
# 200: {"status":"ok","uptime_seconds":...,"environment":"production"}
```

### Readiness (Redis nối được)
```bash
curl https://agent-production-cfcee077.up.railway.app/ready
# 200: {"ready":true}
```

### Không có API key → 401
```bash
curl -X POST https://agent-production-cfcee077.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# 401
```

### Có API key → 200
```bash
curl -X POST https://agent-production-cfcee077.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# 200: {"question":"Hello","answer":"..."}
```

## Environment Variables Set (giá trị không ghi vào repo)
- `AGENT_API_KEY` — chuỗi ngẫu nhiên, đặt trên Railway
- `REDIS_URL` — tham chiếu tới service Redis của Railway
- `ENVIRONMENT=production`
- `PORT` — do Railway tự cấp (app lắng nghe theo biến này)
- `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD` — dùng giá trị mặc định (10 và 1.0)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png) — dashboard Railway của project
- [Service running](screenshots/running.png) — service agent đang chạy (Active) và log khởi động
- [Test results](screenshots/test.png) — `/health` 200, `/ready` 200, `/ask` không có key 401. Ảnh này chụp ở phiên terminal chưa đặt `$KEY` nên lệnh thứ 4 (có key) hiện 401; lệnh đó đã trả 200 khi chạy ở phiên có `$KEY` đúng.
