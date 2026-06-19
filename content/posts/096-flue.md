---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "096. Flue — 자율 에이전트를 배포 서버로 컴파일하는 하니스 프레임워크"
date: 2026-06-19
tags: [flue, ai-agents, agent-framework, typescript, sandbox, harness, durable-execution, withastro, oss-analysis]
summary: "Flue는 agents/·workflows/ 디렉터리의 TypeScript 프로젝트를 배포 가능한 서버 아티팩트로 컴파일하는 에이전트 하니스다. 'Not another SDK'를 표방하며 모델에 컨텍스트·도구·샌드박스를 주고 자율 실행시킨다. 다만 이름과 달리 격리 샌드박스를 직접 구현하지 않고, 에이전트 루프도 외부 패키지에 위임한다. 무엇을 제공하고 무엇을 위임하는지, 샌드박스 세 모드의 실제 격리 수준, durable execution까지 코드 레벨로 분해한다."
source: "https://github.com/withastro/flue"
slug: "096-flue"
categories: ["OSS 분석"]
---

LLM API를 직접 호출해 만든 1세대 에이전트는 챗봇이나 단순 스크립트 수준에 머물렀다. 반면 Claude Code나 Codex 같은 도구는 사전 정의된 절차를 따르지 않는다. 과제를 주면 제공된 컨텍스트와 도구로 스스로 완수한다. Flue는 이 아키텍처를 누구나 만들 수 있게 하는 것을 목표로 한다. `agents/`와 `workflows/` 디렉터리의 TypeScript 프로젝트를 받아 **배포 가능한 서버 아티팩트로 컴파일**한다.

Flue가 스스로를 규정하는 첫 문장은 "Not another SDK"다. LangChain 같은 체인 조립 SDK가 아니라 "프로그래머블 TypeScript 하니스"라는 것이다. 그런데 코드를 열어 보면 두 가지 반전이 있다. 레포 설명은 "sandbox agent framework"인데 **Flue 자체는 격리 샌드박스를 구현하지 않고**, 에이전트 루프도 직접 만들지 않는다. 둘 다 외부에 위임하고, Flue는 그 위에 하니스·배포·영속성·통합 레이어를 얹는다. 이 구조를 정확히 이해하는 게 Flue를 이해하는 핵심이다.

분석 대상은 `@flue/runtime@1.0.0-beta.2`(Apache-2.0). 아직 1.0 이전 베타다.

## 무엇을 푸는가

Flue는 "자율 에이전트에게 필요한 환경"을 TypeScript 하니스로 제공한다. 세션, 도구, 스킬, 지시문, 파일시스템 접근, 그리고 (이름상의) 보안 샌드박스. 개발자는 파일 규약을 따른다. `agents/<name>.ts`는 주소 지정 가능한 에이전트가 되어 `POST /agents/<name>/:id`로 노출되고 세션이 지속된다. `workflows/<name>.ts`는 입력에서 결과로 끝나는 유한 작업이 된다.

## 용어 계층

Flue의 추상화는 명확한 계층을 이룬다.

```
Agent profile   — 재사용 가능한 defineAgentProfile(...) 값
Created agent    — createAgent(...)가 반환하는 런타임 초기화자
Agent module     — agents/<name>.ts; 파일명이 에이전트 이름
  └─ Harness     — init()이 반환하는 초기화된 에이전트 환경
     └─ Session  — harness.session(name?); 대화 컨텍스트 단위
        └─ Operation — prompt / skill / task / shell 한 번의 호출
           └─ Turn   — 내부 LLM 1회 왕복
Workflow         — workflows/<name>.ts; run(...) export
```

- **Agent**: `createAgent(initialize)`가 모델·도구·스킬·지시문·샌드박스를 묶은 초기화자를 동결해 반환한다. 매번 하니스 초기화 시 실행되므로 1회용 생성자가 아니다.
- **Session**: 대화 컨텍스트를 유지하는 단위. 내부 `Session` 클래스는 외부로 절대 노출되지 않고, `FlueSession` facade만 사용자에게 전달된다. 1.0 전 API 안정화 의도다.
- **Operation / Turn**: Operation은 사용자가 호출하는 한 번(`prompt`/`skill`/`task`/`shell`), Turn은 그 안의 LLM 1회 왕복.
- **Skill**: 실행 능력이 아니라 재사용 가능한 지시문이다. agentskills.io 스펙을 따르는 `SKILL.md` 파일이며, 호출 시점에 전체 지시문을 컨텍스트로 지연 로딩한다(progressive disclosure).
- **Tool**: 애플리케이션 코드를 실행하는 타입드 액션. `defineTool({name, description, parameters, execute})`로 정의하고 파라미터는 valibot 스키마.
- **Subagent**: `task` 도구로 위임받는 자식 에이전트. 부모 대화에는 최종 답만 반환한다.
- **Workflow**: 대화 없이 입력에서 결과로 끝나는 작업. 고유 `runId`를 받는다.

