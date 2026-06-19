---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-02. Falco 심화 — K8s 통합, 플러그인, falcosidekick, 커스텀 룰 전략"
date: 2026-06-15
tags: [falco, kubernetes, ebpf, falcosidekick, plugins, k8s-audit, soar, rules-tuning]
summary: "Falco K8s Audit 통합, falcosidekick 출력 팬아웃, 플러그인 시스템, 룰 튜닝 전략, 성능 최적화, SOAR 연동 패턴."
slug: "falco-advanced"
categories: ["보안"]
---

## Falco와 쿠버네티스

Falco는 두 방식으로 K8s를 다룬다.

### 1. syscall + K8s 메타데이터 enrichment

기본 동작. eBPF/kmod로 syscall을 잡고, 그 syscall을 한 PID가 어떤 Pod/Namespace/Deployment에 속하는지를 K8s API로 조회해서 붙인다. 이미 기초 문서에서 본 `k8s.*` 필드가 이 방식.

```
syscall 이벤트
  └─ pid=1234
      └─ libsinsp가 /proc/1234/cgroup 파싱 → container ID
          └─ container runtime socket에서 container → pod 매핑
              └─ K8s API에서 pod → namespace, labels, deployment 조회
                  └─ k8s.pod.name, k8s.ns.name, k8s.deployment.name 필드 생성
```

이 방식은 **workload 내부** 이벤트(파일 접근, 프로세스 실행, 네트워크 연결)를 잡는다.

### 2. K8s Audit Log (k8saudit 플러그인)

**K8s 컨트롤 플레인** 이벤트를 잡는다. API server가 모든 요청을 감사 로그로 남기고, k8saudit 플러그인이 이를 이벤트 소스로 받아 룰을 적용한다.

이 방식으로 탐지할 수 있는 것들:
- 누가 Pod 안에 `kubectl exec`를 했는지
- 새 ClusterRoleBinding을 만들어서 권한을 높였는지
- ServiceAccount 토큰을 노출하는 ConfigMap을 만들었는지
- Namespace를 변경하거나 삭제했는지

```yaml
# falco.yaml에 k8saudit 플러그인 설정
load_plugins:
  - name: k8saudit
    library_path: /usr/share/falco/plugins/libk8saudit.so
    init_config:
      sslCertificate: /etc/falco/certs/server.crt
    open_params: "http://0.0.0.0:9765/k8s-audit"

plugins:
  - name: k8saudit
    library_path: /usr/share/falco/plugins/libk8saudit.so
```

K8s API server 쪽 설정 (`audit-policy.yaml`):

```yaml
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse   # 요청+응답 모두 기록
    resources:
    - group: ""
      resources: ["secrets", "configmaps", "serviceaccounts"]
  - level: Request
    resources:
    - group: ""
      resources: ["pods", "pods/exec", "pods/log"]
  - level: Metadata           # 나머지는 메타데이터만
    omitStages:
    - RequestReceived
```

k8saudit 전용 룰 예시:

```yaml
- rule: K8s Cluster-Admin Binding
  desc: 누군가 cluster-admin 권한을 바인딩함 (위험한 과도한 권한)
  condition: >
    ka.target.resource = "clusterrolebindings" and
    ka.verb in (create, update, patch) and
    ka.req.binding.role = "cluster-admin"
  output: >
    ClusterAdmin binding created (user=%ka.user.name binding=%ka.target.name
    role=%ka.req.binding.role subject=%ka.req.binding.subjects)
  priority: WARNING
  source: k8saudit
  tags: [k8s, rbac, privilege_escalation]

- rule: Create Privileged Pod
  desc: privileged 컨테이너가 포함된 Pod 생성
  condition: >
    ka.target.resource = "pods" and
    ka.verb = create and
    ka.req.pod.containers.privileged = true
  output: >
    Privileged pod created (user=%ka.user.name pod=%ka.target.name
    ns=%ka.target.namespace)
  priority: WARNING
  source: k8saudit
  tags: [k8s, container, privilege_escalation]
```

---

## k8saudit 필드 레퍼런스

k8saudit 소스에서만 쓸 수 있는 필드들.

