---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "099. opencode 활용 — 도구를 넘어 플랫폼으로: 6개 확장 표면과 실전 시나리오"
date: 2026-06-20
tags: [opencode, coding-agent, ai-agents, sdk, acp, mcp, plugin, ci-automation, self-hosting, oss-analysis]
summary: "opencode는 터미널에서 쓰는 코딩 에이전트이자, 클라이언트-서버 구조 덕에 다른 것을 그 위에 얹을 수 있는 플랫폼이기도 하다. HTTP 서버 API와 SDK, 헤드리스·CI 자동화, ACP 에디터 통합, MCP, 플러그인 훅, 커스텀 에이전트·권한까지 여섯 개의 확장 표면을 코드 근거로 짚고, 각각으로 무엇을 만들 수 있는지 정리한다. 보안 같은 도메인 특화 에이전트로 가는 경로도 함께 본다."
source: "https://github.com/anomalyco/opencode"
slug: "099-opencode-use-cases"
categories: ["OSS 분석"]
---

[098번 글](098-opencode.md)에서 opencode의 핵심 구조 두 가지를 봤다. 에이전트를 로컬 HTTP 서버로 만든 클라이언트-서버 분리, 그리고 20개 이상 provider를 지원하는 벤더 중립성이다. 이 두 베팅이 opencode의 활용 범위를 결정한다. 터미널에서 직접 쓰는 것은 가장 단순한 사용법일 뿐이다. 서버 API·SDK·ACP·플러그인·MCP·커스텀 에이전트라는 여섯 개의 확장 표면이 있고, 각각이 다른 활용을 연다.

핵심은 이거다. **opencode는 도구이면서 동시에 플랫폼이다.** 코딩 에이전트 기능을 자기 앱에 임베드하거나, CI 봇으로 박거나, 에디터에 꽂거나, 도메인 특화 에이전트로 깎아 쓸 수 있다. 이 글은 그 표면들을 코드 근거로 하나씩 짚는다.

## 먼저: API와 SDK가 두 벌이다

opencode는 마이그레이션 중이라 서버 API와 SDK가 두 벌 공존한다. 활용을 논하기 전에 이걸 구분해야 한다.

- **안정(stable) API**: hey-api로 생성된 `@opencode-ai/sdk`. 클라이언트 클래스 `OpencodeClient`가 20개 네임스페이스(session, project, provider, file, mcp, lsp, pty, auth, event 등)를 노출한다.
- **V2 실험 API**: `packages/server`의 Effect `HttpApi` 기반. 코드가 스스로 "Experimental HttpApi surface"라고 명시한다. V2 SDK(`@opencode-ai/sdk/v2`)가 대응한다.

지금 무언가를 만든다면 안정 SDK를 기준으로 하되, V2는 실험 표기를 감안한다.

## 1. HTTP 서버 + SDK — 에이전트 백엔드로 임베드

가장 강력한 활용은 opencode를 자기 애플리케이션의 코딩 에이전트 백엔드로 임베드하는 것이다.

세션 API의 흐름이 핵심이다. `POST /api/session`으로 세션을 만들고 `POST /api/session/:id/prompt`로 메시지를 보낸다. 중요한 점은 prompt가 동기 응답이 아니라는 것이다. 스펙에 "Durably admit one session input and schedule agent-loop execution"이라고 적혀 있다. prompt는 에이전트 루프를 비동기로 스케줄하고, 진행은 `GET /api/event`(SSE)로 구독하거나 `POST /api/session/:id/wait`로 idle을 기다린다. 이 비동기 모델 덕에 장시간 도는 에이전트 작업을 웹 UI나 봇에서 자연스럽게 다룰 수 있다.

SDK는 인프로세스 부팅도 지원한다. `createOpencode()`가 서버를 띄우고 같은 baseURL로 클라이언트를 만들어 `{client, server}`를 돌려준다. 레포에 실전 레퍼런스가 있다. glob으로 파일을 모아 **파일마다 세션을 만들고 prompt를 병렬로** 날리는 배치 예제다(`packages/sdk/js/example/example.ts`). 대량 코드 변환이나 테스트 생성 잡을 세션 병렬화로 처리하는 패턴이다.

