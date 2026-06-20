---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-03. 프로세스 — task_struct, fork/exec/clone, 상태 전이, COW, zombie"
date: 2026-06-20
tags: [process, task_struct, fork, exec, clone, cow, zombie, mm_struct, vma, linux-kernel]
summary: "커널이 프로세스를 어떻게 표현하고 관리하는지. task_struct의 핵심 필드, fork/exec/clone의 내부 동작, 프로세스 상태 전이, mm_struct와 vm_area_struct, Copy-on-Write 메커니즘, 프로세스 종료와 zombie reaping까지 정리한다."
slug: "arch-03-process"
categories: ["시스템 아키텍처"]
---

커널은 실행 단위를 **task**라고 부른다. 프로세스와 스레드 모두 `task_struct`라는 하나의 구조체로 표현된다. 프로세스가 스레드와 다른 점은 주소 공간, 파일 디스크립터, 시그널 핸들러를 공유하느냐 여부뿐이다. 이 구조를 이해하면 fork/exec/clone의 동작이 자연스럽게 따라온다.

## task_struct: 커널의 프로세스 표현

`task_struct`는 커널 소스의 `include/linux/sched.h`에 정의되어 있고 수백 개의 필드를 가진다. 핵심 필드만 추려보면:

```c
struct task_struct {
    /* 상태 */
    volatile long state;        // TASK_RUNNING, TASK_INTERRUPTIBLE, ...
    int exit_code;              // 종료 코드

    /* 식별자 */
    pid_t pid;                  // 커널 내 고유 ID (스레드 ID)
    pid_t tgid;                 // 스레드 그룹 ID (= 프로세스 PID)

    /* 계보 */
    struct task_struct *parent; // 부모 태스크
    struct list_head children;  // 자식 목록
    struct list_head sibling;   // 형제 목록

    /* 주소 공간 */
    struct mm_struct *mm;       // 유저 주소 공간 (커널 스레드는 NULL)
    struct mm_struct *active_mm;// 현재 활성 mm

    /* 파일 */
    struct files_struct *files; // 파일 디스크립터 테이블

    /* 파일 시스템 */
    struct fs_struct *fs;       // cwd, root 디렉터리

    /* 시그널 */
    struct signal_struct *signal;
    struct sighand_struct *sighand;

    /* 스케줄링 */
    const struct sched_class *sched_class;
    struct sched_entity se;     // CFS 스케줄링 엔티티 (vruntime)

    /* 권한 */
    const struct cred *cred;    // uid, gid, capabilities

    /* 네임스페이스 */
    struct nsproxy *nsproxy;    // PID/net/mount/uts ns 링크

    /* cgroup */
    struct css_set *cgroups;
};
```

`pid`와 `tgid`의 차이가 중요하다. 메인 스레드는 `pid == tgid`다. 추가 스레드는 별도 `pid`를 가지지만 `tgid`는 메인 스레드의 `pid`를 공유한다. `getpid()`가 반환하는 것이 `tgid`이고, `gettid()`가 반환하는 것이 `pid`다.

## fork() 내부: copy_process

`fork()` 호출 → `clone()` syscall → `_do_fork()` → `copy_process()` 순으로 실행된다.

`copy_process()`가 하는 일:

1. `dup_task_struct()`: 부모 `task_struct`를 복사해 자식 구조체 생성. 커널 스택도 새로 할당.
2. 각 서브시스템 복사 (clone 플래그에 따라 공유 또는 복사):
   - `copy_mm()`: `mm_struct` 복사 (COW 설정 포함)
   - `copy_files()`: 파일 디스크립터 테이블 복사
   - `copy_sighand()`: 시그널 핸들러 복사
   - `copy_namespaces()`: 네임스페이스 링크 복사
3. PID 할당: 새 `pid` 생성 (PID namespace 고려)
4. 스케줄러에 추가: `sched_fork()` → 부모의 CPU 시간 절반 할당
5. 반환: 부모에게 자식 PID, 자식에게 0

