---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-01. Falco 기초 — 아키텍처, 드라이버, 룰 문법"
date: 2026-06-15
tags: [falco, cncf, ebpf, syscall, runtime-security, kubernetes, rules]
summary: "Falco의 내부 아키텍처(커널 드라이버 → 파서 → 룰 엔진 → 출력), 3가지 드라이버(kmod/legacy BPF/modern BPF), 룰 문법 전체(rule/macro/list/exception), 주요 필드 레퍼런스."
slug: "falco-basics"
---

## Falco란

Falco는 Linux 런타임에서 **비정상 행동을 실시간 탐지**하는 CNCF Graduated 프로젝트다. 원래 Sysdig가 2016년 오픈소스로 공개했고, 2020년 CNCF Incubating → 2024년 Graduated.

핵심 아이디어: **커널에서 발생하는 모든 syscall을 관찰하고, 사용자가 작성한 룰과 매칭되면 경보를 낸다.**

컨테이너·K8s 환경에서도 "어떤 Pod의 어떤 컨테이너"가 그 syscall을 불렀는지 메타데이터를 enrichment로 붙여준다.

차단 도구가 아니다. 기본적으로 관찰하고 알린다 (alert-only). 필요하면 `kill` 액션을 룰에 붙일 수 있지만 추가 설정이 필요하고 주의가 필요하다.

---

## 아키텍처 전체 그림

```
┌─────────────────────────────────────────────────────────────────────┐
│  Linux Kernel                                                       │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  syscall table: open, execve, connect, write, read, ...      │  │
│  └──────────────────┬───────────────────────────────────────────┘  │
│                     │ 후킹(driver가 이 지점을 인터셉트)               │
│  ┌──────────────────▼────────────────────────────────────────────┐ │
│  │  Falco Driver (3종 중 하나 선택)                                │ │
│  │  • Kernel Module (kmod)                                        │ │
│  │  • Legacy eBPF probe                                           │ │
│  │  • Modern eBPF probe (권장, CO-RE 기반)                        │ │
│  └──────────────────┬──────────────────────────────────────────── ┘ │
└────────────────────-│──────────────────────────────────────────────-┘
                      │ ring buffer를 통해 이벤트 전달
┌─────────────────────▼──────────────────────────────────────────────┐
│  Falco 사용자 공간 바이너리                                           │
│                                                                     │
│  libscap ─── 이벤트 캡처·디코딩 (syscall 번호 → 이벤트 구조체)        │
│      │                                                              │
│  libsinsp ── 상태 추적(프로세스 트리, FD 테이블, 컨테이너 메타데이터)   │
│      │       enrichment: proc.*, fd.*, container.*, k8s.* 필드 채움 │
│      │                                                              │
│  Rule Engine ── 룰 파싱, 필터 컴파일, 이벤트 매칭                    │
│      │          (falco_engine.cpp + libfilter)                      │
│      │                                                              │
│  Output ───── stdout, syslog, file, http, program                  │
└─────────────────────────────────────────────────────────────────────┘
```

### libscap
"Sysdig capture" 라이브러리. 드라이버(커널 모듈 or eBPF)로부터 이벤트를 읽어서 내부 포맷으로 디코딩하는 역할. scap 이벤트는 타입, 타임스탬프, 인자들을 담은 구조체.

### libsinsp
"Sysdig inspect". libscap 이벤트를 받아서 **상태를 유지한다**. 예를 들어 어떤 PID가 어떤 파일을 열었는지(FD 테이블), 어떤 PID의 부모가 누구인지(프로세스 트리)를 추적한다. 이 상태 덕분에 `proc.pname` 같은 필드(부모 프로세스 이름)를 룰에서 쓸 수 있다.

컨테이너 런타임(containerd/CRI-O)에 붙어서 container ID → 이미지/label/namespace 매핑도 여기서 한다.