**만들 수 있는 것**: 웹 대시보드·슬랙봇·사내 포털이 opencode 서버를 백엔드로 두고 코딩 에이전트 기능을 임베드. 대규모 리팩터·마이그레이션을 세션 병렬 배치로 돌리는 잡 러너.

## 2. 헤드리스·CI 자동화

`opencode serve`는 헤드리스 서버다. 흥미로운 설계는 `instance: false`로 떠서 요청 헤더(`x-opencode-directory`)로 프로젝트 디렉터리를 받는다는 점이다. **하나의 서버가 여러 프로젝트를 멀티테넌트로 처리**한다. 인증은 `OPENCODE_SERVER_PASSWORD` 환경변수이고, 미설정 시 "server is unsecured" 경고를 띄운다.

`opencode run`은 단발 비대화형 실행이다. `--format json`으로 원시 이벤트 스트림을 출력하고, 비대화형 모드에서는 `question`/`plan_enter` 같은 멈춤 동작을 권한 룰셋으로 deny해 끊김 없이 끝까지 돈다. CI에서 `opencode run -m <provider/model> "..."`로 호출하는 게 기본 경로다.

`github`/`pr` 서브커맨드가 CI 봇의 실체다. `opencode github install`은 `.github/workflows/opencode.yml`을 생성하고, 코멘트가 `/oc`나 `/opencode`로 시작할 때 트리거되게 한다. `opencode github run`이 웹훅을 처리한다. PR·이슈 컨텍스트(title/body/files/reviews)를 `<pull_request>`/`<issue>` 블록으로 프롬프트에 주입하고, 응답 후 변경이 있으면 자동 commit/push하거나 이슈면 브랜치를 만들어 PR을 연다. 봇 계정은 `opencode-agent[bot]`이다.

레포 자신의 `.github/workflows/review.yml`이 살아 있는 레퍼런스다. PR 코멘트 `/review`에 반응해 `opencode run`으로 스타일 가이드를 점검하고, 에이전트가 `gh api`로 라인별 리뷰 코멘트를 단다(권한으로 `gh pr review`는 막고 `gh api`만 허용한다). schedule 트리거도 되므로 정기 점검·리팩터 PR 봇도 가능하다.

**정확성 주의**: GitHub 봇의 기본 토큰 경로는 opencode 인프라(`api.opencode.ai`)를 통한 OIDC 토큰 교환이다. 완전 self-host하려면 `use_github_token=true`로 바꿔 `GITHUB_TOKEN`을 직접 써야 한다.

**만들 수 있는 것**: `/oc` 자동 수정봇, `/review` 라인 코멘트 리뷰봇, schedule 기반 정기 점검 PR 봇.

## 3. 에디터 통합 — ACP

`opencode acp`는 opencode를 ACP(Agent Client Protocol) 에이전트로 노출한다. 내부적으로 HTTP 서버를 먼저 띄우고, stdin/stdout을 ND-JSON 스트림으로 감싸 `@agentclientprotocol/sdk`의 연결을 만든다. 즉 Zed 같은 ACP 지원 에디터가 stdio로 JSON-RPC를 말하면 opencode가 에이전트로 응답한다.

ACP로 광고하는 capabilities가 꽤 넓다. `loadSession`, 세션 fork/resume/list/close, 이미지 첨부, MCP 동적 등록(http/sse)까지 프로토콜 레벨에서 노출된다. 에디터에서 세션을 분기하거나 이어받는 것까지 가능하다.

**만들 수 있는 것**: ACP를 지원하는 에디터에 opencode를 에이전트 백엔드로 연결. 자체 에디터를 만든다면 ACP만 구현하면 opencode를 그대로 붙일 수 있다.

## 4. MCP — 클라이언트로만

