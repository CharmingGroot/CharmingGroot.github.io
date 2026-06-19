---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "020. Kubernetes 관측성 — TPS 측정, 분산 추적, 로그 수집"
date: 2026-06-12
tags: [kubernetes, k8s, observability, prometheus, grafana, opentelemetry, jaeger, tps, tracing, logging, metrics]
summary: "k8s에서 서비스를 운영하려면 무슨 일이 일어나는지 볼 수 있어야 한다. 관측성의 세 기둥인 메트릭·트레이스·로그가 k8s에서 어떻게 구성되는지, TPS를 어떻게 측정하는지, 분산 추적이 어떻게 여러 서비스를 하나의 흐름으로 잇는지, 로그는 어떻게 중앙에서 수집하는지를 설명한다."
slug: "020-k8s-observability"
categories: ["쿠버네티스"]
---

k8s 위에서 서비스가 실행된다고 끝이 아니다. 지금 몇 TPS를 처리하는지, 어떤 요청이 느린지, 오류가 어느 서비스에서 나는지를 볼 수 없으면 운영이 불가능하다. 관측성(observability)은 시스템 내부 상태를 외부에서 추론할 수 있는 능력이다. 세 가지 신호로 구성된다. 메트릭(metrics)은 시스템의 수치 상태를, 트레이스(traces)는 요청의 흐름을, 로그(logs)는 개별 이벤트의 기록을 제공한다.

## 메트릭과 TPS — Prometheus + Grafana

### Prometheus가 하는 일

Prometheus는 메트릭을 **시계열(time-series)** 로 수집하고 저장하는 시스템이다. k8s 클러스터에서는 두 종류의 메트릭 소스가 있다.

인프라 메트릭: 노드의 CPU·메모리·디스크, 파드의 리소스 사용량, k8s 컴포넌트 상태 등. kube-prometheus-stack을 설치하면 node-exporter(DaemonSet), kube-state-metrics 등이 자동으로 배포돼 이 메트릭들을 수집한다.

애플리케이션 메트릭: 각 서비스가 직접 노출하는 지표. 요청 수, 응답 시간, 오류 수, 비즈니스 지표 등. 앱이 `/metrics` 엔드포인트를 노출하면 Prometheus가 주기적으로 그 엔드포인트를 긁는다(scrape).

### TPS 측정

TPS(Transactions Per Second, 초당 처리 건수)는 `rate()` 함수로 계산한다.

```promql
# 전체 초당 요청 수
rate(http_requests_total[1m])

# 서비스별 초당 요청 수
rate(http_requests_total[1m]) by (service)

# 5xx 에러율
rate(http_requests_total{status=~"5.."}[1m])
/ rate(http_requests_total[1m])

# p99 응답 시간 (히스토그램 메트릭)
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

`rate(counter[1m])`는 1분 범위에서 카운터의 초당 증가율을 계산한다. 카운터는 누적 값이라 절대값이 아닌 변화율을 봐야 의미 있다. `[1m]`을 너무 짧게 잡으면 노이즈가 크고, 너무 길게 잡으면 최근 변화를 놓친다. 보통 1~5분을 쓴다.

### 파드 자동 발견

k8s 환경에서 파드가 늘어나고 줄어드는데, Prometheus가 어떻게 모든 파드의 `/metrics`를 알고 긁는지 의아할 수 있다. `ServiceMonitor` 오브젝트가 그 역할을 한다.

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: my-app-monitor
spec:
  selector:
    matchLabels:
      app: my-app
  endpoints:
  - port: http
    path: /metrics
    interval: 15s        # 15초마다 수집
```

kube-prometheus-stack의 Prometheus Operator가 ServiceMonitor를 감시하면서 일치하는 Service의 파드들을 자동으로 scrape 대상에 추가한다. 파드가 늘어나도 자동으로 수집 대상에 포함된다.

### Grafana 대시보드

Prometheus가 저장한 데이터를 Grafana가 시각화한다. 미리 만들어진 대시보드(Kubernetes / Overview, Node Exporter Full 등)를 grafana.com에서 ID 하나로 임포트할 수 있다. HPA와 연동해서 보면 "TPS가 올라갈 때 파드가 늘어나는 과정"을 실시간으로 볼 수 있다.

## 분산 추적 — OpenTelemetry + Jaeger

요청 하나가 여러 서비스를 거칠 때 어디서 얼마나 시간이 걸렸는지는 메트릭만으로는 알기 어렵다. 분산 추적이 그 경로를 시각화한다. 이전 글([W3C Trace Context](010-w3c-trace-context.md))에서 표준을 정리했으니, 여기서는 k8s에서의 실제 구성에 집중한다.

### OTel Collector DaemonSet

