---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-00. 런타임 보안 생태계 — 기초 개념 전체 지도"
date: 2026-06-15
tags: [security, runtime, ebpf, siem, soar, waf, ids, mitre-attack]
summary: "Falco·Sigma·Coraza를 이해하기 위한 런타임 보안 생태계 전체 그림. WAF/IDS/SIEM/SOAR의 역할 구분, 탐지-차단-대응 3계층, MITRE ATT&CK 기초."
slug: "runtime-security-ecosystem"
---

## 왜 "런타임" 보안인가

보안은 크게 두 시점으로 나뉜다.

- **빌드·배포 단계 (정적)** — 코드 취약점 스캔(SAST), 의존성 취약점(SCA), 컨테이너 이미지 스캔, 시크릿 탐지. SkillSpector나 Semgrep이 여기 속한다.
- **실행 단계 (런타임)** — 프로세스가 이미 돌고 있는 상황. 실제 공격은 대부분 여기서 일어난다.

정적 분석은 "이 코드에 취약점이 있는가?"를 묻고, 런타임 보안은 "지금 이 시스템에서 이상한 일이 일어나고 있는가?"를 묻는다.

공격자가 취약점을 찾아 침투하면, 코드 스캔이 아무리 잘 돼 있어도 런타임에서는 정상적인 프로세스 뒤에 숨어 움직인다. 그래서 두 계층이 모두 필요하다.

---

## 공격의 흐름: MITRE ATT&CK

공격자는 무작위로 행동하지 않는다. 재현 가능한 패턴이 있다. MITRE ATT&CK는 이 패턴을 14개 전술(Tactic)과 수백 개의 기법(Technique/Sub-technique)으로 분류한다.

```
초기 접근(TA0001)          → 실행(TA0002)              → 지속성(TA0003)
Phishing, 취약점 익스플로잇    cmd/PowerShell/Script 실행    백도어, 예약 작업, 서비스 등록

권한 상승(TA0004)           → 방어 회피(TA0005)           → 자격증명 탈취(TA0006)
sudo 악용, SUID 바이너리       로그 삭제, 프로세스 인젝션       /etc/shadow 덤프, Mimikatz

탐색(TA0007)               → 내부 이동(TA0008)            → 수집(TA0009)
네트워크·파일 스캔             SSH pivot, PsExec             민감 파일 찾기

C2(TA0011)                → 유출(TA0010)                → 영향(TA0040)
암호화 채널, DNS 터널           파일 압축 후 업로드             랜섬웨어, 시스템 파괴
```

Sigma 룰의 `tags` 필드가 `attack.t1059`처럼 기법 ID를 달고 있는 이유가 여기 있다. 탐지 룰을 ATT&CK에 매핑하면 "우리가 어떤 공격 단계를 커버하고 있고 어디가 blind spot인지" 가시화된다.

---

## 보안 도구 4개 레이어

```
─────────────────────────────────────────────────────────
레이어 1: 차단 (Prevention / Blocking)
─────────────────────────────────────────────────────────
 WAF (Web Application Firewall)
   - 들어오는 HTTP 요청을 검사 → XSS/SQLi/Path Traversal 등 차단
   - 인라인(inline): 트래픽이 직접 통과. 막지 않으면 못 들어옴
   - 대표 OSS: Coraza, ModSecurity

─────────────────────────────────────────────────────────
레이어 2: 탐지 (Detection / Monitoring)
─────────────────────────────────────────────────────────
 HIDS (Host-based IDS)
   - 서버/컨테이너 안에서 syscall, 프로세스, 파일, 네트워크를 감시
   - 차단은 못 하지만(기본적으로) 이상한 행동을 "발견"하고 알린다
   - 대표 OSS: Falco, OSSEC, Wazuh

 NIDS (Network IDS)
   - 네트워크 패킷 레벨에서 이상 트래픽 탐지
   - 대표 OSS: Suricata, Snort, Zeek

─────────────────────────────────────────────────────────
레이어 3: 집계·분석 (Aggregation / Correlation)
─────────────────────────────────────────────────────────
 SIEM (Security Information and Event Management)
   - 여러 소스(서버 로그, WAF 로그, IDS 경보, AD 이벤트 등)를 한 곳에 모아
     상관 분석(correlation)으로 공격 패턴을 식별
   - 대표 OSS: Elasticsearch/OpenSearch + 시각화, Graylog, Wazuh SIEM
   - 상용: Splunk, QRadar, Microsoft Sentinel, Google Chronicle

 Sigma는 이 레이어의 "탐지 룰 언어". SIEM마다 쿼리 문법이 달라서
 한 번 Sigma로 쓰고 원하는 SIEM으로 변환하는 방식.

─────────────────────────────────────────────────────────
레이어 4: 자동 대응 (Response / SOAR)
─────────────────────────────────────────────────────────
 SOAR (Security Orchestration, Automation, and Response)
   - SIEM에서 경보가 오면 자동으로 대응 플레이북 실행
   - 예: "특정 IP에서 brute force 탐지" → 방화벽 차단 + Slack 알림 + 티켓 생성
   - 대표 OSS: Shuffle, TheHive + Cortex
   - 상용: Splunk SOAR, Palo Alto XSOAR
```