`fork()` 후 부모와 자식 중 어느 쪽이 먼저 실행될지는 스케줄러가 결정한다. 리눅스는 최근 버전까지 자식을 먼저 실행하는 경향이 있었다(exec-then-fork COW 최적화).

## exec() 내부: load_elf_binary

`execve(path, argv, envp)` syscall → `do_execve()` → `exec_binprm()` → `load_elf_binary()`.

`load_elf_binary()`가 하는 일:

1. 기존 mm을 비우고 새 `mm_struct` 생성
2. ELF 헤더 검증 (magic, architecture)
3. `LOAD` 세그먼트를 새 주소 공간에 매핑 (`vm_mmap()`)
4. `INTERP` 세그먼트가 있으면 동적 링커도 매핑
5. 스택 영역 생성, `argv`/`envp`/auxv 복사
6. 레지스터 초기화: RIP=entry point (동적 링커가 있으면 ld.so의 `_start`)

exec 후에도 같은 `task_struct`를 사용하지만 `mm_struct`는 완전히 교체된다. PID는 바뀌지 않는다.

## clone()과 스레드

`fork()`와 `clone()`의 차이는 플래그에 있다. `fork()`는 `clone(SIGCHLD)`의 편의 래퍼다.

스레드 생성은:
```c
clone(CLONE_VM | CLONE_FS | CLONE_FILES | CLONE_SIGHAND |
      CLONE_THREAD | CLONE_SETTLS | ..., ...)
```
`CLONE_VM`: mm 공유 (같은 주소 공간)
`CLONE_FILES`: 파일 디스크립터 테이블 공유
`CLONE_SIGHAND`: 시그널 핸들러 공유
`CLONE_THREAD`: 같은 스레드 그룹(tgid)

컨테이너 생성은 반대로 새 네임스페이스를 만든다:
```c
clone(CLONE_NEWPID | CLONE_NEWNET | CLONE_NEWNS | ...)
```

`vfork()`는 `clone(CLONE_VFORK | CLONE_VM | SIGCHLD)`다. mm을 공유한 채 자식이 exec하거나 exit할 때까지 부모를 블록한다. exec 전 메모리 복사 비용을 아끼는 최적화였으나 현대에서는 COW+fork가 빠르다.

## 프로세스 상태 전이

```
               fork
                │
       TASK_RUNNING ←──────────────────────────────┐
            │   ↑                                   │
    I/O 대기 │   │ I/O 완료 / 시그널                │ 스케줄 (CPU 획득)
            ↓   │                                   │
  TASK_INTERRUPTIBLE ──시그널→ TASK_RUNNING      TASK_RUNNING
                                                 (run queue)
       TASK_UNINTERRUPTIBLE  ← I/O 대기(중단 불가)
            │
    I/O 완료 │
            ↓
       TASK_RUNNING

       TASK_STOPPED    ← SIGSTOP / SIGTSTP
            │
   SIGCONT  │
            ↓
       TASK_RUNNING

       TASK_ZOMBIE     ← do_exit() 후
            │
  wait()    │
            ↓
       TASK_DEAD
```

`TASK_UNINTERRUPTIBLE`(D 상태): 디스크 I/O를 기다리는 동안. 시그널을 무시한다. `kill -9`도 통하지 않는다. 이 상태가 오래 지속되면 I/O 장치나 NFS 문제일 가능성이 높다. `ps`에서 D로 표시된다.

## mm_struct와 vm_area_struct

`task_struct→mm`이 가리키는 `mm_struct`가 프로세스 전체 주소 공간을 표현한다:

```c
struct mm_struct {
    pgd_t *pgd;           // 페이지 테이블 최상위 (CR3에 넣을 물리 주소)
    struct vm_area_struct *mmap;  // VMA 링크드 리스트 (주소 오름차순)
    struct rb_root mm_rb; // VMA red-black tree (빠른 주소 탐색)
    int map_count;        // VMA 개수
    unsigned long start_code, end_code;
    unsigned long start_data, end_data;
    unsigned long start_brk, brk;     // heap 경계
    unsigned long start_stack;
    atomic_t mm_users;    // 이 mm을 공유하는 스레드 수
    atomic_t mm_count;    // 참조 카운트
};
```

