---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-04. Sigma 심화 — pySigma, 백엔드, 파이프라인, 룰 작성 전략"
date: 2026-06-15
tags: [sigma, pysigma, backend, pipeline, detection-engineering, siem, threat-hunting]
summary: "pySigma 내부 구조(Backend/Pipeline/Transformation), 커스텀 백엔드 작성, 룰 품질 기준, 위협 헌팅과 기본 탐지의 차이, MITRE ATT&CK 커버리지 매핑 실전."
slug: "sigma-advanced"
---

## pySigma 내부 구조

pySigma는 Sigma CLI의 기반 라이브러리다. 3개 레이어로 구성된다.

```
Sigma 룰 (YAML)
    │
    ▼
[Parser]                         ← SigmaRule, SigmaCollection 파싱
    │
    ▼
[Pipeline]                       ← 필드명 변환, 값 변환, 조건 수정
    │ FieldMappingTransformation
    │ ValueTransformation
    │ DetectionItemTransformation
    │ ...
    ▼
[Backend]                        ← 대상 쿼리 언어로 직렬화
    │
    ▼
SIEM 쿼리 (SPL / DSL / KQL / AQL / ...)
```

### Parser 단계

YAML을 파싱해서 내부 객체 모델로 변환한다:
- `SigmaRule`: 단일 룰
- `SigmaDetection`: detection 섹션
- `SigmaDetectionItem`: 하나의 selection 항목 (field + modifier + values)
- `SigmaCondition`: condition 표현식 (AST)

```python
from sigma.rule import SigmaRule
from sigma.collection import SigmaCollection

# 단일 룰 파싱
with open("my_rule.yml") as f:
    rule = SigmaRule.from_yaml(f.read())

print(rule.title)
print(rule.detection.parsed_condition)

# 컬렉션 (디렉터리 전체)
col = SigmaCollection.load_ruleset(["rules/windows/process_creation/"])
```

### Pipeline 단계

파이프라인은 변환 스탭들의 순서 목록이다. 주 역할은 **Sigma 필드 이름 → SIEM 필드 이름 변환**.

```python
from sigma.processing.pipeline import ProcessingPipeline, ProcessingItem
from sigma.processing.transformations import FieldMappingTransformation

pipeline = ProcessingPipeline(
    name="my-siem-pipeline",
    items=[
        ProcessingItem(
            identifier="process_creation_mapping",
            transformation=FieldMappingTransformation({
                "Image": "process.executable",
                "CommandLine": "process.command_line",
                "User": "user.name",
                "ParentImage": "process.parent.executable",
            }),
        )
    ]
)
```

공식 파이프라인들:
- `ecs_windows`: Elastic Common Schema (ECS) + Windows
- `sysmon`: Sysmon 이벤트 ID 기반
- `windows-splunk`: Splunk Windows 필드명
- `windows-audit`: Windows Security Audit 로그

파이프라인 체이닝:

```python
final_pipeline = ecs_windows_pipeline() | my_custom_pipeline()
```

### Backend 단계

`SigmaCollection` + `Pipeline` → 쿼리 문자열.

```python
from sigma.backends.elasticsearch import LuceneBackend
from sigma.processing.resolver import ProcessingPipelineResolver

backend = LuceneBackend(
    processing_pipeline=my_pipeline
)

# 변환
queries = backend.convert(collection)
for query in queries:
    print(query)
```

---

## 커스텀 백엔드 작성

자체 SIEM이나 로그 분석 도구를 위한 백엔드를 만드는 법.

```python
from sigma.backends.base import TextQueryBackend
from sigma.conditions import ConditionOR, ConditionAND, ConditionNOT
from sigma.processing.pipeline import ProcessingPipeline

class MyBackend(TextQueryBackend):
    """Custom SIEM 백엔드"""
    
    name = "my_siem"
    identifier = "my-siem"
    formats = {
        "default": "기본 쿼리 포맷",
        "json": "JSON 포맷",
    }
    
    # 연산자 정의
    and_token = " AND "
    or_token = " OR "
    not_token = "NOT "
    eq_token = ":"
    
    # 문자열 따옴표
    str_quote = '"'
    escape_char = "\\"
    
    # 필드 표현
    field_quote = ""  # 필드명에 따옴표 안 씀
    
    # 와일드카드
    wildcard_multi = "*"
    wildcard_single = "?"
    
    def convert_condition_and(self, cond: ConditionAND, state) -> str:
        exprs = [self.convert_condition(arg, state) for arg in cond.args]
        return f"({self.and_token.join(exprs)})"
    
    def convert_condition_or(self, cond: ConditionOR, state) -> str:
        exprs = [self.convert_condition(arg, state) for arg in cond.args]
        return f"({self.or_token.join(exprs)})"
```

