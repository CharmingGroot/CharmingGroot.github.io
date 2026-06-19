---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "046. mTLS — 서비스 간 양방향 인증서 검증"
date: 2026-06-13
tags: [network, security, mtls, tls, certificate, service-mesh, istio, spiffe, zero-trust]
summary: "일반 TLS는 클라이언트가 서버를 인증한다. mTLS(mutual TLS)는 서버도 클라이언트를 인증한다. 마이크로서비스 환경에서 서비스 간 통신이 실제로 신뢰할 수 있는 서비스에서 왔는지 검증하는 데 쓰인다. 동작 원리, SPIFFE/SPIRE 아이덴티티 체계, Istio가 어떻게 자동화하는지 설명한다."
slug: "046-mtls"
categories: ["클라우드 인프라"]
---

HTTPS로 `api.example.com`에 접속할 때, 브라우저는 서버의 인증서를 확인해 "이 서버가 진짜 example.com이 맞는지" 검증한다. 서버는 클라이언트가 누구인지 확인하지 않는다. 이것이 일반 TLS(단방향 인증)다.

mTLS(mutual TLS, 상호 TLS)는 **양쪽이 서로를 인증한다**. 서버가 클라이언트 인증서도 요구하고 검증한다. 마이크로서비스 환경에서 "이 요청이 실제로 신뢰할 수 있는 서비스에서 왔는가"를 네트워크 레벨에서 보장하는 데 쓰인다.

## 동작 방식

```
일반 TLS:
1. 클라이언트 → 서버: "연결 요청"
2. 서버 → 클라이언트: 서버 인증서 전송
3. 클라이언트: 인증서 검증 (CA 체인 확인)
4. 암호화 통신 시작

mTLS:
1. 클라이언트 → 서버: "연결 요청"
2. 서버 → 클라이언트: 서버 인증서 전송
3. 클라이언트: 서버 인증서 검증
4. 서버 → 클라이언트: "클라이언트 인증서 요청"
5. 클라이언트 → 서버: 클라이언트 인증서 전송
6. 서버: 클라이언트 인증서 검증 (CA 체인 확인)
7. 양방향 검증 완료 → 암호화 통신 시작
```

클라이언트 인증서가 없거나 신뢰할 수 없는 CA가 서명한 인증서를 가져오면 연결이 거부된다. IP 기반이 아니라 **인증서 기반으로 신뢰**를 확립한다.

## 왜 마이크로서비스에 필요한가

마이크로서비스 환경에서 서비스 A가 서비스 B를 호출할 때, 서비스 B는 이 요청이 실제로 서비스 A에서 왔는지 확인할 방법이 필요하다. IP로 확인하면 k8s에서 파드 IP가 바뀌거나, 공격자가 같은 네트워크에서 요청을 위조할 수 있다. API 키를 쓰면 키 관리와 배포가 번거롭다.

mTLS는 인증서를 서비스 아이덴티티로 쓴다. "이 인증서를 가진 서비스만 나에게 접근할 수 있다"는 정책을 설정한다.

## SPIFFE — 서비스 아이덴티티 표준

SPIFFE(Secure Production Identity Framework For Everyone)는 서비스 아이덴티티를 표준화한 스펙이다. 각 서비스에 **SPIFFE ID**라는 URI를 부여한다.

```
spiffe://cluster.local/ns/production/sa/order-service
```

이 아이덴티티를 X.509 인증서(SVID, SPIFFE Verifiable Identity Document)에 담는다. 서비스는 이 인증서로 자신을 증명한다.

SPIRE는 SPIFFE의 구현체다. 각 노드에서 에이전트가 실행되고, 서버가 인증서를 자동으로 발급하고 갱신한다. 개발자가 인증서를 수동으로 관리하지 않아도 된다.

## Istio의 자동 mTLS

서비스마다 mTLS를 직접 설정하는 것은 번거롭다. Istio는 이것을 자동화한다.

```yaml
# Istio PeerAuthentication: 이 Namespace의 모든 서비스 간 통신에 mTLS 강제
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: production
spec:
  mtls:
    mode: STRICT    # mTLS가 아닌 연결은 거부
```

```yaml
# AuthorizationPolicy: 어떤 서비스가 접근할 수 있는지
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: order-service-policy
  namespace: production
spec:
  selector:
    matchLabels:
      app: order-service
  rules:
  - from:
    - source:
        principals:
        - cluster.local/ns/production/sa/api-gateway   # api-gateway만 허용
```

Istio는 각 파드에 Envoy sidecar를 주입한다. 모든 인바운드/아웃바운드 트래픽이 이 sidecar를 거치며, sidecar가 mTLS 핸드쉐이크와 인증서 관리를 대신한다. 앱 코드는 평범한 HTTP를 쓰면 된다.

## 인증서 순환(Rotation)

mTLS의 인증서는 짧은 유효기간(수 시간~수 일)으로 자동 갱신된다. 인증서가 유출돼도 빠르게 무효화된다. Istio/SPIRE가 이 갱신을 자동화한다.

## 트레이드오프

mTLS는 모든 연결에서 TLS 핸드쉐이크를 수행하므로 레이턴시가 약간 늘어난다. 서비스 간 호출이 많은 마이크로서비스 환경에서는 이 오버헤드가 누적된다. TLS 세션 재사용(session resumption)으로 어느 정도 완화할 수 있다.

인증서 관리 인프라가 추가된다. SPIRE 서버나 Istio Citadel이 단일 장애점이 되지 않도록 고가용성으로 구성해야 한다. 이 인프라가 내려가면 인증서 갱신이 안 되고, 인증서가 만료되면 서비스 간 통신이 끊긴다.
