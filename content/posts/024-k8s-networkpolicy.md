---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "024. Kubernetes NetworkPolicy — 파드 간 트래픽을 제어하는 방화벽"
date: 2026-06-12
tags: [kubernetes, k8s, networkpolicy, security, ingress, egress, microsegmentation, cni, calico, cilium]
summary: "k8s에서 기본적으로 모든 파드는 서로 통신할 수 있다. NetworkPolicy는 파드 단위의 방화벽 규칙으로, 어떤 파드가 어떤 파드에 접근할 수 있는지 제어한다. 인그레스·이그레스 규칙 작성 방법, 기본 차단 정책, 네임스페이스 간 트래픽 제어, 그리고 CNI 플러그인이 실제로 규칙을 집행하는 구조를 설명한다."
slug: "024-k8s-networkpolicy"
categories: ["쿠버네티스"]
---

k8s 클러스터에서 기본적으로 모든 파드는 네임스페이스와 관계없이 서로 통신할 수 있다. 주문 서비스가 결제 서비스에 직접 접근할 수 있고, 개발 네임스페이스의 파드가 프로덕션 DB에 접근할 수도 있다. 이 기본 동작은 편리하지만 보안 측면에서는 위험하다. 파드 하나가 침해되면 공격자가 클러스터 안의 모든 서비스에 접근할 수 있다.

NetworkPolicy는 파드 단위의 방화벽 규칙이다. "이 파드는 저 파드에서만 트래픽을 받는다", "이 파드는 저 주소로만 나갈 수 있다"처럼 허용할 트래픽을 명시적으로 정의한다.

## 기본 동작 방식

NetworkPolicy가 없으면 **모두 허용**이다. 파드에 NetworkPolicy가 하나라도 적용되면, 그 파드는 **명시적으로 허용된 트래픽만** 통과시킨다. 화이트리스트 방식이다.

한 파드에 여러 NetworkPolicy가 적용되면 규칙이 합산(OR)된다. 어느 하나의 정책에서 허용하면 통과된다.

## 구조

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-policy
  namespace: production
spec:
  podSelector:            # 이 정책을 적용할 파드 (레이블로 선택)
    matchLabels:
      app: payment
  policyTypes:
  - Ingress               # 들어오는 트래픽 제어
  - Egress                # 나가는 트래픽 제어
  ingress:
  - from:
    - podSelector:        # 이 레이블의 파드에서만 인그레스 허용
        matchLabels:
          app: order
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

`podSelector`가 이 NetworkPolicy가 적용될 파드를 선택한다. `policyTypes`로 인그레스(들어오는 트래픽), 이그레스(나가는 트래픽) 중 무엇을 제어할지 지정한다.

## 기본 차단 정책 — 먼저 막고 필요한 것만 열기

보안의 기본은 기본 차단 후 필요한 것만 열기다. 네임스페이스별로 기본 차단 정책을 먼저 적용한 뒤, 필요한 통신만 명시적으로 허용하는 것이 권장 패턴이다.

```yaml
# 모든 인그레스 차단
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: production
spec:
  podSelector: {}           # 빈 셀렉터 = 이 네임스페이스의 모든 파드에 적용
  policyTypes:
  - Ingress
  # ingress 규칙 없음 = 모든 인그레스 차단

---
# 모든 이그레스 차단
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-egress
  namespace: production
spec:
  podSelector: {}
  policyTypes:
  - Egress
  # egress 규칙 없음 = 모든 이그레스 차단
```

이 두 정책을 적용한 뒤, 각 서비스에 필요한 통신을 허용하는 정책을 추가한다.

## 실제 서비스 구성 예시

주문 서비스 → 결제 서비스 → DB 구조에서 최소 권한으로 구성하는 예다.

```yaml
# 결제 서비스: 주문 서비스에서만 인그레스 허용, DB로만 이그레스 허용
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-service-policy
  namespace: production
spec:
  podSelector:
    matchLabels:
      app: payment
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: order
    ports:
    - port: 8080
  egress:
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - port: 5432
  # DNS 조회를 위해 kube-dns는 항상 허용해야 한다
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
      podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - port: 53
      protocol: UDP
    - port: 53
      protocol: TCP
```