## 아키텍처

pnpm + Turbo 모노레포다. 패키지는 27개. 핵심은 다섯이다.

| 패키지 | 역할 |
|---|---|
| `@flue/runtime` | 하니스, 세션, 도구, 샌드박스 (핵심) |
| `@flue/cli` | `flue` 바이너리. Vite로 배포 아티팩트 빌드 |
| `@flue/sdk` | 배포된 에이전트 소비용 클라이언트 |
| 영속성 어댑터 | postgres / libsql / mysql / redis / mongodb |
| 채널 통합 | slack / discord / github / stripe 등 16개 이상 |

`@flue/runtime` 내부에서 실제 일이 벌어지는 곳은 두 파일이다. `session.ts`(약 2530줄)가 에이전트 루프 구동·이벤트 방출·영속화·컴팩션·task 위임을 담당하고, `agent.ts`는 이름과 달리 에이전트 클래스가 아니라 **빌트인 도구 정의 파일**이다(read/write/edit/bash/grep/glob/task). 이 둘을 혼동하기 쉽다.

## 샌드박스의 실제 격리 수준

여기가 Flue에서 가장 오해하기 쉬운 부분이다. **Flue는 프로세스 격리·컨테이너·VM·WASM을 직접 구현하지 않는다.** "Sandbox"는 `SessionEnv`라는 단일 인터페이스(exec + 파일 연산)에 대한 어댑터 추상화이고, 실제 격리 수준은 선택한 어댑터에 달려 있다. 세 모드가 있다.

**Virtual (기본값)**: `sandbox` 필드를 생략하면 선택된다. `just-bash` 라이브러리 기반의 인메모리 워크스페이스로, bash 환경을 JS로 에뮬레이트한 가상 파일시스템이다. 진짜 OS 프로세스가 아니다. 문서가 한계를 명시한다. 호스트 파일 없음, 비영속, 임의의 Linux toolchain 아님, 그리고 결정적으로 **네트워크 격리 경계가 아니다**(virtual 샌드박스에서 네트워크 접근을 허용한다). 이름이 sandbox여도 신뢰 경계가 아니다.

**Local (`local()`)**: 호스트 파일시스템과 셸에 직접 바인딩한다. `exec`는 `node:child_process.spawn`으로 실제 셸을 띄우고, 파일 연산은 `node:fs/promises`를 직접 호출한다. abort나 timeout 시 프로세스 그룹 전체를 SIGTERM 후 2초 뒤 SIGKILL로 종료해 백그라운드 자식까지 죽인다. 문서가 "모델이 지시한 작업과 호스트 머신 사이에 격리를 제공하지 않는다"고 명시한다. 신뢰된 호스트나 CI 러너 전용이다. 다만 보안 기본값은 보수적이다. 환경변수는 기본 allowlist(PATH/HOME/USER/LANG 등)만 통과하고, 토큰·시크릿은 `local({ env: { GH_TOKEN: ... } })`로 명시적으로 opt-in하지 않으면 모델 셸에 노출되지 않는다.

**Remote**: Daytona, Cloudflare Sandbox(컨테이너), E2B, Modal, Vercel 등 외부 프로바이더를 `SandboxApi`로 래핑한다. **진짜 격리가 필요하면 이 경로를 써야 하고, 그 격리는 프로바이더 책임이다.**

정리하면 Flue의 가치는 "동일한 코드로 인메모리(virtual) → 호스트(local) → 원격 컨테이너(remote)를 전환"하는 어댑터 추상화에 있다. 하지만 "sandbox"라는 이름이 보안 격리를 보장한다고 오해하면 안 된다. 격리는 remote 어댑터를 쓰는 사용자의 몫이다.

## 에이전트 루프와 도구

실제 루프 엔진은 Flue가 아니라 외부 패키지 `@earendil-works/pi-agent-core`의 `Agent` 클래스다. `Session` 생성자에서 `new Agent({ initialState, getApiKey, streamFn, toolExecution: 'parallel' })`로 띄운다. 모델 스트리밍은 `@earendil-works/pi-ai`의 `streamSimple`에 위임한다. 도구는 병렬 실행이다. Flue는 이 루프의 라이프사이클 이벤트(turn_start, tool_execution_start 등)를 구독해 자기 이벤트로 재방출하고 히스토리를 체크포인트한다.

