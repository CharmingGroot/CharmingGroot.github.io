---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "arch-04. 프로세스 가상 메모리 레이어 — VMA, 4단계 페이지 테이블, 페이지 폴트, mmap, Huge Pages"
date: 2026-06-20
tags: [virtual-memory, vma, page-table, mmu, tlb, page-fault, mmap, brk, huge-pages, thp, numa, mm_struct]
summary: "프로세스 가상 메모리의 두 레이어. 커널 소프트웨어 레이어(mm_struct/vm_area_struct)와 하드웨어 레이어(4단계 페이지 테이블/MMU/TLB). 페이지 폴트 핸들러 흐름, mmap/brk 내부 동작, Huge Pages(THP vs HugeTLB), NUMA 메모리 정책까지 정리한다."
slug: "arch-04-virtual-memory"
categories: ["시스템 아키텍처"]
---

프로세스의 가상 메모리는 두 레이어로 나뉜다. **커널 소프트웨어 레이어**: `mm_struct`와 `vm_area_struct`가 가상 주소 범위의 의미와 권한을 관리한다. **하드웨어 레이어**: 4단계 페이지 테이블과 MMU가 실제 주소 변환을 수행한다. 두 레이어가 협업하는 지점이 페이지 폴트다. 커널이 VMA를 보고 폴트가 합법인지 판단하고, 합법이면 페이지 테이블을 채워 MMU가 다음부터 직접 변환하게 한다.

## mm_struct: 프로세스 주소 공간 컨테이너

`task_struct→mm`이 가리키는 `mm_struct`가 프로세스 전체 가상 주소 공간을 관리한다.

```c
struct mm_struct {
    pgd_t *pgd;                   // 페이지 테이블 최상위 (물리 주소, CR3에 들어감)
    struct vm_area_struct *mmap;  // VMA 링크드 리스트 (주소 오름차순)
    struct rb_root mm_rb;         // VMA red-black tree (O(log n) 주소 탐색)
    int map_count;                // 현재 VMA 개수
    unsigned long mmap_base;      // mmap 영역 시작 주소
    unsigned long start_code, end_code;
    unsigned long start_data, end_data;
    unsigned long start_brk, brk; // heap 경계
    unsigned long start_stack;
    unsigned long total_vm;       // 전체 가상 페이지 수
    unsigned long locked_vm;      // mlock으로 고정된 페이지 수
    atomic_t mm_users;            // 공유 스레드 수
    atomic_t mm_count;            // 전체 참조 수
    struct mmu_notifier_subscriptions *notifier_subscriptions; // KVM 등이 훅
};
```

컨텍스트 스위치 시 `CR3 = __pa(mm->pgd)`로 페이지 테이블을 교체한다. 같은 스레드 그룹의 스레드들은 동일한 `mm_struct`를 가리키므로 주소 공간을 공유한다.

## vm_area_struct: 개별 가상 메모리 영역

VMA 하나가 가상 주소 공간의 연속 영역 하나를 표현한다. 같은 영역 안의 페이지들은 같은 권한과 속성을 가진다.

```c
struct vm_area_struct {
    unsigned long vm_start;       // 영역 시작 (inclusive)
    unsigned long vm_end;         // 영역 끝 (exclusive)
    unsigned long vm_flags;
    // VM_READ, VM_WRITE, VM_EXEC    접근 권한
    // VM_SHARED                      공유 매핑 여부
    // VM_GROWSDOWN                   스택처럼 아래로 자람
    // VM_DONTFORK                    fork 시 자식에게 복사 안 함
    // VM_LOCKED                      물리 메모리에 고정 (mlock)
    // VM_IO                          I/O 매핑 (캐시 bypass)
    // VM_PFNMAP                      물리 주소 직접 매핑 (드라이버)
    pgoff_t vm_pgoff;             // 파일 매핑이면 파일 내 페이지 오프셋
    struct file *vm_file;         // 파일 매핑이면 struct file*
    const struct vm_operations_struct *vm_ops;
    // .fault   → 페이지 폴트 처리
    // .open    → mmap 시 호출
    // .close   → munmap 시 호출
    // .mprotect, .madvise
    struct rb_node vm_rb;         // mm_rb 트리 노드
    struct list_head anon_vma_chain; // 반대 매핑(rmap)을 위한 링크
};
```

`/proc/PID/maps`로 현재 프로세스의 VMA 목록을 확인한다. 각 줄이 VMA 하나다:
```
7f3a1b400000-7f3a1b420000 r-xp 00000000 fd:01 12345  /lib/libc.so.6
주소 범위                  권한 파일오프셋 장치 inode  파일
```

## 4단계 페이지 테이블 (x86-64)

가상 주소 48비트를 4단계로 분할해 변환한다:

```
가상 주소 (48비트):
[PGD 9비트][PUD 9비트][PMD 9비트][PTE 9비트][페이지 내 오프셋 12비트]
   47-39      38-30      29-21      20-12         11-0
```