---

## 파이프라인 심화: Transformation 타입들

파이프라인 변환 타입 전체:

### 필드 관련

```python
# 필드 이름 변환 (가장 많이 씀)
FieldMappingTransformation({"Image": "process.exe"})

# 필드 이름 접두사 추가
AddFieldnamePrefixTransformation("winlog.event_data.")

# 조건에 맞는 필드만 변환
ConditionalFieldMappingTransformation(
    {"CommandLine": "event_data.CommandLine"},
    rule_conditions=[LogsourceCondition(category="process_creation")]
)
```

### 값 관련

```python
# 값에 접두사/접미사 추가
PrependValueTransformation("*")  # 모든 값 앞에 와일드카드

# 정규식으로 값 변환
ReplaceStringTransformation(
    regex=r"^C:\\Windows\\",
    replacement="%SystemRoot%\\"
)
```

### 탐지 항목 관련

```python
# 특정 필드 삭제
DropDetectionItemTransformation()  # 필터 조건에 맞으면 제거

# 탐지 항목 추가
AddConditionTransformation({"index": "windows-*"})
```

### logsource 관련

```python
# logsource를 실제 인덱스/소스로 변환
AddFieldnameSuffixTransformation("_evt")

# logsource 조건으로 변환 트리거
LogsourceCondition(
    product="windows",
    category="process_creation"
)
```

---

## 파이프라인 YAML 정의

Python 코드 대신 YAML로도 파이프라인 정의 가능.

```yaml
name: my-custom-pipeline
priority: 50
transformations:
  - id: field_mapping_process
    type: field_name_mapping
    mapping:
      Image: process.executable
      CommandLine: process.command_line
      User: user.name
    rule_conditions:
      - type: logsource
        category: process_creation

  - id: add_index
    type: add_condition
    conditions:
      index: "logs-*"

  - id: drop_hash_field
    type: drop_detection_item
    field_name_conditions:
      - type: include_fields
        fields: [Hashes]
```

```bash
# CLI에서 커스텀 파이프라인 사용
sigma convert \
  --target my-siem \
  --pipeline my-pipeline.yml \
  rules/windows/
```

---

## 룰 품질 기준 (SigmaHQ 커뮤니티 기준)

PR을 내려면 알아야 할 기준들.

### 필수 조건

1. **제목**: 명확하고 행동 중심적. "Suspicious X via Y" 패턴.
2. **UUID**: `uuidgen`으로 생성한 새 UUID.
3. **status**: 테스트 안 됐으면 `experimental`, 검증됐으면 `test`.
4. **logsource 정확성**: `product`와 `category` 올바르게 설정. 잘못된 logsource는 변환이 안 됨.
5. **MITRE ATT&CK 태그**: 해당하는 기법 ID 필수.
6. **falsepositives**: 명확한 FP 케이스 기술. "None"이면 "Unknown" 권장.
7. **level**: 탐지 정확도에 맞게.

### 품질 체크 포인트

```bash
# sigma-cli로 룰 검증
sigma check my_rule.yml

# 특정 백엔드로 변환 테스트
sigma convert --target elasticsearch --pipeline ecs_windows my_rule.yml
```

### 좋은 룰 vs 나쁜 룰

**나쁜 룰:**
```yaml
# 너무 넓음 — powershell.exe가 뭔가를 실행하면 다 잡힘
detection:
  selection:
    Image|endswith: '\powershell.exe'
  condition: selection
```

**좋은 룰:**
```yaml
# 구체적 — 인코딩 + 특정 컨텍스트
detection:
  selection:
    Image|endswith: '\powershell.exe'
    CommandLine|contains|windash: ' -enc '
    CommandLine|base64offset|contains:
      - 'IEX'
      - 'Invoke-Expression'
      - 'DownloadString'
  filter_admin:
    ParentImage|startswith: 'C:\Windows\System32\mmc.exe'
  condition: selection and not filter_admin
```

**FP를 줄이는 원칙:**
- 부모 프로세스(ParentImage)로 컨텍스트 좁히기
- 특정 인자 조합 요구
- 알려진 정상 경로 필터
- 사용자 컨텍스트 고려 (SYSTEM vs 일반 사용자)

---

## 위협 헌팅 룰 vs 탐지 룰

SigmaHQ는 두 종류의 룰을 구분한다.

### 탐지 룰 (`rules/`)
- 목적: 실시간 SIEM 경보
- 특징: 정밀도(Precision) 우선. FP 낮아야 함.
- 범위: 좁은 조건, 확실한 악성 시그니처
- 예: 알려진 악성툴의 특정 named pipe 패턴

