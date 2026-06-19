---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "063. k8s 부하 테스트 — k6, Grafana, 비동기 구조"
date: 2026-06-14
tags: [k8s, load-testing, k6, grafana, prometheus, hpa, keda, queue, async]
summary: "k8s 환경에서 부하 테스트는 애플리케이션 성능과 인프라 반응을 동시에 검증한다. k6를 Pod으로 실행해 클러스터 내부에서 트래픽을 발생시키고, Prometheus와 Grafana로 실시간 메트릭을 수집한다. 동기 API뿐 아니라 큐 기반 비동기 구조도 측정 포인트를 나누면 테스트 가능하다."
slug: "063-k8s-load-testing"
categories: ["쿠버네티스"]
---

일반 환경의 부하 테스트와 k8s의 차이는 측정 대상이 하나가 아니라는 것이다. 애플리케이션의 레이턴시와 에러율뿐 아니라 HPA(Horizontal Pod Autoscaler)가 제때 스케일아웃하는지, Pod이 OOM으로 죽지 않는지, Node 자원이 한계에 도달하지 않는지를 동시에 봐야 한다.

## k6를 클러스터 내부에서 실행한다

k6는 Grafana Labs가 관리하는 오픈소스 부하 테스트 도구다. JavaScript로 시나리오를 작성하고 CLI로 실행한다. k8s에서는 k6 자체를 Job Pod으로 띄워 클러스터 내부에서 트래픽을 발생시킨다. 외부에서 호출하면 네트워크 지연이 섞여 애플리케이션 순수 성능을 측정하기 어렵다.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: k6-load-test
spec:
  template:
    spec:
      containers:
        - name: k6
          image: grafana/k6:latest
          command: ["k6", "run", "/scripts/test.js"]
          env:
            - name: TARGET_URL
              value: "http://my-service.default.svc.cluster.local"
            - name: AUTH_TOKEN
              valueFrom:
                secretKeyRef:
                  name: load-test-secrets
                  key: auth-token
          volumeMounts:
            - name: scripts
              mountPath: /scripts
      volumes:
        - name: scripts
          configMap:
            name: k6-scripts
      restartPolicy: Never
```

테스트 스크립트는 ConfigMap으로 주입하고, 인증 토큰이나 비밀번호는 Secret으로 분리한다.

```javascript
// test.js
import http from 'k6/http'
import { check, sleep, Trend } from 'k6'

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // 50 VU(가상 유저)로 램프업
    { duration: '3m', target: 50 },   // 유지
    { duration: '1m', target: 0 },    // 램프다운
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // P95 레이턴시 500ms 이내
    http_req_failed: ['rate<0.01'],    // 에러율 1% 미만
  },
}

export default function () {
  const res = http.get(`${__ENV.TARGET_URL}/api/products`, {
    headers: { Authorization: `Bearer ${__ENV.AUTH_TOKEN}` },
  })
  check(res, { 'status 200': (r) => r.status === 200 })
  sleep(1)
}
```

P95는 전체 요청 중 95번째 백분위 레이턴시다. 평균은 이상치에 희석되어 실제 사용자 경험을 반영하지 못한다. P95와 P99를 함께 보는 것이 일반적이다.

## 분산 부하 테스트: k6 Operator

단일 Pod으로는 트래픽 규모가 부족할 때 k6 Operator를 사용한다. CRD(Custom Resource Definition)로 `TestRun` 리소스를 정의하면 Operator가 여러 k6 Pod을 생성해 VU를 나눠 담당한다.

```yaml
apiVersion: k6.io/v1alpha1
kind: TestRun
metadata:
  name: distributed-test
spec:
  parallelism: 4        # k6 Pod 4개가 동시 실행
  script:
    configMap:
      name: k6-scripts
      file: test.js
```

`parallelism: 4`, VU 200이면 Pod 1개당 50 VU를 담당한다. 결과는 자동으로 집계된다.

## Prometheus와 Grafana 연동

k6 결과를 Prometheus로 내보내면 인프라 메트릭과 부하 메트릭을 Grafana 하나에서 함께 볼 수 있다.

```bash
k6 run --out experimental-prometheus-rw test.js
```

또는 환경변수로 설정한다.

```yaml
env:
  - name: K6_PROMETHEUS_RW_SERVER_URL
    value: "http://prometheus:9090/api/v1/write"
