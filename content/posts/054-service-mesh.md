---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "054. Service Mesh — 서비스 간 통신을 인프라 레이어에서 제어하기"
date: 2026-06-13
tags: [service-mesh, istio, envoy, sidecar, mtls, traffic-management, observability, kubernetes]
summary: "마이크로서비스가 많아지면 서비스 간 통신 관리가 복잡해진다. 재시도, 타임아웃, 서킷 브레이커, mTLS, 분산 추적을 각 서비스 코드에 중복 구현하게 된다. Service Mesh는 이 공통 기능을 sidecar proxy로 분리해 인프라 레이어에서 처리한다. Istio와 Envoy의 구조, 주요 기능, 그리고 오버헤드를 설명한다."
slug: "054-service-mesh"
categories: ["IaC · 플랫폼"]
---

마이크로서비스가 10개, 20개가 되면 서비스 간 통신에서 반복되는 문제들이 생긴다. 서비스 A가 서비스 B를 호출할 때 타임아웃은 얼마로 잡을지, 실패하면 몇 번 재시도할지, 서비스 B가 느려지면 요청을 끊을지, 이 통신이 암호화되는지, 어떤 서비스가 어디서 얼마나 오래 걸리는지.

이 문제들을 각 서비스에서 공통 라이브러리로 해결할 수 있지만, 언어마다 다르고 버전 관리가 어렵다. Service Mesh는 이 공통 기능을 **sidecar proxy**로 분리한다. 각 파드에 Envoy proxy 컨테이너를 주입하고, 모든 트래픽이 이 proxy를 거치게 한다. 앱 코드는 localhost로 통신하는 것처럼 쓰고, 실제 복잡한 처리는 proxy가 담당한다.

## 구조

### Data Plane — Envoy Sidecar

Envoy는 고성능 L7 proxy다. Istio는 각 파드에 Envoy를 sidecar 컨테이너로 자동 주입한다.

```
Pod:
  ├── App Container (포트 8080에서 서비스)
  └── Envoy Sidecar (포트 15001, 15006 등)

인바운드 트래픽: 외부 → Envoy → App (15006)
아웃바운드 트래픽: App → Envoy → 외부 (15001)
```

iptables 규칙이 파드의 모든 인바운드/아웃바운드 트래픽을 Envoy로 리다이렉트한다. 앱은 자신이 proxy를 거치는지 모른다.

### Control Plane — Istiod

Istio의 컨트롤 플레인이다. 서비스 디스커버리, 인증서 발급, Envoy 설정 배포를 담당한다. 각 Envoy에게 "어떤 서비스가 어디 있는지, 어떤 정책을 적용할지"를 xDS API로 전달한다.

```
Istiod
  ├── Pilot: 서비스 디스커버리, 트래픽 라우팅 규칙 배포
  ├── Citadel: 인증서 발급 및 갱신 (SPIFFE 기반 mTLS)
  └── Galley: 설정 유효성 검사
```

## 주요 기능

### mTLS 자동화

파드 간 모든 통신에 mTLS를 자동으로 적용한다. Istio가 인증서를 발급하고 Envoy가 핸드쉐이크를 처리한다. 앱 코드 변경 없이 서비스 간 암호화와 인증이 된다.

```yaml
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT    # mTLS가 아닌 연결 거부
```

### 트래픽 관리

Envoy를 통한 정교한 트래픽 제어가 가능하다.

```yaml
# VirtualService: 트래픽 라우팅 규칙
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: my-service
spec:
  hosts:
  - my-service
  http:
  - match:
    - headers:
        x-canary:
          exact: "true"
    route:
    - destination:
        host: my-service
        subset: v2              # 카나리 배포: x-canary 헤더 있으면 v2로
  - route:
    - destination:
        host: my-service
        subset: v1
      weight: 90
    - destination:
        host: my-service
        subset: v2
      weight: 10                # 가중치 기반 트래픽 분산

---
# DestinationRule: 서브셋 정의 및 재시도/타임아웃 설정
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: my-service
spec:
  host: my-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
    outlierDetection:           # 서킷 브레이커
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s     # 5번 연속 실패 시 30초 동안 제외
  subsets:
  - name: v1
    labels:
      version: v1
  - name: v2
    labels:
      version: v2
```

`outlierDetection`이 서킷 브레이커다. 특정 파드가 연속으로 실패하면 일정 시간 동안 그 파드로 트래픽을 보내지 않는다. 앱 코드에 Hystrix나 Resilience4j를 넣지 않아도 된다.

### 분산 추적 자동화

Envoy가 모든 요청에 `x-b3-traceid` 같은 추적 헤더를 자동으로 주입하고 전파한다. Jaeger나 Zipkin으로 서비스 간 호출 흐름을 시각화할 수 있다.

단, 앱 코드에서 인바운드 헤더를 아웃바운드로 전파하는 것은 여전히 앱이 해야 한다. Envoy는 자신을 거치는 구간의 span을 기록하지만, 앱이 다음 서비스를 호출할 때 헤더를 넘겨야 트레이스가 이어진다.

### Observability — Kiali

Istio와 함께 쓰는 Kiali는 서비스 그래프를 시각화한다. 서비스 간 트래픽 흐름, 오류율, 레이턴시를 실시간으로 보여준다. 어느 서비스에서 오류가 발생하는지 한눈에 파악할 수 있다.

## 트레이드오프

Sidecar proxy가 모든 트래픽을 거치므로 레이턴시가 늘어난다. Envoy 한 홉당 약 0.5~1ms의 오버헤드가 추가된다. 서비스 A → 서비스 B 호출은 A의 Envoy → B의 Envoy를 거치므로 최소 1~2ms가 추가된다. 레이턴시에 민감한 고빈도 내부 API에서는 이 오버헤드가 유의미할 수 있다.

메모리 사용량도 증가한다. 각 파드에 Envoy가 추가되므로 파드당 50~100MB의 메모리를 더 쓴다. 파드가 수백 개면 전체 클러스터 메모리 비용이 증가한다.

운영 복잡도가 높다. Istio 자체를 운영하는 것이 하나의 프로젝트다. 버전 업그레이드가 까다롭고, 설정 오류가 전체 서비스 통신에 영향을 줄 수 있다. 소규모 팀이나 서비스가 많지 않은 경우 오버엔지니어링일 수 있다. Linkerd가 Istio보다 가볍고 단순한 대안으로 자주 언급된다.
