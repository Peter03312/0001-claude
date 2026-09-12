# 卷材超声扫查缺陷簇归并服务

纯后端 API：将圆周扫查的毫米制回波归并为**唯一缺陷簇**，自动合并跨周长零点被拆成首尾两组的同一缺陷。

- Python 3.12 + FastAPI + Pydantic v2
- Docker Compose 一键运行，宿主端口由 `API_PORT` 覆盖（默认 8000）
- 一次性验收服务 `verify`
- pytest 覆盖算法边界与请求校验

## 快速开始

```bash
# 构建并启动 API（默认 http://localhost:8000）
docker compose up --build api

# 覆盖宿主端口，例如 9000
API_PORT=9000 docker compose up --build api
```

交互式文档：`http://localhost:8000/docs`，健康检查：`GET /health`。

## 一次性验收

```bash
# 方式一：运行验收套件（自动拉起 api 并等待健康）
docker compose run --rm verify

# 方式二：验收失败时让整个 compose 以非零码退出
docker compose up --build --exit-code-from verify
```

`verify` 观察：跨零点合并、阈值包含边界、稳定起点与长度、回波数、峰值位置，以及非法请求整单拒绝。

## 运行测试

```bash
# 容器内
docker compose run --rm api pytest

# 或本地（Python 3.12）
pip install -r requirements.txt
pytest
```

## API

### `POST /clusters`

请求体（单位均为 mm）：

| 字段 | 约束 |
| --- | --- |
| `L` | 周长，有限且 `L > 0` |
| `G` | 归并间距，有限且 `0 ≤ G < L/2` |
| `echoes` | 至少 1 项；空数组整单拒绝 |
| `echoes[].position` | 有限且 `0 ≤ position < L` |
| `echoes[].amplitude` | 任意有限数值 |

不允许未知字段。任何非法字段都返回 `422` 与可定位的 `detail[].loc`，且不输出任何部分簇。

请求示例：

```bash
curl -s http://localhost:8000/clusters \
  -H 'Content-Type: application/json' \
  -d '{
    "L": 360.0,
    "G": 10.0,
    "echoes": [
      {"position": 355.0, "amplitude": 80.0},
      {"position": 358.0, "amplitude": 120.0},
      {"position": 2.0,   "amplitude": 90.0},
      {"position": 5.0,   "amplitude": 60.0}
    ]
  }'
```

响应（`200`，簇按起点升序）：

```json
{
  "clusters": [
    {
      "start": 355.0,
      "length": 10.0,
      "echo_count": 4,
      "peak_amplitude": 120.0,
      "peak_position": 358.0
    }
  ]
}
```

校验失败示例（`G ≥ L/2`）：

```bash
curl -s http://localhost:8000/clusters -H 'Content-Type: application/json' \
  -d '{"L": 100.0, "G": 50.0, "echoes": [{"position": 10.0, "amplitude": 1.0}]}'
```

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "G"],
      "msg": "G must satisfy 0 <= G < L/2 (got G=50.0, L/2=50.0)",
      "input": 50.0
    }
  ]
}
```

### 响应字段

| 字段 | 含义 |
| --- | --- |
| `start` | 簇起点位置 |
| `length` | 沿周长正向从起点到末点的弧长 |
| `echo_count` | 去重后的回波数 |
| `peak_amplitude` | 簇内最大幅值 |
| `peak_position` | 峰值位置；幅值并列时取最小位置 |

## 归并规则

1. **同位置去重**：同一 `position` 的回波只保留幅值最大者。
2. **环向归并**：相邻（含末点到首点的环绕距离）距离 `≤ G` 的回波归为一簇；距离恰等于 `G` 也合并。若所有相邻距离均 `≤ G`，全体为一簇。
3. **簇起点**：普通簇以最小位置为起点；跨零点簇以簇内最大空隙后的回波为起点，最大空隙并列时选择结束位置数值最大的空隙。
4. **簇长度**：沿周长正向从起点计算至末点。
5. **峰值**：取最大幅值；幅值并列时取最小位置。
6. 结果按起点升序返回。

## 项目结构

```
app/
  main.py        # FastAPI 入口、路由、跨字段校验
  models.py      # Pydantic 请求/响应模型
  clustering.py  # 纯算法：去重、环向归并、簇描述
verify/
  verify.py      # 一次性验收套件（python -m verify.verify）
tests/
  test_clustering.py  # 算法边界
  test_api.py         # API 与校验
docker-compose.yml    # api + verify 服务
Dockerfile            # python:3.12-slim
```