```

Grafana에서 k6가 보내는 주요 메트릭은 다음과 같다.

| 메트릭 | 의미 |
|---|---|
| `k6_http_req_duration` | 요청 레이턴시 (P50/P95/P99) |
| `k6_http_req_failed` | 에러율 |
| `k6_vus` | 현재 활성 가상 유저 수 |
| `k6_iterations` | 완료된 반복 횟수 |

이 메트릭과 `container_memory_usage_bytes`, `container_cpu_usage_seconds_total` 같은 Pod 메트릭을 같은 대시보드에 올려두면 "VU 100명 이상에서 CPU가 한계에 도달한다"는 관계를 직접 확인할 수 있다.

## HPA 반응 확인

부하 테스트 중 별도 터미널에서 HPA와 Pod 변화를 관찰한다.

```bash
kubectl get hpa -w
kubectl get pods -w
kubectl describe hpa my-app-hpa
```

HPA는 기본적으로 15초마다 메트릭을 수집하고, 스케일업 후 3분 동안 추가 스케일업을 유예한다(cooldown). 이 때문에 트래픽 스파이크가 짧으면 HPA가 반응하기 전에 P99 레이턴시가 급격히 높아진다. 이 취약 구간을 의도적으로 만들어 확인하는 것이 스파이크 테스트(Spike Test)다.

```javascript
// 급격한 스파이크 시나리오
export const options = {
  stages: [
    { duration: '10s', target: 5 },
    { duration: '10s', target: 200 },  // 갑자기 200 VU
    { duration: '1m',  target: 200 },
    { duration: '10s', target: 5 },
  ],
}
```

## 비동기 구조 (큐 기반)

API가 요청을 받아 큐에 적재하고 워커가 별도로 처리하는 구조에서는 측정 포인트를 세 단계로 나눠야 한다.

**1단계: API 레이턴시**

API가 큐에 넣는 것까지의 시간이다. 일반 k6 테스트와 동일하다. 응답이 `202 Accepted`인지 확인한다.

**2단계: 큐 적체**

부하를 발생시키는 동안 큐 깊이(Queue Depth)를 Prometheus로 수집한다. 큐 깊이가 지속적으로 증가하면 워커가 처리 속도를 따라가지 못하는 것이다.

```bash
# Kafka LAG 확인
kafka-consumer-groups.sh --describe --group my-worker-group

# SQS 적체 메시지 수
aws sqs get-queue-attributes \
  --attribute-names ApproximateNumberOfMessages
```

KEDA를 쓴다면 이 큐 깊이 메트릭을 기준으로 워커 Pod이 자동으로 스케일아웃된다. 부하 테스트 중 KEDA가 실제로 워커를 늘리는지, 큐가 결국 소화되는지를 확인한다.

**3단계: End-to-End 레이턴시**

요청을 넣은 시각부터 처리가 완료된 시각까지의 전체 시간이다. 이를 측정하려면 API가 Job ID를 반환하고, 별도 상태 조회 엔드포인트가 있어야 한다.

```javascript
const e2eLatency = new Trend('e2e_latency_ms')

export default function () {
  const submitRes = http.post('/api/jobs', JSON.stringify({ payload: 'test' }), {
    headers: { 'Content-Type': 'application/json' },
  })
  const jobId = submitRes.json('jobId')
  const startTime = Date.now()

  // 완료될 때까지 폴링
  const timeout = 30000
  while (Date.now() - startTime < timeout) {
    sleep(0.5)
    const statusRes = http.get(`/api/jobs/${jobId}/status`)
    if (statusRes.json('status') === 'completed') {
      e2eLatency.add(Date.now() - startTime)
      break
    }
  }
}
```

상태 조회 엔드포인트가 없으면 테스트를 위해 만들어야 한다. 비동기 구조에서 E2E 레이턴시를 측정하려면 처음부터 Observability를 고려한 API 설계가 필요하다.

## 테스트 데이터 준비

| 상황 | 전략 |
|---|---|
| 테스트 환경 DB가 비어있음 | 테스트 전 seed 스크립트로 데이터 주입 |
| 실제 유저 데이터가 필요함 | 프로덕션 덤프에서 PII 제거 후 CSV 추출 |
| 매 요청마다 다른 유저 필요 | CSV + VU 인덱스로 분배 (`users[__VU % users.length]`) |
| 결제 같은 부작용 있는 API | sandbox 엔드포인트 또는 mock 서버 |
| 외부 API 의존성 있음 | WireMock으로 stub 처리 |

인증 토큰은 테스트 전용 장수 토큰을 발급해 Secret으로 주입하거나, `setup()` 함수에서 로그인해 토큰을 획득한 뒤 각 VU에 전달한다.

## 트레이드오프

클러스터 내부에서 부하 테스트를 실행하면 k6 Pod 자체가 Node 자원을 소비한다. 테스트 대상 애플리케이션과 같은 Node에 스케줄링되면 결과가 왜곡된다. k6 Job에 `nodeSelector`나 taint/toleration을 걸어 전용 Node에서 실행하거나, 리소스 요청량을 명시해 스케줄러가 분리하도록 해야 한다.

또한 부하 테스트는 테스트 환경에서만 실행해야 한다. 프로덕션 환경에서 실수로 실행하면 실제 사용자에게 영향을 준다. CI/CD 파이프라인에 통합할 때는 네임스페이스나 클러스터 분리를 철저히 확인한다.