각 서비스에서 생성된 스팬(span)을 수집해 백엔드로 전달하는 OpenTelemetry Collector를 DaemonSet으로 올린다. 파드들이 같은 노드의 Collector에 localhost로 보내면 돼서 네트워크 오버헤드가 적고, Collector 장애가 클러스터 전체로 번지지 않는다.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
  namespace: observability
spec:
  template:
    spec:
      containers:
      - name: collector
        image: otel/opentelemetry-collector-contrib:latest
        ports:
        - containerPort: 4317    # OTLP gRPC
        - containerPort: 4318    # OTLP HTTP
        volumeMounts:
        - name: config
          mountPath: /etc/otelcol
      volumes:
      - name: config
        configMap:
          name: otel-collector-config
      tolerations:
      - operator: Exists          # 모든 노드에서 실행
```

Collector 설정(ConfigMap)에서 수신기(receiver), 처리기(processor), 내보내기(exporter)를 정의한다.

```yaml
# otel-collector-config ConfigMap
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:                          # 스팬을 모아서 배치로 보냄 (성능 향상)
    timeout: 1s
  memory_limiter:                 # 메모리 초과 방지
    limit_mib: 400

exporters:
  otlp/jaeger:
    endpoint: jaeger-collector:4317

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/jaeger]
```

### 자동 계측

OTel SDK를 코드에 직접 붙이지 않아도 사이드카 주입으로 자동 계측이 가능하다. OpenTelemetry Operator를 설치하고 파드에 어노테이션을 달면 된다.

```yaml
metadata:
  annotations:
    instrumentation.opentelemetry.io/inject-python: "true"
    instrumentation.opentelemetry.io/inject-java: "true"
    instrumentation.opentelemetry.io/inject-nodejs: "true"
```

Operator가 파드 시작 시 init container를 주입해 OTel 에이전트를 설치하고, 환경변수를 설정해 앱이 자동으로 추적 데이터를 Collector로 보내게 한다. HTTP, gRPC, DB 쿼리 같은 공통 라이브러리 호출이 자동으로 계측된다.

## 로그 수집 — DaemonSet 기반 파이프라인

각 파드의 표준출력(stdout/stderr)은 노드의 `/var/log/pods/` 경로에 파일로 저장된다. DaemonSet으로 올린 로그 수집기가 이 경로를 마운트해 읽어 중앙 로그 저장소로 보낸다.

흔한 스택은 Fluentd 또는 Fluent Bit (DaemonSet) → Elasticsearch → Kibana(EFK 스택)이거나, 최근에는 더 가벼운 Promtail(DaemonSet) → Loki → Grafana(PLG 스택)가 많이 쓰인다. Loki는 로그를 인덱스 없이 압축 저장해 Elasticsearch보다 저장 비용이 낮다. 이미 Grafana를 쓴다면 메트릭과 로그를 같은 UI에서 볼 수 있는 장점도 있다.

## 세 가지 신호의 연결

관측성의 진짜 가치는 세 신호를 연결할 때 나온다.

1. Grafana 대시보드에서 특정 시간대에 에러율이 급등한 것을 메트릭으로 발견한다.
2. 그 시간대의 느린 요청의 trace-id를 Jaeger에서 찾아, 어느 서비스 어느 스팬에서 지연이 발생했는지 폭포수 그래프로 확인한다.
3. 그 서비스의 그 시간대 로그를 Loki에서 trace-id로 필터링해 정확한 오류 메시지를 찾는다.

이 연결이 되려면 로그에 trace-id가 포함돼야 한다. OTel SDK는 현재 실행 맥락의 trace-id와 span-id를 로그에 자동으로 심는 기능을 제공한다. 이 설정을 해두면 메트릭 → 트레이스 → 로그를 하나의 흐름으로 따라갈 수 있다.

## 트레이드오프

관측성 스택은 그 자체로 상당한 자원을 쓴다. Prometheus는 수집 주기마다 모든 파드를 긁으며, 메트릭 보존 기간이 길수록 저장 공간이 늘어난다. OTel Collector DaemonSet은 모든 노드에 올라가고, 로그 수집기도 마찬가지다. 클러스터 전체 자원의 5~15%가 관측성 인프라에 사용되는 경우도 드물지 않다.

모든 요청을 다 추적하면 추적 데이터 양이 폭증한다. 샘플링으로 일부만 기록하는데, 1~10%로 잡는 경우가 많다. 문제는 장애가 났을 때 그 요청이 샘플에서 빠질 수 있다는 것이다. 꼬리 기반 샘플링(tail-based sampling)은 완료된 트레이스를 보고 오류나 지연이 있는 것은 무조건 포함하는 방식으로 이 문제를 완화한다. OTel Collector에 tail sampling processor를 설정하면 된다.
