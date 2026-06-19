---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "042. L4 vs L7 로드밸런서 — NLB와 ALB"
date: 2026-06-13
tags: [network, load-balancer, nlb, alb, l4, l7, aws, http, tcp, routing]
summary: "로드밸런서는 들어오는 트래픽을 여러 서버에 분산한다. OSI 모델의 어느 계층에서 동작하느냐에 따라 L4와 L7으로 나뉜다. L4는 TCP/UDP 레벨에서, L7은 HTTP 내용을 보고 라우팅 결정을 내린다. AWS의 NLB와 ALB를 기준으로 각각 언제 쓰는지 설명한다."
slug: "042-l4-l7-load-balancer"
categories: ["클라우드 인프라"]
---

트래픽이 서버 한 대로 몰리면 처리 한계에 부딪힌다. 로드밸런서는 여러 서버에 트래픽을 나눠 보내는 역할을 한다. 어떻게 나눌지는 로드밸런서가 어느 계층의 정보를 볼 수 있느냐에 달려 있다.

## L4 로드밸런서 — TCP/UDP 레벨

L4(전송 계층) 로드밸런서는 IP 주소와 포트 번호만 본다. HTTP 헤더나 URL 같은 내용은 보지 않는다. 패킷을 열어보지 않고 연결을 통째로 특정 서버로 전달한다.

AWS에서는 **NLB(Network Load Balancer)** 가 L4다.

```
클라이언트 → NLB (1.2.3.4:443) → 서버 A (10.0.1.5:443)
                                 → 서버 B (10.0.1.6:443)
```

NLB는 연결(TCP 세션)을 서버에 고정시킨다. 같은 클라이언트의 패킷은 같은 서버로 간다.

### NLB의 특징

**Ultra-low latency**: 패킷 내용을 분석하지 않아 처리가 빠르다. 초당 수백만 연결을 처리할 수 있다.

**클라이언트 IP 보존**: 서버가 실제 클라이언트 IP를 그대로 본다. ALB는 X-Forwarded-For 헤더로 원본 IP를 전달하는 반면, NLB는 IP 자체를 보존한다.

**TCP/UDP/TLS 지원**: HTTP 외 프로토콜도 처리한다. gRPC, WebSocket, 게임 서버처럼 HTTP가 아닌 TCP 기반 프로토콜에 쓴다.

**고정 IP**: NLB는 AZ별로 고정 IP(Elastic IP)를 붙일 수 있다. IP 화이트리스트가 필요한 경우(금융 시스템 등) NLB를 써야 한다.

## L7 로드밸런서 — HTTP 레벨

L7(응용 계층) 로드밸런서는 HTTP 요청의 내용을 읽는다. URL 경로, 호스트 헤더, HTTP 메서드, 쿠키를 보고 라우팅 결정을 내린다.

AWS에서는 **ALB(Application Load Balancer)** 가 L7이다.

```
클라이언트 → ALB
  /api/* → API 서버 그룹 (10.0.1.x)
  /static/* → 정적 파일 서버 그룹 (10.0.2.x)
  app1.example.com → 서비스 A
  app2.example.com → 서비스 B
```

### ALB의 특징

**콘텐츠 기반 라우팅**: URL 경로, 호스트명, HTTP 헤더, 쿼리 파라미터, HTTP 메서드로 라우팅할 타깃 그룹을 결정한다.

```
규칙 1: Host = api.example.com → Target Group: API 서버
규칙 2: Path = /admin/* → Target Group: Admin 서버
규칙 3: 기본 → Target Group: 프론트엔드 서버
```

**HTTPS 종료(TLS Termination)**: ALB에서 HTTPS를 종료하고 내부는 HTTP로 통신한다. 인증서 관리를 ALB에서 집중한다. cert-manager 없이 ACM(AWS Certificate Manager)으로 인증서를 자동 갱신할 수 있다.

**인증 통합**: Cognito나 OIDC 프로바이더와 연동해 ALB 레벨에서 인증을 처리할 수 있다. 앱 서버가 인증 로직을 직접 가지지 않아도 된다.

**WebSocket, HTTP/2 지원**: ALB는 WebSocket 업그레이드와 HTTP/2를 지원한다.

**X-Forwarded-For**: 원본 클라이언트 IP가 `X-Forwarded-For` 헤더에 담겨 백엔드로 전달된다.

## 비교

| | NLB (L4) | ALB (L7) |
|---|---|---|
| 동작 계층 | TCP/UDP | HTTP/HTTPS |
| 라우팅 기준 | IP + 포트 | URL, 호스트, 헤더 |
| 레이턴시 | 매우 낮음 | NLB보다 약간 높음 |
| 고정 IP | 가능 (Elastic IP) | 불가 (DNS 이름만) |
| TLS 종료 | 가능 (pass-through도 가능) | 가능 |
| 프로토콜 | TCP, UDP, TLS | HTTP, HTTPS |
| WebSocket | 가능 (TCP 레벨) | 가능 (HTTP 업그레이드) |
| 인증 통합 | 불가 | Cognito/OIDC |

## 선택 기준

HTTP/HTTPS 서비스라면 **ALB가 기본 선택**이다. 콘텐츠 기반 라우팅, TLS 종료, 인증 통합이 실용적이다. k8s Ingress Controller를 ALB로 쓰는 경우(AWS Load Balancer Controller)가 대표적이다.

다음 경우에는 NLB를 쓴다.
- HTTP가 아닌 TCP/UDP 프로토콜 (gRPC, 게임 서버, DB 프록시)
- 고정 IP가 필요한 경우 (파트너사 IP 화이트리스트)
- 극단적으로 낮은 레이턴시가 필요한 경우
- 클라이언트 IP를 원본 그대로 서버에 전달해야 하는 경우