| 필드 | 설명 |
|---|---|
| `ka.user.name` | 요청한 사용자/ServiceAccount |
| `ka.user.groups` | 사용자 그룹 목록 |
| `ka.verb` | get, list, create, update, patch, delete, ... |
| `ka.target.resource` | pods, secrets, configmaps, ... |
| `ka.target.name` | 대상 리소스 이름 |
| `ka.target.namespace` | 대상 네임스페이스 |
| `ka.uri` | 요청 URI |
| `ka.response.code` | HTTP 응답 코드 |
| `ka.req.pod.containers.image` | Pod 컨테이너 이미지 |
| `ka.req.pod.containers.privileged` | privileged 여부 |
| `ka.req.pod.volumes.hostpath` | hostPath 마운트 경로 |
| `ka.req.binding.role` | RoleBinding의 역할 |
| `ka.req.binding.subjects` | 바인딩 대상 (User/Group/ServiceAccount) |

---

## Helm 배포 상세

운영 환경에서 쓰는 values.yaml 패턴:

```yaml
# values.yaml
driver:
  kind: modern_ebpf

falco:
  json_output: true
  priority: notice   # warning 이상만 처리하면 performance 향상
  
  # 룰 오버라이드 inline으로 정의
  rules:
    - rule: Terminal Shell in Container
      condition: append and not k8s.ns.name = debug
      override:
        condition: append

# 커스텀 룰 파일 ConfigMap으로 마운트
customRules:
  my-rules.yaml: |-
    - rule: My Custom Detection
      desc: 커스텀 탐지 룰
      condition: >
        spawned_process and proc.name = nc and container
      output: netcat spawned in container (container=%container.name)
      priority: WARNING
      tags: [custom]

# falcosidekick 연동
falcosidekick:
  enabled: true
  config:
    slack:
      webhookurl: "https://hooks.slack.com/..."
      minimumpriority: error
    loki:
      hostport: "http://loki:3100"
      minimumpriority: notice
```

---

## falcosidekick

Falco 자체는 stdout/file/syslog/http/program 정도만 지원한다. falcosidekick은 Falco의 http_output을 받아서 50개 이상의 출력 대상으로 팬아웃하는 사이드카.

```
Falco → [HTTP POST json] → falcosidekick → Slack
                                          → PagerDuty
                                          → Elasticsearch
                                          → Loki
                                          → Datadog
                                          → AWS Lambda
                                          → Google Cloud Run
                                          → Webhook (커스텀)
```

설정:

```yaml
# falcosidekick config.yaml
listenaddress: "0.0.0.0"
listenport: 2801
debug: false

slack:
  webhookurl: "https://hooks.slack.com/services/..."
  channel: "#security-alerts"
  minimumpriority: "error"
  messageformat: "Alert: [%rule%] on %hostname% at %time%"

loki:
  hostport: "http://loki:3100"
  minimumpriority: "notice"
  extralabels: "environment=prod,team=security"

elasticsearch:
  hostport: "http://elasticsearch:9200"
  index: "falco"
  minimumpriority: "notice"

webhook:
  address: "http://my-soar/webhook"
  minimumpriority: "warning"
  checkcert: true
```

`minimumpriority`로 출력 대상별로 다른 임계값을 설정할 수 있다. 예: Slack에는 error 이상만, Loki에는 notice 이상 모두.

### falcosidekick-ui

falcosidekick과 함께 배포하는 대시보드. 경보를 시각화하고 Rule별/우선순위별/호스트별로 필터링할 수 있다.

```bash
# docker-compose로 전체 스택 띄우기
docker compose -f docker/docker-compose/docker-compose.yaml up -d
# falco + falcosidekick + falcosidekick-ui + redis 모두 올라옴
```

---

## 플러그인 시스템

Falco 0.32+부터 플러그인으로 이벤트 소스와 필드 extractor를 추가할 수 있다.

### 플러그인 타입

1. **Event Source 플러그인**: 새 이벤트 소스를 추가 (k8saudit, cloudtrail)
2. **Field Extractor 플러그인**: 기존 이벤트에서 새 필드를 추출 (json 플러그인)