`vm_area_struct`는 가상 주소 공간의 연속 영역 하나를 표현한다:

```c
struct vm_area_struct {
    unsigned long vm_start, vm_end;  // 가상 주소 범위 [start, end)
    unsigned long vm_flags;          // VM_READ, VM_WRITE, VM_EXEC, VM_SHARED...
    pgoff_t vm_pgoff;                // 파일 매핑이면 파일 내 페이지 오프셋
    struct file *vm_file;            // 파일 매핑이면 struct file*
    const struct vm_operations_struct *vm_ops;  // fault, open, close
    struct rb_node vm_rb;            // rb-tree 노드
};
```

`/proc/PID/maps`로 실행 중인 프로세스의 모든 VMA를 확인할 수 있다. 각 줄이 VMA 하나다.

## Copy-on-Write (COW)

`fork()` 시 부모의 물리 메모리를 즉시 복사하면 비용이 크다. COW는 이를 미룬다.

1. **fork 직후**: 부모·자식이 같은 물리 페이지를 공유한다. 두 프로세스의 PTE가 같은 물리 프레임을 가리키되, 둘 다 **읽기 전용**으로 설정한다.

2. **쓰기 시도**: 어느 쪽이든 해당 페이지에 쓰기를 시도하면 → Page Fault(Protection Fault) 발생 → `do_wp_page()` 호출.

3. **페이지 복사**: 참조 카운트가 1이면(공유 중이 아니면) 그냥 쓰기 권한만 부여. 1보다 크면 새 물리 페이지를 할당하고 내용을 복사한 뒤, 쓰기 시도한 프로세스의 PTE를 새 페이지로 바꾼다.

COW 덕분에 `fork()` 후 즉시 `exec()`를 하면(shell의 일반적 패턴) 복사 비용이 거의 없다. exec가 mm을 통째로 교체하기 때문이다.

## 프로세스 종료와 zombie

`exit()` 또는 `return`으로 프로세스가 종료되면:

1. `do_exit()` 실행: 파일 닫기, 메모리 해제, 시그널 무시 설정, 상태를 `TASK_ZOMBIE`로 변경
2. 자식 프로세스가 있으면 PID 1(init/systemd)에 입양(reparent)
3. 부모에게 `SIGCHLD` 전송

부모가 `wait()`/`waitpid()`를 호출하면:
1. `task_struct`에서 종료 상태 수거
2. `task_struct` 해제 → 상태 `TASK_DEAD`

**Zombie 프로세스**: `TASK_ZOMBIE` 상태로 남은 프로세스. 메모리는 해제됐지만 `task_struct`는 부모가 `wait()`를 부를 때까지 남아 있다. `ps`에서 Z로 표시된다. 좀비가 많이 쌓이면 PID 고갈이 일어날 수 있다. 부모가 `SIGCHLD`를 무시하거나(`signal(SIGCHLD, SIG_IGN)`) `SA_NOCLDWAIT`를 설정하면 커널이 자동으로 좀비를 회수한다.

## 정리

커널에서 프로세스와 스레드는 모두 `task_struct`로, 차이는 mm/files/sighand 공유 여부다. `fork()`는 `copy_process()`로 자식 태스크를 만들고 COW로 메모리 복사를 지연한다. `exec()`는 mm을 교체하고 새 ELF를 올린다. `clone()`은 공유 범위를 플래그로 세밀하게 조절하며 스레드와 컨테이너 생성에 쓰인다. 프로세스 주소 공간은 `mm_struct`가 전체를, `vm_area_struct`가 각 영역을 표현한다. COW는 fork 후 실제 쓰기가 일어날 때만 복사해 비용을 아낀다. 종료 후 부모가 `wait()`를 부를 때까지 좀비 상태로 남는다.
