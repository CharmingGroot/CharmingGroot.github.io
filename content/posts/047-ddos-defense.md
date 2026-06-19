---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "047. DDoS 방어 레이어 — 볼류메트릭 공격부터 애플리케이션 레이어까지"
date: 2026-06-13
tags: [network, security, ddos, cdn, rate-limiting, waf, anycast, aws-shield, cloudflare]
summary: "DDoS(Distributed Denial of Service)는 대량의 트래픽으로 서비스를 마비시키는 공격이다. 공격 유형에 따라 방어 레이어가 다르다. 네트워크 레벨 볼류메트릭 공격, 프로토콜 레벨 공격, 애플리케이션 레벨 공격 각각에 어떤 방어가 적용되는지, 그리고 실무에서 어떤 구성이 표준인지 설명한다."
slug: "047-ddos-defense"
categories: ["클라우드 인프라"]
---

DDoS는 수많은 장치(봇넷)에서 동시에 요청을 보내 서버의 자원(대역폭, CPU, 연결 수)을 소진시키는 공격이다. 정상 트래픽을 처리할 여력을 없애는 것이 목적이다. 공격 계층에 따라 방어 방법이 다르다.

## 공격 유형

### L3/L4 — 볼류메트릭 공격

네트워크 대역폭이나 패킷 처리량을 포화시킨다.

**UDP Flood**: 대량의 UDP 패킷을 보내 대역폭을 소진한다. DNS amplification 공격이 대표적이다. 작은 DNS 쿼리로 큰 응답을 유발해 피해자에게 증폭된 트래픽을 반사시킨다.

**SYN Flood**: TCP 연결 시작(SYN)만 대량으로 보내고 완료(ACK)를 안 한다. 서버의 연결 대기 큐를 꽉 채워 정상 연결을 못 받게 한다.

이런 공격은 수십~수백 Gbps 규모로 발생한다. 단일 서버나 데이터센터로는 감당이 안 된다.

### L7 — 애플리케이션 레이어 공격

정상적인 HTTP 요청처럼 보이는 트래픽으로 애플리케이션을 과부하시킨다. 적은 트래픽으로도 효과적이어서 방어가 더 어렵다.

**HTTP Flood**: 특정 API 엔드포인트에 대량 요청을 보낸다. DB 쿼리를 유발하는 검색 API, 인증 API가 주요 대상이다.

**Slowloris**: HTTP 요청을 매우 느리게 보내 서버 연결을 오래 점유한다. 요청을 완성하지 않고 주기적으로 헤더만 조금씩 보내 연결을 유지한다.

## 방어 레이어

### 1. CDN + Anycast (L3/L4 방어)

대규모 CDN(Cloudflare, AWS CloudFront)은 전 세계에 분산된 PoP(Point of Presence)를 가진다. 공격 트래픽이 전 세계 수백 개 노드에 분산 흡수된다.

Anycast는 같은 IP 주소가 여러 지리적 위치에서 동시에 서비스되는 라우팅 기술이다. 공격 패킷이 가장 가까운 노드로 라우팅되어 분산 처리된다. Cloudflare의 서비스는 Anycast 기반이다.

```
공격 트래픽 100Gbps
→ Anycast로 전 세계 분산
→ 각 PoP에서 1~2Gbps만 처리
→ 오리진 서버는 정상 트래픽만 받음
```

### 2. Rate Limiting (L7 방어)

같은 IP 또는 사용자에서 일정 시간 내에 허용되는 요청 수를 제한한다.

```nginx
# nginx rate limiting
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    limit_req_status 429;
}
```

IP 단위 외에도 사용자 ID, API 키, 디바이스 핑거프린트 단위로 제한할 수 있다. 정교한 공격자는 IP를 계속 바꾸므로 IP 단위만으로는 부족하고, 여러 차원을 조합한다.

### 3. WAF — Web Application Firewall (L7 방어)

HTTP 요청 내용을 분석해 악의적인 패턴을 차단한다. SQL Injection, XSS, 알려진 공격 시그니처를 필터링한다. DDoS뿐 아니라 일반 웹 공격도 막는다.

AWS WAF는 CloudFront나 ALB 앞에 붙인다.

```
규칙 예시:
- 요청 속도 기반 규칙: 5분에 2000건 이상 요청하는 IP 차단
- 지리 기반 규칙: 서비스 대상 국가 외 IP 차단
- 봇 관리: 알려진 봇 시그니처 차단, CAPTCHA 적용
- IP 평판 목록: 알려진 악성 IP 차단
```

### 4. AWS Shield

**Shield Standard**: 모든 AWS 계정에 기본 포함. L3/L4 공격(SYN flood, UDP flood)을 자동으로 탐지하고 완화한다. 추가 비용 없다.

**Shield Advanced**: 유료. L7 공격 탐지, DDoS 대응팀(DRT) 24/7 지원, 공격으로 인한 AWS 비용 환급 등을 제공한다. 대규모 서비스나 금융, 게임처럼 DDoS 위험이 높은 업종에 적합하다.

## 실무 표준 구성

```
인터넷
  ↓
[CDN / Cloudflare / AWS CloudFront]
  - Anycast로 L3/L4 볼류메트릭 흡수
  - WAF로 L7 공격 필터링
  - Rate Limiting
  ↓
[ALB]
  - AWS WAF 연동
  - Security Group으로 CDN IP만 허용 (오리진 직접 공격 차단)
  ↓
[앱 서버]
  - 애플리케이션 레벨 Rate Limiting
  - 비정상 패턴 로깅 및 알람
```

오리진 서버 IP를 CDN 뒤에 숨기는 것이 기본이다. 오리진 IP가 노출되면 CDN을 우회해서 직접 공격할 수 있다. ALB Security Group에서 CDN IP 대역만 허용하면 CDN을 거치지 않는 트래픽을 차단할 수 있다.

## 트레이드오프

Rate Limiting은 정상 사용자를 오탐(false positive)으로 막을 위험이 있다. 임계값을 너무 낮게 잡으면 배치 처리나 API 헤비 유저가 차단된다. 임계값을 높이면 공격이 더 많이 통과된다. 서비스 트래픽 패턴을 분석해 임계값을 조정해야 한다.

L7 공격은 정상 요청과 구분이 어렵다. 특히 분산된 봇넷이 각 IP에서 적은 요청을 보내면 IP 기반 Rate Limiting으로는 잡기 어렵다. 행동 분석(짧은 세션, 비인간적 패턴), CAPTCHA, 디바이스 핑거프린팅 등 추가 계층이 필요하다.
