---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-03. Sigma 기초 — 룰 문법, logsource, detection 완전 분해"
date: 2026-06-15
tags: [sigma, siem, detection-engineering, logsource, mitre-attack, yaml]
summary: "Sigma 룰의 모든 필드를 하나씩 분해. logsource의 3축(product/category/service), detection의 selection+modifier+condition, 상관관계(correlation) 기초."
slug: "sigma-basics"
categories: ["보안"]
---

## Sigma란

Sigma는 "로그를 위한 YARA"다. YARA가 파일을 위한 범용 시그니처 포맷이고, Snort가 네트워크 패킷을 위한 포맷인 것처럼, Sigma는 **로그 이벤트를 위한 범용 탐지 룰 포맷**이다.

핵심 가치:
- 룰을 한 번만 쓴다 (YAML)
- `sigma-cli` 또는 pySigma 백엔드로 원하는 SIEM 쿼리로 변환한다
- Splunk, Elasticsearch, QRadar, Microsoft Sentinel, Chronicle, OpenSearch, Graylog... 모두 지원

```
Sigma 룰 (YAML)
    │
    ▼
pySigma 변환기
    │
    ├─→  Splunk SPL: index=wineventlog EventID=4688 AND CommandLine=*base64*
    ├─→  Elastic DSL: {"query": {"bool": {"must": [...]}}}
    ├─→  Microsoft KQL: SecurityEvent | where EventID == 4688 | where CommandLine has "base64"
    └─→  QRadar AQL: SELECT * FROM events WHERE ...
```

벤더 종속 쿼리 언어를 배울 필요 없이 탐지 로직 자체에 집중할 수 있다.

---

## 룰 파일 전체 구조

Sigma 룰 하나는 YAML 파일 하나다. 모든 필드:

```yaml
title: Suspicious AWK Shell Spawn
id: 8c1a5675-cb85-452f-a298-b01b22a51856
related:
  - id: 11f9a6f7-72e6-4a12-bc73-3a8c2e6e5e24
    type: derived   # obsoletes | derived | merged | similar
status: test        # stable | test | experimental | deprecated | unsupported
description: |
  awk로 셸을 spawn하는 행위 탐지. GTFOBins에 기록된 권한 상승 기법.
references:
  - https://gtfobins.github.io/gtfobins/awk/#shell
author: Li Ling, Andy Parkidomo
date: 2024-09-02
modified: 2024-11-15
tags:
  - attack.execution
  - attack.t1059
logsource:
  category: process_creation
  product: linux
detection:
  selection_img:
    Image|endswith:
      - '/awk'
      - '/gawk'
  selection_cli:
    CommandLine|contains:
      - '/bin/bash'
      - '/bin/sh'
  condition: all of selection_*
falsepositives:
  - 스크립트 개발 중 정상 사용
level: high
```

---

## 필드별 상세 설명

### `title`
룰 이름. 짧고 명확하게. 보통 "행동 - 플랫폼" 패턴.
- `Suspicious AWK Shell Spawn - Linux`
- `Windows Credential Dump via ProcDump`
- `AWS Console Login Without MFA`

### `id`
UUID v4. 룰을 유니크하게 식별. 절대 바뀌지 않는다. `uuidgen`으로 생성.

### `related`
파생/대체 관계를 추적. `type` 값:
- `derived`: 이 룰이 다른 룰에서 파생됨
- `obsoletes`: 이 룰이 다른 룰을 대체함
- `merged`: 여러 룰을 합침
- `similar`: 비슷하지만 다른 룰

### `status`
| 값 | 의미 |
|---|---|
| `stable` | 프로덕션 사용. 잘 검증됨 |
| `test` | 테스트 완료, 운영에 쓸 수 있지만 FP 가능성 있음 |
| `experimental` | 새 탐지 아이디어. 검증 안 됨. 주의해서 사용 |
| `deprecated` | 더 이상 유지 안 됨. `related`로 대체 룰 표시 |
| `unsupported` | 지원 중단 (logsource가 사라졌거나 할 수 없는 경우) |

SigmaHQ 공식 레포의 대부분 룰은 `test`. `stable`은 엄격한 검증을 거쳐야 한다.

