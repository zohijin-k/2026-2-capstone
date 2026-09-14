# Trellis 하네스 — 셋업 가이드 (Windows)

> 대상: 2026-2-capstone TF 팀원 (엔진 / 데모사이트 / 대시보드)
> 최종 수정: 2026-09-14
> **Mac 사용자는 [TRELLIS_SETUP_MAC.md](./TRELLIS_SETUP_MAC.md)를 볼 것.**

---

## 현재 상태 — 먼저 읽을 것

| 항목 | 상태 |
|---|---|
| 저장소 Trellis 초기 도입 | **완료** (hcw889, 2026-09-14) |
| Trellis 버전 | **0.6.17** (`.trellis/.version`) |
| 팀원이 할 일 | **1 → 2 → 3 → 4 순서로 따라 하면 끝.** 4장의 "첫 도입" 절차는 **하지 말 것.** |

이 문서에서 `hcw889`가 나오면 채운(대시보드)이고, 그 외 이름 자리는 **본인 ID**로 바꿔 읽는다.

---

## 0. 왜 Trellis인가

우리 팀은 역할이 셋으로 쪼개져 있는데(**엔진 / 데모사이트 / 대시보드**) 저장소는 아직 합류 전이다.
README에 이미 적혀 있는 대로, 다음 세 군데에서 **인터페이스가 어긋나는 게 확정적**이다.

1. `doc_type` 문자열 — `config.REQUIRED_DOCUMENTS`의 `"주민등록등본"` 등과 OCR 분류 라벨이 **정확히 일치**해야 매칭된다
2. `Document` / `Applicant` 스키마 — 데모사이트가 넘기고, 엔진이 받고, 대시보드가 집계하는 **유일한 접점**
3. `config.py`의 가정값 — 전부 가짜값이고 9/15 TF 이후 교체해야 한다

Trellis는 이걸 **저장소 안의 spec**으로 고정하고, 세션마다 AI에 자동 주입한다.

| 우리 목적 | Trellis의 대응 |
|---|---|
| 컨텍스트 공유 | `.trellis/spec/` — git으로 공유, 세션마다 자동 주입 |
| 팀원별 위키 | `.trellis/workspace/{ID}/` — 사람별로 분리되어 머지 충돌 없음 |
| 트러블슈팅 | `trellis-check` → `trellis-update-spec` — 삽질이 spec으로 환류 |

Claude Code 포함 20여 개 플랫폼을 지원하므로, 팀원이 각자 다른 도구를 써도 **같은 구조**를 쓴다.

> **라이선스 주의:** Trellis는 **AGPL-3.0**이다. 프레임워크 자체의 라이선스이고 우리 코드에 전염되지 않는다.
> 다만 나중에 개발사(나루)에 코드를 넘길 때 `.trellis/`를 포함할지 여부는 미리 정해두자.

---

## 1. 사전 준비 (머신당 1회)

### 요구사항

| 항목 | 버전 | 용도 |
|---|---|---|
| Node.js | **18 이상** | Trellis CLI 본체 |
| Python | **3.9 이상** | `.trellis/scripts/*.py` + Claude Code 훅 전부 |
| Git | - | 이미 있음 |

Python은 장식이 아니다. 세션 시작 훅, 태스크 관리, 저널 기록이 **전부 Python**이라 없으면 하네스가 통째로 안 돈다.
(참고: 우리 엔진도 Python이므로 어차피 필요하다.)

### 이미 깔려 있는지 먼저 확인

```powershell
node -v; npm -v; python --version; git --version
```

셋 다 버전이 찍히면 **설치 건너뛰고 2장으로.** (OSLAB PC는 Node 24 / Python 3.13 / Git 2.55로 이미 통과.)

### 설치 (없는 것만 / winget)

```powershell
winget install OpenJS.NodeJS.LTS
```

```powershell
winget install Python.Python.3.13
```

### 설치 직후 반드시 — 터미널을 새로 열 것

**이게 제일 많이 걸리는 함정이다.**
프로세스는 시작할 때 PATH를 복사해두고, 그 뒤의 변경은 반영하지 않는다.
설치 전에 열어둔 PowerShell 창에서는 설치가 끝나도 계속 이 에러가 난다:

```
npm : 'npm' 용어가 cmdlet, 함수, 스크립트 파일 또는 실행할 수 있는 프로그램 이름으로 인식되지 않습니다.
```

**해결 1 (권장):** PowerShell 창을 닫고 새로 연다.

**해결 2:** 창을 유지한 채 PATH만 다시 읽는다.

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

### 확인

```powershell
node -v; npm -v; python --version
```

