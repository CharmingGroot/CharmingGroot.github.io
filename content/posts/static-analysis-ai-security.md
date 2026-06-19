---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-05. 정적 분석·AI 보안 기초 — 웹 취약점·OWASP LLM·YARA·Taint"
date: 2026-06-16
tags: [security, owasp, prompt-injection, ssrf, supply-chain, static-analysis, yara, ast, taint, llm-security, ai-agents]
summary: "SkillSpector 같은 보안 스캐너에 기여하거나 코드를 읽을 때 필요한 개념들. 웹 취약점 기초, OWASP LLM Top 10, 정적 분석(regex·AST·YARA·taint tracking)을 개발자 시각에서 정리한다."
slug: "static-analysis-ai-security"
categories: ["보안"]
---

보안 문서를 읽다 보면 모르는 단어가 줄줄이 나온다. 그걸 하나씩 검색하며 읽으면 흐름이 끊긴다. 여기서는 SkillSpector 코드나 OWASP 문서를 읽을 때 자주 만나는 개념들을 미리 정리한다. 손으로 해본 지식이 아니라 독해를 위한 개념 지도다.

---

## 1. 공격자 관점: 왜 코드가 취약해지는가

보안 취약점의 공통 원인은 **신뢰 경계(trust boundary) 착각**이다. 외부에서 들어오는 데이터를 믿어버리거나, 내부 코드가 입력을 그대로 실행하거나, 권한이 필요한 곳에 검증이 없는 경우다. 취약점의 이름은 달라도 이 패턴에서 벗어나는 경우는 드물다.

---

## 2. 웹 보안 기초 취약점

### Injection (인젝션)

외부 입력이 코드나 명령의 일부로 해석되는 것. 가장 넓은 카테고리다.

**SQL Injection** — DB 쿼리에 사용자 입력이 그대로 들어갈 때.

```python
# 취약
query = f"SELECT * FROM users WHERE name = '{user_input}'"
# user_input = "'; DROP TABLE users; --" 이면?
```

`'`로 문자열을 닫고 SQL 명령을 덧붙인다. 결과적으로 DB 명령이 의도와 다르게 실행된다.

**Command Injection** — OS 쉘 명령에 입력이 끼어드는 것.

```python
import os
os.system(f"ping {user_input}")
# user_input = "8.8.8.8; rm -rf /"
```

세미콜론으로 명령을 이어붙이면 임의 명령이 실행된다.

**Code Injection** — `eval()`이나 `exec()`에 외부 입력이 들어올 때. Python에서는 특히 위험하다. SkillSpector의 `agent_skill_remote_bootstrap_execution` 룰이 잡는 패턴이 이것: `exec(requests.get("...").text)`.

### SSRF (Server-Side Request Forgery)

서버가 외부 URL을 대신 요청하게 만드는 공격. 클라이언트에서 직접 접근하면 막히는 내부 리소스에, 서버를 경유해서 도달한다.

```
공격자 → 서버에 "http://169.254.169.254/latest/meta-data/ 로 요청해줘" → 서버가 AWS 메타데이터에 접근
```

`169.254.169.254`는 AWS/GCP/Azure 클라우드 인스턴스 내부에서만 접근 가능한 메타데이터 서버 주소다. 여기서 API 키, IAM 토큰, 인스턴스 정보를 꺼낼 수 있다. SkillSpector에 아직 탐지 룰이 없는 갭이다([[095-qlora]]와 무관, 별도 맥락).

### Path Traversal (경로 탐색)

`../`를 이용해 의도한 디렉터리 밖의 파일에 접근하는 것.

```
요청: /files/../../../etc/passwd
실제 접근: /etc/passwd
```

### Credential / Secret Exposure (자격증명 노출)

API 키, 비밀번호, 토큰 같은 민감한 값이 코드, 로그, 환경변수를 통해 새어 나가는 것. SkillSpector의 `data_exfiltration_analyzer`가 이걸 잡는다.

### Supply Chain Attack (공급망 공격)

내가 쓰는 패키지나 도구 자체가 오염된 경우. 코드를 직접 공격하는 게 아니라, 의존성(dependency)을 경유해서 들어온다. npm의 `event-stream` 사건, PyPI에 올라온 타이포스쿼팅 패키지들이 대표적. SkillSpector의 SC(Supply Chain) 카테고리가 이걸 다루고, OSV.dev에 실시간 조회한다.