### `level`
탐지 심각도. SIEM 경보 우선순위로 그대로 쓴다.

| 값 | 의미 | 예시 |
|---|---|---|
| `critical` | 즉각 대응 필요. 확실한 공격 | 알려진 랜섬웨어 IoC |
| `high` | 빠른 조사 필요 | 권한 상승 시도, 크리덴셜 덤프 |
| `medium` | 조사 필요하나 urgent 아님 | 의심스러운 프로세스, 비정상 네트워크 |
| `low` | 정보성. FP 많을 수 있음 | 관리 도구 실행 |
| `informational` | 로그 수집용. 경보 아님 | 정상 활동 기록 |

### `tags`
MITRE ATT&CK 매핑 + 커스텀 태그.

```yaml
tags:
  - attack.execution          # 전술 (소문자, _ 구분)
  - attack.t1059              # 기법 ID
  - attack.t1059.004          # 세부 기법 (AWK = T1059.004 = Unix Shell)
  - attack.privilege_escalation
  - attack.t1548
  - detection.threat_hunting  # 위협 헌팅 전용 태그
```

ATT&CK 전술 이름들:
- `attack.initial_access`, `attack.execution`, `attack.persistence`
- `attack.privilege_escalation`, `attack.defense_evasion`, `attack.credential_access`
- `attack.discovery`, `attack.lateral_movement`, `attack.collection`
- `attack.command_and_control`, `attack.exfiltration`, `attack.impact`

---

## logsource: 어떤 로그를 보는가

logsource는 `product`, `category`, `service` 3개 축으로 로그 소스를 특정한다.

```yaml
logsource:
  product: windows     # 플랫폼
  category: process_creation   # 이벤트 유형
  # service: security  # 특정 서비스 (category와 배타적으로 쓰는 경우 多)
```

### `product`

| 값 | 설명 |
|---|---|
| `windows` | Windows 이벤트 로그 |
| `linux` | Linux 시스템 로그 |
| `macos` | macOS 통합 로그 |
| `cloud` | 클라우드 서비스 (aws, azure, gcp 등 별도 product도 있음) |
| `aws` | AWS 서비스 (CloudTrail 등) |
| `azure` | Azure 서비스 |
| `gcp` | GCP 서비스 |
| `okta` | Okta |
| `github` | GitHub |
| `m365` | Microsoft 365 |

### `category` (Windows 중심)

Windows에서 자주 쓰는 category:

| category | 설명 | 주요 필드 |
|---|---|---|
| `process_creation` | 프로세스 생성 | Image, CommandLine, ParentImage, User |
| `network_connection` | 네트워크 연결 | DestinationIp, DestinationPort, Image |
| `file_event` | 파일 생성/수정 | TargetFilename, Image |
| `file_access` | 파일 접근 | TargetFilename, Image |
| `file_delete` | 파일 삭제 | TargetFilename |
| `registry_add` | 레지스트리 키 추가 | TargetObject, Details |
| `registry_set` | 레지스트리 값 설정 | TargetObject, Details |
| `registry_delete` | 레지스트리 키 삭제 | TargetObject |
| `pipe_created` | Named Pipe 생성 | PipeName |
| `image_load` | DLL/드라이버 로드 | ImageLoaded, Image |
| `driver_load` | 드라이버 로드 | ImageLoaded, Signed |
| `ps_script` | PowerShell 스크립트 | ScriptBlockText |
| `ps_module` | PowerShell 모듈 | ModuleName |
| `wmi_event` | WMI 이벤트 | EventNamespace, Query |
| `create_remote_thread` | 원격 스레드 생성 | TargetImage, StartAddress |
| `create_stream_hash` | ADS(대안 데이터 스트림) 해시 | Contents |

### `category` (Linux 중심)

| category | 설명 | 로그 소스 |
|---|---|---|
| `process_creation` | 프로세스 실행 | auditd execve, sysmon for linux |
| `file_event` | 파일 이벤트 | auditd, sysmon |
| `network_connection` | 네트워크 연결 | auditd, sysmon |

### `service` (특정 서비스 로그)

