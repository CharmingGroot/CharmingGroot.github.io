---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-02. 유저 공간 — ELF, 동적 링킹, vDSO, 주소 공간 레이아웃, ASLR"
date: 2026-06-20
tags: [userspace, elf, dynamic-linking, plt, got, vdso, aslr, pie, libc, execve, address-space]
summary: "ring 3에서 돌아가는 세계의 전체 지도. ELF 바이너리 구조, execve에서 main()까지의 과정, 동적 링킹(PLT/GOT/lazy binding), libc와 syscall 래핑, vDSO, 64비트 유저 공간 주소 레이아웃, ASLR/PIE/Stack canary까지 정리한다."
slug: "arch-02-userspace"
categories: ["시스템 아키텍처"]
---

유저 공간은 ring 3에서 돌아가는 모든 것의 무대다. 프로그래머가 짠 코드가 실제로 어떻게 메모리에 올라가고, 함수 호출이 어떻게 연결되며, 커널과 어떻게 통신하는지는 ELF 바이너리 구조와 동적 링킹에 숨어 있다. 이 층을 모르면 디버깅, 성능 최적화, 보안 분석 모두 표면만 긁는다.

## ELF 바이너리 구조

Linux에서 실행 파일, 공유 라이브러리(.so), 오브젝트 파일(.o)은 모두 ELF(Executable and Linkable Format) 형식이다.

**ELF Header**: 파일 첫 64바이트. 매직 넘버(`\x7fELF`), 아키텍처(64비트/32비트), 엔디안, 파일 타입(ET_EXEC=실행 파일, ET_DYN=공유 라이브러리/PIE), entry point 주소, 섹션 헤더·프로그램 헤더의 오프셋 등을 담는다.

**Section vs Segment**: 섹션(section)은 링커 관점, 세그먼트(segment)는 로더 관점이다.

주요 섹션:
- `.text`: 실행 코드 (읽기 전용)
- `.rodata`: 문자열 리터럴 등 읽기 전용 데이터
- `.data`: 초기화된 전역/정적 변수
- `.bss`: 0으로 초기화되는 전역/정적 변수 (파일에 공간 없음, 크기만 기록)
- `.plt`: PLT 코드 (동적 함수 호출 트램펄린)
- `.got.plt`: PLT가 실제 주소를 읽는 테이블
- `.dynsym` / `.dynstr`: 동적 링킹에 필요한 심볼 테이블
- `.debug_*`: DWARF 디버그 정보 (strip하면 제거됨)

주요 세그먼트(Program Header):
- `LOAD`: 메모리에 올릴 영역 (rx=코드, rw=데이터)
- `INTERP`: 동적 링커 경로 (`/lib64/ld-linux-x86-64.so.2`)
- `DYNAMIC`: 동적 링킹 정보 (필요한 라이브러리, 재배치 정보)
- `GNU_STACK`: 스택 실행 권한 (NX 설정)
- `GNU_RELRO`: 읽기 전용으로 만들 영역 (GOT protection)

`readelf -h`, `readelf -S`, `readelf -l`로 ELF 구조를 확인한다.

## execve에서 main()까지

`execve("/usr/bin/ls", argv, envp)` syscall이 호출되면 커널이 ls를 메모리에 올린다.

1. **커널 단계**: `load_elf_binary()`가 ELF 헤더를 파싱해 `LOAD` 세그먼트를 가상 주소에 매핑한다. `INTERP` 세그먼트가 있으면 동적 링커(`ld-linux.so`)도 메모리에 올린다. 스택에 `argc`, `argv`, `envp`, **auxiliary vector(auxv)**를 넣는다. auxv는 동적 링커에게 기본 정보(entry point, page size, uid, 하드웨어 기능 등)를 전달하는 커널→유저 통신 채널이다.

2. **동적 링커 단계**: 실행 파일의 entry point 대신 ld.so가 먼저 실행된다. ld.so가 하는 일:
   - `.dynamic` 섹션에서 필요한 공유 라이브러리(DT_NEEDED) 목록 확인
   - 각 라이브러리를 mmap으로 메모리에 로드
   - 재배치(relocation): 심볼 주소를 GOT에 채움
   - 각 라이브러리의 초기화 함수(`.init_array`) 실행
   - 실행 파일의 entry point(`_start`)로 점프

3. **C 런타임 단계**: `_start` → `__libc_start_main()` → `main()`. `__libc_start_main`은 argc/argv 파싱, 환경 변수 설정, atexit 핸들러 등록, `main()` 호출, 반환 후 `exit()`을 담당한다.

## 동적 링킹: PLT / GOT

공유 라이브러리 함수(예: `printf`)의 주소는 런타임에 결정된다. 링크 타임에는 주소를 모르기 때문이다.

**Lazy binding (기본 동작)**:

```
코드: call printf
  → PLT의 printf 항목으로 점프  (plt[printf])
  → GOT.plt[printf] 주소로 간접 점프
    → 첫 호출: GOT.plt[printf]가 아직 ld.so 리졸버를 가리킴
    → ld.so가 실제 printf 주소를 찾아 GOT.plt[printf]에 씀
    → 이후 호출: GOT.plt[printf]가 실제 주소를 가리킴 → 직접 점프
```

PLT는 함수마다 3개 명령의 작은 트램펄린이다. GOT.plt는 PLT가 읽는 주소 테이블이다. 처음 호출 시에만 ld.so 리졸버가 실행되어 GOT에 실제 주소를 쓴다(lazy). 이후에는 GOT→실제 함수로 바로 간다.