---

## 차단 vs 탐지: 뭐가 다른가

흔히 헷갈리는 지점이다.

| | WAF (차단) | IDS (탐지) |
|---|---|---|
| 동작 방식 | 인라인 — 트래픽이 통과. 악성이면 드랍 | 아웃오브밴드 — 복사본 or 로그를 봄 |
| 오탐(FP) 영향 | 크다 — 정상 요청도 막힘 | 작다 — 경보만 날림 |
| 지연 영향 | 있음 — 모든 요청이 거침 | 없음 — 처리 흐름에 영향 안 줌 |
| 사용 목적 | "막는다" | "안다" |

Falco는 기본적으로 탐지 도구다. syscall을 모니터링하고 이상하면 경보를 날리지만, 프로세스를 죽이거나 syscall을 막지는 않는다(kill 액션을 설정하면 가능하지만 제한적). 그래서 Falco의 경보를 받아서 SOAR가 자동 대응하는 구조를 만드는 게 일반적이다.

---

## 이벤트 소스: 뭘 보는가

런타임 보안 도구들이 보는 이벤트 소스는 크게 4가지다.

### 1. Syscall (시스템 콜)
OS와 프로세스 사이의 경계. `open()`, `execve()`, `connect()`, `write()` 같은 호출을 가로채면 프로세스가 무엇을 하는지 정확히 알 수 있다. 우회가 어렵다 — 사용자 공간의 어떤 코드도 커널 서비스를 받으려면 syscall을 써야 한다.

Falco가 주로 보는 것.

### 2. 커널 이벤트 (eBPF)
eBPF(Extended Berkeley Packet Filter)를 쓰면 커널에 커스텀 코드를 안전하게 삽입할 수 있다. kprobe, tracepoint, XDP 등을 통해 syscall뿐 아니라 네트워크 스택, 파일시스템, 스케줄러까지 관찰 가능. Falco의 modern BPF 드라이버가 이 방식.

### 3. 감사 로그 (Audit Logs)
- **Linux auditd**: 커널 감사 서브시스템. 파일 접근, 프로세스 실행, 네트워크 연결을 룰 기반으로 로그
- **Windows Event Log**: Sysmon이 프로세스 생성, 네트워크 연결, 레지스트리 변경 등을 Event ID로 기록
- **K8s Audit**: API server가 모든 요청을 감사 로그로 남김 (누가 어떤 리소스를 만들었는지)
- **Cloud Audit**: CloudTrail(AWS), Cloud Audit Logs(GCP) 등

Sigma 룰의 `logsource`가 이것들을 가리킨다.

### 4. 컨테이너/K8s 메타데이터
컨테이너 런타임(containerd, CRI-O)과 K8s API가 제공하는 컨텍스트. "이 syscall은 `my-app` Deployment의 `backend` 컨테이너에서 발생했다"는 정보를 붙여준다. Falco가 이 메타데이터를 syscall 이벤트에 enrichment로 추가한다.

---