빌트인 도구는 Claude Code의 도구 셋을 닮았다. read(2000줄/50KB로 truncate), write, edit(유일 매칭 강제 치환), bash(2계층 timeout — 프로바이더 네이티브 + 로컬 AbortSignal backstop), grep(`rg` 우선 탐색 후 캐시), glob, task(자식 세션 위임, 깊이 제한 `MAX_TASK_DEPTH=4`). 세션은 한 번에 하나의 operation만 처리한다(`SessionBusyError`).

흥미로운 패턴이 두 개 있다. **구조화 결과**는 `session.prompt(text, { result: schema })`로 호출하면 그 호출 동안만 `finish`/`give_up` 두 도구를 주입한다. 모델이 plain text로 답하면 follow-up으로 도구 호출을 강제한다. "텍스트로 답하지 말고 구조화 도구를 호출하라"는 강제 패턴이다. **컴팩션**은 토큰이 `contextWindow - reserveTokens`를 넘으면 오래된 메시지를 구조화 요약으로 치환하고, LLM이 context overflow를 반환하면 압축 후 자동 재시도한다.

## Durable Execution

Flue가 경량 프레임워크치고 드물게 갖춘 강점이다. HTTP 프롬프트와 dispatch 입력을 SQL 기반 submission으로 영속화해 크래시와 재시작을 넘어 진행을 보존한다. 인터럽트된 도구 호출은 "interrupted" 에러 결과로 안전하게 복구한다(가짜 성공을 만들지 않는다). 부분 스트림 청크도 영속화 후 재구성한다. 기본값은 `maxAttempts=10`, `timeoutMs=1시간`, lease 30초다. 타깃 중립 인터페이스라 Node(node:sqlite), Cloudflare(DO SQLite), Postgres/MySQL이 같은 코드를 공유한다.

## 사용법

```ts
import { createAgent, type FlueContext } from '@flue/runtime';
import * as v from 'valibot';

const agent = createAgent(() => ({ model: 'anthropic/claude-sonnet-4-6' }));

export async function run({ init }: FlueContext) {
  const harness = await init(agent);
  const session = await harness.session();
  const response = await session.prompt('What is 2 + 2? Return only the number.', {
    result: v.object({ answer: v.number() }),   // 구조화 결과
  });
  return response.data;
}
```

주소 지정 에이전트는 `sandbox: local()`, `skills: [...]`, `tools: [...]`를 묶어 default export하고 `route` 핸들러로 노출한다. 모델은 `'<provider>/<model>'` 문자열로 지정하고, `registerProvider`로 ollama 같은 로컬/게이트웨이 프로바이더까지 붙일 수 있다.

## 강점과 한계

**강점**은 일관된 개발 경험(프로젝트를 배포 아티팩트로 컴파일), 샌드박스 어댑터로 dev→prod 전환이 코드 변경 최소, 강력한 durable execution, Claude Code를 닮은 빌트인 도구 셋, 16개 이상 채널과 다양한 영속성·관측 통합, 보수적 보안 기본값이다.

**한계**는 분명하다. "sandbox"가 보안 격리를 보장하지 않는다(virtual은 네트워크 허용, local은 호스트 직접 접근). 핵심 루프가 비교적 알려지지 않은 외부 패키지에 결합돼 있다. 1.0 미만 베타라 breaking change가 잦다(도구 파라미터가 TypeBox에서 valibot으로 바뀌는 등). 멀티에이전트는 단방향 `task` 위임뿐이고, AutoGen식 다자 대화는 1급 개념이 아니다.

## 차별점

LangChain/LangGraph는 체인·그래프로 LLM 호출을 조립하는 SDK다. Flue는 "Not another SDK"를 명시하고, 미리 정의된 그래프 대신 모델에 샌드박스·도구·자율성을 주고 풀게 한다. Workflow가 LangGraph의 결정적 오케스트레이션에 가장 가까운 대응물이지만 노드 그래프가 아니라 그냥 TypeScript `run()` 함수다. 철학적으로 가장 가까운 것은 Claude Agent SDK다(자율 에이전트 + 코딩 도구 셋 + 샌드박스). 차이는 Flue가 모델·프로바이더 중립이고, 배포·HTTP·채널·durable execution을 프레임워크로 내장하며, TypeScript 모노레포 생태계라는 점이다.

## 정리

Flue의 정체는 "프로젝트를 배포 서버로 컴파일하는 에이전트 하니스"다. 본질은 에이전트 루프(외부 pi-agent-core) 위에 세션·영속성·HTTP·통합·샌드박스 어댑터를 얹는 레이어다. 두 가지를 기억하면 된다. 첫째, "sandbox"는 어댑터 추상화일 뿐 격리는 어댑터가 책임진다. virtual과 local은 신뢰 경계가 아니다. 둘째, 자율성은 모델에 맡기고 결정성·관측성은 코드(Workflow와 durable execution)가 떠받친다. 아직 베타라 API는 유동적이다.
