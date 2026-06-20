---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-01. 커널 — 내부 구조, 메모리 레이아웃, 동기화, 자료구조, eBPF"
date: 2026-06-20
tags: [kernel, linux, kernel-memory, buddy-allocator, slab, spinlock, rcu, rbtree, ebpf, kernel-module, boot]
summary: "커널이 하드웨어 위에서 어떻게 구성되는지. 부트 과정, 커널 메모리 레이아웃(direct map/vmalloc/fixmap), 커널 스택, 동기화 원시 연산(spinlock/mutex/RCU), 커널 자료구조(list_head/rbtree/radix_tree), 모듈 시스템, eBPF까지 정리한다."
slug: "arch-01-kernel"
categories: ["시스템 아키텍처"]
---

커널은 하드웨어 위에서 가장 먼저 실행되는 소프트웨어다. 부팅 직후 커널이 초기화되면 그 이후의 모든 것(프로세스, 파일 시스템, 네트워크)은 커널이 제공하는 추상 위에서 돈다. 커널 자체가 어떻게 구성되고 메모리에 어떻게 올라가는지를 모르면, 그 위의 모든 것이 마법처럼 보인다.

## 부트 과정

**BIOS/UEFI → GRUB**: 전원 인가 후 CPU는 미리 정해진 주소(x86: 0xFFFFFFF0)에서 실행을 시작한다. BIOS/UEFI가 하드웨어 초기화(POST)를 하고 부트 장치에서 부트로더(GRUB)를 로드한다. GRUB는 압축된 커널 이미지(vmlinuz)와 initramfs를 메모리에 올리고 커널 진입점으로 점프한다.

**커널 초기화**: 압축 해제 후 `start_kernel()`이 호출된다. 이 함수 하나가 커널의 모든 서브시스템 초기화를 순서대로 진행한다.

```
start_kernel()
├── setup_arch()         아키텍처 초기화(페이징, ACPI, APIC)
├── mm_init()            메모리 관리자 초기화(buddy, slab)
├── sched_init()         스케줄러 초기화(runqueue, CFS)
├── time_init()          타이머/클럭 초기화
├── vfs_caches_init()    VFS 캐시 초기화
├── signals_init()       시그널 큐 초기화
└── rest_init()          → kernel_thread(kernel_init)
                           → kernel_init() → execve("/sbin/init")
```

`rest_init()` 이후 PID 1(init/systemd)이 유저 공간에서 시작된다. 커널 메인 스레드(idle thread, PID 0)는 CPU가 아무것도 할 일이 없을 때 실행된다.

**initramfs**: 실제 루트 파일 시스템을 마운트하기 전에 임시 루트를 제공하는 메모리 기반 파일 시스템이다. 드라이버 로드, 암호화 볼륨 해제, RAID 조립 등을 처리한 뒤 실제 루트로 전환한다.

## 커널 메모리 레이아웃

유저 공간 주소와 커널 주소는 같은 가상 주소 공간 안에서 분리된다. x86-64 기준, 가상 주소 공간은 128TB(47비트)씩 둘로 나뉜다.

```
0x0000_0000_0000_0000 ~ 0x0000_7FFF_FFFF_FFFF   유저 공간 (128TB)
                  [canonical hole — 접근 불가]
0xFFFF_8000_0000_0000 ~ 0xFFFF_FFFF_FFFF_FFFF   커널 공간 (128TB)
```

커널 공간 안의 주요 영역:

- **Direct mapping (PAGE_OFFSET)**: 물리 메모리 전체를 가상 주소에 1:1로 매핑한 영역. `phys_to_virt()`/`virt_to_phys()` 변환이 단순한 덧셈이다. 커널이 물리 메모리를 직접 다룰 때 이 영역을 쓴다.
- **vmalloc**: 물리적으로 흩어진 페이지를 가상으로 연속되게 매핑하는 영역. 큰 커널 자료구조나 모듈 코드가 올라간다.
- **kernel text/data/bss**: 커널 코드와 정적 데이터. `_text ~ _etext`, `_sdata ~ _edata`
- **fixmap**: 컴파일 타임에 고정된 가상 주소에 특수 목적 매핑을 두는 영역. APIC, ACPI 테이블 접근 등에 쓰인다.
- **modules**: `insmod`로 로드된 커널 모듈 코드가 올라가는 영역.

`/proc/iomem`으로 물리 메모리 맵, `/proc/kallsyms`로 커널 심볼과 주소를 확인한다.

## 커널 스택

프로세스마다 커널 스택이 따로 있다(x86-64: 기본 16KB). 유저 모드에서 syscall이나 인터럽트가 발생해 커널 모드로 진입할 때 이 스택으로 전환된다. 커널 스택은 작기 때문에 커널 함수에서 큰 지역 변수를 쓰거나 재귀 호출이 깊어지면 스택 오버플로가 난다(`CONFIG_KASAN`, `CONFIG_KSTACKDET`으로 감지).

인터럽트 처리는 별도 IRQ 스택을 쓴다. 그래야 인터럽트 핸들러가 현재 실행 중인 프로세스의 커널 스택에 영향을 주지 않는다.

## 커널 동기화

커널 코드는 여러 CPU에서 동시에 실행될 수 있고, 인터럽트도 언제든 끼어들 수 있다. 공유 자료구조를 보호하는 여러 원시 연산이 있다.