### Rule Engine
룰 파일을 파싱하고 각 룰의 `condition`을 내부 필터 AST로 컴파일한다. 이벤트가 올 때마다 필터를 평가해서 매칭되는 룰이 있으면 출력 메시지를 만들어 내보낸다.

---

## 3가지 드라이버

### 1. Kernel Module (kmod)
가장 오래된 방식. `.ko` 파일을 커널에 올린다. 커널 버전에 맞게 컴파일해야 한다. 성능이 가장 좋지만 커널 ABI 의존성 때문에 커널 업그레이드 시 다시 빌드해야 할 수 있다. DKMS(Dynamic Kernel Module Support)로 자동 빌드하는 게 일반적.

운영 환경: VM 또는 bare-metal에서 커널 모듈 로드가 허용된 경우.

### 2. Legacy eBPF Probe
커널 4.14+ 에서 동작. eBPF CO-RE(Compile Once, Run Everywhere) 적용 전 버전이라 특정 커널 헤더 의존성이 있다. 커널 패닉 위험이 kmod보다 낮다(eBPF verifier가 검증).

### 3. Modern eBPF Probe (권장)
커널 5.8+ (CONFIG_DEBUG_INFO_BTF=y 필요). CO-RE 기반이라 한 번 컴파일한 바이너리가 여러 커널 버전에서 동작. BTF(BPF Type Format)로 커널 구조체 오프셋을 런타임에 추론한다. Falco 공식 권장 드라이버.

```
# 드라이버 선택 (falco.yaml)
engine:
  kind: modern_ebpf   # kmod | ebpf | modern_ebpf
```

---

## eBPF 기초 (알아두면 좋은 것)

eBPF는 "확장 BPF". 원래 BPF는 패킷 필터링용(tcpdump가 쓰는 것)이었는데, Linux 3.18+부터 범용 커널 내 VM으로 확장됐다.

핵심 특성:
- **안전**: eBPF 프로그램은 커널 로딩 전 verifier를 통과해야 한다. 무한 루프, 잘못된 메모리 접근은 거부된다.
- **고성능**: 컨텍스트 스위치 없이 커널 안에서 실행된다.
- **이식성(CO-RE)**: BTF를 이용해 커널 버전마다 구조체 레이아웃이 달라도 런타임에 오프셋을 조정한다.

Falco의 modern eBPF는 kprobe/tracepoint를 후킹 포인트로 쓴다:
- `sys_enter_execve`: 프로세스 실행 직전
- `sys_exit_execve`: 실행 직후 (성공/실패 여부 포함)
- `sys_enter_openat`, `sys_exit_openat`: 파일 열기
- `sys_enter_connect`, `sys_exit_connect`: TCP 연결
- ...

이벤트는 커널 ring buffer → 사용자 공간 ring buffer → libscap으로 흐른다.

---

## 이벤트 소스

Falco가 보는 이벤트는 syscall만이 아니다.

| 소스 | 설명 | 플러그인 |
|---|---|---|
| `syscall` | 기본. kmod/eBPF로 수집 | 내장 |
| `k8saudit` | K8s API server audit log | k8saudit 플러그인 |
| `cloudtrail` | AWS CloudTrail 이벤트 | cloudtrail 플러그인 |
| `okta` | Okta 감사 이벤트 | okta 플러그인 |
| `github` | GitHub webhook 이벤트 | github 플러그인 |

플러그인은 Go로 작성된 별도 바이너리. Falco가 동적으로 로드한다.

---

## 룰 구조: 전체 문법

Falco 룰 파일은 YAML. 4가지 최상위 엔티티가 있다.

### 1. `rule`

