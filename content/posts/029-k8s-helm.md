---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "029. Helm — Kubernetes 패키지 매니저"
date: 2026-06-12
tags: [kubernetes, k8s, helm, chart, release, values, template, repository, kustomize]
summary: "하나의 서비스를 k8s에 배포하려면 Deployment, Service, ConfigMap, Ingress, ServiceAccount 등 여러 YAML 파일이 필요하다. Helm은 이 파일들을 하나의 패키지(Chart)로 묶고, 환경마다 다른 값을 변수로 분리해 관리하는 k8s 패키지 매니저다. Chart 구조, values 오버라이드, Release 관리, 그리고 Kustomize와의 차이를 설명한다."
slug: "029-k8s-helm"
categories: ["쿠버네티스"]
---

서비스 하나를 k8s에 배포하려면 Deployment, Service, Ingress, ConfigMap, ServiceAccount, HPA... 여러 YAML 파일이 필요하다. 개발 환경과 프로덕션 환경은 이미지 태그, replica 수, resource 크기, 도메인이 다르다. 환경마다 복사해서 수정하면 파일들이 금방 제각각이 된다.

Helm은 이 문제를 푸는 k8s 패키지 매니저다. 관련 YAML들을 **Chart**라는 패키지로 묶고, 환경마다 다른 값은 **values**로 분리해 템플릿으로 관리한다. `helm install`, `helm upgrade`, `helm rollback` 같은 명령으로 배포 라이프사이클을 관리하고, 수천 개의 오픈소스 Chart를 받아 쓸 수 있다.

## Chart 구조

```
my-app/
├── Chart.yaml          # Chart 메타데이터 (이름, 버전, 설명)
├── values.yaml         # 기본 설정값
├── templates/          # k8s YAML 템플릿들
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   ├── configmap.yaml
│   ├── _helpers.tpl    # 재사용 템플릿 조각
│   └── NOTES.txt       # 설치 후 출력할 안내 메시지
└── charts/             # 의존 Chart (서브차트)
```

### Chart.yaml

```yaml
apiVersion: v2
name: my-app
description: My application
type: application
version: 1.2.0          # Chart 버전 (패키지 버전)
appVersion: "2.5.1"     # 앱 버전 (이미지 태그 등)
dependencies:
- name: postgresql
  version: "12.x.x"
  repository: "https://charts.bitnami.com/bitnami"
  condition: postgresql.enabled    # values에서 활성화 여부 제어
```

### values.yaml — 기본값

```yaml
replicaCount: 2

image:
  repository: my-app
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80

ingress:
  enabled: false
  host: ""

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

postgresql:
  enabled: true
  auth:
    database: myapp
```

### 템플릿

템플릿은 Go 템플릿 문법으로 values를 참조한다.

```yaml
# templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "my-app.fullname" . }}    # _helpers.tpl의 함수
  labels:
    {{- include "my-app.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  template:
    spec:
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
```

```yaml
# templates/ingress.yaml
{{- if .Values.ingress.enabled }}    # enabled가 true일 때만 생성
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "my-app.fullname" . }}
spec:
  rules:
  - host: {{ .Values.ingress.host }}
    ...
{{- end }}
```

## 설치와 업그레이드

```bash
# Chart 설치 (Release 생성)
helm install my-release ./my-app \
  --namespace production \
  --create-namespace \
  --values production-values.yaml

# 설치된 Release 목록
helm list -n production

# 업그레이드 (values 변경 또는 Chart 버전 업)
helm upgrade my-release ./my-app \
  --namespace production \
  --values production-values.yaml \
  --set image.tag=2.6.0            # 커맨드라인에서 개별 값 오버라이드

# 롤백
helm rollback my-release 1         # 리비전 1로 롤백
helm history my-release            # 릴리즈 히스토리

# 삭제
helm uninstall my-release -n production
```

Helm은 Release 히스토리를 k8s Secret에 저장한다. `helm rollback`은 이전 상태의 YAML을 다시 적용한다.

## values 오버라이드 — 환경별 설정

기본값을 `values.yaml`에 두고, 환경별 차이를 별도 파일로 관리한다.

```yaml
# values-production.yaml
replicaCount: 5

image:
  tag: "2.5.1"           # 고정 버전

ingress:
  enabled: true
  host: api.example.com

resources:
  requests:
    cpu: 500m
    memory: 512Mi
  limits:
    cpu: 2000m
    memory: 2Gi
```

```bash
# production 환경 배포
helm upgrade my-release ./my-app \
  --values values.yaml \
  --values values-production.yaml    # 뒤 파일이 앞 파일을 덮어씀
```

CI/CD에서는 보통 `--set image.tag=$(git rev-parse --short HEAD)` 같은 방식으로 이미지 태그만 동적으로 주입한다.

## 공개 Chart 저장소 활용

Prometheus, Grafana, nginx-ingress, cert-manager 같은 인프라 컴포넌트를 처음부터 직접 YAML로 작성할 필요가 없다. 검증된 Chart가 이미 있다.

```bash
# 저장소 추가
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Chart 검색
helm search repo prometheus

# Chart의 기본 values 확인
helm show values prometheus-community/kube-prometheus-stack > default-values.yaml

# 설치
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --values my-prometheus-values.yaml
```

## Kustomize — Helm의 대안

Helm과 자주 비교되는 Kustomize는 다른 철학으로 접근한다. 템플릿 대신 **기존 YAML을 패치(patch)** 한다.

```
base/                   # 공통 기본 YAML
├── deployment.yaml
├── service.yaml
└── kustomization.yaml

overlays/
├── development/        # dev 환경 패치
│   ├── kustomization.yaml
│   └── replica-patch.yaml
└── production/         # prod 환경 패치
    ├── kustomization.yaml
    └── replica-patch.yaml
```

```yaml
# overlays/production/kustomization.yaml
resources:
- ../../base
patches:
- path: replica-patch.yaml
images:
- name: my-app
  newTag: "2.5.1"
```

| | Helm | Kustomize |
|---|---|---|
| 방식 | 템플릿 + values | 기본 YAML + 패치 |
| 학습 비용 | 높음 (Go 템플릿) | 낮음 (순수 YAML) |
| 패키지 재사용 | 강력 (Chart 저장소) | 약함 |
| 히스토리/롤백 | 내장 | 없음 (git으로 관리) |
| 외부 의존성 없음 | Helm CLI 필요 | kubectl에 내장 |

실무에서는 오픈소스 인프라(Prometheus, nginx-ingress 등)는 Helm Chart로 설치하고, 자체 서비스는 Helm 또는 Kustomize 중 팀 취향에 맞는 것을 쓰는 경우가 많다. Argo CD 같은 GitOps 도구는 둘 다 지원한다.

## 트레이드오프

Helm의 Go 템플릿 문법은 YAML 안에서 프로그래밍 로직이 섞여 읽기 어렵고, 복잡한 조건이 들어가면 유지보수가 어려워진다. 템플릿 오류 메시지도 불친절하다.

`helm upgrade`는 기본적으로 애플리케이션 배포 성공 여부를 기다리지 않는다. `--wait` 플래그를 붙이면 파드가 Ready 될 때까지 기다리고 실패하면 롤백할 수 있다. CI/CD 파이프라인에서는 `--wait --timeout 5m`을 붙이는 것이 안전하다.
