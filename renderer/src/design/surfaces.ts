import type {Layout, TemplateName} from '../lib/types';
import type {Theme} from './tokens';

export type SurfaceName = 'board' | 'paper' | 'ink' | 'signal' | 'overlay' | 'photo' | 'crumple' | 'collage';

export type Surface = {
  name: SurfaceName;
  bg: string;
  fg: string;
  dim: string;
  faint: string;
  accent: string;
  rule: string;
  chalk: boolean; // 분필 질감(선 거칠게)
};

export const surface = (theme: Theme, name: SurfaceName): Surface => {
  switch (name) {
    case 'board':
      return {name, bg: theme.board, fg: theme.chalk, dim: theme.chalkDim, faint: theme.chalkFaint,
        accent: theme.accentLight, rule: 'rgba(241,236,221,0.22)', chalk: true};
    case 'paper':
      return {name, bg: theme.paper, fg: theme.ink, dim: '#6E6C68', faint: 'rgba(17,17,17,0.12)',
        accent: theme.accent, rule: theme.paperLine, chalk: false};
    case 'ink':
      // 반전 면(챕터당 1회): 순흑 대신 따뜻한 책상색
      return {name, bg: '#1D1916', fg: '#F2EFE6', dim: 'rgba(242,239,230,0.62)', faint: 'rgba(242,239,230,0.14)',
        accent: theme.accentTint, rule: 'rgba(242,239,230,0.22)', chalk: false};
    case 'collage':
      // 디자인 v3 종이 콜라주(운영자 레퍼런스): 크림 종이 · 웜 잉크 · 짙은 디자인 색. 바탕 그림은 PaperStage 가 그린다
      return {name, bg: '#ECEAE1', fg: '#24211E', dim: 'rgba(36,33,30,0.64)', faint: 'rgba(36,33,30,0.14)',
        accent: theme.accentDeep, rule: 'rgba(36,33,30,0.2)', chalk: false};
    case 'signal':
      return {name, bg: theme.accent, fg: theme.accentDeep, dim: 'rgba(0,0,0,0.45)', faint: 'rgba(0,0,0,0.12)',
        accent: '#111111', rule: 'rgba(0,0,0,0.25)', chalk: false};
    case 'crumple':
      // 종이 콜라주 스킨: 구겨진 짙은 종이 위 흰 글씨 + 주황 강조(레퍼런스 측정값)
      return {name, bg: '#2A2A2F', fg: '#F4F4F5', dim: 'rgba(244,244,245,0.66)', faint: 'rgba(244,244,245,0.14)',
        accent: '#F85301', rule: 'rgba(244,244,245,0.28)', chalk: false};
    case 'photo':
      return {name, bg: '#0B0B0B', fg: '#FFFFFF', dim: 'rgba(255,255,255,0.7)', faint: 'rgba(255,255,255,0.15)',
        accent: theme.accentLight, rule: 'rgba(255,255,255,0.3)', chalk: false};
    case 'overlay':
    default:
      return {name: 'overlay', bg: 'transparent', fg: '#FFFFFF', dim: 'rgba(255,255,255,0.78)',
        faint: 'rgba(255,255,255,0.18)', accent: theme.accentLight, rule: 'rgba(255,255,255,0.35)', chalk: false};
  }
};

/** 템플릿 × 레이아웃 → 표면. 디자인 v3: 한 재질 — 칠판·순흑·주황 전면 대신 모두 크림 종이 콜라주(사진·스톡만 사진 면) */
export const surfaceFor = (template: TemplateName, layout: Layout): SurfaceName => {
  if (layout === 'split') return template === 'photo' || template === 'broll' ? 'photo' : 'board';
  if (layout === 'overlay') return 'overlay';
  switch (template) {
    case 'photo':
    case 'broll':
      return 'photo';
    case 'card':
      return 'paper'; // 카드가 자기 배경을 그린다 — 뒤에는 종이색
    default:
      return 'collage';
  }
};

/** 모션 장면의 bg 값 → 표면(한 재질: board·paper·signal 은 종이 콜라주, ink 는 따뜻한 반전 면) */
export const surfaceForSpecBg = (bg: string | undefined): SurfaceName | null =>
  !bg || bg === 'transparent' ? null : bg === 'ink' ? 'ink' : 'collage';

// 화면에 나오는 역할 이름 — 내부 템플릿 이름(chapter·keyword·motion·card·broll·title)은 화면에 내지 않는다(품질 게이트 B5,
// 10/1 테스트: 숏폼 카드 머리에 'motion'·'card', 보드 머리줄에 '( motion )'). 빈 문자열이면 쓰는 곳이 라벨을 그리지 않는다.
export const TEMPLATE_LABEL: Record<TemplateName, string> = {
  chapter: '',
  keyword: '',
  definition: '정의',
  quote: '인용',
  list: '정리',
  process: '프로세스',
  cycle: '순환',
  double_diamond: '더블 다이아몬드',
  matrix: '매트릭스',
  compare: '비교',
  timeline: '연표',
  stat: '숫자',
  venn: '교집합',
  pyramid: '위계',
  photo: '자료',
  motion: '',
  card: '',
  broll: '',
  evidence: '',
  title: '',
  lower_third: '',
  recap: '정리',
};