```yaml
- rule: Unexpected Outbound Connection
  desc: |
    프로세스가 예상치 못한 외부 IP에 연결을 시도했다.
  condition: >
    outbound and not proc.name in (allowed_binaries) and not fd.sip.name in (trusted_domains)
  output: >
    Unexpected connection (proc=%proc.name pid=%proc.pid user=%user.name 
    ip=%fd.rip port=%fd.rport container=%container.name)
  priority: WARNING
  tags: [network, mitre_command_and_control]
  enabled: true
  warn_evttypes: false   # condition이 특정 이벤트 타입에 묶이지 않을 때 경고 억제
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `rule` | ✅ | 룰 이름 (유니크해야 함) |
| `desc` | ✅ | 설명 |
| `condition` | ✅ | 이벤트 필터 표현식 |
| `output` | ✅ | 경보 메시지 템플릿 |
| `priority` | ✅ | EMERGENCY, ALERT, CRITICAL, ERROR, WARNING, NOTICE, INFORMATIONAL, DEBUG |
| `tags` | - | 분류 태그 |
| `enabled` | - | false면 비활성 (기본 true) |
| `exceptions` | - | 예외 조건 목록 |

### 2. `macro`

반복 사용하는 조건 조각을 이름에 묶는다. 룰의 `condition`에서 참조.

```yaml
- macro: outbound
  condition: (evt.type = connect and evt.dir = <)

- macro: container
  condition: (container.id != host)

- macro: spawned_process
  condition: (evt.type = execve and evt.dir = <)
```

매크로 안에서 다른 매크로를 참조할 수 있다:

```yaml
- macro: container_started
  condition: (spawned_process and container)
```

### 3. `list`

값들의 목록. 조건에서 `in` 연산자와 함께 쓴다.

```yaml
- list: allowed_binaries
  items: [curl, wget, git, python3, node]

- list: sensitive_files
  items:
    - /etc/shadow
    - /etc/passwd
    - /root/.ssh/authorized_keys
    - /etc/kubernetes/admin.conf
```

### 4. `exception`

룰 내 예외를 구조적으로 정의. `exceptions` 키로 룰에 붙인다.

```yaml
- rule: Write Below etc
  desc: 프로세스가 /etc 아래에 파일을 씀
  condition: >
    open_write and fd.name startswith /etc
  exceptions:
    - name: known_etc_writers
      fields: [proc.name, fd.name]
      comps: [in, startswith]
      values:
        - [dpkg, /etc/apt]
        - [puppet, /etc/puppet]
  output: Write below /etc (proc=%proc.name file=%fd.name)
  priority: ERROR
```

---

## 조건 표현식 (condition)

condition은 boolean 표현식이다. 연산자:

```
and, or, not
=, !=, <, <=, >, >=
in, not in          # 목록 포함 여부
contains            # 문자열 포함
startswith          # 접두사
endswith            # 접미사
glob                # 글로브 패턴 (* ? [] 지원)
pmatch              # prefix match
regex               # PCRE 정규식
exists              # 필드가 존재하는지 (null 체크)
```

예시들:

```yaml
# 특정 syscall 타입 필터
condition: evt.type = execve

# 방향 필터 (> = 호출 진입, < = 호출 반환)
condition: evt.type = connect and evt.dir = <

# 리스트 포함
condition: proc.name in (bash, sh, zsh, dash)

# not in
condition: not proc.name in (known_processes)

# 문자열 매칭
condition: fd.name startswith /etc/
condition: fd.name contains shadow
condition: proc.cmdline contains "wget http"

# 정규식
condition: proc.cmdline regex "base64\\s+-d"

# glob
condition: fd.name glob "/tmp/*.sh"

# 복합 조건
condition: >
  spawned_process and 
  container and 
  proc.name in (python, python3) and
  proc.cmdline contains "import socket"
