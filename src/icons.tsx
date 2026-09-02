/**
 * 자작 인라인 SVG 아이콘 13종. 공통 규격은 1em·viewBox 0 0 36 36·currentColor다.
 * `IconChip`과 `IconGear`의 작은 크기 식별성은 [미확인]이다.
 *
 * react-icons를 쓰지 않는다 — 의존에 없고, `@decky/ui`가 주는 것은 `icon?: ReactNode` 슬롯뿐이라
 *   인라인 SVG를 직접 넣는다.
 *
 * 규격
 *   - 색은 호출부가 준다 — 내부는 `currentColor`뿐이다. 하드코딩 색상값 0건
 *   - 배경 불투명 요소 없음 · `opacity` 미사용 — 단색 실루엣으로 성립한다
 *   - 획은 4.5와 5 두 값뿐이다(36 기준)
 *
 * 소스 경로: `icons-workshop/minimal-bold/svg/` — 다시 뽑을 때 여기서 가져온다. 보완이 필요하면
 *   다른 세트로 갈아타지 말고 이 세트를 개선한다.
 *
 * Steam의 path를 복사하지 않았다 — 자작이다. i18n 무관(가시 문자열 아님).
 */
import type { CSSProperties } from "react";

/** 모든 아이콘 공통 props. 크기는 지정하지 않는다 — 1em이라 주변 글자를 따라간다. */
type IconProps = { style?: CSSProperties };

const box = {
  width: "1em",
  height: "1em",
  viewBox: "0 0 36 36",
  // 면 기반 path는 fill을 상속한다 — 없으면 SVG 기본값(검정)으로 굳어 다크 UI에서 안 보인다.
  // 선 기반 그룹은 fill="none"으로 스스로 덮으므로 무영향.
  fill: "currentColor",
  // 인라인 요소의 baseline 정렬 흔들림을 없앤다(라벨과 같은 줄에 서므로).
  display: "block",
} as const;


/** eGPU 프로필 계열 — QAM 일괄 버튼·행 적용 버튼 */
export const IconBolt = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path d="M21.4 2.8a1.5 1.5 0 0 1 1.4 2l-3.1 9.4h7.1a1.7 1.7 0 0 1 1.3 2.8L15.6 32.7a1.5 1.5 0 0 1-2.6-1.4l3.1-9.5H9.2a1.7 1.7 0 0 1-1.3-2.8L20 3.3a1.5 1.5 0 0 1 1.4-.5Z"/>
  </svg>
);

/** 내장 프로필 계열 */
export const IconChip = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path fillRule="evenodd" d="M12 3a1.5 1.5 0 0 1 3 0v4h6V3a1.5 1.5 0 0 1 3 0v4h1a4 4 0 0 1 4 4v1h4a1.5 1.5 0 0 1 0 3h-4v6h4a1.5 1.5 0 0 1 0 3h-4v1a4 4 0 0 1-4 4h-1v4a1.5 1.5 0 0 1-3 0v-4h-6v4a1.5 1.5 0 0 1-3 0v-4h-1a4 4 0 0 1-4-4v-1H3a1.5 1.5 0 0 1 0-3h4v-6H3a1.5 1.5 0 0 1 0-3h4v-1a4 4 0 0 1 4-4h1V3Zm0 7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V12a2 2 0 0 0-2-2H12Zm2 5.5a1.5 1.5 0 0 1 1.5-1.5h5a1.5 1.5 0 0 1 1.5 1.5v5a1.5 1.5 0 0 1-1.5 1.5h-5a1.5 1.5 0 0 1-1.5-1.5v-5Z"/>
  </svg>
);

/** "현재 적용됨" 마커 · 상태박스 성공 결과 줄 */
export const IconCheck = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"> <path d="m7 18.5 7.2 7.2L29 10.3"/> </g>
  </svg>
);

/** 상태박스 문제 결과 줄 — 색은 호출부에서 준다(성공 줄과 같은 자리, 다른 색) */
export const IconWarn = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path fillRule="evenodd" d="M15.4 4.5a3 3 0 0 1 5.2 0l13 22.6a3 3 0 0 1-2.6 4.5H5a3 3 0 0 1-2.6-4.5l13-22.6ZM18 11a2.2 2.2 0 0 0-2.2 2.4l.7 7.1a1.5 1.5 0 0 0 3 0l.7-7.1A2.2 2.2 0 0 0 18 11Zm0 16.2a2.3 2.3 0 1 0 0-4.6 2.3 2.3 0 0 0 0 4.6Z" clipRule="evenodd"/>
  </svg>
);