```yaml
# 탐지 룰 예: Mimikatz 특정 파이프
logsource:
  product: windows
  category: pipe_created
detection:
  selection:
    PipeName|contains:
      - '\lsadump'
      - '\cachedump'
  condition: selection
level: critical  # 높은 신뢰도 → 높은 level
```

### 위협 헌팅 룰 (`rules-threat-hunting/`)
- 목적: 사람이 분석할 후보 이벤트 추출
- 특징: 재현율(Recall) 우선. 넓게 잡고 애널리스트가 걸러냄
- 범위: 의심스럽지만 정상일 수 있는 행동
- 예: net.exe를 누군가 실행했다

```yaml
# 헌팅 룰 예: 네트워크 정찰 명령 실행
logsource:
  product: windows
  category: process_creation
detection:
  selection:
    Image|endswith: '\net.exe'
    CommandLine|contains:
      - ' user '
      - ' group '
      - ' localgroup '
      - ' accounts '
  condition: selection
falsepositives:
  - 시스템 관리자 일상 작업
level: low  # FP 많음 → 낮은 level, 헌팅 시작점
```

---

## MITRE ATT&CK 커버리지 분석

내 룰셋이 ATT&CK의 어떤 기법을 커버하는지 시각화하는 방법.

### MITRE ATT&CK Navigator

1. https://mitre-attack.github.io/attack-navigator/ 접속
2. 내 룰들의 태그에서 기법 ID 추출
3. Navigator에 레이어로 업로드

```bash
# 룰 디렉터리에서 ATT&CK 기법 ID 추출
find rules/ -name "*.yml" -exec grep -h "attack\\.t" {} \; | \
  grep -oP 'attack\.t\d+(\.\d+)?' | \
  sort -u | \
  sed 's/attack\.//'
```

### 커버리지 갭 찾기

```bash
# 기법별 룰 수 카운트
find rules/ -name "*.yml" -exec grep -h "attack\.t" {} \; | \
  grep -oP 'attack\.t\d+\.\d+' | \
  sort | uniq -c | sort -rn | head -20
```

많이 커버된 기법(PowerShell, cmd 실행 등)은 충분하고, 잘 안 다뤄진 기법(메모리 인젝션, 펌웨어 조작 등)이 contribution 기회.

---

## 실전: 룰 작성부터 PR까지

### 단계 1: 위협 리서치