각 단계:
- **PGD (Page Global Directory)**: CR3이 가리키는 최상위 테이블. 512개 엔트리, 각 8바이트 → 4KB.
- **PUD (Page Upper Directory)**: PGD 엔트리가 가리킴. 역시 512 엔트리.
- **PMD (Page Middle Directory)**: PUD 엔트리가 가리킴. PMD 엔트리가 1GB 또는 2MB 페이지를 직접 가리킬 수 있다(Huge Page).
- **PTE (Page Table Entry)**: PMD 엔트리가 가리킴. 각 엔트리가 4KB 물리 프레임을 가리킨다.

PTE 플래그:
- Present(P): 물리 메모리에 있음
- Read/Write(R/W): 쓰기 허용 여부
- User/Supervisor(U/S): 유저 모드 접근 허용 여부
- Accessed(A), Dirty(D): 접근/수정 여부 (페이지 교체에 활용)
- NX(No-Execute): 코드 실행 금지

안 쓰는 영역은 상위 테이블 엔트리를 NULL로 두어 하위 테이블을 아예 만들지 않는다. 희소한 주소 공간을 메모리 효율적으로 표현한다.

5단계 페이지 테이블(LA57): PGD 위에 P4D를 추가해 57비트 가상 주소를 지원한다. `CONFIG_X86_5LEVEL` 커널 옵션.

## MMU와 TLB

**MMU**: CPU 내 하드웨어. 매 메모리 접근마다 가상→물리 주소 변환을 한다. 구체적으로는 Page Table Walker가 4단계 테이블을 따라 물리 프레임 번호를 찾는다(page walk). TLB 미스 시에만 walk한다.

**TLB (Translation Lookaside Buffer)**: 최근 변환 결과를 캐시하는 작은 CPU 내 캐시. 히트율이 높으면 page walk 없이 변환한다. TLB 엔트리는 (PCID, 가상 페이지 번호) → 물리 프레임 번호로 이뤄진다.

**PCID (Process-Context ID)**: 컨텍스트 스위치 시 TLB를 통째로 비우지 않게 해주는 기능이다. 각 프로세스마다 PCID를 부여하면 TLB에 여러 프로세스의 매핑을 공존시킬 수 있다. Meltdown 패치(KPTI) 도입 후 TLB 플러시 비용이 커져 PCID의 중요성이 높아졌다.

**TLB Shootdown**: 한 CPU가 페이지 테이블을 수정하면 다른 CPU의 TLB에 있는 stale 엔트리를 무효화해야 한다. IPI(Inter-Processor Interrupt)를 보내 다른 코어가 TLB 무효화 함수를 실행하게 한다. 대규모 munmap이나 mprotect 시 모든 코어에 IPI가 날아가 성능 병목이 될 수 있다.

## 페이지 폴트 핸들러 상세

Present=0이거나 권한 위반이면 CPU가 `#PF` 예외를 발생시키고 `do_page_fault()`가 호출된다. CR2 레지스터에 폴트를 일으킨 가상 주소가 담긴다.

```
do_page_fault(fault_address, error_code)
├── find_vma(mm, fault_address)
│   ├── VMA 없음 → SIGSEGV  (잘못된 주소 접근)
│   └── VMA 있음 → handle_mm_fault()
│       ├── 권한 위반 (write to RO page)
│       │   └── COW 페이지? → do_wp_page()  → 페이지 복사
│       │   └── 진짜 위반 → SIGSEGV
│       ├── Present=0, anonymous VMA
│       │   └── do_anonymous_page() → 새 물리 페이지 할당, 0 초기화, PTE 업데이트
│       ├── Present=0, file-backed VMA
│       │   └── do_fault() → vm_ops->fault() → 페이지 캐시에서 읽기 또는 디스크 I/O
│       └── Present=0, swap VMA
│           └── do_swap_page() → swap 영역에서 읽기, PTE 업데이트
```

**마이너 폴트(minor fault)**: 물리 페이지가 이미 메모리에 있는데 PTE만 없는 경우. 페이지 캐시 히트, COW에서 부모가 이미 할당한 페이지 재사용. I/O 없이 PTE만 채우면 된다.

**메이저 폴트(major fault)**: 물리 페이지가 디스크에 있어 I/O가 필요한 경우. 아직 한 번도 읽지 않은 실행 파일 페이지, swap된 페이지. 페이지 폴트 자체가 비싼 I/O를 유발한다.

`/proc/PID/stat`의 minor_flt, major_flt 필드 또는 `ps -o min_flt,maj_flt`로 확인한다.

## mmap() 내부 동작

```c
void *mmap(void *addr, size_t len, int prot, int flags, int fd, off_t offset);
```

`mmap()` syscall → `do_mmap()` → `mmap_region()`:

1. 요청 범위에 겹치는 기존 VMA 처리 (분할 또는 실패)
2. 새 `vm_area_struct` 할당 및 설정
3. `vm_flags` 설정 (prot → VM_READ/VM_WRITE/VM_EXEC)
4. **파일 매핑** (`fd != -1`): `vm_file = filp`, `vm_pgoff = offset`, `file->f_op->mmap()` 호출 → `vm_ops` 설정
5. **Anonymous 매핑** (`MAP_ANONYMOUS`): `vm_file = NULL`, `vm_pgoff = 0`
6. VMA를 mm의 리스트와 rb-tree에 삽입

