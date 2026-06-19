---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "023. Kubernetes Ingress — HTTP(S) 트래픽의 단일 진입점"
date: 2026-06-12
tags: [kubernetes, k8s, ingress, ingress-controller, nginx, tls, host-based-routing, path-based-routing, cert-manager]
summary: "Service를 LoadBalancer 타입으로 노출하면 서비스마다 로드밸런서가 하나씩 생겨 비용이 선형으로 늘어난다. Ingress는 하나의 진입점에서 호스트 이름과 URL 경로로 트래픽을 여러 Service로 분배한다. Ingress 오브젝트와 Ingress Controller의 관계, 경로 기반·호스트 기반 라우팅, TLS 종료, cert-manager 자동 인증서 갱신을 설명한다."
slug: "023-k8s-ingress"
categories: ["쿠버네티스"]
---

서비스가 5개인데 각각 LoadBalancer 타입 Service로 외부에 노출하면 로드밸런서가 5개 만들어진다. 클라우드 로드밸런서는 월 비용이 붙는다. 더 큰 문제는 서비스마다 IP나 포트가 달라져 API 구조가 복잡해진다는 것이다. Ingress는 **하나의 로드밸런서**가 외부 트래픽을 받아 호스트 이름이나 URL 경로를 보고 여러 Service로 분배하는 방식이다.

## Ingress Controller — 오브젝트와 구현의 분리

k8s는 Ingress 오브젝트의 스펙을 정의하지만, 그 오브젝트를 실제로 처리하는 로드밸런서를 직접 내장하지는 않는다. **Ingress Controller**가 그 역할을 한다. Ingress 오브젝트를 감시하면서 실제 로드밸런서 설정을 갱신하고 라우팅을 수행한다.

대표적인 Ingress Controller는 다음과 같다.

- **ingress-nginx**: 가장 널리 쓰이는 오픈소스. nginx를 백엔드로 한다.
- **AWS ALB Ingress Controller**: Ingress를 AWS Application Load Balancer로 구현한다.
- **Traefik**: 동적 설정과 Let's Encrypt 자동화로 인기가 높다.
- **GKE Ingress Controller**: GCP 환경에서 Google Cloud Load Balancer를 쓴다.

Ingress Controller는 보통 클러스터에 Deployment 또는 DaemonSet으로 배포되고, LoadBalancer 타입 Service로 외부 IP를 받는다. 이 IP 하나로 모든 Ingress 트래픽이 들어온다.

## 기본 구조

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: my-ingress
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /    # 컨트롤러별 추가 설정
spec:
  ingressClassName: nginx                            # 어떤 Ingress Controller를 쓸지
  rules:
  - host: api.example.com
    http:
      paths:
      - path: /orders
        pathType: Prefix
        backend:
          service:
            name: order-service
            port:
              number: 80
      - path: /payments
        pathType: Prefix
        backend:
          service:
            name: payment-service
            port:
              number: 80
  - host: admin.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: admin-service
            port:
              number: 80
```

## 경로 기반 라우팅

같은 호스트로 들어온 요청을 URL 경로로 나눈다. `api.example.com/orders`는 order-service로, `api.example.com/payments`는 payment-service로 보내는 식이다.

`pathType`은 경로 매칭 방식을 정한다.

`Prefix`: 지정한 경로로 시작하는 모든 요청. `/orders`는 `/orders`, `/orders/123`, `/orders/123/items` 등에 매칭된다.

`Exact`: 정확히 일치하는 경로만. `/orders`는 `/orders`에만 매칭된다.

여러 규칙이 있을 때 더 구체적인 경로가 우선한다. `/orders/vip`와 `/orders`가 함께 있으면 `/orders/vip/123` 요청은 `/orders/vip`에 매칭된다.

## 호스트 기반 라우팅

호스트 이름으로 트래픽을 나눈다. `api.example.com`과 `admin.example.com`을 같은 Ingress에서 다른 Service로 분리한다. 와일드카드 호스트도 가능하다.

```yaml
rules:
- host: "*.example.com"      # 와일드카드 (정확히 한 레벨 서브도메인)
  http:
    paths:
    - path: /
      pathType: Prefix
      backend:
        service:
          name: default-service
          port:
            number: 80
```

## TLS 종료

Ingress에서 TLS 인증서를 설정하면 HTTPS 요청을 Ingress에서 복호화하고, 내부 서비스로는 HTTP로 전달한다. 이를 TLS 종료(TLS termination)라 한다. 내부 서비스들이 각자 TLS를 처리하지 않아도 된다.

```yaml
spec:
  tls:
  - hosts:
    - api.example.com
    secretName: api-tls-secret    # TLS 인증서가 담긴 Secret
  rules:
  - host: api.example.com
    ...
```

```yaml
# TLS Secret (cert와 key는 base64 인코딩)
apiVersion: v1
kind: Secret
metadata:
  name: api-tls-secret
type: kubernetes.io/tls
data:
  tls.crt: <base64 인코딩된 인증서>
  tls.key: <base64 인코딩된 개인키>
```

## cert-manager — 인증서 자동 발급과 갱신

TLS 인증서를 수동으로 발급받아 Secret에 넣는 것은 번거롭고, 만료일을 놓치면 서비스가 막힌다. cert-manager를 쓰면 Let's Encrypt에서 인증서를 자동으로 발급받고 만료 전에 갱신한다.

cert-manager를 설치하고 Ingress에 어노테이션 하나만 추가하면 된다.

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - api.example.com
    secretName: api-tls-secret      # cert-manager가 이 Secret을 자동으로 채운다
  rules:
  - host: api.example.com
    ...
```

cert-manager가 Ingress를 감시하면서 `api-tls-secret`이 없거나 만료 30일 전이 되면 Let's Encrypt에 자동으로 인증서를 요청해 Secret을 갱신한다. 인증서 관리가 완전히 자동화된다.

## 어노테이션 — 컨트롤러별 고급 설정

Ingress 스펙에 없는 컨트롤러별 기능은 어노테이션으로 설정한다. ingress-nginx 기준으로 자주 쓰이는 것들이다.

```yaml
annotations:
  # 요청 본문 크기 제한 (파일 업로드 등)
  nginx.ingress.kubernetes.io/proxy-body-size: "50m"

  # 타임아웃
  nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
  nginx.ingress.kubernetes.io/proxy-send-timeout: "60"

  # HTTPS 강제 리다이렉트
  nginx.ingress.kubernetes.io/ssl-redirect: "true"

  # Rate limiting
  nginx.ingress.kubernetes.io/limit-rps: "10"

  # CORS
  nginx.ingress.kubernetes.io/enable-cors: "true"
  nginx.ingress.kubernetes.io/cors-allow-origin: "https://example.com"

  # WebSocket 지원
  nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
  nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
```

## 트레이드오프

Ingress는 HTTP/HTTPS 전용이다. TCP나 UDP 레벨의 트래픽 분기가 필요하면 Service의 LoadBalancer 타입이나 별도 TCP/UDP 프록시를 써야 한다.

모든 외부 트래픽이 Ingress Controller 하나를 통과하므로 이 컴포넌트의 가용성이 중요하다. 프로덕션에서는 Ingress Controller를 여러 레플리카로 띄우고, PodDisruptionBudget을 설정해 업데이트 중에도 최소 가용성을 보장해야 한다.

어노테이션으로 설정하는 고급 기능들은 Ingress Controller마다 다르다. ingress-nginx에서 AWS ALB Controller로 바꾸면 어노테이션을 전부 다시 써야 한다. 컨트롤러에 종속적인 설정이 많아질수록 교체 비용이 올라간다.