**Spinlock**: 잠금을 얻을 때까지 CPU를 점유하며 바쁘게 대기한다. 짧은 임계 구역에 적합하다. spinlock을 잡은 상태에서 sleep할 수 없다(스케줄러가 개입하면 데드락). `spin_lock_irqsave()`는 인터럽트도 함께 비활성화한다.

**Mutex**: 잠금을 얻지 못하면 태스크를 대기 큐에 넣고 sleep한다. 잠금이 해제되면 깨어난다. 긴 임계 구역에 적합하다. sleep이 가능하므로 인터럽트 핸들러(atomic context)에서는 쓸 수 없다.

**RCU (Read-Copy-Update)**: 읽기가 압도적으로 많은 자료구조(라우팅 테이블, 프로세스 목록)를 위한 동기화 메커니즘이다. 읽기는 잠금 없이 수행한다. 쓰기는 새 버전을 만들어 포인터를 교체하고(atomic), 이전 버전은 모든 CPU가 참조를 끝낸 뒤(grace period) 해제한다. 읽기 성능이 극히 높다.

**Atomic operations**: 단일 CPU 명령으로 수행되는 연산(atomic_inc, atomic_add, cmpxchg). 간단한 카운터나 플래그에 쓴다.

**Memory barriers**: 컴파일러와 CPU의 명령 재순서화를 막는다. `smp_rmb()`, `smp_wmb()`, `smp_mb()`. 잠금을 쓰면 묵시적으로 포함되지만, 잠금 없는 알고리즘에서는 명시적으로 필요하다.

## 커널 자료구조

**list_head**: 원형 이중 연결 리스트. 구조체 안에 `list_head` 멤버를 포함시켜 사용한다. `list_entry(ptr, type, member)` 매크로로 포함 구조체를 역산한다. 프로세스 목록, 모듈 목록 등 커널 전반에서 쓴다.

**rb_root / rb_node**: Red-Black Tree. 삽입·삭제·탐색 O(log n). CFS 스케줄러의 런큐(vruntime 순서), VMA 관리(주소 범위 탐색), 타이머 관리에 쓴다.

**radix_tree (XArray)**: 페이지 캐시 인덱스(파일 오프셋 → struct page). 스파스한 인덱스를 효율적으로 표현한다. 최근 커널은 XArray로 통합됐다.

**Per-CPU 변수**: `DEFINE_PER_CPU(type, var)`로 선언하면 코어마다 독립된 복사본이 생긴다. 접근 시 잠금 불필요. CPU 카운터, 스케줄러 통계, 네트워크 통계에 쓴다. `this_cpu_read()`/`this_cpu_write()`로 접근한다.

## 커널 모듈

커널 기능을 런타임에 로드·언로드할 수 있는 `.ko` 파일이다. 주로 디바이스 드라이버와 파일 시스템에 쓴다.

```c
static int __init mymod_init(void) { /* 로드 시 실행 */ return 0; }
static void __exit mymod_exit(void) { /* 언로드 시 실행 */ }
module_init(mymod_init);
module_exit(mymod_exit);
MODULE_LICENSE("GPL");
```

`insmod`/`modprobe`로 로드, `rmmod`로 언로드, `lsmod`로 목록 확인. 모듈 코드는 커널 공간의 modules 영역에 올라가 ring 0에서 실행되므로 버그가 커널 패닉으로 이어진다.

## eBPF

커널 안에서 안전하게 실행되는 바이트코드 VM이다. 커널을 재컴파일하거나 모듈을 쓰지 않고 커널 이벤트에 동적으로 코드를 붙일 수 있다.

**핵심 구성**:
- **Verifier**: 로드 시 바이트코드를 정적 분석해 무한 루프·잘못된 메모리 접근·권한 위반을 사전 차단한다. 안전하다고 검증된 코드만 JIT 컴파일 후 실행된다.
- **BPF Map**: 유저 공간과 커널 eBPF 프로그램 사이의 데이터 공유 자료구조. Hash, Array, RingBuffer, PerfEvent 등.
- **Attach point**: kprobe(임의 커널 함수), tracepoint(커널 정의 이벤트), XDP(네트워크 패킷 수신 최초 지점), cgroup(cgroup 이벤트), LSM hook, syscall 진입·퇴출.

**사용 예**:
```bash
bpftrace -e 'kprobe:do_sys_open { printf("%s\n", str(arg1)); }'  # 파일 열기 추적
bpftrace -e 'tracepoint:sched:sched_switch { @[args->next_comm] = count(); }'
```

BCC(Python), bpftrace(고수준 언어), libbpf(C)가 주요 프론트엔드다. Falco, Cilium, Tetragon 같은 보안·네트워크 도구가 eBPF 기반이다.

## 정리

커널은 부트 후 서브시스템을 순서대로 초기화하고, PID 1로 유저 공간을 시작한다. 커널 주소 공간은 direct map, vmalloc, text/data, modules 영역으로 나뉜다. 프로세스마다 커널 스택이 따로 있어 ring 전환 시 사용한다. 공유 자료구조는 spinlock(짧은 임계 구역), mutex(긴 임계 구역), RCU(읽기 다수), atomic으로 보호한다. 핵심 자료구조는 list_head(리스트), rb_root(트리), XArray(인덱스), per-CPU 변수다. 모듈은 ring 0에서 실행되므로 버그가 치명적이다. eBPF는 verifier가 보장하는 안전한 커널 내 프로그래밍으로 관측·제어의 기반이 됐다.