| service | 설명 |
|---|---|
| `security` | Windows Security 이벤트 로그 (이벤트 ID 4xxx) |
| `system` | Windows System 이벤트 로그 |
| `application` | Windows Application 이벤트 로그 |
| `powershell` | PowerShell 이벤트 로그 |
| `sysmon` | Sysinternals Sysmon |
| `auditd` | Linux auditd |
| `auth` | Linux /var/log/auth.log |
| `cron` | Linux 크론 로그 |

---

## detection: 핵심

detection 섹션이 실제 탐지 로직이다.

```yaml
detection:
  selection:      # selection 블록 (여러 개 가능)
    field: value
  filter:
    field: value
  condition: selection and not filter   # 조건 표현식
```

### Selection 블록

selection 블록 이름은 자유롭게 정할 수 있다. 관례적으로 `selection`, `selection_A`, `filter`, `filter_main` 등을 쓴다.

블록 내부 필드들은 **AND** 관계다:

```yaml
detection:
  selection:
    EventID: 4688          # AND
    CommandLine|contains: 'base64'   # AND
    User|endswith: '$'     # 모두 만족해야 선택됨
  condition: selection
```

같은 필드에 여러 값은 **OR** 관계:

```yaml
detection:
  selection:
    CommandLine|contains:
      - 'base64 -d'    # OR
      - 'base64 -D'    # OR
      - 'FromBase64'
```

즉: "같은 블록 내 필드 간 = AND, 같은 필드의 여러 값 = OR"

---

## 모디파이어 (Modifier) 완전 정리

`field|modifier: value` 형태. 여러 개 체이닝 가능: `field|modifier1|modifier2`.

### 기본 비교 모디파이어

| 모디파이어 | 설명 | 예시 |
|---|---|---|
| (없음) | 정확히 일치 (=) | `EventID: 4688` |
| `contains` | 문자열 포함 | `CommandLine\|contains: 'wget'` |
| `contains\|all` | 모든 값을 포함 | 여러 값이 모두 있어야 |
| `startswith` | 접두사 | `Image\|startswith: 'C:\Windows\'` |
| `endswith` | 접미사 | `Image\|endswith: '\cmd.exe'` |
| `re` | PCRE 정규식 | `CommandLine\|re: 'powershell.*-enc'` |

### 인코딩 모디파이어

| 모디파이어 | 설명 |
|---|---|
| `base64` | base64 인코딩된 값과 매칭 |
| `base64offset` | base64 오프셋(0,1,2) 변형 모두 체크 |
| `wide` | UTF-16LE 인코딩 (Windows 유니코드 문자열) |
| `utf16le` | UTF-16 Little Endian |
| `utf16be` | UTF-16 Big Endian |

```yaml
# PowerShell -EncodedCommand 탐지
# -enc로 전달되는 base64 + UTF-16LE 조합
detection:
  selection:
    CommandLine|base64offset|contains:
      - 'IEX'     # Invoke-Expression
      - 'Invoke-Expression'
      - 'WebClient'
```

### 네트워크/특수 모디파이어

| 모디파이어 | 설명 | 예시 |
|---|---|---|
| `cidr` | CIDR 범위로 IP 매칭 | `DestinationIp\|cidr: '192.168.0.0/16'` |
| `fieldref` | 다른 필드 값을 참조 | `TargetImage\|fieldref: Image` |
| `expand` | 변수 확장 (placeholder) | `CommandLine\|expand: '%SUSPICIOUS_CMDS%'` |
| `windash` | - 와 / 구분자 모두 체크 | `CommandLine\|contains\|windash: ' -Enc '` |

### `contains|all` — 모두 포함

```yaml
# 모든 값이 CommandLine에 있어야 함 (AND)
detection:
  selection:
    CommandLine|contains|all:
      - 'powershell'   # AND
      - '-nop'         # AND
      - '-enc'
```

vs 일반 `contains` (OR):

```yaml
# 하나라도 있으면 됨 (OR)
detection:
  selection:
    CommandLine|contains:
      - 'powershell'   # OR
      - '-nop'         # OR
      - '-enc'
```

---

## condition 표현식

condition에서 selection 블록들을 논리 연산자로 조합한다.

### 기본 연산자

```yaml
condition: selection                  # 단일 블록
condition: selection and not filter   # AND NOT
condition: selection_a or selection_b # OR
condition: not selection              # NOT (단독 사용 지양)
```

