import type {Surface} from '../../design/surfaces';
import type {Theme} from '../../design/tokens';
import type {Brand, Episode, GraphicData, Layout} from '../../lib/types';

export type TemplateProps = {
  id: string;
  data: GraphicData;
  frame: number; // 시퀀스 내부 프레임
  dur: number; // 전체 프레임 수
  fps: number;
  theme: Theme;
  surface: Surface;
  box: {w: number; h: number};
  layout: Layout;
  brand: Brand;
  episode: Episode;
  compact?: boolean; // 숏폼 상단 패널
};
