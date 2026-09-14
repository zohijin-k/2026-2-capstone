# Trellis 하네스 — 셋업 가이드 (macOS)

> 대상: 2026-2-capstone TF 팀원 중 Mac 사용자
> 최종 수정: 2026-09-14
> **Windows 사용자는 [TRELLIS_SETUP.md](./TRELLIS_SETUP.md)를 볼 것.**
> 배경 설명(왜 Trellis인가, spec에 뭘 넣나, 매일 흐름)은 Windows 문서와 같다. 이 문서는 **Mac에서 다른 부분**에 집중한다.

---

## 현재 상태 — 먼저 읽을 것

| 항목 | 상태 |
|---|---|
| 저장소 Trellis 초기 도입 | **완료** (hcw889, 2026-09-14, Windows에서) |
| Trellis 버전 | **0.6.17** (`.trellis/.version`) |
| 팀원이 할 일 | **1 → 2 → 3 → 4 순서.** "첫 도입" 절차(`trellis init -u ... --claude`)는 **하지 말 것.** |

### Mac에서 반드시 알아야 할 것 한 가지

저장소의 Trellis 설정은 **Windows에서 생성됐다.** 그래서 `.claude/settings.json`, `.trellis/workflow.md` 등
커밋된 파일 안의 Python 호출이 전부 **`python`** 으로 되어 있다 (`python3`가 아님).

**macOS에는 기본적으로 `python` 명령이 없다.** `python3`만 있다.
아무 조치 없이 pull만 하면 Claude Code 세션 시작 훅이 **에러도 없이 조용히 실패**하고, 하네스가 없는 것과 똑같이 동작한다.

→ 1장에서 **`python` 명령을 만들어주는 절차**가 있다. 건너뛰지 말 것.

---

## 1. 사전 준비 (머신당 1회)

### 요구사항

| 항목 | 버전 | 용도 |
|---|---|---|
| Node.js | **18 이상** | Trellis CLI 본체 |
| Python | **3.9 이상**, **`python`이라는 이름으로 호출 가능해야 함** | `.trellis/scripts/*.py` + Claude Code 훅 전부 |
| Git | - | Xcode Command Line Tools에 포함 |

### 1-1. Xcode Command Line Tools (git 포함)

```zsh
xcode-select --install
```

이미 있으면 "already installed" 라고 뜬다. 그럼 넘어간다.

### 1-2. Homebrew

