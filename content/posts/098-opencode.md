---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "098. opencode — 벤더 중립 오픈소스 코딩 에이전트의 클라이언트-서버 구조"
date: 2026-06-19
tags: [opencode, coding-agent, ai-agents, typescript, bun, effect, llm-provider, mcp, client-server, oss-analysis]
summary: "opencode는 터미널에서 도는 오픈소스 코딩 에이전트다. 단일 LLM 벤더에 종속되지 않고 20개 이상 provider를 지원하는 것이 핵심이고, 에이전트를 로컬 HTTP 서버로 만들어 TUI·데스크톱·웹·CI가 같은 API를 공유한다. Claude Code의 UX 패턴을 차용하되 벤더 종속을 깬다. 에이전트 루프, LLM 추상화 두 층, 권한 모델, 그리고 V1/V2 이중 런타임 부채까지 코드 레벨로 분해한다."
source: "https://github.com/anomalyco/opencode"
slug: "098-opencode"
categories: ["OSS 분석"]
---

opencode는 터미널에서 동작하는 오픈소스 AI 코딩 에이전트다. 자연어 지시로 코드베이스를 읽고 수정하고 명령을 실행한다. 여기까지는 Claude Code나 Aider와 같다. 차별점은 두 가지다. 첫째, 특정 LLM 벤더에 종속되지 않고 수십 개 provider를 지원한다. 둘째, 단순 CLI가 아니라 **클라이언트-서버 구조**를 택했다. 에이전트 로직은 로컬 HTTP 서버(데몬)에서 돌고 TUI·데스크톱·웹은 그 서버의 클라이언트다.

분석 대상은 `anomalyco/opencode` 버전 1.17.8(MIT, 기본 브랜치 `dev`), GitHub 스타 약 176k다. 두 가지 흔한 오해부터 바로잡는다. 소유 조직은 한때 SST 팀이었다가 anomalyco로 이전됐다. 그리고 TUI는 한때 Go + Bubbletea였으나 이 버전에서는 전부 TypeScript이고, TUI는 SolidJS + OpenTUI로 재작성됐다. "TypeScript + Go 혼합"은 이 버전에 해당하지 않는다.

## 핵심 개념

코드에서 실제 쓰이는 추상화는 다음과 같다.

- **Session**: 대화 단위. 메시지·파트로 구성되고 SQLite에 영속화된다. ID는 `ses_` prefix.
- **Message / Part**: 메시지는 user/assistant 역할. Part는 discriminated union이다. `text`, `reasoning`, `tool`, `file`, `step-start`, `step-finish`, `snapshot`, `patch`, `agent`, `subtask`, `compaction` 등.
- **Agent**: 권한·프롬프트·모델 설정을 묶은 프로필. 빌트인은 `build`(기본, 전체 권한), `plan`(읽기 전용, 편집 거부), `general`·`explore`(서브에이전트), `compaction`/`title`/`summary`(숨김 내부용)다. mode는 `primary`/`subagent`/`all`.
- **Tool**: Effect Schema 기반 입력/출력 + `execute`.
- **Provider / Model**: LLM 벤더 추상화. 카탈로그는 models.dev에서 동적 로드된다.
- **Permission**: `allow`/`ask`/`deny` 룰셋. 도구·리소스별 와일드카드 정책.
- **Mode**: build↔plan을 Tab키로 전환. 코드상으로는 agent와 거의 합쳐져 있다.

## 아키텍처

Bun workspaces + Turbo 모노레포다. 패키지는 25개. 주요한 것들이다.

| 패키지 | 역할 |
|---|---|
| `opencode` | CLI 진입점 + V1 세션 런타임 (실제 프로덕션 에이전트 루프) |
| `core` | 도메인 로직: tool/provider/permission/session/storage. V1+V2 공존 |
| `llm` | 자체 LLM 프로토콜 어댑터(Anthropic Messages, OpenAI Chat/Responses, Gemini 등). AI SDK 대안 |
| `tui` | SolidJS + OpenTUI 터미널 UI |
| `server` | Effect 기반 HTTP API (Hono + hono-openapi) |
| `sdk/js` | HTTP 클라이언트 SDK (자동 생성) |
| `desktop` | Electron 데스크톱 앱 |

배포본은 Bun으로 컴파일한 단일 바이너리다. `bin/opencode`는 플랫폼·아키텍처(AVX2 감지 포함)에 맞는 컴파일 바이너리를 찾아 spawn하는 Node 셸 스크립트다. CLI는 yargs 기반이고 서브커맨드가 23개다(`run`, `serve`, `tui`, `mcp`, `agent`, `models`, `github`, `pr` 등).