**Full RELRO**: 링크 옵션 `-Wl,-z,relro,-z,now`를 쓰면 프로그램 시작 시 모든 GOT 항목을 즉시 채우고(eager binding), GOT 영역을 읽기 전용으로 만든다. GOT overwrite 공격(return-to-PLT, GOT hijacking)을 막는다.

## libc와 syscall

C 코드에서 `write(fd, buf, n)`을 호출하면 glibc의 `write()` 래퍼가 실행된다. 래퍼는 다음을 한다:

```asm
mov eax, 1         ; syscall number (write=1 on x86-64)
mov rdi, fd        ; 1st arg
mov rsi, buf       ; 2nd arg
mov rdx, n         ; 3rd arg
syscall            ; ring 0 진입
; 반환: rax에 결과 (음수 = -errno)
```

syscall 인자는 레지스터로 전달된다: `rdi, rsi, rdx, r10, r8, r9` (최대 6개). 반환값은 rax. 음수면 errno에 절댓값을 넣고 -1을 반환하는 것이 glibc 래퍼의 역할이다.

`strace ./a.out`으로 프로그램이 실제로 어떤 syscall을 몇 번 호출하는지 확인할 수 있다. `ltrace ./a.out`은 라이브러리 함수 호출을 보여준다.

## vDSO (virtual Dynamic Shared Object)

`gettimeofday`, `clock_gettime`, `getcpu` 같은 함수는 자주 호출되지만 특권이 필요 없다. 매번 syscall을 하면 ring 전환 비용이 낭비다. vDSO는 이 문제를 해결한다.

커널이 모든 프로세스의 주소 공간에 작은 공유 라이브러리(vdso.so)를 매핑한다. 이 라이브러리 코드는 ring 3에서 실행되면서 커널이 공유 메모리(vvar)에 유지하는 시간 데이터를 직접 읽는다. syscall 없이 시간을 얻는다. 커널이 타이머 틱마다 vvar를 갱신한다.

`/proc/PID/maps`에서 `[vdso]`와 `[vvar]` 매핑을 확인할 수 있다. glibc의 `clock_gettime`은 자동으로 vDSO를 사용한다.

## 유저 공간 주소 공간 레이아웃 (x86-64 Linux)

64비트 프로세스의 주소 공간 배치:

```
0x0000_0000_0000_0000   [NULL 페이지, 언매핑]
0x0000_0000_0040_0000   실행 파일 text (PIE 아니면 고정)
                        heap (text 끝 ~ brk 포인터, 위로 자람)
...
0x0000_7F??_????_????   공유 라이브러리, mmap 영역 (아래로 자람)
0x0000_7FFF_FF60_0000   [vvar]
0x0000_7FFF_FF80_0000   [vdso]
0x0000_7FFF_FFFF_E000   스택 (아래로 자람)
0x0000_7FFF_FFFF_FFFF   유저 공간 상한
                        [canonical hole]
0xFFFF_8000_0000_0000   커널 공간 시작
```

heap과 mmap 영역이 만나는 방향이 반대라 충분히 커다란 가상 공간을 효율적으로 쓴다. PIE 바이너리는 text 위치도 랜덤화된다.

## ASLR / PIE / Stack Canary

**ASLR (Address Space Layout Randomization)**: 매 실행마다 스택, mmap, heap의 시작 주소를 랜덤화한다. `/proc/sys/kernel/randomize_va_space` 값으로 제어한다(0=비활성, 1=스택+mmap, 2=힙 포함). 공격자가 특정 주소를 예측할 수 없게 만든다.

**PIE (Position Independent Executable)**: `-fPIE -pie`로 컴파일한 실행 파일은 text 세그먼트도 랜덤 주소에 올라간다. ASLR은 스택/mmap만 랜덤화하지만, PIE는 코드 자체도 랜덤화한다. 현대 배포판의 시스템 바이너리는 대부분 PIE다.

**Stack Canary**: 함수 진입 시 스택 프레임과 반환 주소 사이에 랜덤 값(canary)을 삽입한다. 함수 복귀 전에 canary가 바뀌었으면 스택 버퍼 오버플로를 감지하고 프로세스를 종료한다. `-fstack-protector-strong`으로 활성화한다.

**NX (No-Execute) / DEP**: `GNU_STACK` 세그먼트가 실행 권한 없이 설정되면 스택·힙 코드를 실행할 수 없다. CPU의 NX 비트(PTE의 XD/NX 플래그)를 이용한다. 코드를 스택에 올리는 shellcode 공격을 막는다.

## 정리

유저 공간의 실행 파일은 ELF 형식이고, section은 링커가 data(코드·데이터) 보는 시각, segment는 로더가 메모리에 올리는 단위다. execve 후 커널이 LOAD 세그먼트를 매핑하고, 동적 링커(ld.so)가 공유 라이브러리를 로드하고 재배치한 뒤, `_start` → `main()`으로 흐른다. 함수 호출은 PLT→GOT 간접 참조로 이뤄지고, 첫 호출 때 ld.so가 GOT를 채운다. syscall은 레지스터에 번호·인자를 넣고 `syscall` 명령으로 ring 0에 진입한다. vDSO는 자주 쓰는 syscall을 ring 전환 없이 처리한다. 보안은 ASLR, PIE, Stack Canary, NX가 계층을 이뤄 방어한다.