```zsh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

설치 끝에 **"Next steps"** 로 `~/.zprofile`에 추가하라는 두 줄이 나온다. **반드시 그대로 실행한다.**
(Apple Silicon 기준 `eval "$(/opt/homebrew/bin/brew shellenv)"` 를 `~/.zprofile`에 넣는 내용이다.)
안 하면 새 터미널에서 `brew`를 못 찾는다.

```zsh
brew --version
```

### 1-3. Node.js, Python

```zsh
brew install node python
```

> `python` 뒤에 버전을 붙이지 않는다. Homebrew의 `python` 포뮬러가 최신 3.x를 준다.

### 1-4. `python` 명령 만들기 ★ Mac 전용, 필수

Homebrew의 Python은 `python3`만 PATH에 올리고, `python`은 별도 폴더에 숨겨둔다. 그 폴더를 PATH에 추가한다.

```zsh
echo 'export PATH="$(brew --prefix python)/libexec/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
```

> **`~/.zshrc`가 아니라 `~/.zprofile`에 넣는 이유:** VS Code 등 GUI 앱은 시작할 때 **로그인 셸**의 환경을 읽어간다.
> `.zshrc`는 대화형 셸에서만 읽히므로 거기 넣으면 터미널에서는 되는데 Claude Code 훅에서는 안 되는 상황이 생긴다.
>
> **`alias python=python3`는 안 된다.** alias는 대화형 셸에서만 동작하고, 훅은 비대화형으로 실행된다.

### 1-5. 확인 — 터미널을 새로 열고

```zsh
node -v; npm -v; python --version; python3 --version; git --version
```

**다섯 개 전부** 버전이 찍혀야 통과다. 특히 `python --version`이 `command not found`면 1-4를 다시 본다.

---

## 2. Trellis CLI 설치 (머신당 1회, 위치 무관)

```zsh
npm install -g @mindfoldhq/trellis@0.6.17
```

```zsh
trellis --version
```

`0.6.17`이 찍히면 통과다. 버전을 `@latest`가 아니라 `0.6.17`로 고정하는 이유는 6장 [버전 규칙](#버전-규칙) 참고.

> **`sudo`를 붙이지 말 것.** Homebrew로 깐 Node는 전역 패키지를 사용자 소유 폴더(`/opt/homebrew/lib/node_modules`)에 넣으므로 권한 문제가 없다.
> `EACCES` 에러가 난다면 Node를 Homebrew가 아닌 다른 방법(공식 설치기 등)으로 깐 것이다. 8장 참고.

---

## 3. 저장소 준비

```zsh
mkdir -p ~/dev
git clone https://github.com/zohijin-k/2026-2-capstone.git ~/dev/2026-2-capstone
cd ~/dev/2026-2-capstone
```

> **`~/Desktop`, `~/Documents`에 두지 말 것.** iCloud Drive의 "데스크탑 및 문서 폴더 동기화"가 켜져 있으면
> `.git/` 내부 파일이 동기화 도중 잠기거나 중복 생성되어 저장소가 깨진다. `~/dev` 같은 동기화 밖 경로를 쓴다.
> 경로에 공백·한글도 넣지 않는다.

pull 후 루트에 `.trellis/`, `.claude/`, `AGENTS.md`, `.gitattributes`가 보이면 정상이다.

---

## 4. 개발자 신원 등록 (기기당 1회)

> ### 가장 중요한 규칙
> `trellis init`을 실행했을 때 선택지가 3개 뜨면,
> **`Full re-initialize`는 절대 고르지 말 것.**
> 기존 `.trellis/`, `.claude/` 설정을 통째로 덮어써서 **팀 전체에 영향이 간다.**
> Mac에서 이걸 누르면 설정 파일 전체가 `python3`로 다시 써져 Windows 팀원 쪽까지 깨진다.

저장소 루트에서:

```zsh
trellis init -u <본인ID>
```

`.trellis/`가 이미 있는 저장소에서 `-u`를 주면 **메뉴 없이 바로 신원 등록**만 한다. 옵션 없이 `trellis init`만 치면 선택지 3개가 뜨는데, 그때는 **`Set up developer identity on this device`** 를 고른다 (결과는 같다).
`--claude` 같은 플랫폼 플래그는 **붙이지 않는다** — 이미 설정돼 있다.

- `<본인ID>`는 [이름 규약](#이름-규약) 참고. 메뉴로 갔다면 Git `user.name`이 기본값으로 뜬다 → 그대로 써도 된다.
- `.trellis/.developer` (gitignore, 기기별)에 본인 이름이 기록됨
- `.trellis/workspace/{본인ID}/`가 생성됨 — **이건 커밋 대상**이다
- `.trellis/tasks/00-join-{본인ID}/` **온보딩 태스크가 자동 생성**된다 — 첫 세션에서 이 태스크가 활성 태스크가 되고, AI가 워크플로우를 안내해준다. 다 봤으면 `/trellis:finish-work`로 아카이브한다.

### 세션이 제대로 열리는지 확인

Trellis는 **Claude Code 세션이 시작될 때 훅으로 컨텍스트를 주입**한다. 훅이 안 돌면 하네스는 없는 거나 마찬가지다.

**① 저장소 루트에서 세션을 열어야 한다.**
VS Code라면 *File → Open Folder*로 `~/dev/2026-2-capstone`을 **직접** 연다. 상위 폴더를 열고 그 안에서 세션을 시작하면 훅이 안 돈다. 터미널이라면:

```zsh
cd ~/dev/2026-2-capstone && claude
```

**② 처음 열 때 훅/폴더 신뢰 여부를 물으면 허용한다.**

**③ 확인.** 세션 첫 메시지로 이렇게 물어본다:

```
현재 활성 Trellis 태스크가 뭐야?
```

`00-join-<본인ID>`라고 답하면 통과. "모르겠다"면 훅이 안 돈 것이다. 파일로 확인하려면: 훅이 돌면 `.trellis/.runtime/` 폴더가 생긴다.

Mac에서 훅이 안 도는 원인은 **거의 항상 1-4(`python` 명령)** 다. 터미널에서 직접 돌려보면 에러가 보인다:

```zsh
python .claude/hooks/session-start.py
```

`command not found: python`이면 1-4로 돌아간다.

---

## 5. spec — 팀원이 검토·수정하는 것

Windows 문서 5장과 동일하다. 요약만:

- `.trellis/spec/`은 AI가 세션마다 읽는 팀 규약. 초안은 hcw889가 코드에서 뽑는다.
- **팀원이 할 일은 "검토"**: pull 후 본인 파트 관련 spec을 읽고, 틀렸거나 빠진 걸 **PR로** 고친다.
- 반드시 들어가야 할 3가지: `doc_type` 문자열 표 / `Document`·`Applicant` 스키마 계약 / `config.py` 가정값 대장.
- 실제 예시가 없는 규칙은 지운다. 빈 템플릿은 채우지 말고 삭제한다.

placeholder 잔존 확인 (아무것도 안 나와야 정상):

```zsh
grep -rE "To fill|TODO|Fill in|your project" .trellis/spec/
```

---

## 6. 매일 쓰는 흐름 · 팀 규칙

흐름은 Windows 문서 6장과 같다. `/trellis:start`는 **없다** — 루트에서 세션을 열면 훅이 알아서 주입한다.

```
루트에서 세션 열기 → 작업 → /trellis:continue → 코드 커밋 → /trellis:finish-work
```

태스크 명령은 경로 구분자만 다르다:

```zsh
python ./.trellis/scripts/task.py create "OCR doc_type 라벨 정합" --slug doc-type-contract --priority P1 --assignee <담당자ID>
python ./.trellis/scripts/task.py list
```

### 이름 규약

Windows 문서 7장의 표와 같다. **Git `user.name`을 그대로 쓰는 것**이 기본. `init` 후 그 표의 본인 칸을 채워 커밋한다.

### 커밋 대상

Windows 문서 7장과 같다. Mac에서 추가로 신경 쓸 것:

- **`.DS_Store`를 커밋하지 말 것.** 루트 `.gitignore`에 들어 있지만, `git add -A` 전에 `git status`로 한 번 본다.

### 버전 규칙

```zsh
trellis --version        # 내 CLI 버전
cat .trellis/.version    # 저장소 버전
```

- 둘이 **같아야 한다.**
- **버전 올리기(`trellis upgrade` → `trellis update`)는 hcw889(Windows)만 한다.**
- **Mac에서 `trellis update`를 절대 돌리지 말 것.** `update`는 실행한 OS에 맞춰 생성 파일 안의 Python 명령어를 다시 쓴다.
  Mac에서 돌리면 `.claude/settings.json`, `.trellis/workflow.md` 등 45곳이 `python` → `python3`로 바뀌고,
  이걸 커밋하면 Windows 팀원(`python3` 없음) 쪽이 통째로 깨진다. 실수로 돌렸으면 `git checkout -- .claude .trellis AGENTS.md`로 되돌린다.
- 저장소 버전이 올라가면 pull 후 CLI만 맞춘다: `npm install -g @mindfoldhq/trellis@<새버전>`

---

## 7. 트러블슈팅 (Mac)

| 증상 | 원인 | 해결 |
|---|---|---|
| `command not found: python` | macOS 기본에 `python` 없음 | **1-4.** Homebrew python의 `libexec/bin`을 `~/.zprofile`에서 PATH 추가 |
| 터미널에서는 `python`이 되는데 Claude Code 훅은 안 돎 | PATH를 `.zshrc`에만 넣었거나 alias로 해결함 | `.zprofile`로 옮긴다. alias는 훅에서 안 먹는다. VS Code를 완전히 종료 후 재시작 |
| AI가 Trellis 태스크를 모른다 / `.trellis/.runtime/`이 안 생김 | 훅이 안 돎 | 4장. 루트를 직접 열고, 신뢰 프롬프트 허용, `python .claude/hooks/session-start.py`를 직접 돌려 에러 확인 |
| `npm install -g` → `EACCES: permission denied` | Node를 Homebrew가 아닌 방법으로 깔아서 전역 폴더가 root 소유 | `sudo` 쓰지 말고: `brew install node`로 갈아타거나, `npm config set prefix ~/.npm-global` 후 `~/.npm-global/bin`을 PATH에 추가 |
| `brew: command not found` (새 터미널에서) | Homebrew 설치 후 "Next steps"를 안 함 | 1-2. `~/.zprofile`에 `brew shellenv` 줄 추가 |
| `trellis: command not found` | npm 전역 bin이 PATH에 없음 | `npm prefix -g` 결과의 `/bin`이 PATH에 있는지 확인 (Homebrew면 `/opt/homebrew/bin`, 보통 이미 있음) |
| 저장소가 이상하게 깨짐, `.git` 안에 ` 2` 붙은 파일 | iCloud Drive 동기화 폴더에 클론함 | 3장. `~/dev`로 옮긴다 |
| `.claude/settings.json` 등이 `python3`로 바뀐 diff | `trellis update`를 Mac에서 돌림 | `git checkout -- .claude .trellis AGENTS.md`. 6장 버전 규칙 |
| `git status`에 `.DS_Store` | Finder가 만든 파일 | `.gitignore`에 있는지 확인. 이미 add했으면 `git rm --cached .DS_Store` |
| 남의 설정이 갑자기 사라짐 | 누군가 **Full re-initialize**를 누름 | git에서 `.trellis/`, `.claude/` 복구. 4장 경고 재공지 |

---

## 8. 참고 링크

- [Trellis 저장소 (GitHub)](https://github.com/mindfold-ai/Trellis)
- [설치 및 첫 태스크](https://docs.trytrellis.app/start/install-and-first-task)
- [일상 사용 · 커맨드 목록](https://docs.trytrellis.app/beta/start/everyday-use.md)
- [멀티플랫폼 · 팀 설정](https://docs.trytrellis.app/beta/advanced/multi-platform.md)
- [Homebrew Python — unversioned `python` 심볼릭 링크 안내](https://docs.brew.sh/Homebrew-and-Python)

---

## 부록 — 전체 순서 요약

```
[머신당 1회]
  xcode-select --install
  Homebrew 설치 → "Next steps" 두 줄을 ~/.zprofile에 (안 하면 brew 못 찾음)
  brew install node python
  ★ echo 'export PATH="$(brew --prefix python)/libexec/bin:$PATH"' >> ~/.zprofile ★
  터미널 새로 열기
  node -v; npm -v; python --version; python3 --version; git --version   ← 5개 전부
  npm install -g @mindfoldhq/trellis@0.6.17   (sudo 금지)

[저장소]
  git clone ... ~/dev/2026-2-capstone   (iCloud 동기화 폴더 밖, ASCII 경로)
  cd ~/dev/2026-2-capstone

[기기당 1회]
  trellis init -u <본인ID>     (--claude 등 플랫폼 플래그 금지 / Full re-initialize 금지)
  이름표에 본인 ID 기입 → 커밋

[세션 확인]
  저장소 루트를 직접 열기 → 신뢰 프롬프트 허용
  → "현재 활성 Trellis 태스크가 뭐야?" → 답이 00-join-<본인ID> 면 통과
  안 되면: python .claude/hooks/session-start.py 직접 실행해서 에러 확인

[spec]
  본인 파트 spec 검토 → 틀린 것 PR

[매일]
  루트에서 세션 열기 → 작업 → /trellis:continue → 코드 커밋 → /trellis:finish-work

[절대 금지]
  trellis update   (Windows 담당자만)
```