## WAF 동작 원리 (Coraza/ModSecurity 기준)

HTTP 요청이 들어오면 4개의 Phase를 순서대로 거친다.

```
Phase 1: Request Headers    — User-Agent, Cookie, Content-Type 등
Phase 2: Request Body       — POST body, JSON payload, 파일 업로드
Phase 3: Response Headers   — Set-Cookie, X-Powered-By 등
Phase 4: Response Body      — HTML, JSON 응답 (민감 정보 유출 방지)
```

각 Phase에서 SecLang(ModSecurity 룰 언어)으로 쓴 룰이 패턴 매칭. CRS(Core Rule Set)는 이 룰들의 대규모 모음이다.

```
# 예시: SQLi 탐지 룰 (CRS 스타일)
SecRule REQUEST_URI|REQUEST_BODY \
  "@detectSQLi" \
  "id:942100,phase:2,deny,status:403,msg:'SQL Injection'"
```

OWASP CRS는 XSS, SQLi, RFI, LFI, RCE, PHP injection, Command Injection, Scanner 탐지 등 3000개 이상의 룰을 제공한다.

---

## SIEM의 상관 분석 (Correlation)

개별 이벤트 하나만 봐서는 공격인지 모르는 경우가 많다. 상관 분석은 여러 이벤트를 시간/컨텍스트로 연결한다.

예:
- "같은 IP에서 5분 안에 로그인 실패가 10번 넘으면 → brute force"
- "프로세스 A가 spawn한 B가 외부에 connect한 직후 C가 /etc/shadow를 열면 → credential dump"

Sigma v2의 correlation 기능이 바로 이걸 규칙화한다. 단순 pattern match에서 시간 기반 상관관계로 넘어간다.

---

## 보안 에이전트가 그리는 그림

이 문서들이 지향하는 목표:

```
         ┌─────────────────────────────────────────────────────┐
         │                  보안 에이전트 (LLM Brain)            │
         │  관측 → 추론 → 대응 플레이북 실행                     │
         └─────┬────────────────────────────────────┬──────────┘
               │ 경보 입력                          │ 대응 명령
         ┌─────▼──────────────────────┐   ┌────────▼─────────────┐
         │  탐지 레이어                │   │  대응 레이어           │
         │  • Falco (runtime syscall) │   │  • IP 차단             │
         │  • Sigma (log detection)   │   │  • 컨테이너 격리        │
         │  • Suricata (network)      │   │  • 티켓 생성            │
         └─────────────────────────── ┘   │  • Slack 알림          │
                                          └────────────────────────┘
         ┌──────────────────────────────────────────────────────┐
         │  차단 레이어                                          │
         │  • Coraza/CRS (WAF: XSS/SQLi 인라인 차단)            │
         └──────────────────────────────────────────────────────┘
```

Falco + Sigma는 탐지 레이어. 이 두 도구의 경보를 에이전트가 받아서 Temporal/ReactFlow 기반 플레이북으로 대응하는 구조가 최종 목표.

---

## 용어 정리

| 용어 | 풀이 |
|---|---|
| HIDS | Host-based IDS. 호스트 안을 봄 |
| NIDS | Network-based IDS. 네트워크 패킷을 봄 |
| SIEM | 로그 수집·저장·상관 분석 플랫폼 |
| SOAR | 보안 오케스트레이션·자동화·대응 |
| WAF | 웹 레이어 인라인 차단 |
| IPS | IDS + 인라인 차단 능력 추가 |
| eBPF | 커널에 안전하게 코드 삽입하는 기술 |
| Syscall | 사용자 공간 ↔ 커널 간 인터페이스 |
| SecLang | ModSecurity/WAF 룰 언어 |
| CRS | OWASP Core Rule Set (WAF 룰 묶음) |
| ATT&CK | MITRE의 공격 전술·기법 분류 체계 |
| IOC | Indicator of Compromise. 침해 지표 (IP, 해시, 도메인 등) |
| TTP | Tactics, Techniques, Procedures. ATT&CK의 분류 단위 |
| SOC | Security Operations Center. 보안 관제 조직 |
| DFIR | Digital Forensics & Incident Response |