**클라이언트-서버 분리**가 구조의 핵심이다. `opencode`를 인자 없이 실행하면 백그라운드 데몬 서버를 띄우고 TUI는 그 서버에 HTTP/SSE 클라이언트로 붙는다. 데몬이 없거나 비정상이면 `serve --register`를 detached로 spawn하고 `~/.opencode/server.json`에 URL과 PID를 등록한다. 서버 API는 Effect `HttpApi.make()`로 agents/sessions/messages/models/providers/events 핸들러를 조립하고, 이벤트는 `GET /api/event` SSE로 스트리밍된다. 이 구조 덕분에 TUI·데스크톱·웹·CI(github, pr 커맨드)가 모두 같은 서버 API를 공유한다.

## V1/V2 이중 런타임

opencode를 읽을 때 가장 중요한 사실이다. 코드에 두 런타임이 공존한다. **V1**(레거시이지만 현역)과 **V2**(Effect 기반 신규, 마이그레이션 중)다.

실제 프로덕션 에이전트 루프는 V1이다. `packages/opencode/src/session/prompt.ts`(1722줄)에 있다. V2의 `SessionRunner`는 인터페이스만 정의된 단계이고 실행체는 비어 있다. `CONTEXT.md`와 `AGENTS.md`의 "V2 Session Core"는 진행 중인 재설계 명세이며, `event-v2-bridge.ts`가 V1과 V2 이벤트를 이중 기록한다(주석에 "Temporary dual-write while migrating"). 코드를 볼 때 둘을 혼동하면 안 된다.

## 에이전트 루프

V1의 `runLoop`은 `while (true)` 루프로 다음을 반복한다.

1. **종료 판정**: 마지막 assistant의 finish가 tool-calls가 아니고 미처리 tool call이 없으면 탈출한다. 일부 provider가 tool call이 있어도 stop을 주는 문제를 보정한다.
2. **step 카운트**. step 1에서 세션 제목 자동 생성을 fork한다.
3. **subtask 분기**(서브에이전트 호출)와 **compaction 분기**(히스토리 압축).
4. **오버플로 자동 압축**: 컨텍스트가 넘치면 auto compaction을 생성한다.
5. **maxSteps**: 마지막 step이면 `max-steps.txt` 프롬프트를 주입해 텍스트 응답을 강제한다.
6. **system reminder 주입**: step>1에서 중간에 들어온 user 메시지를 `<system-reminder>`로 감싼다. Claude Code의 패턴과 동일하다.
7. **도구 해석**: agent 권한·MCP·플러그인을 반영해 이번 턴 도구 세트를 결정한다.
8. **시스템 프롬프트 조립**: env + 지시문(AGENTS.md) + skills.
9. **LLM 호출**: processor가 스트림을 소비한다.

## LLM 통합: 두 층

벤더 중립이 어떻게 구현되는지가 여기 있다.

**기본 경로는 Vercel AI SDK `streamText`다.** provider별 `@ai-sdk/*` 패키지(anthropic, openai, google, bedrock, azure, mistral, groq, cohere, xai, openrouter 등 20개 이상)를 동적 로드한다. `wrapLanguageModel`로 미들웨어를 끼워 메시지를 provider별로 변환하고, `experimental_repairToolCall`로 잘못된 tool call을 복구한다.

**실험적 native 경로**는 자체 `@opencode-ai/llm` 패키지다. provider별 HTTP를 직접 다루는 프로토콜 어댑터로, Anthropic Messages(845줄), OpenAI Responses(1004줄), Gemini, Bedrock Converse를 Effect Schema로 정의한다(Anthropic의 cache_control, thinking, tool_use 블록까지). `experimentalNativeLlm` 플래그가 켜지면 이 경로를 쓰고 미지원이면 AI SDK로 폴백한다. 두 경로 모두 동일한 `LLMEvent` 스트림으로 정규화된다.

모델 카탈로그는 models.dev API에서 동적 로드된다(5분 TTL 캐시, flock으로 프로세스간 잠금, 임베디드 스냅샷 폴백). provider는 잘 알려진 것은 빠른 경로를 쓰고 없으면 on-demand로 npm 설치한다. 모델별로 시스템 프롬프트가 갈리고(claude → `anthropic.txt`, gpt → `gpt.txt`, gemini → `gemini.txt` 등), reasoning effort도 provider별로 변형된다(Anthropic은 `thinking.budgetTokens`, OpenAI는 `reasoningEffort`, Gemini는 `thinkingLevel`).

인증은 OAuth / API key / WellKnown 세 종이다. `~/.opencode/data/auth.json`에 0600 권한으로 저장하고, env → 저장된 credential → config → provider 기본값 순으로 해석한다. GitHub Copilot, AWS Bedrock, Google Vertex 같은 엔터프라이즈 인증을 풍부하게 처리한다.

## 도구와 권한

