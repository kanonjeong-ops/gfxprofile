import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * 렌더 실패를 가두는 **우리 자신의** 경계 (설계 E13 완화 2).
 *
 * ★★ 왜 `@decky/ui`의 `ErrorBoundary`를 쓰지 않는가 — 그것이 이 파일의 존재 이유다.
 *   `@decky/ui`의 컴포넌트는 **전부** Steam 프론트엔드 webpack 모듈을 문자열 시그니처로
 *   찾아 얻어지고(`findModuleExport`), **실패하면 예외가 아니라 `undefined`가 된다.**
 *   `DFL.ErrorBoundary`도 예외가 아니다. 그러면 `<ErrorBoundary>` 렌더 자체가
 *   **바로 그 안전장치가 막으려던 크래시**를 일으킨다.
 *   → **안전장치는 자기가 감시하는 실패에 걸려선 안 된다.** 그래서 Steam 결합 0인
 *     순수 React 클래스 컴포넌트로 직접 만든다.
 *
 * ★ 폴백을 **`t()`로 그리지 않는다**(설계 B-3이 인정한 유일한 하드코딩 예외).
 *   i18n 자체가 못 뜨는 상황 — 언어 판정 실패·번역 테이블 로드 실패·`t()`가 던지는 경우 —
 *   이 그대로 여기로 온다. 폴백이 `t()`를 부르면 **폴백이 다시 던진다.**
 *   그래서 영어 리터럴로 고정한다. 이 예외가 넓어지지 않도록 `test_i18n_sets.py`가
 *   **이 파일 하나만** 허용하고, 이 파일이 i18n을 import하지 않는지까지 잠근다.
 *
 * ★ 폴백을 **검사 대상 컴포넌트로 그리지 않는다**(`PanelSection` 등). `index.tsx`의
 *   self-check 실패 안내와 같은 원칙이다 — 순수 intrinsic 요소만 쓴다.
 *
 * ★ 화면 문구에 **내부 식별자를 쓰지 않는다** — 그것은 옛 표시명이고
 *   `test_frontend_display_name.py`가 화면에 남은 옛 이름을 막는다. 진단 태그는 로그에만 둔다.
 *
 * ★ 진단은 `console.error`다. Steam CEF에서 **`cef_log`에 실리는 레벨은 그것뿐**이고(실측),
 *   Game Mode에는 터미널이 없어 로그가 유일한 단서다.
 *   ⚠️ 백엔드 로그로도 보내지 않는다 — 그러려면 RPC를 불러야 하는데, **지금 무너진 것이
 *     바로 그 RPC 경로일 수 있다.** 경계가 자기 진단을 위해 새 실패 지점을 만들면 안 된다.
 */

interface Props {
  /** 어느 진입점인가 — 로그에서 QAM 패널과 팝업 3종을 가르는 값이다. 화면에 뜨지 않는다. */
  where: string;
  children: ReactNode;
}

interface State {
  failed: boolean;
  /** 진단용 요약. 화면에는 이름만 뜨고 전문은 `console.error`에 있다. */
  detail: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false, detail: "" };

  /** 렌더 중 throw를 상태로 바꾼다. **여기서는 부작용을 내지 않는다**(React가 두 번 부를 수 있다). */
  static getDerivedStateFromError(error: unknown): State {
    const name = error instanceof Error ? error.name : typeof error;
    return { failed: true, detail: String(name) };
  }

  /** 부작용(로그)은 여기서만. E6 판별표가 "렌더 단계 실패"를 집을 수 있게 태그를 고정한다. */
  componentDidCatch(error: unknown, info: ErrorInfo) {
    try {
      console.error(
        `[gfxprofile] boundary where=${this.props.where}`,
        error,
        info && info.componentStack,
      );
    } catch {
      // 로그조차 못 남기는 상황이라도 폴백은 떠야 한다 — 여기서 다시 던지지 않는다.
    }
  }

  render() {
    if (!this.state.failed) return this.props.children;
    // i18n-exempt: 설계 B-3이 인정한 유일한 하드코딩 예외 — i18n 자체가 못 뜨는 상황이다.
    return (
      <div style={{ padding: "8px", fontSize: "13px", color: "#ffb454" }}>
        RENDER_FAILED ({this.state.detail}) — this part of the UI could not be drawn.
        See the console log for details.
      </div>
    );
  }
}
