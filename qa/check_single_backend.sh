#!/usr/bin/env bash
# 이행 절차 6단계에서 **사람이 직접** 실행한다. build.sh all에는 안 물린다 —
# 진짜 Decky 로더·진짜 설치 상태가 있어야 의미가 있어 무인 CI에서 돌릴 수 없다(설계 E19).
#
# 왜 경로로 세나: setproctitle(f"{self.name} ({self.file})")에서 self.name은 **표시명**이라
# 이름을 바꾸면 같이 바뀐다. self.file은 plugin_directory(=IDENT)를 포함한 진입점 경로라 고정이다.
#
# ⚠️ 2026-08-06 수정 — 첫 판은 `pgrep -af main.py | grep -c …`였고 **자기 자신을 셌다.**
#    이 스크립트를 부른 셸의 명령줄에 패턴 문자열이 들어 있어 pgrep -f에 걸렸고,
#    백엔드가 1개인 상태에서 2개라고 **거짓 FAIL**을 냈다(실제로 이행 6단계에서 발생).
#    검사가 거짓말을 하면 없느니만 못하다 → PID를 하나씩 훑어 **자기 자신과 셸류를 제외**한다.
IDENT=gfxprofile

n=0
pids=""
for p in $(pgrep -f "plugins/${IDENT}/main.py" 2>/dev/null); do
  [ "$p" = "$$" ] && continue                      # 이 스크립트 자신
  case "$(ps -o comm= -p "$p" 2>/dev/null)" in
    bash|sh|dash|zsh|grep|pgrep|"") continue ;;     # 패턴을 명령줄에 달고 있는 셸·검색기
  esac
  n=$((n + 1))
  pids="$pids $p"
done

if [ "$n" -eq 1 ]; then
  echo "PASS: 백엔드 1개 (PID$pids)"
  exit 0
fi
echo "FAIL: 백엔드가 ${n}개다 (1이어야 한다)${pids:+ — PID$pids}"
if [ "$n" -gt 1 ]; then
  echo "  ⚠️ 두 백엔드가 같은 ~/homebrew/data/${IDENT}/를 동시에 쓰고 있을 수 있다."
  echo "  → Steam을 완전 재시작해 정리한 뒤 registry.json sha1을 백업과 대조하라 (E19 복구표)."
else
  echo "  → 플러그인이 안 떠 있다. 로더 로그와 ~/homebrew/logs/${IDENT}/를 보라."
fi
exit 1