도구는 `Tool.make({ description, input, output, execute })`로 정의한다. 입력/출력은 Effect Schema이고 JSON Schema로 자동 변환해 LLM에 노출한다. 빌트인은 bash, read, write, edit, apply_patch, glob, grep, webfetch, websearch, question, skill, todowrite다. bash는 timeout 기본 2분/최대 10분, 출력 1MB 캡이다.

권한은 `allow`/`ask`/`deny` 세 종이고 와일드카드로 매칭하며 **기본 폴백은 가장 안전한 ask**다. 각 도구가 실행 시점에 `permission.assert`로 검사한다. agent별 기본 권한이 다르다. `build`는 question/plan_enter를 허용하고, `plan`은 모든 편집을 deny하되 `.opencode/plans/*.md`만 허용하며, `explore`는 전부 deny한 뒤 grep/glob/bash/read/webfetch/websearch만 허용한다. 세션은 SQLite + Drizzle ORM으로 영속화하고, snapshot/patch part로 파일 변경 이력을 보존해 되돌리기를 지원한다.

## 설계 결정과 트레이드오프

- **전면 TypeScript + Bun**: 패키지 매니저와 런타임이 Bun이고 배포는 Bun 컴파일 단일 바이너리다. JS 생태계(AI SDK 등) 활용이 강점, Go 대비 시작 비용·배포 크기(17M 패키지)가 트레이드오프다.
- **Effect 전면 채택**: core 전체가 Effect 기반이다(Schema, Layer DI, Stream). 강타입·합성성이 장점, 가파른 러닝 커브가 단점이다.
- **클라이언트-서버 분리**: 헤드리스·원격·CI를 가능하게 한다.
- **V1→V2 점진 마이그레이션**: 현역 V1 루프를 유지하면서 Effect 기반 V2를 병행 구축하고 dual-write 브리지로 전환 중이다.

## 사용법

```bash
curl -fsSL https://opencode.ai/install | bash   # 또는 npm i -g opencode-ai
opencode                # 현재 디렉터리에서 TUI 시작 (데몬 자동 기동)
opencode run "..."      # 비대화형 1회 실행
opencode serve          # 헤드리스 서버
```

Tab키로 build↔plan 전환, `@general`로 서브에이전트를 호출한다.

## 강점과 한계

**강점**은 provider 중립성(20개 이상 AI SDK provider + 자체 프로토콜 + models.dev 동적 카탈로그), 진짜 클라이언트-서버(헤드리스·CI·다중 프런트엔드), 세밀한 권한 모델, 스킬·서브에이전트·MCP·LSP·플러그인 등 풍부한 확장점, 강타입 도메인과 SQLite 영속화·되돌리기·압축이다.

**한계**는 이중 런타임 부채(V1/V2 공존, dual-write 브리지, bash 등에 다수의 V2 포팅 TODO), 거대·복잡(17M 패키지, Effect 추상화의 진입 장벽), Bun 1차 의존, native LLM 경로가 아직 실험 플래그 뒤라는 점이다.

## 차별점

| | opencode | Claude Code | Aider | Cursor |
|---|---|---|---|---|
| 형태 | 터미널 TUI + 서버/데스크톱/웹 | 터미널 CLI | 터미널 CLI | IDE 포크 |
| 라이선스 | MIT 오픈소스 | 비공개 | Apache-2.0 | 비공개 |
| LLM | 벤더 중립, 20+ provider | Anthropic 전용 | 멀티 provider | 멀티(자체 라우팅) |
| 구조 | 클라이언트-서버 | 단일 프로세스 | 단일 프로세스 | IDE 내장 |

요약하면 opencode의 정체성은 "벤더 중립 + 완전 오픈소스 + 클라이언트-서버"다. Claude Code의 에이전트 UX 패턴(서브에이전트, system-reminder 주입, skill, plan 모드)을 상당 부분 차용하되, 단일 벤더 종속을 깨고 다중 프런트엔드를 지원한다는 점에서 갈린다. Aider(Python, git-diff 중심), Cursor/Continue(IDE 내장)와는 "터미널 우선 + 서버화"라는 축에서 구분된다.

## 정리

opencode는 Claude Code류 코딩 에이전트의 UX를 오픈소스·벤더 중립으로 옮긴 도구다. 본질은 에이전트 루프(V1 `prompt.ts`) 위에 LLM 추상화 두 층(AI SDK 기본 + 자체 프로토콜 실험)과 동적 모델 카탈로그(models.dev)를 얹고, 전체를 HTTP 서버로 만들어 여러 프런트엔드가 공유하게 한 구조다. 코드를 읽을 때 두 가지를 기억하면 된다. 현역 루프는 V1이고 V2는 마이그레이션 중이다. 그리고 기본 LLM 경로는 AI SDK이며 자체 프로토콜은 아직 플래그 뒤의 실험이다. 벤더 중립과 클라이언트-서버라는 두 베팅이 이 프로젝트를 다른 코딩 에이전트와 구분 짓는다.