```

---

## 필드 레퍼런스

Falco가 제공하는 필드는 카테고리별로 나뉜다.

### evt.* — 이벤트 자체

| 필드 | 타입 | 설명 |
|---|---|---|
| `evt.type` | string | syscall 이름 (execve, open, connect, ...) |
| `evt.dir` | char | `>` = 진입(enter), `<` = 반환(exit) |
| `evt.time` | uint64 | 나노초 타임스탬프 |
| `evt.cpu` | uint16 | 실행된 CPU 번호 |
| `evt.args` | string | syscall 인자들 전체 텍스트 |
| `evt.res` | int64 | 반환값 (성공=양수, 실패=음수 errno) |
| `evt.failed` | bool | `evt.res < 0` |
| `evt.rawres` | int64 | 원시 반환값 |

### proc.* — 프로세스

| 필드 | 타입 | 설명 |
|---|---|---|
| `proc.pid` | int64 | PID |
| `proc.tid` | int64 | 스레드 ID |
| `proc.name` | string | 프로세스 이름 (basename) |
| `proc.exepath` | string | 실행 파일 전체 경로 |
| `proc.cmdline` | string | 명령어 + 인자 전체 |
| `proc.args` | string | 인자만 |
| `proc.cwd` | string | 현재 작업 디렉터리 |
| `proc.ppid` | int64 | 부모 PID |
| `proc.pname` | string | 부모 프로세스 이름 |
| `proc.pcmdline` | string | 부모 명령어 |
| `proc.aname[n]` | string | n번째 조상 프로세스 이름 (0=부모, 1=조부모...) |
| `proc.env` | string | 환경변수 전체 |
| `proc.env[VAR]` | string | 특정 환경변수 값 |
| `proc.sid` | int64 | 세션 ID |
| `proc.tty` | uint16 | TTY 번호 (0이면 데몬) |
| `proc.is_container_healthcheck` | bool | K8s 헬스체크 프로세스인지 |

### fd.* — 파일 디스크립터

| 필드 | 타입 | 설명 |
|---|---|---|
| `fd.name` | string | 파일 경로 or 소켓 정보 |
| `fd.num` | int64 | FD 번호 |
| `fd.type` | string | file, directory, ipv4, ipv6, unix, pipe, ... |
| `fd.ip` | ipnet | 소켓 IP (로컬+원격 둘 다) |
| `fd.lip` | ipaddr | 로컬 IP |
| `fd.rip` | ipaddr | 원격 IP |
| `fd.rip.name` | string | 원격 IP의 역방향 DNS |
| `fd.lport` | uint16 | 로컬 포트 |
| `fd.rport` | uint16 | 원격 포트 |
| `fd.l4proto` | string | tcp, udp, sctp |
| `fd.sport` | string | 서버 포트 |
| `fd.cport` | string | 클라이언트 포트 |
| `fd.sip` | ipaddr | 서버 IP |
| `fd.cip` | ipaddr | 클라이언트 IP |

### user.* — 사용자

| 필드 | 타입 | 설명 |
|---|---|---|
| `user.uid` | uint32 | UID |
| `user.name` | string | 사용자 이름 |
| `user.gid` | uint32 | GID |
| `user.group` | string | 그룹 이름 |
| `user.loginuid` | int32 | 로그인 UID (아무도 없으면 -1) |
| `user.loginname` | string | 로그인 이름 |

### container.* — 컨테이너

| 필드 | 타입 | 설명 |
|---|---|---|
| `container.id` | string | 컨테이너 ID (12자) |
| `container.full_id` | string | 전체 ID (64자) |
| `container.name` | string | 컨테이너 이름 |
| `container.image` | string | 이미지 이름:태그 |
| `container.image.id` | string | 이미지 ID |
| `container.image.repository` | string | 이미지 레포 |
| `container.image.tag` | string | 이미지 태그 |
| `container.privileged` | bool | privileged 모드인지 |
| `container.mounts` | string | 마운트 정보 |
| `container.label[LABEL]` | string | 특정 레이블 값 |

### k8s.* — 쿠버네티스

| 필드 | 타입 | 설명 |
|---|---|---|
| `k8s.pod.name` | string | Pod 이름 |
| `k8s.pod.id` | string | Pod UUID |
| `k8s.pod.label[LABEL]` | string | Pod 레이블 값 |
| `k8s.pod.ip` | ipaddr | Pod IP |
| `k8s.ns.name` | string | 네임스페이스 |
| `k8s.deployment.name` | string | Deployment 이름 |
| `k8s.daemonset.name` | string | DaemonSet 이름 |
| `k8s.node.name` | string | 노드 이름 |

---

## 실전 룰 예시

### 예시 1: 셸 생성 탐지

```yaml
# 매크로
- macro: spawned_process
  condition: (evt.type = execve and evt.dir = <)