### 집합 연산자

```yaml
# selection_A, selection_B, selection_C 중 하나 이상
condition: 1 of selection_*

# filter_로 시작하는 블록 중 하나도 안 맞으면
condition: selection and not 1 of filter_*

# filter_로 시작하는 모든 블록에 안 맞으면
condition: selection and not all of filter_*
```

`1 of selection_*`는 `selection_*` 패턴에 매칭되는 모든 블록 중 **하나** 이상 매칭이면 true. `all of selection_*`는 **모두** 매칭이면 true.

### 실전 패턴들

**패턴 1: 선택 + 필터 제외**
```yaml
detection:
  selection:
    Image|endswith: '\powershell.exe'
    CommandLine|contains: '-enc'
  filter_admin:
    User: SYSTEM
  filter_legit_path:
    Image|startswith: 'C:\Windows\System32\'
  condition: selection and not 1 of filter_*
```

**패턴 2: 여러 선택 중 하나**
```yaml
detection:
  selection_image:
    Image|endswith:
      - '\nc.exe'
      - '\ncat.exe'
      - '\netcat.exe'
  selection_cmdline:
    CommandLine|contains|all:
      - ' -e '
      - '/bin/sh'
  condition: 1 of selection_*
```

**패턴 3: 복합 AND 조건**
```yaml
detection:
  selection_parent:
    ParentImage|endswith: '\word.exe'
  selection_child:
    Image|endswith:
      - '\cmd.exe'
      - '\powershell.exe'
      - '\wscript.exe'
  condition: all of selection_*
# 해석: ParentImage가 word.exe이면서 동시에 Image가 cmd/ps/wscript 중 하나
```

---

## 상관관계 (Correlation) — v2 기능

Sigma v2의 `correlation` 타입은 여러 이벤트를 시간 기반으로 연결한다.

```yaml
# 기반 룰
- name: failed_login_attempt
  title: Failed Login Attempt
  logsource:
    product: windows
    service: security
  detection:
    selection:
      EventID: 4625   # 로그인 실패
    condition: selection

# 상관관계 룰
- title: Brute Force Attack
  type: event_count
  rules:
    failed_login: failed_login_attempt
  group-by:
    - TargetUserName   # 사용자별로 그룹화
    - IpAddress
  timespan: 5m
  condition:
    gte: 10            # 5분 안에 10번 이상 실패
  level: high
  tags: [attack.credential_access, attack.t1110]
```

상관관계 타입:

| 타입 | 설명 |
|---|---|
| `event_count` | 시간 내 이벤트 발생 횟수 |
| `value_count` | 고유 값 개수 (예: 접속한 IP 수) |
| `temporal` | 여러 룰이 같은 시간 창 안에 모두 발생 |
| `temporal_ordered` | 여러 룰이 순서대로 발생 |

`temporal_ordered` 예시: "로그인 성공 → 민감 파일 접근 → 외부 연결"이 순서대로 발생하면 내부자 데이터 유출 의심.

---

## logsource별 필드 맵

변환기가 `process_creation` 이벤트의 `Image` 필드를 실제 SIEM 필드로 어떻게 변환하는지:

### Windows process_creation

| Sigma 필드 | Sysmon (Event 1) | Windows Audit (4688) | auditd |
|---|---|---|---|
| `Image` | `Image` | `NewProcessName` | `exe` |
| `CommandLine` | `CommandLine` | `CommandLine` | `cmd` |
| `ParentImage` | `ParentImage` | `ParentProcessName` | `ppid→exe` |
| `User` | `User` | `SubjectUserName` | `uid→name` |
| `Hashes` | `Hashes` | (없음) | (없음) |

변환기(pySigma)는 파이프라인 설정에서 이 매핑을 처리한다.

---

## 실전 룰 작성 예시

### 예시 1: Linux에서 passwd 덤프 시도