여기서 흔한 오해를 바로잡아야 한다. opencode는 **MCP 클라이언트**다. 외부 MCP 도구서버를 붙이는 쪽이다.

`opencode mcp add`로 local(command/env) 또는 remote(url/headers/oauth) MCP 서버를 `opencode.json`의 `mcp` 키에 등록한다. remote MCP는 OAuth 흐름(동적 클라이언트 등록 포함)까지 지원하고, `mcp auth`/`mcp debug`로 토큰 상태와 `WWW-Authenticate`까지 확인할 수 있다.

반대 방향, 즉 **opencode 자체를 MCP 서버로 노출하는 기능은 없다.** 코드 전역에 MCP 서버 생성(`new McpServer`)이 0건이고 클라이언트측 에러 클래스만 있다. opencode를 외부 프로그램에서 부르려면 MCP가 아니라 HTTP 서버 + SDK, 또는 ACP를 써야 한다.

**만들 수 있는 것**: 사내 도구를 MCP 서버로 만들어 `mcp add`로 붙여 에이전트의 도구를 확장.

## 5. 플러그인 — 훅으로 동작을 가로채기

플러그인 SDK(`@opencode-ai/plugin`)의 `Hooks` 인터페이스가 후킹 표면이다. 플러그인은 `client`(SDK), `project`, `directory`, `$`(Bun shell) 등을 받는 함수이고, 다음을 확장·가로챌 수 있다.

- **커스텀 도구**: `tool({description, args, execute})`로 새 도구를 주입.
- **커스텀 provider/auth**: 동적 모델 목록과 provider별 인증 흐름.
- **라이프사이클 훅**: `event`(모든 이벤트), `config`, `chat.message`, `chat.params`(temperature/maxTokens 등 조정), `permission.ask`(allow/deny/ask 강제), `command.execute.before`, `tool.execute.before`/`after`, `shell.env`, `tool.definition`.
- **실험적 훅**: 메시지 배열 변형, 시스템 프롬프트 변형, 저가 모델 지정, 압축 제어.
- **워크스페이스 어댑터**: `experimental_workspace.register`로 원격 실행 환경을 주입.

이 훅들이 정책 적용 지점이 된다. `permission.ask`로 특정 경로 편집을 자동 거부하고, `tool.execute.after`로 감사 로그나 DLP를 걸고, `chat.params`로 비용 가드레일을 두는 식이다.

**만들 수 있는 것**: 사내 도구·provider 연동, 정책 강제(편집 차단), 감사·DLP, 비용 가드, 원격 실행 환경 주입.

## 6. 커스텀 에이전트·권한·스킬

opencode는 도메인 특화 에이전트로 깎을 수 있다. 설정은 `opencode.json`(또는 `.opencode/agent/*.md` 마크다운 + frontmatter)에서 한다.

권한 룰셋이 핵심이다. V2 스키마는 `{ action, resource, effect("allow"|"deny"|"ask") }`의 배열이고, **마지막으로 매칭된 규칙이 이긴다**(매칭 없으면 기본 ask). action과 resource 모두 와일드카드다. (주의: 코드에 V1 스키마 `{permission, action, pattern}`도 공존하며 자동 마이그레이션된다.)

내장 `explore` 에이전트가 "읽기 전용" 패턴의 본보기다. 전부 deny한 뒤 grep/glob/read/webfetch/websearch만 허용한다. 이 패턴으로 **보안 리뷰 전용 읽기 전용 에이전트**를 만들 수 있다.

```jsonc
{ "agents": { "security-review": {
  "mode": "subagent",
  "description": "Read-only security analysis",
  "model": "opencode/...",
  "permissions": [
    { "action": "*",        "resource": "*", "effect": "deny" },
    { "action": "read",     "resource": "*", "effect": "allow" },
    { "action": "grep",     "resource": "*", "effect": "allow" },
    { "action": "glob",     "resource": "*", "effect": "allow" },
    { "action": "websearch","resource": "*", "effect": "allow" }
  ] } } }
```

