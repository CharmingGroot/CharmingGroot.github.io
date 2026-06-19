---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "055. eBPF & Cilium — 커널 레벨 네트워킹과 차세대 CNI"
date: 2026-06-13
tags: [ebpf, cilium, kubernetes, cni, networking, observability, security, iptables, hubble]
summary: "eBPF(extended Berkeley Packet Filter)는 리눅스 커널 안에서 사용자 정의 프로그램을 안전하게 실행하는 기술이다. Cilium은 eBPF 기반의 k8s CNI 플러그인으로, iptables를 대체하고 고성능 네트워킹, NetworkPolicy 구현, 서비스 메시 기능, 실시간 관찰 가능성을 커널 레벨에서 제공한다."
slug: "055-ebpf-cilium"
categories: ["IaC · 플랫폼"]
---

k8s 네트워킹은 전통적으로 iptables에 의존한다. kube-proxy가 각 노드에 수천 개의 iptables 규칙을 심어 서비스 로드밸런싱과 NetworkPolicy를 구현한다. 규칙이 많아질수록 매칭 비용이 선형으로 늘어나고, 규칙 업데이트 시 전체 체인을 재적용해야 한다.

eBPF는 다른 접근 방식이다. 커널 안에서 직접 패킷을 처리하는 프로그램을 실행해 iptables의 한계를 넘어선다.

## eBPF란

eBPF(extended Berkeley Packet Filter)는 원래 패킷 필터링 목적으로 시작했지만, 현재는 리눅스 커널에서 사용자 정의 프로그램을 안전하게 실행하는 범용 기술이 됐다. JIT 컴파일로 네이티브에 가까운 성능을 내고, 커널 소스를 수정하거나 모듈을 로드하지 않아도 된다.

```
전통 방식:
패킷 → 네트워크 스택 → iptables 체인 순회 → 목적지

eBPF 방식:
패킷 → eBPF 프로그램 (커널 내 직접 처리) → 목적지
       ↑ 체인 순회 없이 O(1) 결정
```

iptables는 규칙이 1000개면 1000번 체크할 수 있지만, eBPF는 해시 테이블로 O(1)에 결정한다. 서비스가 많고 파드가 많은 대규모 클러스터에서 차이가 드러난다.

## Cilium

Cilium은 eBPF 기반의 k8s CNI 플러그인이다. 네트워킹, 보안, 관찰 가능성 세 가지를 eBPF로 통합 처리한다.

### kube-proxy 대체

Cilium은 kube-proxy 없이 동작한다. eBPF로 Service의 로드밸런싱을 처리한다. 파드 수나 서비스 수가 늘어도 성능 저하가 적다.

```bash
# EKS에서 Cilium 설치 시 kube-proxy 비활성화
helm install cilium cilium/cilium \
  --set kubeProxyReplacement=true \
  --set k8sServiceHost=<API_SERVER_ENDPOINT>
```

### NetworkPolicy 구현

Calico, Flannel 등 다른 CNI도 NetworkPolicy를 구현하지만, Cilium은 iptables 대신 eBPF로 처리한다. 규칙이 많아도 성능 저하가 적다.

Cilium은 표준 k8s NetworkPolicy 외에 **CiliumNetworkPolicy**를 추가로 제공한다.

```yaml
# 표준 NetworkPolicy보다 세밀한 제어
apiVersion: cilium.io/v2
kind: CiliumNetworkPolicy
metadata:
  name: api-policy
spec:
  endpointSelector:
    matchLabels:
      app: api-server
  ingress:
  - fromEndpoints:
    - matchLabels:
        app: frontend
    toPorts:
    - ports:
      - port: "8080"
        protocol: TCP
      rules:
        http:                         # HTTP 레벨 정책
        - method: GET
          path: "/api/.*"             # GET 요청만, 특정 경로만
        - method: POST
          path: "/api/orders"
```

L7(HTTP) 레벨까지 내려가 특정 메서드와 경로만 허용하는 정책을 만들 수 있다. 기존 NetworkPolicy는 IP/포트 레벨(L4)까지만 가능했다.

### Hubble — 실시간 네트워크 관찰

Cilium에 내장된 Hubble은 eBPF로 모든 네트워크 흐름을 캡처한다. 별도 sidecar 없이 커널 레벨에서 수집하므로 성능 영향이 최소화된다.

```bash
# 흐름 실시간 조회
hubble observe --namespace production

# 특정 서비스 트래픽
hubble observe --to-pod order-service

# 드롭된 패킷
hubble observe --verdict DROPPED
```

Hubble UI에서 서비스 간 트래픽 흐름을 그래프로 볼 수 있다. NetworkPolicy가 의도대로 동작하는지 드롭된 패킷으로 확인할 수 있다.

## Cilium Service Mesh

Cilium은 eBPF 기반 서비스 메시 기능도 제공한다. sidecar proxy 없이 커널에서 직접 처리하는 **Sidecarless Service Mesh**다.

```
Istio (sidecar 방식):
파드 → Envoy sidecar → 네트워크 → Envoy sidecar → 파드
     (추가 메모리, 추가 레이턴시)

Cilium Service Mesh (sidecarless):
파드 → eBPF (커널) → 네트워크 → eBPF (커널) → 파드
     (메모리 오버헤드 최소, 레이턴시 최소)
```

mTLS, 트래픽 관리, 관찰 가능성을 sidecar 없이 구현한다. 단, Istio에 비해 기능이 아직 제한적이고 성숙도가 낮다.

## 성능 비교

| | iptables/kube-proxy | Cilium (eBPF) |
|---|---|---|
| 서비스 룩업 | O(n) 체인 순회 | O(1) 해시 테이블 |
| 규칙 업데이트 | 전체 체인 재적용 | 증분 업데이트 |
| 대규모 클러스터 | 성능 저하 | 선형 확장 |
| 관찰 가능성 | 별도 도구 필요 | Hubble 내장 |

## 트레이드오프

eBPF는 커널 버전 의존성이 있다. 일부 기능은 최신 커널(5.10+, 5.15+ 권장)에서만 동작한다. 오래된 OS 이미지를 쓰는 온프렘 환경에서는 커널 업그레이드가 선행돼야 한다.

Cilium의 설정이 기존 CNI보다 복잡하다. CiliumNetworkPolicy, Hubble, 서비스 메시 기능을 모두 이해하고 운영하려면 학습 비용이 있다. 기능을 전부 쓰지 않는다면 Calico로 시작해 필요할 때 마이그레이션하는 것도 합리적인 선택이다.

AWS EKS에서 Cilium을 쓸 때 AWS VPC CNI와 함께 체이닝 모드로 쓰거나, Cilium을 단독 CNI로 쓰는 두 가지 방식이 있다. EKS Managed Node Group에서 kube-proxy를 비활성화하는 데 별도 설정이 필요하다.