이그레스를 차단할 때 **DNS(포트 53) 허용을 빠뜨리면** 파드가 도메인 이름을 해석하지 못해 서비스 이름으로 통신이 안 된다. 이그레스 정책을 쓸 때 자주 실수하는 부분이다.

## 네임스페이스 간 트래픽 제어

`namespaceSelector`로 다른 네임스페이스의 파드를 선택할 수 있다.

```yaml
ingress:
- from:
  # 같은 네임스페이스 + 레이블 조건 (AND)
  - namespaceSelector:
      matchLabels:
        env: production
    podSelector:
      matchLabels:
        app: order
  # 또는 다른 네임스페이스 전체 허용 (OR)
  - namespaceSelector:
      matchLabels:
        kubernetes.io/metadata.name: monitoring
```

`namespaceSelector`와 `podSelector`를 같은 항목(`-`) 안에 쓰면 **AND** 조건이다. "production 네임스페이스이면서 app=order인 파드". 별도 항목으로 쓰면 **OR** 조건이다.

모니터링 네임스페이스의 Prometheus가 모든 파드의 `/metrics`를 긁을 수 있도록, 모니터링 네임스페이스에서 오는 메트릭 포트 접근을 허용하는 정책을 추가하는 패턴이 흔하다.

## IP 블록 기반 규칙

파드 셀렉터 외에 IP CIDR 범위로도 트래픽을 제어할 수 있다.

```yaml
egress:
- to:
  - ipBlock:
      cidr: 10.0.0.0/8        # 내부 네트워크만 허용
      except:
      - 10.0.1.0/24            # 이 대역은 제외
- to:
  - ipBlock:
      cidr: 0.0.0.0/0          # 외부 인터넷 전체 허용
```

외부 API 호출이 필요한 파드는 이그레스에 해당 IP 범위를 열어야 한다. 반대로 외부 인터넷 접근이 필요 없는 서비스는 이그레스를 내부 대역으로만 제한해 데이터 유출 경로를 줄일 수 있다.

## CNI 플러그인이 실제로 집행한다

NetworkPolicy는 k8s API 오브젝트로 정의되지만, 실제로 트래픽을 차단하는 것은 CNI(Container Network Interface) 플러그인이다. **Calico**, **Cilium**, **WeaveNet** 같은 CNI 플러그인이 NetworkPolicy를 읽어 각 노드의 iptables 또는 eBPF 규칙으로 변환해 집행한다.

기본 k8s 네트워크 플러그인(Kubenet)은 NetworkPolicy를 지원하지 않는다. NetworkPolicy를 쓰려면 지원하는 CNI 플러그인이 설치돼 있어야 한다. EKS는 기본적으로 Amazon VPC CNI를 쓰는데, NetworkPolicy 지원을 위해 Calico나 Cilium을 추가로 설치하거나 Amazon VPC CNI의 NetworkPolicy 기능(비교적 최근에 추가)을 활성화해야 한다.

Cilium은 iptables 대신 eBPF를 사용해 더 효율적이고, L7(HTTP 경로, gRPC 메서드 수준) 정책도 지원한다.

## 트레이드오프

NetworkPolicy는 선언하기는 쉽지만 디버깅이 어렵다. 트래픽이 막혔을 때 어느 정책이 차단하는지 확인하는 도구가 부족하다. `kubectl describe networkpolicy`로 정책 내용은 볼 수 있지만, "이 요청이 왜 막히는지"를 추적하려면 CNI 플러그인의 로그나 전용 도구가 필요하다. Cilium은 Hubble이라는 네트워크 관측 도구를 제공해 이 문제를 어느 정도 해결한다.

서비스가 많아지면 NetworkPolicy 수도 선형으로 늘어난다. 각 서비스마다 인그레스·이그레스 정책이 필요하고, 의존 관계가 바뀔 때마다 정책도 함께 업데이트해야 한다. 이를 놓치면 정상적인 트래픽이 막히는 장애가 난다. 작은 팀이라면 기본 차단 정책만 두고 점진적으로 세분화하는 접근이 현실적이다.