셋 다 버전이 찍히면 통과다.

> **`python`이 아무것도 안 찍거나 Microsoft Store가 열리는 경우** — Windows 앱 실행 별칭(스텁)이
> 실제 Python보다 PATH 앞에 있는 것이다. `설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭`에서
> `python.exe` / `python3.exe`를 끄면 된다.
> (OSLAB PC에서는 실제 Python이 앞순위여서 이 조치가 필요 없었다. 기기마다 다를 수 있다.)

---

## 2. Trellis CLI 설치 (머신당 1회, 위치 무관)

`-g`는 **전역 설치**다. 저장소 안에서 할 필요가 없다. 아무 디렉토리에서나 한 번만 하면 된다.

**저장소에 기록된 버전(`0.6.17`)에 맞춰서** 깐다. `@latest`를 쓰지 않는 이유는 7장 [버전 규칙](#버전-규칙) 참고.

```powershell
npm install -g @mindfoldhq/trellis@0.6.17
```

```powershell
trellis --version
```

`0.6.17`이 찍히면 통과다.

> `trellis` 명령을 못 찾으면 → 터미널을 새로 연다. 그래도 안 되면 `%APPDATA%\npm`이 PATH에 있는지 확인.

---

## 3. 저장소 준비

```powershell
git clone https://github.com/zohijin-k/2026-2-capstone.git C:\dev\2026-2-capstone
```

> **경로에 공백·한글을 넣지 말 것.** Windows에서 npm CLI + Python 스크립트를 섞어 쓸 때
> 흔한 마찰 지점이다. `C:\dev\2026-2-capstone` 같은 순수 ASCII 경로를 권한다.
> (`C:\Users\<영문ID>\Desktop\...`도 공백·한글만 없으면 된다. 중요한 건 **클론을 한 곳에만 두는 것**이다.
> 두 군데 클론해두면 어느 쪽에 `.trellis/`가 있는지부터 헷갈린다.)
>
> 원본 자료 폴더(`캡스톤 초기자료`)는 그대로 두고, **코드 작업만** 이 경로에서 한다.

이미 클론이 있다면:

```powershell
cd C:\dev\2026-2-capstone; git pull
```

pull 후 루트에 `.trellis/`, `.claude/`, `AGENTS.md`, `.gitattributes`가 보이면 정상이다.

---

## 4. 개발자 신원 등록 (기기당 1회)

> ### 가장 중요한 규칙
> `trellis init`을 실행했을 때 선택지가 3개 뜨면,
> **`Full re-initialize`는 절대 고르지 말 것.**
> 기존 `.trellis/`, `.claude/` 설정을 통째로 덮어써서 **팀 전체에 영향이 간다.**

### 4-A. 첫 도입 — 이미 끝났다. 하지 말 것.

`trellis init -u hcw889 --claude`는 **2026-09-14에 hcw889가 이미 실행했고, 그 결과물(`.trellis/`, `.claude/`)이 커밋돼 있다.**
`--claude` 같은 플랫폼 플래그는 **붙이지 않는다** — 이미 설정돼 있고, 다시 붙이면 생성 파일을 다시 써서 불필요한 diff가 생긴다.
**팀원은 아래 4-B만 한다.**

### 4-B. 팀원이 할 것

저장소 루트에서:

```powershell
trellis init -u <본인ID>
```

`.trellis/`가 이미 있는 저장소에서 `-u`를 주면 **메뉴 없이 바로 신원 등록**만 한다. 옵션 없이 `trellis init`만 치면 선택지 3개가 뜨는데, 그때는 **`Set up developer identity on this device`** 를 고른다 (결과는 같다).

- `<본인ID>`는 [이름 규약](#이름-규약) 참고. 메뉴로 갔다면 Git `user.name`이 기본값으로 뜬다 → 그대로 써도 된다.
- `.trellis/.developer` (gitignore, 기기별)에 본인 이름이 기록됨
- `.trellis/workspace/{본인ID}/`가 생성됨 — **이건 커밋 대상**이다
- `.trellis/tasks/00-join-{본인ID}/` **온보딩 태스크가 자동 생성**된다 — 첫 세션에서 이 태스크가 활성 태스크가 되고, AI가 워크플로우를 안내해준다. 다 봤으면 `/trellis:finish-work`로 아카이브한다.

이 구조 덕분에 **세 명이 같은 저장소를 써도 저널이 충돌하지 않는다.**

### 4-C. 세션이 제대로 열리는지 확인

Trellis는 **Claude Code 세션이 시작될 때 훅으로 컨텍스트를 주입**한다. 훅이 안 돌면 하네스는 없는 거나 마찬가지다. 아래 셋을 확인한다.

**① 저장소 루트에서 세션을 열어야 한다.**
VS Code라면 *파일 → 폴더 열기*로 `C:\dev\2026-2-capstone`을 **직접** 연다. 상위 폴더(`C:\dev`)를 열고 그 안에서 세션을 시작하면 `.claude/settings.json`을 못 봐서 훅이 안 돈다. 터미널이라면:

```powershell
cd C:\dev\2026-2-capstone; claude
```

**② 처음 열 때 훅/폴더 신뢰 여부를 물으면 허용한다.** 거부하면 루트에서 열어도 훅이 안 돈다.

**③ 확인.** 세션 첫 메시지로 이렇게 물어본다:

```
현재 활성 Trellis 태스크가 뭐야?
```

`00-join-<본인ID>`라고 답하면 통과. "모르겠다"거나 `.trellis/`를 직접 뒤지기 시작하면 훅이 안 돈 것이다.
파일로 확인하려면: 훅이 돌면 `.trellis\.runtime\` 폴더가 생긴다.

---

## 5. spec — 팀원이 검토·수정하는 것

`.trellis/spec/`은 AI가 세션마다 읽는 **팀 규약**이다. `init`은 빈 템플릿만 만들고,
첫 도입자(hcw889)가 `trellis-spec-bootstrap` 스킬로 실제 코드에서 초안을 뽑는다.

**팀원이 할 일은 "쓰기"가 아니라 "검토"다.** pull 후 본인 파트와 관련된 spec을 읽고,
틀렸거나 빠진 걸 **PR로** 고친다. spec은 코드처럼 리뷰한다.

### 우리 프로젝트 spec에 반드시 들어가야 할 3가지

0장에서 짚은 리스크 그대로다. 없으면 만들고, 틀리면 고쳐라.

1. **`doc_type` 문자열 표** — 엔진의 `config.REQUIRED_DOCUMENTS` ↔ 데모사이트 OCR 분류 라벨 (지빈 ↔ 진)
2. **`Document` / `Applicant` 스키마 계약** — 필드, 타입, 제약, 에러 케이스 (셋 다)
3. **`config.py` 가정값 대장** — 무엇이 가짜값이고 9/15 TF에서 뭘로 바뀌어야 하는지 (진)

Trellis가 정의한 **인프라/레이어 교차 변경 7항목 서식**이 정확히 이 용도다:

```
1. Scope / Trigger
2. Signatures
3. Contracts (fields, types, constraints)   ← 2번이 여기 들어간다
4. Validation & Error Matrix
5. Good / Base / Bad Cases
6. Tests Required
7. Wrong vs Correct (명시적 대비쌍)
```

> 공식 문서의 경고를 그대로 옮긴다:
> *"희망사항을 이미 지켜지는 규칙인 것처럼 문서화하지 마라. 템플릿을 다 채우려 하지 마라.
> 거짓 규칙은 빈 칸보다 해롭다."*
>
> 실제 예시가 없는 규칙은 지워라. 비어 있는 템플릿 파일은 채우지 말고 삭제해라.

### spec을 다시 뽑아야 할 때 (참고)

코드가 크게 바뀌어서 spec을 처음부터 다시 뽑아야 하면, 루트에서 세션을 열고 아래를 붙여넣는다.
공식 문서의 기본 프롬프트만 주면 **"제안"만 하고 파일을 안 쓴다.** 뒤에 붙인 제약이 핵심이다.

```
This is an existing repo. Do not refactor code yet.
Inspect the codebase and propose a minimal Trellis bootstrap for the next feature task.
After proposing, go ahead and write the spec files — do not stop at the proposal.

Constraints for this repo:
1. Only document what exists. Delete template files that have no real counterpart
   in the code (e.g. .trellis/spec/frontend/ if there is no frontend code).
   Keep index.md in sync with the final file set.
2. Prioritize cross-team interface contracts over generic coding conventions:
   a. doc_type string table from engine/config.py REQUIRED_DOCUMENTS and
      DOCUMENT_TYPE_CONFUSION_GROUPS — must match the OCR classifier labels exactly.
   b. Document / Applicant / StageResult / FinalResult schema from engine/models.py —
      fields, types, nullability, issue_date vs declared_issue_date.
   c. Inventory of placeholder values in engine/config.py that must be replaced
      after the 9/15 TF meeting.
3. Use the 7-section cross-layer format for (a) and (b).
4. Do not document aspirational rules. No example in the code → leave it out.
```

끝나면 placeholder가 남았는지 확인한다. 아무것도 안 나와야 통과:

```powershell
Select-String -Path ".trellis\spec\*\*.md" -Pattern "To fill|TODO|Fill in|your project"
```

---

## 6. 매일 쓰는 흐름

```
(세션 열기)            저장소 루트에서. SessionStart 훅이 컨텍스트를 자동 주입 — 칠 명령 없음
   ↓
(자연어로 할 일 설명)   brainstorm이 한 번에 하나씩 질문해서 PRD 정리
   ↓                   → implement가 코드 작성
   ↓                   → check가 spec/lint/타입/테스트 대비 자동 검증
/trellis:continue      진행 중 태스크를 다음 단계로
   ↓
(코드 커밋)            AI가 워크플로우 Phase 3.4에서 커밋
   ↓
/trellis:finish-work   태스크 아카이브 + 저널 기록 (이 둘은 자동 커밋됨)
```

> **`/trellis:start`는 없다.** 예전 버전 문서나 블로그에 나오지만, 우리가 쓰는 **0.6.17**에서는
> 세션 시작이 `.claude/hooks/session-start.py` 훅으로 자동화되어 커맨드가 사라졌다.
> 실제로 `.claude/commands/trellis/`에 생성되는 건 `continue`와 `finish-work` **둘뿐이다.**
> 저장소 루트에서 세션을 열기만 하면 컨텍스트는 알아서 들어온다. (4-C 참고)

### 이 두 개를 안 하면 하네스를 깐 의미가 없다

- **`/trellis:finish-work`** → **팀원별 위키(저널)에 기록이 남는 순간**
- **`trellis-update-spec`** → 거기서 나온 교훈을 `spec/`으로 올려보내는 **트러블슈팅 축적 지점**

세션 컨텍스트가 꽉 찼을 때도 `/trellis:finish-work`를 치면 된다.

`finish-work`는 코드 커밋을 **하지 않는다.** 코드는 그 전(Phase 3.4)에 커밋돼 있어야 하고,
안 돼 있으면 finish-work가 거부한다. 저널·아카이브 커밋(`chore: record journal`)은 스크립트가 자동으로 한다.

### 역할 분담은 태스크에 직접 박는다

```powershell
python .\.trellis\scripts\task.py create "OCR doc_type 라벨 정합" --slug doc-type-contract --priority P1 --assignee <담당자ID>
```

```powershell
python .\.trellis\scripts\task.py list
```

---

## 7. 팀 규칙

### 이름 규약

`trellis init`에서 넣는 이름은 `.trellis/workspace/` 아래 **폴더명**이 된다. **나중에 바꾸면 지저분해진다.**
**Git `user.name`을 그대로 쓰는 것**을 기본으로 한다 — `init`이 기본값으로 제안하는 값이고, 커밋 작성자와 저널 폴더가 같은 이름이면 추적이 쉽다.

| 담당 | 파트 | ID |
|---|---|---|
| 채운 | 대시보드 | `hcw889` (확정) |
| 진 | 엔진 | `<본인 ID>` — `init` 후 이 칸을 채워 커밋할 것 |
| 지빈 | 데모사이트 | `<본인 ID>` — `init` 후 이 칸을 채워 커밋할 것 |

### 커밋 대상

| 커밋한다 | 커밋하지 않는다 (자동 gitignore) |
|---|---|
| `.trellis/spec/` | `.trellis/.developer` (기기별 신원) |
| `.trellis/tasks/` | `.trellis/.runtime/` (세션 임시) |
| `.trellis/workspace/` | `.claude/settings.local.json` (개인 권한 승인 기록) |
| `.claude/` | `__pycache__/`, `.venv/`, `.env` 등 |
| `AGENTS.md`, `.gitattributes` | |

> `.agents/` 폴더는 **없다.** 0.6.17은 스킬을 `.claude/skills/`에 넣는다. 예전 문서의 `git add .agents`는 실패한다.

spec 변경은 **PR로 리뷰**한다. 코드와 똑같이 취급.

`.trellis/workspace/*/index.md`는 세션마다 통째로 재생성되는 파일이라 **머지 충돌이 나는 게 정상**이다.
아무 쪽이나 골라서 해결하면 된다 (실제 상태는 `task.json`에 있다). 저널(`journal-*.md`)은 `.gitattributes`의 `merge=union` 덕분에 충돌 안 난다.

### 버전 규칙

```powershell
trellis --version          # 내 CLI 버전
Get-Content .trellis\.version   # 저장소 버전
```

- 둘이 **같아야 한다.** 다르면 세션 시작 시 업데이트 권고가 뜨고, 팀원 간 동작이 달라진다.
- **버전 올리기는 hcw889(Windows)만 한다.** `trellis upgrade` → `trellis update` → 커밋. 나머지는 pull 후 `npm install -g @mindfoldhq/trellis@<새버전>`으로 CLI만 맞춘다.
- **Mac에서 `trellis update`를 돌리면 안 된다.** `update`는 실행한 OS에 맞춰 생성 파일 안의 Python 명령어를 다시 쓴다
  (Windows → `python`, Mac → `python3`). Mac에서 돌리면 `.claude/settings.json`, `.trellis/workflow.md` 등 45곳이 `python3`로 바뀌어 Windows 쪽이 깨진다.

---

## 8. 트러블슈팅

| 증상 | 원인 | 해결 |
|---|---|---|
| `npm : 용어가 ... 인식되지 않습니다` | 설치 전에 열어둔 터미널의 PATH가 낡음 | **터미널 새로 열기** (1장) |
| `trellis` 명령을 못 찾음 | npm 전역 bin(`%APPDATA%\npm`)이 PATH에 없음 | 터미널 재시작 → 그래도 안 되면 해당 경로를 PATH에 추가 |
| `python`이 아무것도 안 찍음 / 스토어가 열림 | Windows 앱 실행 별칭 스텁 | 앱 실행 별칭에서 `python.exe` 끄기 (1장) |
| AI가 Trellis 태스크를 모른다 / `.trellis\.runtime\`이 안 생김 | 훅이 안 돎 — 루트가 아닌 곳에서 세션을 열었거나 훅 신뢰를 거부함 | 4-C. 저장소 루트를 직접 열고, 신뢰 프롬프트 허용 |
| `task.py` 실행 실패 | Python 미설치 또는 경로에 공백·한글 | Python 확인 → 저장소를 ASCII 경로로 이동 (3장) |
| `git add .agents` → `pathspec did not match` | `.agents/`는 이 버전에 없음 | 7장 커밋 대상 표 참고 |
| 팀원마다 동작이 다름 | `.trellis/` 버전 불일치 | 7장 버전 규칙. CLI를 `.trellis/.version`에 맞춘다 |
| 남의 설정이 갑자기 사라짐 | 누군가 **Full re-initialize**를 누름 | git에서 `.trellis/`, `.claude/` 복구. 4장 경고 재공지 |
| `.claude/settings.json` 등이 `python3`로 바뀐 diff | Mac에서 `trellis update`를 돌림 | 되돌리고 7장 버전 규칙 재공지 |
| `workspace/*/index.md` 머지 충돌 | 정상 (세션마다 재생성) | 아무 쪽이나 골라 해결 |

---

## 9. 참고 링크

- [Trellis 저장소 (GitHub)](https://github.com/mindfold-ai/Trellis)
- [설치 및 첫 태스크](https://docs.trytrellis.app/start/install-and-first-task)
- [일상 사용 · 커맨드 목록](https://docs.trytrellis.app/beta/start/everyday-use.md)
- [멀티플랫폼 · 팀 설정](https://docs.trytrellis.app/beta/advanced/multi-platform.md)
- [실전 시나리오 (브라운필드 · 팀 도입)](https://docs.trytrellis.app/beta/start/real-world-scenarios.md)
- [스펙 템플릿 모음](https://docs.trytrellis.app/templates/specs-index.md)

---

## 부록 — 전체 순서 요약

```
[머신당 1회]
  node -v; npm -v; python --version; git --version   ← 이미 있으면 설치 건너뜀
  (없는 것만) winget install OpenJS.NodeJS.LTS / Python.Python.3.13
  ★ 설치했으면 터미널 새로 열기 ★
  npm install -g @mindfoldhq/trellis@0.6.17

[저장소]
  git clone ... C:\dev\2026-2-capstone   (ASCII 경로, 한 곳에만)
  cd C:\dev\2026-2-capstone

[기기당 1회]
  trellis init -u <본인ID>     (--claude 등 플랫폼 플래그 금지 / Full re-initialize 금지)
  7장 이름표에 본인 ID 기입 → 커밋

[세션 확인]
  저장소 루트를 직접 열기 → 신뢰 프롬프트 허용
  → "현재 활성 Trellis 태스크가 뭐야?" → 답이 00-join-<본인ID> 면 통과

[spec]
  본인 파트 spec 검토 → 틀린 것 PR

[매일]
  루트에서 세션 열기(컨텍스트 자동 주입)
  → 작업 → /trellis:continue → 코드 커밋 → /trellis:finish-work
```