- macro: shell_procs
  condition: (proc.name in (bash, sh, zsh, dash, fish, ksh))

# 컨테이너 안에서 인터랙티브 셸이 실행될 때
- rule: Terminal Shell in Container
  desc: 컨테이너 안에서 대화형 셸이 실행됨 (exec으로 접속했을 가능성)
  condition: >
    spawned_process and container and shell_procs and
    proc.tty != 0 and container.id != host
  output: >
    Shell spawned in container (user=%user.name container=%container.name
    pod=%k8s.pod.name ns=%k8s.ns.name shell=%proc.name 
    parent=%proc.pname cmdline=%proc.cmdline)
  priority: NOTICE
  tags: [container, shell, mitre_execution]
```

### 예시 2: 민감 파일 읽기

```yaml
- list: sensitive_file_names
  items:
    - /etc/shadow
    - /etc/sudoers
    - /root/.ssh/id_rsa
    - /root/.ssh/authorized_keys
    - /etc/kubernetes/admin.conf

- macro: open_read
  condition: >
    (evt.type in (open, openat, openat2) and evt.dir = < and
     fd.typechar = f and (evt.arg.flags contains O_RDONLY or
                          not evt.arg.flags contains O_WRONLY))

- rule: Read Sensitive File After Startup
  desc: 민감한 파일을 비루트 프로세스가 읽으려 함
  condition: >
    open_read and
    fd.name in (sensitive_file_names) and
    not proc.name in (sshd, passwd, sudo, su) and
    not user.uid = 0
  output: >
    Sensitive file read (user=%user.name proc=%proc.name 
    file=%fd.name container=%container.name)
  priority: WARNING
  tags: [filesystem, credential_access, mitre_credential_access]
```

### 예시 3: 외부 연결

```yaml
- macro: outbound
  condition: >
    (evt.type = connect and evt.dir = < and
     fd.typechar = 4 and          # IPv4
     not fd.rip in (127.0.0.1, ::1) and
     not fd.rip startswith "10." and
     not fd.rip startswith "172.16." and
     not fd.rip startswith "192.168.")

- list: expected_outbound_processes
  items: [curl, wget, git, apt, apt-get, yum, dnf, pip, npm]

- rule: Unexpected Outbound Connection from Container
  desc: 컨테이너 안 프로세스가 예상치 않은 외부 IP에 접속
  condition: >
    outbound and container and
    not proc.name in (expected_outbound_processes)
  output: >
    Outbound connection from container (proc=%proc.name pid=%proc.pid
    ip=%fd.rip port=%fd.rport container=%container.name image=%container.image)
  priority: NOTICE
  tags: [network, container, mitre_command_and_control]
```

### 예시 4: 패키지 관리자 실행 (컨테이너 안에서)

```yaml
- macro: package_mgmt_binaries
  condition: >
    proc.name in (apt, apt-get, aptitude, dpkg, yum, dnf, rpm,
                  pip, pip3, npm, yarn, gem, cargo)

- rule: Launch Package Management Process in Container
  desc: |
    컨테이너 런타임 중에 패키지 설치. 이미지 빌드 시점이 아니라
    실행 중 패키지를 추가하는 것은 의심스럽다.
  condition: >
    spawned_process and package_mgmt_binaries and container
  output: >
    Package management launched (user=%user.name proc=%proc.name 
    cmdline=%proc.cmdline container=%container.name image=%container.image)
  priority: ERROR
  tags: [container, process, mitre_persistence]
