---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "026. Kubernetes Job & CronJob — 일회성 작업과 주기적 작업"
date: 2026-06-12
tags: [kubernetes, k8s, job, cronjob, batch, parallel, completions, backoff, schedule]
summary: "Deployment는 파드를 계속 실행 상태로 유지하지만, 데이터 마이그레이션이나 리포트 생성처럼 한 번 실행하고 끝나는 작업도 있다. Job은 파드가 성공적으로 완료될 때까지 실행을 보장하고, CronJob은 Job을 cron 표현식으로 주기적으로 실행한다. 완료 보장 메커니즘, 병렬 실행, 실패 처리, 그리고 CronJob의 주의사항을 설명한다."
slug: "026-k8s-job-cronjob"
categories: ["쿠버네티스"]
---

Deployment, StatefulSet, DaemonSet은 모두 파드를 계속 실행 상태로 유지하려 한다. 파드가 종료되면 다시 살린다. 하지만 DB 마이그레이션, 리포트 생성, 이메일 일괄 발송처럼 **한 번 실행하고 성공적으로 끝나면 되는 작업**은 이 모델이 맞지 않는다. 끝난 파드를 다시 살릴 필요가 없고, 오히려 실수로 두 번 실행되면 안 되는 경우도 있다.

Job은 파드가 **성공적으로 완료(exit code 0)** 될 때까지 실행을 보장하는 오브젝트다. 파드가 실패하면 재시도하고, 성공하면 멈춘다. CronJob은 Job을 cron 표현식으로 주기적으로 생성한다.

## Job 기본 구조

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
spec:
  completions: 1          # 성공적으로 완료할 파드 수 (기본값 1)
  parallelism: 1          # 동시에 실행할 파드 수 (기본값 1)
  backoffLimit: 3         # 실패 시 재시도 횟수 (기본값 6)
  activeDeadlineSeconds: 300   # 최대 실행 시간 (초). 초과 시 강제 종료
  ttlSecondsAfterFinished: 600 # 완료 후 이 시간이 지나면 Job과 파드 자동 삭제
  template:
    spec:
      restartPolicy: Never      # Job 파드는 Never 또는 OnFailure만 가능
      containers:
      - name: migration
        image: my-app:1.0.0
        command: ["python", "manage.py", "migrate"]
        env:
        - name: DB_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
```

`restartPolicy`는 `Never` 또는 `OnFailure`만 쓸 수 있다. Deployment의 기본값인 `Always`는 Job에 쓸 수 없다.

`Never`: 파드가 실패하면 새 파드를 만들어 재시도한다. 실패한 파드는 삭제되지 않아 로그를 볼 수 있다.

`OnFailure`: 같은 파드를 재시작한다. 파드가 살아있어 IP가 유지되지만, 재시작 전 상태(임시 파일 등)가 남아있을 수 있다.

`backoffLimit`만큼 재시도를 모두 소진하면 Job은 Failed 상태가 된다.

## 병렬 실행

completions와 parallelism을 조합해 병렬 배치 처리를 구성할 수 있다.

```yaml
spec:
  completions: 10     # 총 10개 파드가 성공해야 완료
  parallelism: 3      # 동시에 3개씩 실행
```

10개 작업을 3개씩 병렬로 실행해 완료된 것부터 채워나간다. 큰 데이터셋을 파티션으로 나눠 처리하거나, 독립적인 작업 목록을 빠르게 처리할 때 쓴다.

작업 목록을 Job에 어떻게 전달하느냐는 별도 패턴이 필요하다. 환경변수로 인덱스를 넘기거나(`JOB_COMPLETION_INDEX`, k8s 1.21+에서 자동 주입), 메시지 큐(Redis, RabbitMQ)에서 파드가 직접 가져오는 방식이 흔하다.

## CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: report-generator
spec:
  schedule: "0 9 * * 1-5"        # 평일 오전 9시
  timeZone: "Asia/Seoul"          # k8s 1.27+
  concurrencyPolicy: Forbid       # 이전 Job이 아직 실행 중이면 새 Job 생성 안 함
  successfulJobsHistoryLimit: 3   # 성공한 Job 기록 보존 수
  failedJobsHistoryLimit: 1       # 실패한 Job 기록 보존 수
  startingDeadlineSeconds: 60     # 예정 시각에서 이 초 이내에 못 시작하면 건너뜀
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: reporter
            image: my-reporter:1.0.0
```

cron 표현식은 `분 시 일 월 요일` 순이다. `0 9 * * 1-5`는 월~금 09:00.

`timeZone`이 없으면 UTC 기준이다. 한국 시간으로 실행하려면 명시해야 한다.

### concurrencyPolicy — 가장 중요한 설정

이전 실행이 아직 끝나지 않았는데 다음 실행 시각이 되면 어떻게 할지 정한다.

`Allow`(기본값): 이전 Job이 실행 중이어도 새 Job을 만든다. DB에 동시에 두 Job이 쓰는 상황이 생길 수 있다.

`Forbid`: 이전 Job이 아직 실행 중이면 새 Job을 건너뛴다. 멱등성이 없는 작업에 적합하다.

`Replace`: 이전 Job을 종료하고 새 Job을 시작한다.

작업 시간이 실행 간격보다 길어질 수 있다면 `Forbid`를 기본으로 두는 것이 안전하다.

### 놓친 실행(missed schedule)

컨트롤 플레인이 내려가 있던 동안 예정된 실행을 놓쳤다면, `startingDeadlineSeconds` 안에 있으면 재시작 시 밀린 실행을 처리한다. 오래 내려가 있었다면 밀린 실행이 쏟아질 수 있다. 이를 막으려면 `startingDeadlineSeconds`를 짧게 잡아 너무 오래된 실행은 건너뛰게 한다.

## ttlSecondsAfterFinished — Job 자동 정리

완료된 Job과 파드는 자동으로 삭제되지 않는다. 방치하면 완료된 파드들이 쌓인다. `ttlSecondsAfterFinished`로 완료 후 일정 시간이 지나면 자동으로 정리되게 한다. 로그를 충분히 확인할 시간을 주되, 무한정 남겨두지 않는 균형점을 잡으면 된다.

## 트레이드오프

Job은 **최소 한 번(at-least-once)** 실행을 보장한다. 파드가 실패한 뒤 재시도하는 과정에서 작업이 두 번 실행될 수 있다. 특히 `restartPolicy: OnFailure`는 파드를 재시작하므로 이전 실행이 중간에 실패했어도 처음부터 다시 시작한다. 중복 실행이 문제라면 작업을 **멱등성(idempotent)** 있게 설계해야 한다. DB 마이그레이션에서 `IF NOT EXISTS`를 쓰거나, 처리 상태를 기록해 이미 처리된 것은 건너뛰는 식이다.

CronJob은 Job을 만드는 것을 보장하지만 실행 완료를 보장하지는 않는다. 실행 시각에 클러스터 자원이 없으면 파드가 Pending 상태로 머물 수 있다. 중요한 주기 작업이라면 완료 여부를 모니터링하고, 실패 시 알림을 받는 체계가 필요하다.