물리 페이지는 아직 할당하지 않는다. 이후 해당 주소 접근 시 페이지 폴트가 나고 그때 물리 페이지를 올린다(디맨드 페이징).

`MAP_SHARED` 파일 매핑: 여러 프로세스가 같은 물리 페이지를 공유한다. 한쪽 수정이 다른 쪽에 즉시 보인다. 페이지 캐시 페이지를 직접 매핑하는 것이다.

`MAP_PRIVATE` 파일 매핑: 초기에는 페이지 캐시 공유. 쓰기 시 COW로 복사 후 수정. 파일에 반영 안 됨. 실행 파일 로딩에 쓴다.

## brk/sbrk와 힙 확장

```c
int brk(void *addr);       // heap 끝(mm->brk) 을 addr로 이동
void *sbrk(intptr_t inc);  // heap을 inc만큼 늘리거나 줄임
```

`brk()` syscall → `do_brk_flags()` → 새 anonymous VMA 추가 또는 기존 VMA 확장.

glibc의 `malloc()` 내부 동작:
- 작은 할당(< MMAP_THRESHOLD, 기본 128KB): `sbrk()`로 heap 영역에서 청크 할당. ptmalloc2가 chunk 경계와 freelist를 관리.
- 큰 할당(≥ MMAP_THRESHOLD): `mmap(MAP_ANONYMOUS)`로 독립 영역 할당. `free()` 시 즉시 `munmap()`으로 반환.

## Huge Pages

4KB 페이지 대신 큰 페이지를 써서 TLB 커버 범위를 늘리는 기법이다.

**THP (Transparent Huge Pages)**: 커널이 자동으로 연속된 4KB 페이지들을 2MB 페이지로 합친다. 애플리케이션 코드 변경 불필요.
- `/sys/kernel/mm/transparent_hugepage/enabled`: `always | madvise | never`
- `khugepaged` 데몬이 백그라운드에서 페이지 병합
- `madvise(MADV_HUGEPAGE)`: 특정 영역에 THP를 적극 사용
- 단점: 병합 시 CPU 오버헤드, 메모리 단편화(2MB 정렬 필요)

**HugeTLB (Explicit Huge Pages)**: 관리자가 미리 큰 페이지를 예약해 두고 명시적으로 사용한다.
- `/proc/sys/vm/nr_hugepages`: 예약할 2MB 페이지 수
- `/proc/sys/vm/nr_overcommit_hugepages`: 추가 허용 수
- `mmap(MAP_ANONYMOUS | MAP_HUGETLB, ...)` 또는 `/dev/hugepages` 파일시스템
- HugePages는 스왑되지 않아 지연이 예측 가능하다
- Oracle DB, Redis 같은 메모리 집약적 애플리케이션에서 성능 향상이 크다

TLB 효과: 2MB 페이지는 TLB 엔트리 하나로 4KB 페이지 512개 분량을 커버한다. 대규모 메모리를 쓰는 워크로드에서 TLB miss가 대폭 줄어든다.

## NUMA 메모리 정책

멀티 소켓 서버에서 메모리 접근 지연이 소켓마다 다르다. 커널은 VMA 단위로 NUMA 정책을 설정할 수 있다.

**정책 종류**:
- `MPOL_DEFAULT`: 현재 CPU 소켓의 로컬 노드에서 할당(기본)
- `MPOL_BIND`: 지정한 노드에서만 할당. 없으면 대기
- `MPOL_INTERLEAVE`: 지정 노드들에 라운드로빈으로 할당. 여러 노드에 분산
- `MPOL_PREFERRED`: 선호 노드, 없으면 다른 노드

`mbind(addr, len, mode, nodemask, maxnode, flags)` syscall로 VMA 단위 정책 설정.
`set_mempolicy(mode, nodemask, maxnode)` syscall로 스레드 기본 정책 설정.
`numactl --interleave=all ./app` 로 프로세스 전체에 적용.

`/proc/PID/numa_maps`로 프로세스의 VMA별 NUMA 정책과 실제 노드 배분을 확인한다.

## 정리

프로세스 가상 메모리는 두 레이어다. 커널 레이어: `mm_struct`가 전체 주소 공간을 관리하고, `vm_area_struct`가 각 영역의 권한과 매핑 방식을 정의한다. 하드웨어 레이어: 4단계 페이지 테이블이 GVA→HPA 변환 정보를 담고, MMU가 변환을 실행하며, TLB가 결과를 캐시한다. 두 레이어의 교차점이 페이지 폴트다: PTE가 없거나 권한 위반이면 커널이 VMA를 검사해 합법성을 판단하고, 합법이면 물리 페이지를 할당하거나 I/O해서 PTE를 채운다. mmap은 VMA만 만들고 물리 페이지는 첫 접근 시 할당한다. Huge Pages는 TLB 커버 범위를 늘려 대규모 메모리 워크로드의 성능을 올린다. NUMA 정책은 VMA 단위로 메모리 할당 노드를 제어한다.