### Privilege Escalation (권한 상승)

낮은 권한에서 높은 권한을 획득하는 것. 웹에서는 일반 사용자 → 관리자, 시스템에서는 일반 프로세스 → root.

---

## 3. AI/LLM 보안 — OWASP LLM Top 10

OWASP(Open Web Application Security Project)는 웹 보안 가이드라인을 만드는 비영리 재단이다. LLM 앱 전용 Top 10을 따로 만들었고, SkillSpector PR들이 이 번호를 reference로 단다(`LLM01`, `LLM06` 등).

### LLM01: Prompt Injection (프롬프트 인젝션)

가장 중요한 항목. 외부 입력이 LLM의 지시(instruction)를 덮어쓰거나 조작하는 것. SQL Injection의 LLM 버전.

두 종류가 있다:
- **Direct**: 사용자가 직접 시스템 프롬프트를 우회하는 지시를 입력 ("이전 지시를 무시하고...")
- **Indirect**: 에이전트가 처리하는 외부 문서(웹페이지, 파일)에 숨겨진 지시가 있어, 에이전트가 그걸 지시로 받아들임

AI 에이전트가 스킬을 실행할 때, 스킬 안에 숨겨진 지시가 있으면 에이전트가 그대로 따를 수 있다. SkillSpector의 `prompt_injection_analyzer`가 이걸 잡는다.

### LLM02: Sensitive Information Disclosure (민감 정보 노출)

모델이 학습 데이터에 포함된 개인정보, API 키, 내부 시스템 정보를 노출하거나, 시스템 프롬프트를 사용자에게 유출하는 것.

### LLM03: Supply Chain (공급망)

LLM 앱에서의 공급망 위협. 오염된 파인튜닝 데이터, 악성 플러그인/스킬, 서드파티 모델 자체의 백도어. 스킬이 공급망 공격의 벡터가 될 수 있다는 게 SkillSpector의 전제다.

### LLM06: Excessive Agency (과도한 자율성)

에이전트가 필요 이상의 권한을 갖거나, 사람 확인 없이 되돌리기 어려운 행동을 자동으로 수행하는 것. 파일 삭제, 이메일 발송, API 호출, 코드 배포 같은 행동을 "silently"(조용히, 확인 없이) 하면 여기에 해당한다.

SkillSpector의 `excessive_agency_analyzer`와 `destructive_autonomous_actions` YARA 룰이 이걸 잡는다.

### LLM07: System Prompt Leakage (시스템 프롬프트 유출)

에이전트가 자신의 시스템 프롬프트(내부 지시)를 사용자에게 노출하도록 유도하는 공격. 시스템 프롬프트에는 보통 내부 정책, API 키, 비즈니스 로직이 들어 있다.

### Tool Poisoning (도구 포이즈닝)

MCP/에이전트 도구의 메타데이터(description, parameters)에 악성 지시를 숨기는 것. LLM이 도구 설명을 읽고 그 지시를 따르게 만든다. `debugactiveprocess`의 `agent_skill_mcp_tool_poisoning_metadata` 룰이 잡는 패턴.

### Rug Pull (러그풀)

처음에는 정상인 스킬/패키지가 나중에 악성 버전으로 교체되는 것. npm 생태계에서 자주 발생했고, MCP 스킬 생태계에서도 동일한 위협이 있다.

---

## 4. 정적 분석 기초

SkillSpector가 코드를 실행하지 않고 파일을 보는 방식. 탐지 룰을 이해하려면 이 기법들을 알아야 한다.

### Regex (정규식) 기반 탐지

코드를 문자열로 보고 패턴을 찾는다. 빠르고 단순하지만 문맥을 모른다.

```python
# SkillSpector가 이런 패턴을 찾음
r"os\.environ\s*\.items\s*\(\)"
```

한계: 주석 안에 있어도 잡힌다, 변수 이름만 바꿔도 우회된다.

### AST (Abstract Syntax Tree, 추상 구문 트리)

코드를 파싱해서 구조로 분석한다. `import os` 다음에 `os.system()` 호출이 있는지처럼, 코드의 의미 구조를 본다. Regex보다 정확하고 우회가 어렵다.

