import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * 렌더 실패를 가두는 우리 자신의 경계.
 *
 * 왜 `@decky/ui`의 `ErrorBoundary`를 쓰지 않는가 — 그것이 이 파일의 존재 이유다. 설치된
 *   `@decky/ui` 소스에서 그 경계는 `findModuleExport`로 얻는다. 실제 Loader 런타임의 조회 실패
 *   동작은 [미확인]이다. 이 경계는 그 벤더 의존 자체를 피한다 — 안전장치는 자기가 감시하는
 *   실패에 걸려선 안 되므로, Steam 결합 0인 순수 React 클래스 컴포넌트로 직접 만든다.
 *
 * 폴백은 `t()`를 쓰지 않는다 — 화면에 나오는 문장 가운데 `t()`를 거치지 않는 것은 이것뿐이다
 *   (그 밖의 하드코딩은 플러그인 이름이고, 고유명사라 번역하지 않는다). 경계 아래 렌더 중
 *   `t()`가 던져도 폴백은 같은 실패 경로를 다시 밟지 않는다. 그래서 영어 리터럴로 고정한다.
 *   이 예외가 넓어지지 않게 하는 것은 이 파일의 import 목록뿐이다: 맨 위 줄이 `react` 하나이고
 *     i18n을 들이지 않는다. 그 줄이 유지되는 한 `t()`를 부를 방법이 없다 — 검사가 아니라
 *     의존 없음이 방어선이므로, 여기에 import를 더하지 말 것.
 *
 * 폴백을 검사 대상 컴포넌트로 그리지 않는다(`PanelSection` 등). `index.tsx`의 self-check 실패
 *   안내와 같은 원칙이다 — 순수 intrinsic 요소만 쓴다.
 *
 * 화면 문구에 내부 식별자를 쓰지 않는다 — 그것은 옛 표시명이다. 진단 태그(`where`)는 로그에만
 *   둔다. 이 규칙을 강제하는 검사는 없다.
 *
 * 진단은 `console.error`다. Steam CEF에서 `cef_log`에 실리는 레벨은 그것뿐이고(실측), Game
 *   Mode에는 터미널이 없어 로그가 유일한 단서다.
 *   백엔드 로그로도 보내지 않는다 — 그러려면 RPC를 불러야 하는데, 지금 무너진 것이 바로 그
 *     RPC 경로일 수 있다. 경계가 자기 진단을 위해 새 실패 지점을 만들면 안 된다.
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

  /** 렌더 중 throw를 상태로 바꾼다. 여기서는 부작용을 내지 않는다(React가 두 번 부를 수 있다). */
  static getDerivedStateFromError(error: unknown): State {
    const name = error instanceof Error ? error.name : typeof error;
    return { failed: true, detail: String(name) };
  }

  /** 부작용(로그)은 여기서만. 로그에서 "렌더 단계 실패"를 집을 수 있게 태그를 고정한다. */
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
    // 비상 폴백은 `t()`를 쓰지 않는다 — 경계 아래의 i18n 렌더 실패를 다시 밟지 않기 위해서다.
    return (
      <div style={{ padding: "8px", fontSize: "13px", color: "#ffb454" }}>
        RENDER_FAILED ({this.state.detail}) — this part of the UI could not be drawn.
        See the console log for details.
      </div>
    );
  }
}