### 주요 공식 플러그인

| 플러그인 | 설명 |
|---|---|
| `k8saudit` | K8s API server 감사 로그 |
| `cloudtrail` | AWS CloudTrail 이벤트 |
| `okta` | Okta 감사 이벤트 (SSO/MFA 관련) |
| `github` | GitHub webhook 이벤트 |
| `json` | 임의 JSON 필드 접근 (`jevt.value[/path]`) |
| `dummy` | 테스트용 |

### 플러그인 설치

```bash
# falcoctl로 플러그인 설치
falcoctl artifact install k8saudit:latest
falcoctl artifact install cloudtrail:latest
```

### cloudtrail 플러그인 예시

```yaml
# cloudtrail 이벤트 소스에서 동작하는 룰
- rule: Console Login Without MFA
  desc: AWS 콘솔에 MFA 없이 로그인
  condition: >
    ct.name = "ConsoleLogin" and
    ct.req.console_login.mfa_used = false
  output: >
    Console login without MFA (user=%ct.user.name ip=%ct.srcip)
  priority: CRITICAL
  source: aws_cloudtrail
  tags: [cloud, aws, authentication]
```

---

## 룰 튜닝 전략

실제 운영에서 가장 힘든 부분이 false positive 줄이기다.

### 접근 방법

1. **드라이 런**: `--dry-run` 플래그로 룰이 어떤 이벤트에 매칭되는지 먼저 확인
2. **카운팅**: 처음에는 WARNING 이상만 활성화하고, NOTICE→DEBUG 순서로 확장
3. **네임스페이스 제외**: 신뢰할 수 있는 네임스페이스(kube-system, monitoring 등) 제외
4. **이미지 기반 화이트리스트**: 알려진 이미지에 대해 예외 처리

```yaml
# kube-system 네임스페이스 제외 패턴
- macro: kube_system_namespace
  condition: (k8s.ns.name = kube-system)

- rule: Unexpected Network Connection
  condition: >
    outbound and container and
    not kube_system_namespace and     # 이 줄 추가
    not proc.name in (known_processes)
  ...
```

### 예외 처리 구조화

```yaml
# 구조화된 exception 사용
- rule: Write Below Binary Dir
  desc: /usr/bin, /bin 등 바이너리 디렉터리 아래에 파일 씀
  condition: >
    open_write and bin_dir
  exceptions:
    - name: package_manager
      fields: proc.name
      comps: in
      values: [[dpkg], [rpm], [yum], [apt-get]]
    - name: deployment_scripts
      fields: [proc.name, fd.name]
      comps: [=, startswith]
      values:
        - [deploy.sh, /usr/local/bin/]
  output: Write below binary dir (proc=%proc.name file=%fd.name)
  priority: ERROR
```

### 룰 성능 측정

```bash
# 어떤 룰이 얼마나 자주 발화하는지 확인
falco --stats-interval 1000 2>&1 | grep "STATS"

# JSON 출력에서 집계
falco --json-output | jq '.rule' | sort | uniq -c | sort -rn | head -20
```

자주 발화하는 룰을 찾아서 조건을 좁히거나, 해당 룰의 `enabled: false`로 임시 비활성화하고 원인을 파악한다.

---

## 성능 고려사항

### CPU 영향

modern eBPF는 kmod보다 CPU 오버헤드가 약간 높다(verifier 검증 때문). 하지만 대부분의 환경에서 5% 미만.

CPU 사용량을 줄이는 방법:
- `priority: warning` 이상만 처리 → 낮은 우선순위 룰 비활성
- 특정 이벤트 타입만 보는 룰은 condition을 `evt.type` 체크로 시작 → 빠른 early exit
- 고성능 환경에서는 `outputs_queue.capacity`를 늘려서 드랍 방지

```yaml
outputs_queue:
  capacity: 0  # 0 = 무제한 (메모리 허용하는 한)
```

### 메모리 영향

libsinsp는 프로세스/FD/컨테이너 상태를 메모리에 유지한다. Pod가 많은 환경에서는 수백 MB도 쓸 수 있다.