/** [게임 감지] */
export const IconSearch = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round"> <circle cx="15.5" cy="15.5" r="9.5"/> <path d="m22.5 22.5 7.5 7.5"/> </g>
  </svg>
);

/** [게임별 적용/저장] */
export const IconList = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <circle cx="7" cy="9" r="2.5"/><rect x="12" y="6.5" width="19" height="5" rx="2.5"/> <circle cx="7" cy="18" r="2.5"/><rect x="12" y="15.5" width="19" height="5" rx="2.5"/> <circle cx="7" cy="27" r="2.5"/><rect x="12" y="24.5" width="19" height="5" rx="2.5"/>
  </svg>
);

/** 전역 [설정] 전용 — 행 버튼에 쓰지 말 것 */
export const IconGear = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path fillRule="evenodd" d="M15.2 2.5h5.6l1 4a13 13 0 0 1 2.6 1.1L28 5.4l4 4-2.2 3.5a13 13 0 0 1 1.1 2.7l4.1 1v5.7l-4.1 1a13 13 0 0 1-1.1 2.6l2.2 3.5-4 4-3.6-2.2a13 13 0 0 1-2.6 1.1l-1 4.1h-5.6l-1-4.1a13 13 0 0 1-2.6-1.1L8 33.4l-4-4 2.2-3.5a13 13 0 0 1-1.1-2.6l-4.1-1v-5.7l4.1-1a13 13 0 0 1 1.1-2.7L4 9.4l4-4 3.6 2.2a13 13 0 0 1 2.6-1.1l1-4Zm2.8 9a7.9 7.9 0 1 0 0 15.8 7.9 7.9 0 0 0 0-15.8Zm0 4.5a3.4 3.4 0 1 1 0 6.8 3.4 3.4 0 0 1 0-6.8Z" clipRule="evenodd"/>
  </svg>
);

/** 행 상세 진입 버튼 */
export const IconChevron = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"> <path d="m13.5 7.5 10.5 10.5-10.5 10.5"/> </g>
  </svg>
);

/** 프로필 저장 (디스켓 은유) */
export const IconSave = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path fillRule="evenodd" d="M6 3.5A2.5 2.5 0 0 0 3.5 6v24A2.5 2.5 0 0 0 6 32.5h24a2.5 2.5 0 0 0 2.5-2.5V11.1a2.5 2.5 0 0 0-.73-1.77l-5.1-5.1a2.5 2.5 0 0 0-1.77-.73H6Zm5 2.75a1 1 0 0 0-1 1v6.5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6.5a1 1 0 0 0-1-1h-1.75V11a1.25 1.25 0 0 1-2.5 0V6.25H11Zm.5 15.25a2 2 0 0 0-2 2v7h17v-7a2 2 0 0 0-2-2h-13Z" clipRule="evenodd"/>
  </svg>
);

/** 백업 복원 · [다시 포함] */
export const IconRestore = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round"> <path d="M7.2 13.3A13 13 0 1 1 6 23"/> <path d="M7.2 6.5v6.8H14"/> <path d="M18 11.5V19l5 3"/> </g>
  </svg>
);

/** [다시 확인]·[다시 검색] */
export const IconRefresh = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round"> <path d="M30.5 13A13 13 0 0 0 8.8 8.6L5.5 12"/> <path d="M5.5 5.5V12H12"/> <path d="M5.5 23A13 13 0 0 0 27.2 27.4l3.3-3.4"/> <path d="M30.5 30.5V24H24"/> </g>
  </svg>
);

/** 등록 해제 · 전체 초기화 */
export const IconTrash = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <path fillRule="evenodd" d="M13 3a3 3 0 0 0-3 3v2H5a2.5 2.5 0 0 0 0 5h1l1.7 17a4 4 0 0 0 4 3.6h12.6a4 4 0 0 0 4-3.6L30 13h1a2.5 2.5 0 0 0 0-5h-5V6a3 3 0 0 0-3-3H13Zm1 5V7h8v1h-8Zm-1.7 8.5a1.7 1.7 0 0 1 3.4-.2l.7 11a1.7 1.7 0 1 1-3.4.2l-.7-11Zm11.4 0a1.7 1.7 0 0 0-3.4-.2l-.7 11a1.7 1.7 0 1 0 3.4.2l.7-11Z" clipRule="evenodd"/>
  </svg>
);

/** 뒤로가기 — 지금 이 아이콘을 그리는 화면은 없다(export만 서 있다) */
export const IconBack = ({ style }: IconProps) => (
  <svg {...box} style={style}>
    <g fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"> <path d="M30 18H7"/> <path d="m15 9-9 9 9 9"/> </g>
  </svg>
);
