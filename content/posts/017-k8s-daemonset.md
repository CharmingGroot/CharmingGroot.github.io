---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "017. Kubernetes DaemonSet — 모든 노드에 하나씩 실행되는 파드"
date: 2026-06-12
tags: [kubernetes, k8s, daemonset, node, taint, toleration, log-collector, monitoring, otel]
summary: "DaemonSet은 클러스터의 모든 노드(또는 선택한 노드)에 파드를 정확히 하나씩 실행한다. 노드가 추가되면 자동으로 파드가 생기고, 노드가 제거되면 파드도 사라진다. 로그 수집, 메트릭 수집, 네트워크 플러그인처럼 노드 단위로 실행돼야 하는 인프라 컴포넌트에 쓰인다."
slug: "017-k8s-daemonset"
categories: ["쿠버네티스"]
---

Deployment는 파드를 지정한 개수만큼 클러스터 어딘가에 올린다. 어느 노드에 올라가는지는 스케줄러가 결정하고, 운영자는 신경 쓰지 않는다. 하지만 어떤 컴포넌트는 모든 노드에서 실행돼야 한다. 각 노드의 로그를 수집하거나, 노드의 시스템 메트릭을 가져오거나, 네트워크 플러그인을 설치하는 일이 그렇다. DaemonSet은 이 "모든 노드에 하나씩"을 보장한다.

## Deployment와의 차이

Deployment는 "총 N개"를 보장하고, DaemonSet은 "노드마다 1개"를 보장한다.

| | Deployment | DaemonSet |
|---|---|---|
| 파드 배치 | 스케줄러가 결정 | 모든 (또는 선택된) 노드에 하나씩 |
| 파드 수 | replicas로 지정 | 노드 수에 따라 자동 결정 |
| 노드 추가 시 | 기존 파드 수 유지 | 새 노드에 자동으로 파드 생성 |
| 노드 제거 시 | 다른 노드로 재스케줄 | 해당 노드의 파드 삭제 |
| 주 용도 | 서비스 앱 | 인프라 에이전트 |

## 기본 구조

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: log-collector
  namespace: kube-system
spec:
  selector:
    matchLabels:
      app: log-collector
  template:
    metadata:
      labels:
        app: log-collector
    spec:
      containers:
      - name: fluentd
        image: fluentd:latest
        volumeMounts:
        - name: varlog
          mountPath: /var/log
          readOnly: true
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
        resources:
          requests:
            cpu: "100m"
            memory: "200Mi"
          limits:
            cpu: "200m"
            memory: "400Mi"
      volumes:
      - name: varlog
        hostPath:
          path: /var/log        # 노드의 실제 경로를 마운트
      - name: varlibdockercontainers
        hostPath:
          path: /var/lib/docker/containers
      tolerations:              # 마스터 노드 포함 모든 노드에서 실행하려면
      - operator: Exists
```

로그 수집기의 핵심은 `hostPath` 볼륨이다. 파드 안의 컨테이너가 노드의 실제 파일시스템 경로를 마운트해서 읽는다. 노드의 `/var/log`에 모든 컨테이너 로그가 쌓이므로, 로그 수집기가 이 경로를 마운트해 읽어 중앙 로그 저장소로 보낸다.

## 실행 노드 범위 제어

기본적으로 DaemonSet은 모든 노드에 파드를 올린다. 마스터 노드는 기본 Taint가 걸려 있어 Toleration을 추가해야 올라간다. 반대로 일부 노드에만 올리려면 `nodeSelector`나 `nodeAffinity`로 제한한다. Taint/Toleration과 Affinity의 상세 동작은 028 문서에서 다룬다.

## 주요 사용 사례

**로그 수집**: Fluentd, Filebeat가 각 노드의 컨테이너 로그를 읽어 Elasticsearch나 CloudWatch 같은 중앙 저장소로 보낸다. 모든 노드의 로그를 빠짐없이 수집하려면 DaemonSet이 유일한 방법이다.

**메트릭 수집**: Prometheus의 node-exporter가 각 노드의 CPU, 메모리, 디스크, 네트워크 메트릭을 수집한다. 노드 자체의 상태를 모니터링하는 것이므로 모든 노드에 있어야 한다.

**분산 추적 수집기**: OpenTelemetry Collector를 DaemonSet으로 올리면 각 파드가 같은 노드의 Collector로 추적 데이터를 보낼 수 있다(localhost 통신). 중앙 Collector 하나로 몰리는 트래픽을 분산하고, 네트워크 홉을 줄인다.

**네트워크 플러그인**: Calico, Flannel, Cilium 같은 CNI(Container Network Interface) 플러그인이 각 노드에서 파드 간 네트워크를 구성한다. 이것이 없으면 파드 간 통신이 안 된다.

**보안 에이전트**: Falco 같은 런타임 보안 도구가 각 노드에서 시스템 콜을 감시한다.

## 업데이트 전략

DaemonSet도 업데이트 전략을 설정할 수 있다.

`RollingUpdate`(기본값): 노드마다 이전 파드를 내리고 새 파드를 올리는 방식으로 순차적으로 업데이트한다. `maxUnavailable`로 동시에 업데이트할 노드 수를 제어한다.

`OnDelete`: 자동으로 업데이트하지 않는다. 직접 파드를 삭제하면 새 버전으로 생성된다. 업데이트를 수동으로 제어해야 할 때 쓴다.

## 트레이드오프

DaemonSet 파드는 모든 노드에서 실행되므로 리소스 계획이 중요하다. 노드가 100대라면 DaemonSet 파드도 100개다. `resources.requests`를 크게 잡으면 모든 노드의 가용 자원이 그만큼 줄어든다. 인프라 에이전트는 보통 가볍게 유지하는 것이 원칙이다.

`hostPath` 볼륨은 편리하지만 보안 위험이 있다. 노드의 실제 파일시스템에 접근하므로 파드가 침해되면 노드 전체가 위험해질 수 있다. 꼭 필요한 경로만, 읽기 전용으로 마운트하는 것이 원칙이다.