`syscall_buf_size_preset`으로 ring buffer 크기 조정:

```yaml
engine:
  kind: modern_ebpf
  modern_ebpf:
    cpus_for_each_syscall_buffer: 2  # 몇 개 CPU당 버퍼 하나
```

### 이벤트 드랍

고트래픽 환경에서 이벤트를 처리하지 못하면 드랍이 발생한다. 로그에 `Syscall event drop` 메시지가 나오면 버퍼 크기 늘리거나, 룰 조건을 좁혀서 처리량을 줄여야 한다.

---

## SOAR 연동 패턴

Falco → SOAR 자동 대응 파이프라인.

### 패턴 1: falcosidekick → Webhook → SOAR

```
Falco → falcosidekick → HTTP webhook → Shuffle/TheHive → 플레이북
```

Shuffle (오픈소스 SOAR) workflow 예시:
1. Trigger: Webhook (falcosidekick이 보낸 JSON)
2. Action: JSON 파싱 → `container.name`, `k8s.pod.name` 추출
3. Action: kubectl exec로 컨테이너 격리
4. Action: Slack 알림
5. Action: TheHive에 케이스 생성

### 패턴 2: falcosidekick → Loki → Grafana Alert → SOAR

```
Falco → falcosidekick → Loki → Grafana (LogQL 알림 룰) → Webhook → 플레이북
```

Loki에 로그를 저장하면 Grafana에서 시각화와 알림을 동시에. 임계값 기반 (예: "같은 Pod에서 WARNING이 10분에 5번 이상")으로 에스컬레이션.

### 패턴 3: Falco gRPC → 커스텀 에이전트

Falco는 gRPC 인터페이스(`falco.outputs.v1`)를 노출한다. Go/Python 클라이언트로 실시간으로 경보를 구독해서 직접 처리할 수 있다.

```python
import grpc
from falco.outputs.v1 import outputs_pb2, outputs_pb2_grpc

channel = grpc.secure_channel("localhost:5060", creds)
stub = outputs_pb2_grpc.ServiceStub(channel)

for response in stub.Get(outputs_pb2.Request()):
    alert = response
    # LLM에 넘겨서 판단 → 자동 대응
    handle_alert(alert.rule, alert.priority, alert.output_fields)
```

이 방식이 보안 에이전트와 직접 연결하는 가장 깔끔한 방법. 에이전트가 Falco를 MCP 도구로 래핑할 때도 이 gRPC 스트림을 쓰거나, http_output을 받는 미니 서버를 중간에 두는 방식을 쓴다.

---

## 룰셋 레포 vs 이 레포

이 레포(`falcosecurity/falco`)는 Falco 바이너리와 Helm chart 코드가 있다. 공식 룰셋은 별도 레포:

- **[falcosecurity/rules](https://github.com/falcosecurity/rules)**: 공식 `falco_rules.yaml`. 여기가 룰 PR을 날릴 대상.
- falcoctl로 설치하면 이 레포의 룰 아티팩트를 받아온다.

기여 패턴:
1. `falcosecurity/rules` 에서 새 룰 제안 이슈 등록
2. `rules/falco_rules.yaml`에 룰 추가 PR
3. 룰 테스트: `falco-tester` 프레임워크로 룰 동작 검증

---

## 실전 배포 체크리스트

```
□ 드라이버 선택: modern_ebpf (커널 5.8+) 또는 kmod
□ Helm values.yaml에 커스텀 룰 ConfigMap 마운트
□ json_output: true 설정
□ falcosidekick 함께 배포 (DaemonSet)
□ falcosidekick → Slack/PagerDuty 연동 (최소 error 이상)
□ falcosidekick → Loki 연동 (notice 이상 전체 보관)
□ Grafana 대시보드 연동
□ K8s Audit 정책 설정 + k8saudit 플러그인 활성화
□ RBAC: Falco ServiceAccount에 필요한 최소 권한만
□ priority 임계값 조정: 처음엔 warning, 안정화 후 notice
□ 주요 FP 룰 오버라이드 파일 작성 (custom_rules.yaml)
□ 성능 모니터링: 이벤트 드랍 여부 주기적 확인
```