공격 기법 파악:
- [MITRE ATT&CK](https://attack.mitre.org) — 기법 설명, 사용된 툴
- [GTFOBins](https://gtfobins.github.io) — Linux 바이너리 어뷰즈
- [LOLBAS](https://lolbas-project.github.io) — Windows Living off the Land
- 보안 블로그/Threat Intel 리포트

### 단계 2: 로그 이벤트 파악

해당 공격이 어떤 로그를 남기는지 확인:
- Windows: Sysmon Event 1 (process creation), Event 3 (network), Event 11 (file create)
- Linux: auditd execve, openat, connect

### 단계 3: 룰 초안 작성

```yaml
title: Suspicious Binary Download via Curl
id: <새 UUID>
status: experimental
description: curl을 이용해 실행 파일을 다운로드하는 의심 행동
logsource:
  product: linux
  category: process_creation
detection:
  selection:
    Image|endswith: '/curl'
    CommandLine|contains:
      - ' -o '
      - '--output'
    CommandLine|contains:
      - '.sh'
      - '.py'
      - '.elf'
      - '.bin'
  condition: selection
falsepositives:
  - 패키지 설치 스크립트
  - CI/CD 파이프라인
level: medium
tags:
  - attack.execution
  - attack.t1105  # Ingress Tool Transfer
```

### 단계 4: 검증

```bash
# 형식 검증
sigma check my_rule.yml

# 변환 테스트
sigma convert --target elasticsearch --pipeline ecs_linux my_rule.yml

# 실제 로그에 적용 (Elasticsearch)
curl -X GET "localhost:9200/logs-*/_search" -H 'Content-Type: application/json' -d '{
  "query": <변환된 쿼리>
}'
```

### 단계 5: 튜닝

FP를 발견하면 필터 추가:

```yaml
  filter_package_install:
    ParentImage|endswith:
      - '/apt'
      - '/yum'
      - '/brew'
  filter_ci:
    User: jenkins
  condition: selection and not 1 of filter_*
```

### 단계 6: PR

SigmaHQ CONTRIBUTING 가이드:
- 파일 이름 규칙: `{category}_{product}_{description}.yml`
  - `proc_creation_lnx_curl_suspicious_download.yml`
- 파일 위치: `rules/{product}/{category}/`
- 기존 룰과 중복 없는지 확인 (`sigma check --duplicate`)
- PR 제목: "New: <rule title>"

---

## pySigma로 에이전트 통합

보안 에이전트에서 Sigma 룰을 런타임에 변환·적용하는 패턴.

```python
from sigma.collection import SigmaCollection
from sigma.backends.elasticsearch import LuceneBackend
from sigma.processing.resolver import ProcessingPipelineResolver
from sigma.processing.pipeline import ProcessingPipeline
import yaml

class SigmaQueryEngine:
    """런타임에 Sigma 룰을 SIEM 쿼리로 변환하는 엔진"""
    
    def __init__(self, backend_name: str, pipeline_path: str):
        # 파이프라인 로드
        with open(pipeline_path) as f:
            pipeline_config = yaml.safe_load(f)
        self.pipeline = ProcessingPipeline.from_yaml(yaml.dump(pipeline_config))
        
        # 백엔드 초기화
        if backend_name == "elasticsearch":
            self.backend = LuceneBackend(processing_pipeline=self.pipeline)
        # ... 다른 백엔드들
    
    def convert_rule(self, rule_path: str) -> list[str]:
        with open(rule_path) as f:
            collection = SigmaCollection.from_yaml(f.read())
        return self.backend.convert(collection)
    
    def convert_directory(self, rules_dir: str) -> dict[str, list[str]]:
        """디렉터리의 모든 룰을 변환. 파일명 → 쿼리 목록"""
        from pathlib import Path
        results = {}
        for rule_file in Path(rules_dir).glob("**/*.yml"):
            try:
                queries = self.convert_rule(str(rule_file))
                results[rule_file.stem] = queries
            except Exception as e:
                print(f"변환 실패 {rule_file}: {e}")
        return results

# 사용
engine = SigmaQueryEngine("elasticsearch", "pipeline.yml")
queries = engine.convert_directory("rules/linux/")
# 이 쿼리들을 Elasticsearch에 Watch/Alert으로 등록
```

이 패턴으로 에이전트가:
1. Sigma 룰 레포에서 최신 룰 pull
2. 대상 SIEM에 맞게 변환
3. SIEM에 알림 룰로 등록
4. 경보를 받아서 자동 대응

---

## 룰셋 관리 전략

### 레이어 구조

```
rules/            ← upstream SigmaHQ (git submodule 또는 별도 clone)
custom-rules/     ← 자체 작성 룰 (organization 특화)
  ├── my-product/ ← 자체 제품 로그 소스
  ├── tuned/      ← upstream 룰 튜닝 버전
  └── internal/   ← 내부 정책 기반 탐지
```

### 버전 관리

```bash
# upstream 룰 특정 버전 고정
git submodule add https://github.com/SigmaHQ/sigma rules-upstream
git -C rules-upstream checkout v1.2.3   # 검증된 버전 고정

# 새 버전 업그레이드 시
git -C rules-upstream pull
# 변경된 룰 중 우리 환경에 영향 있는 것 리뷰
# 파이프라인으로 재변환하고 SIEM 업데이트
```

### 자동화 파이프라인

```yaml
# .github/workflows/sigma-sync.yml
name: Sigma Rules Sync
on:
  schedule:
    - cron: '0 6 * * 1'  # 매주 월요일 오전 6시
  workflow_dispatch:

jobs:
  convert:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: true
      
      - name: Install sigma-cli
        run: pip install sigma-cli
      
      - name: Convert rules
        run: |
          sigma convert \
            --target elasticsearch \
            --pipeline ecs_windows \
            --output-format ndjson \
            rules-upstream/rules/windows/ > converted/windows.ndjson
      
      - name: Deploy to SIEM
        run: |
          curl -X POST "https://es.internal/sigma-rules/_bulk" \
            --data-binary @converted/windows.ndjson
```

---

## 다음 단계

공부 순서 제안:

1. **기초 다지기**: `rules/linux/` 디렉터리의 간단한 룰 10개 읽고 문법 익히기
2. **변환 실습**: `sigma-cli` 설치 → 룰 하나 골라서 Elasticsearch/Splunk 쿼리로 변환
3. **직접 작성**: GTFOBins에서 기법 하나 골라서 Linux process_creation 룰 작성
4. **FP 관리 실습**: 룰을 실제 로그에 적용하고 FP 찾아서 필터 추가
5. **코드 기여**: SigmaHQ에 새 Linux 룰 PR 도전 (good-first-issue 라벨 확인)
6. **pySigma**: 간단한 커스텀 백엔드 작성 (자체 로그 소스)