```

---

## 룰 오버라이드 (Override)

기존 룰을 수정할 때 전체를 재작성하지 않고 `override` 키를 쓴다.

```yaml
# 기본 룰의 조건을 확장
- rule: Terminal Shell in Container
  condition: append and not proc.name = my_debug_tool
  override:
    condition: append

# 기본 룰을 비활성화
- rule: Terminal Shell in Container
  enabled: false
  override:
    enabled: replace
```

`append`는 기존 조건 뒤에 `and <추가 조건>`을 붙인다. 이 방식으로 기본 룰셋을 건드리지 않고 `custom_rules.yaml`에 오버라이드만 쌓는 패턴을 많이 쓴다.

---

## falco.yaml 주요 설정

```yaml
# 드라이버
engine:
  kind: modern_ebpf    # kmod | ebpf | modern_ebpf

# 룰 파일 (여러 개 가능, 순서대로 로드)
rules_files:
  - /etc/falco/falco_rules.yaml       # 공식 룰셋 (읽기 전용)
  - /etc/falco/falco_rules.local.yaml # 커스텀/오버라이드

# 출력 포맷
json_output: false          # true면 JSON으로 출력
json_include_output_property: true
time_format_iso_8601: false

# 최소 우선순위 (이것보다 낮은 룰은 무시)
priority: debug   # debug, info, notice, warning, error, critical, alert, emergency

# 출력 채널
stdout_output:
  enabled: true

syslog_output:
  enabled: false

file_output:
  enabled: false
  filename: /var/log/falco.log

http_output:
  enabled: false
  url: http://localhost:2801    # falcosidekick이 여기를 listen

program_output:
  enabled: false
  keep_alive: false
  program: mail -s "Falco Alert" security@example.com
```

---

## 설치 방법

### Docker (가장 빠른 테스트)

```bash
# modern eBPF (호스트 커널 5.8+ 필요)
docker run --rm -i \
  --privileged \
  -v /var/run/docker.sock:/host/var/run/docker.sock \
  -v /proc:/host/proc:ro \
  -v /boot:/host/boot:ro \
  -v /lib/modules:/host/lib/modules:ro \
  falcosecurity/falco:latest \
  falco --modern-bpf
```

### Helm (K8s)

```bash
helm repo add falcosecurity https://falcosecurity.github.io/charts
helm repo update

helm install falco falcosecurity/falco \
  --namespace falco \
  --create-namespace \
  --set driver.kind=modern_ebpf \
  --set falco.json_output=true
```

### 바이너리

```bash
# Ubuntu/Debian
curl -fsSL https://falco.org/repo/falcosecurity-packages.asc | \
  sudo gpg --dearmor -o /usr/share/keyrings/falco-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/falco-archive-keyring.gpg] \
  https://download.falco.org/packages/deb stable main" | \
  sudo tee /etc/apt/sources.list.d/falcosecurity.list

sudo apt update && sudo apt install -y falco
sudo systemctl start falco
```

---

## 출력 예시

경보 하나가 나오면 이렇게 생겼다 (JSON 모드):

```json
{
  "time": "2026-06-15T10:23:45.123456789Z",
  "rule": "Terminal Shell in Container",
  "priority": "Notice",
  "source": "syscall",
  "tags": ["container", "shell", "mitre_execution"],
  "output": "Shell spawned in container (user=root container=backend pod=backend-7d4f8-xk9p2 ns=production shell=bash parent=runc cmdline=bash)",
  "output_fields": {
    "user.name": "root",
    "container.name": "backend",
    "k8s.pod.name": "backend-7d4f8-xk9p2",
    "k8s.ns.name": "production",
    "proc.name": "bash",
    "proc.pname": "runc",
    "proc.cmdline": "bash"
  },
  "hostname": "node-01"
}
```

이 JSON을 falcosidekick이 받아서 Slack, PagerDuty, Loki, Elasticsearch 등으로 팬아웃한다.