스킬도 붙는다. `skills: [...]`로 디렉터리/URL을 주면 `SKILL.md`를 frontmatter(name/description/slash)로 발견하고, `slash:true`면 `/<skill>` 슬래시 커맨드로 등록한다. 레포 자신도 `.opencode/agent/triage.md`, `duplicate-pr.md`로 이슈 분류와 중복 PR 처리를 자기 에이전트로 자동화한다.

## 벤더 중립의 실전 의미

provider 설정은 `opencode.json`의 `providers` 키다. `api: { type:"aisdk", package:"@ai-sdk/...", url }` + `request.headers` 형태다.

- **로컬 모델**: `@ai-sdk/openai-compatible` + `url: "http://localhost:11434/v1"`로 ollama/LM Studio/vLLM 연결.
- **사내 게이트웨이**: 같은 openai-compatible에 `url`을 사내 엔드포인트로, `request.headers`에 인증·테넌트 헤더 주입.
- **저가 라우팅**: 전역 `model`을 싼 모델로 두거나, `cost` 메타를 주면 카탈로그가 제목·요약용 보조 모델을 비용 기준으로 자동 선택한다. 플러그인 훅 `experimental.provider.small_model`로 강제할 수도 있다.

**만들 수 있는 것**: 완전 온프렘(로컬 모델만), 사내 LLM 게이트웨이 단일 경유, 메인은 고급·보조 작업은 저가로 가르는 비용 최적화.

## 종합 — 무엇을 build할 수 있나

1. **사내 코딩 에이전트 셀프호스팅**: `opencode serve`(헤더 멀티테넌트, 패스워드 보호) + provider를 로컬 모델/사내 게이트웨이로. 코드가 밖으로 안 나가는 온프렘 에이전트.
2. **커스텀 프런트엔드**: SDK + `/api/event` SSE로 자체 UI. `createOpencode()` 인프로세스 임베드, 배치 잡은 세션 병렬화.
3. **에디터 플러그인**: `opencode acp`로 Zed류 에디터에 백엔드 연결.
4. **CI 리뷰·PR 봇**: `opencode github run`으로 자동 수정봇·라인 코멘트 리뷰봇·정기 PR 봇.
5. **도메인 특화 에이전트**: 읽기 전용 권한 룰셋으로 보안 리뷰 에이전트 등. `.opencode/agent/*.md`로 버전 관리.
6. **MCP·플러그인 생태계**: 외부 MCP 도구서버 연결, 플러그인 훅으로 정책 강제·감사·비용 가드·커스텀 도구.

## 정리

opencode의 활용은 결국 그 구조에서 나온다. 에이전트를 HTTP 서버로 만들었기 때문에 SDK로 임베드하고, ACP로 에디터에 꽂고, 헤드리스로 CI에 박을 수 있다. 벤더 중립이라 온프렘·저비용 라우팅이 열린다. 플러그인 훅과 권한 룰셋이 있어 정책을 강제하고 도메인 특화 에이전트로 깎을 수 있다. 도구가 아니라 플랫폼으로 보면 활용 범위가 달라진다.

보안 에이전트를 만든다면 특히 세 표면이 토대가 된다. 읽기 전용 권한 룰셋(도메인 에이전트), 플러그인의 `permission.ask`/`tool.execute.after`(정책 강제·감사), 그리고 셀프호스팅 + 온프렘 provider(코드 유출 차단)다. opencode를 처음부터 다시 만들 필요 없이, 그 위에 보안 정책 레이어를 얹는 접근이 가능하다.

세 가지만 기억하면 된다. API와 SDK는 두 벌이고(안정 vs V2 실험), 권한 스키마도 두 벌이다(V1 vs V2). opencode는 MCP 클라이언트일 뿐 MCP 서버로 노출되지 않는다. 그리고 GitHub 봇을 완전 self-host하려면 토큰 경로를 `GITHUB_TOKEN` 직접 사용으로 바꿔야 한다.