```yaml
title: Passwd File Read Attempt
id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
status: experimental
description: 비루트 프로세스가 /etc/passwd를 읽으려 함
references:
  - https://attack.mitre.org/techniques/T1003/008/
author: My Name
date: 2026-06-15
tags:
  - attack.credential_access
  - attack.t1003.008
logsource:
  product: linux
  category: file_access
detection:
  selection:
    FileName: '/etc/passwd'
  filter_root:
    UserId: 0
  filter_legit:
    Image|endswith:
      - '/login'
      - '/passwd'
      - '/useradd'
  condition: selection and not filter_root and not 1 of filter_legit
falsepositives:
  - 관리 스크립트가 직접 읽는 경우
level: medium
```

### 예시 2: Windows에서 PowerShell 난독화

```yaml
title: PowerShell Encoded Command Execution
id: b2c3d4e5-f6a7-8901-bcde-f12345678901
status: test
description: PowerShell이 -EncodedCommand 플래그로 실행됨. 악성 스크립트가 탐지를 피하려 자주 씀.
references:
  - https://attack.mitre.org/techniques/T1059/001/
author: My Name
date: 2026-06-15
tags:
  - attack.execution
  - attack.t1059.001
  - attack.defense_evasion
  - attack.t1027
logsource:
  product: windows
  category: process_creation
detection:
  selection_encoded:
    Image|endswith:
      - '\powershell.exe'
      - '\pwsh.exe'
    CommandLine|contains|windash:
      - ' -EncodedCommand '
      - ' -enc '
      - ' -ec '
  filter_scheduled:
    ParentImage|endswith: '\taskhost.exe'
    CommandLine|contains: 'ScheduledTasks'
  condition: selection_encoded and not filter_scheduled
falsepositives:
  - SCCM, 관리 스크립트 일부
level: medium
```

### 예시 3: 네트워크 스캔 탐지 (auditd)

```yaml
title: Network Scanning Tool Execution
id: c3d4e5f6-a7b8-9012-cdef-123456789012
status: test
description: nmap, masscan 같은 네트워크 스캔 도구 실행
logsource:
  product: linux
  service: auditd
detection:
  selection:
    type: EXECVE
    a0|endswith:
      - '/nmap'
      - '/masscan'
      - '/zmap'
      - '/rustscan'
  condition: selection
falsepositives:
  - 네트워크 팀의 정기 스캔
  - 취약점 점검 업무
level: medium
tags:
  - attack.discovery
  - attack.t1046
```

---

## false positives 관리

FP(오탐)가 많으면 룰을 신뢰할 수 없다. 관리 방법:

1. **`falsepositives` 필드에 기록**: 어떤 정상 행동이 이 룰에 걸릴 수 있는지 설명. 룰 사용자에게 힌트.

2. **`filter_*` 블록 추가**: 알려진 FP를 구조적으로 제외.

3. **level 낮추기**: 확신이 없으면 `high` → `medium`으로 내리고 운영 중 모니터링.

4. **status 표시**: 검증이 덜 됐으면 `experimental`로.

---

## sigma-cli 사용

```bash
# 설치
pip install sigma-cli

# 플러그인 목록 확인
sigma plugin list

# 백엔드 설치 (Elasticsearch)
sigma plugin install pySigma-backend-elasticsearch

# 변환
sigma convert \
  --target elasticsearch \
  --pipeline ecs_windows \
  rules/windows/process_creation/proc_creation_win_powershell_enc.yml

# 여러 룰 일괄 변환
sigma convert \
  --target splunk \
  --pipeline windows-splunk \
  rules/windows/process_creation/

# 파이프라인 지정
sigma convert \
  --target qradar \
  --pipeline sysmon \
  my_rule.yml
```

---

## 도구 생태계

| 도구 | 역할 |
|---|---|
| [sigma-cli](https://github.com/SigmaHQ/sigma-cli) | 공식 CLI 변환기 |
| [pySigma](https://github.com/SigmaHQ/pySigma) | Python 라이브러리 (백엔드 구현체) |
| [sigconverter.io](https://sigconverter.io) | 웹 GUI 변환기 |
| [detection.studio](https://detection.studio) | 웹 GUI 변환기 |
| [uncoder.io](https://uncoder.io) | 쿼리 변환 (Sigma 포함) |
| [Phoenix](https://sigma.nasbench.dev) | Sigma 룰 인텔리전스 플랫폼 |
| [MITRE ATT&CK navigator](https://mitre-attack.github.io/attack-navigator/) | ATT&CK 커버리지 시각화 |