```python
# AST로 보면 이게 같은 패턴임을 알 수 있다
os.system(cmd)
getattr(os, 'system')(cmd)
```

### YARA

악성 파일 탐지에 쓰는 시그니처 언어. 바이너리와 텍스트 모두 지원하고, 여러 조건을 조합해서 룰을 만든다.

```yara
rule example {
    strings:
        $a = "OPENAI_API_KEY"
        $b = /requests\.post\s*\(/
        $c = "discord.com/api/webhooks"
    condition:
        $a and $b and $c  // 세 조건이 모두 있을 때만
}
```

단일 문자열 매칭이 아니라 **여러 인디케이터의 조합**으로 탐지하기 때문에 FP(오탐)를 줄일 수 있다. SkillSpector는 YARA를 malware, webshell, cryptominer 탐지에 쓰고, PR #1이 에이전트 스킬 전용 룰을 추가했다.

### Taint Tracking (오염 추적)

데이터가 **소스(source)**에서 **싱크(sink)**로 흐르는 경로를 추적한다.

- **Source**: 신뢰할 수 없는 입력이 들어오는 지점 (`request.body`, `os.environ`, 파일 읽기)
- **Sink**: 위험한 함수가 호출되는 지점 (`eval()`, `os.system()`, DB 쿼리, HTTP 요청)

소스에서 시작한 데이터가 중간에 검증 없이 싱크에 도달하면 취약점. SQL Injection을 예로 들면: `request.body` → (untainted) → `cursor.execute()` 경로가 taint path다.

### FP / FN

- **False Positive (FP, 오탐)**: 정상인데 악성이라고 잡는 것. 탐지 룰이 너무 넓을 때.
- **False Negative (FN, 미탐)**: 악성인데 못 잡는 것. 탐지 룰이 너무 좁을 때.

둘은 트레이드오프다. YARA 룰에 `and` 조건을 많이 걸수록 FP가 줄지만 FN이 늘 수 있다. `debugactiveprocess`가 `test_credential_webhook_requires_collection_and_transmission`처럼 FP 방지 테스트를 넣은 이유.

---

## 5. 자주 보이는 용어 빠른 참조

| 용어 | 한줄 설명 |
|---|---|
| CVE | 공개된 취약점에 붙는 고유 번호 (CVE-2024-XXXXX) |
| OSV | 오픈소스 취약점 DB. SkillSpector SC4가 여기 조회함 |
| SARIF | 정적 분석 결과 교환 포맷. GitHub code scanning에 바로 연동됨 |
| SPDX | 소프트웨어 라이선스 식별자. 파일 헤더에 `SPDX-License-Identifier: Apache-2.0` 형태로 씀 |
| DCO | Developer Certificate of Origin. 커밋에 `Signed-off-by:` 줄을 붙여 저작권 귀속을 선언 |
| SSRF | 서버가 공격자 대신 내부 리소스에 요청하도록 유도하는 공격 |
| RCE | Remote Code Execution. 원격에서 임의 코드 실행. 가장 심각한 취약점 유형 |
| Exfiltration | 내부 데이터를 외부로 빼내는 것. SkillSpector에서는 자격증명 유출이 주요 대상 |
| Severity | 취약점 심각도. CRITICAL > HIGH > MEDIUM > LOW |
| Confidence | 탐지 결과가 맞을 확률에 대한 추정. YARA 룰 메타에 0.0~1.0으로 표기 |
| Zero-width char | 화면에 안 보이는 유니코드 문자 (ZWSP, ZWNJ 등). 숨겨진 지시를 삽입할 때 쓰임 |
| RTL override | 우→좌 텍스트 방향 제어 문자. 파일명·코드에서 내용을 숨기는 데 악용됨 |
| Webhook | 이벤트 발생 시 지정 URL로 POST 요청을 보내는 패턴. exfiltration 경로로 자주 쓰임 |
| Typosquatting | `numpy` → `nunpy`처럼 오타를 노린 악성 패키지명. 공급망 공격 벡터 |

---

SkillSpector 코드를 읽을 때 위 개념들이 어디에 해당하는지 보이면, 탐지 룰이 왜 그렇게 생겼는지 따라갈 수 있다. 실제 취약점이 동작하는 걸 보려면 [[PortSwigger-labs]]가 필요하지만, 그건 다음 단계.
