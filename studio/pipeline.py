"""오토파일럿: 주제 설명 + 원본 영상 + 대본 → 롱폼 1편 + 숏폼 2편(+ 썸네일·자막·업로드 정보).

사용자가 주는 것은 세 가지뿐이고(원본 영상은 여러 개여도 된다), 나머지는 전부 여기서 자동으로 정한다.
  원본 확인(여러 개면 소리로 다시점 싱크·묶음 → 가상 타임라인, studio/media/sources.py)
  → 목소리 다듬기 → 얼굴 추적·화면 품질 → 음성 인식 → 대본 정렬·가장 또렷하고 잘 나온 테이크 → 자동 색보정
  → 🎬 AI 기획(감독 + 전문 팀: 구성·얼굴/그래픽 배분·강조 순간·모션그래픽·자료·자막·숏폼·제목)
  → 편집본(컷 + 색) → 🔎 편집 검사(Whisper 로 다시 받아 적어 남은 되풀이·무음을 더 자름)
  → 자료 사진·스톡(모션 장면 이미지 포함)·효과음·배경음악 → 🧐 아트 디렉터 검수
  → 렌더(앵글 고르기(다시점) + 편집 문법 엔진: 점프컷 프레이밍·소프트 컷·강조 글라이드·전환·콜아웃·강조 자막,
    화면 구성은 대본·기획을 보고 챕터·그래픽마다 섞는 하이브리드)
  → 음향 믹스·마스터링(-14 LUFS) → 마무리(썸네일·자막·검토 시트·업로드 정보)

각 단계 결과는 작업 폴더(work/)에 캐시되어, 재실행하면 바뀐 단계부터만 다시 한다.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import shutil
import threading
import time
import traceback
from concurrent.futures import FIRST_EXCEPTION, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from rapidfuzz import fuzz

from . import diag, gate
from .agents.studio import Studio
from .asr.transcribe import gpu_expected, load_audio_16k, speech_regions, transcribe
from .broll.entities import find_entities
from .broll.images import Wikimedia, list_local_images
from .broll.logos import SimpleIcons
from .broll.mat import mat_tall
from .broll.resolve import MediaPlan, MediaResolver, contact_rows
from .broll.wikipedia import WikipediaImages
from .director import fallback
from .director.catalog import TEMPLATES
from .director.claude import ClaudeClient, DirectorError
from .director.claude_code import ClaudeCodeClient, find_claude, resolve_backend
from .director.context import (JobBrief, load_prompt, long_instruction, shared_context, shorts_instruction,
                               system_prompt)
from .motion.card import card_settle_time, card_text
from .motion.check import CheckError, check_cards, problem_lines
from .director.plan import EVIDENCE as EVIDENCE_TEMPLATES
from .director.plan import (TimedGraphic, blank_graphic, merge_step_runs, type_card, normalize_long, normalize_shorts, seg_edit_times,
                            spec_settle_time, time_graphics, word_edit_time)
from .director.schema import LONG_PLAN, SHORTS_PLAN
from .edit.assemble import build_proxy, cut_audio, proxy_height_for
from .edit.cuts import PACES, build_keeps, keeps_for_segments
from .edit.grammar import PARAMS, EditDecisions, Moment, build_long_edit, build_short_edit, directed_sfx
from .edit.style import LookPlan, apply_looks, choose_looks
from .edit.verify import find_issues, merge, subtract, to_source
from .eta import Eta, features
from .export.premiere import export_xml
from .export.report import edit_report, write_text, youtube_text
from .grade import auto as grade
from .grade import scopes
from .media.audio import build_voice_track
from .media.ffmpeg import FFmpeg, MediaInfo, hdr_to_sdr_filter, pick_output_fps
from .media.mix import BgmPlan, SfxCue, measure_lufs, mix, mux_final
from .media.sources import (Piece, Quality, SourceMap, analyze_sources, angle_cut_times, angle_summary, choose_angles,
                            clips_for, face_track, master_audio_args, visual_scorer)
from .models import Span, Tag, TimeMap, Utterance, Word
from .net import download as net_download, redact
from .paths import USER_DIR
from .render.assets import copy_fonts, make_grain, make_paper
from .render.props import (Episode, apply_edit, brand_props, caption_overlays, dedupe_captions, hide_over, high_load_spans,
                           mark_sequences, face_safe_layouts, long_props,
                           mark_soft_cuts, mark_stack_cues, prepend_props, shift_decisions, shift_props, short_beats,
                           short_props, strip_audio, text_graphic_spans, chapter_maps, chapter_recaps,
                           fold_keywords_into_media, bridge_split_gaps, stack_avoid_spans)
from .render.remotion import RenderItem, RenderJob, find_node, run_render
from .settings import Settings
from .sound.cues import clean_music, fallback_music, plan_cues, resolve as resolve_cues
from .sound.library import MOODS_LONG, MOODS_SHORT, SoundLibrary
from .sound.tracks import track_listing
from .stock.providers import StockHub
from .stock.research import StockResearcher, contact_sheet, strip_stock_images
from .text.align import ScriptAligner, build_utterances, norm
from .text import fidelity
from .text.takes import clean_words, vad_pause
from .text.captions import cues_to_srt
from .text.script import glossary_terms, parse_script
from .util import (CancelToken, Cancelled, LogFn, file_fingerprint, fmt_ts, noop_log, read_json, slugify, text_hash,
                   write_json)
from .vision.face import track_faces

StageProgress = Callable[[str, float, float], None]  # (단계 키, 단계 진행률, 전체 진행률)

STAGES: list[tuple[str, str, float]] = [
    ("probe", "영상 확인", 1),
    ("audio", "목소리 다듬기(잡음 제거·EQ·음량)", 4),
    ("face", "얼굴 추적 · 화면 품질", 5),
    ("asr", "음성 인식(Whisper)", 20),
    ("research", "주제 조사(🔎 리서치 디렉터 · 웹)", 6),
    ("align", "대본 맞추기 · 가장 또렷한 테이크 고르기", 2),
    ("grade", "자동 색보정", 3),
    ("director", "AI 기획(감독 + 전문 팀)", 9),
    ("proxy", "편집본 만들기(컷·색)", 8),
    ("verify", "편집 오류 검사(음성 다시 인식)", 5),
    ("broll", "자료 사진", 2),
    ("stock", "스톡 영상·사진", 3),
    ("sound", "효과음·배경음악 준비", 2),
    ("qa", "아트 디렉터 검수", 4),
    ("music", "음악 큐 시트(음악 감독)", 1),
    ("render", "렌더링", 30),
    ("master", "음향 믹스·마스터링", 5),
    ("export", "마무리(썸네일·자막·검토 시트·업로드 정보)", 2),
]
STAGE_LABEL = {k: v for k, v, _ in STAGES}
EXTRAS = "부가자료"

# 서로 기다릴 필요가 없는 단계는 동시에 돈다 — 칸(차례로) → 줄(동시에) → 단계(줄 안에서 차례로).
#  · 얼굴 추적(영상 디코딩)은 목소리 다듬기 → 음성 인식(소리·GPU)과 함께, 🔎 주제 조사(웹 · 대본과 주제 설명만 본다)도 함께
#  · 🎬 AI 기획(네트워크)은 색보정 → 편집본 인코딩(GPU/CPU)과 함께 — 컷은 둘 다 끝난 뒤(_make_edit)
#  · 🔎 편집 검사(Whisper)는 자료 사진 → 스톡(네트워크) · 효과음 준비 → 렌더 번들 미리 만들기와 함께
#  · 🎼 음악 큐 시트는 편집 검사가 컷을 확정한 뒤, 아트 디렉터 검수와 함께
#  · 렌더 중에 음향 믹스를 미리 만들어 두고(stage_render) 마스터링 단계는 합치기만 한다
# STAGES 에 없는 키(bundle)는 화면·남은 시간에 나오지 않는 준비 작업이다(실패해도 작업은 계속).
SCHEDULE: list[list[list[str]]] = [
    [["probe"]],
    [["audio", "asr"], ["face"], ["research"]],
    [["align"]],
    [["director"], ["grade", "proxy"]],
    [["verify"], ["broll", "stock"], ["sound", "bundle"]],
    [["qa"], ["music"]],
    [["render"]],
    [["master"]],
    [["export"]],
]
PLAN_ONLY = ("probe", "audio", "asr", "face", "research", "align", "grade", "director")
# 말단 작업 — 실패해도 영상은 끝까지 만든다(그 단계만 건너뛰고 안전한 대체 상태로). 원본·음성 인식·대본 맞추기·
# 렌더·합치기만 영상에 꼭 필요하다. 채널 주인: "초기 작업의 외부 프로그램 오류 하나로 전체 작업이 다 망한다"
SOFT_STAGES = {"audio", "face", "research", "grade", "verify", "broll", "stock", "sound", "qa", "music", "export"}
MUSIC_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}


def schedule_for(until: str = "all") -> list[list[list[str]]]:
    """until='plan' 이면 기획까지만(편집본·렌더 없이)."""
    if until != "plan":
        return [[list(lane) for lane in st] for st in SCHEDULE]
    out = []
    for st in SCHEDULE:
        lanes = [[k for k in lane if k in PLAN_ONLY] for lane in st]
        lanes = [lane for lane in lanes if lane]
        if lanes:
            out.append(lanes)
    return out


@dataclass
class JobSpec:
    """사용자가 주는 것은 video · topic · script 세 가지. 나머지는 자동(테스트·고급용으로만 남김).
    원본을 여러 개 넣으면 첫 번째가 video, 나머지가 videos — 같은 순간을 다른 각도에서 찍었으면(다시점) 소리로 싱크를
    맞춰 구간마다 가장 잘 나온 앵글을 고르고, 따로 찍었으면 입력 순서대로 이어 붙여 같은 문장은 더 나은 테이크를 쓴다."""
    video: str
    videos: list[str] = field(default_factory=list)   # 두 번째 이후 원본
    topic: str = ""                     # ① 이 영상의 주제 설명(무엇을·누구에게·왜)
    script: str = ""                    # ③ 대본
    title: str = ""                     # 비우면 🎬 감독이 정한다
    # ---- 이하 자동(기본값 그대로 쓰는 것을 전제) ----
    audio: str = ""
    episode: str = ""
    subtitle: str = ""
    series: str = "디자인 이론"
    notes: str = ""                     # (이전 버전) 메모 → topic 과 합친다
    images_dir: str = ""
    bgm: str = ""                       # 직접 고른 배경음악(비우면 라이브러리에서 무드로 자동)
    lut: str = ""                       # 직접 만든 LUT(비우면 자동 색보정)
    make_long: bool = True
    shorts_count: int = 2               # 최대 편수 — 제대로 된 1편이 우선, 둘째는 다른 아이디어·8점 이상일 때만
    short_max_sec: int = 55
    opening_highlight: bool = True      # 롱폼 맨 앞에 임팩트 있는 문장 2~4개(≤20초)를 붙이고 처음부터 시작
    highlight_max_sec: int = 20
    out_height: int = 1080
    pace: str = "calm"
    use_claude: bool = True
    fetch_broll: bool = True
    grain: bool = False                 # 필름 그레인(리서치: 교육 채널은 끔)
    caption_preset: str = "auto"
    short_caption_preset: str = "auto"
    studio_mode: bool = True
    research: bool = True          # 🔎 주제 조사(웹) — 대본의 인물·제품·개념을 먼저 조사해 팀에 넘긴다
    fetch_stock: bool = True
    verify_edit: bool = True       # 편집 후 목소리를 다시 인식해 남은 되풀이·무음을 한 번 더 자른다
    # 화면 구성: auto = 대본·전사·기획을 보고 챕터·그래픽마다 기본 디자인과 사용자 템플릿(종이 콜라주)을 섞는 하이브리드
    #           (studio/edit/style.py). classic·paper 는 한쪽만 쓰는 개발·시험용
    skin: str = "auto"
    motion_scenes: bool = True
    qa_rounds: int = 1
    direction: str = ""
    thumbnails: bool = True
    sfx: bool = True
    music: bool = True
    auto_grade: bool = True
    enhance_voice: bool = True
    shorts_layout: str = "reel"         # 참고 릴스식(위 큰 카드 · 아래 얼굴 · 이음새 굵은 자막) | window | full | framed
    progress_bar: bool = False
    endcard: bool = True
    reuse_plan: bool = True
    export_xml: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobSpec":
        names = {f.name for f in fields(cls)}
        d = dict(d)
        if "caption_style" in d and "caption_preset" not in d:  # 이전 버전 job.json 호환
            d["caption_preset"] = "boxed" if d["caption_style"] == "box" else "auto"
        return cls(**{k: v for k, v in d.items() if k in names})

    def sources(self) -> list[str]:
        out: list[str] = []
        for v in [self.video] + list(self.videos or []):
            if v and v not in out:
                out.append(v)
        return out

    @property
    def topic_text(self) -> str:
        return "\n\n".join(x.strip() for x in (self.topic, self.notes) if x and x.strip())

    def working_title(self) -> str:
        if self.title.strip():
            return self.title.strip()
        first = next((ln.strip(" #-*") for ln in self.topic_text.splitlines() if ln.strip()), "")
        if first:
            return first[:40]
        return Path(self.video).stem[:40] or "새 영상"


def new_job_dir(settings: Settings, title: str) -> Path:
    base = Path(settings.projects_dir)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    d = base / f"{stamp}_{slugify(title, 30)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Pipeline:
    def __init__(self, spec: JobSpec, settings: Settings, job_dir: Path, *, log: LogFn = noop_log,
                 progress: Optional[StageProgress] = None, cancel: Optional[CancelToken] = None,
                 eta: Optional[Eta] = None, preview: Optional[Callable[[str, str], None]] = None,
                 force_render: bool = False):
        """preview(이미지 경로, 설명): 진행 화면 미리보기 — 색보정 전후 · 자료 사진 · 검수 장면 · 렌더 중 프레임 · 썸네일.
        force_render: 품질 게이트가 막아도 렌더한다(CLI --force-render 로만 — 창에는 버튼이 없다)."""
        self.spec = spec
        self.settings = settings
        self.dir = Path(job_dir).resolve()   # 렌더 스크립트는 renderer/ 에서 돈다 — 상대 경로면 못 찾음
        self.work = self.dir / "work"
        self.media = self.dir / "media"
        self.render_dir = self.dir / "render"
        self.public = self.render_dir / "public_src"
        self.out = self.dir / "output"
        self.extras = self.out / EXTRAS
        for d in (self.work, self.media, self.public, self.out, self.extras):
            d.mkdir(parents=True, exist_ok=True)
        self._user_log = log
        self.log_file = self.work / "log.txt"
        self.log = self._log   # 창·콘솔 + work/log.txt(진단 자료에 들어감)
        self._progress = progress or (lambda *_: None)
        self.cancel = cancel or CancelToken()
        self.eta = eta or Eta(USER_DIR / "eta_history.json")
        self._preview_cb = preview
        self.ff = FFmpeg(settings.ffmpeg_path, settings.ffprobe_path)
        self.title = spec.working_title()
        self.slug = slugify(self.title, 30)
        # 단계 사이에 공유하는 상태
        self.info: Optional[MediaInfo] = None       # 원본이 여러 개면 가상 타임라인(이어 붙인 목소리 기준)
        self.infos: dict[int, MediaInfo] = {}          # 카메라(입력 순서) → 원본 정보
        self.smap: SourceMap = SourceMap()
        self.quality: dict[int, Quality] = {}          # 카메라 → 화면 품질 표본
        self.face_cams: dict[int, list[dict]] = {}     # 카메라 → 얼굴 트랙(카메라 영상 시각)
        self.soft_failures: list[dict] = []             # 건너뛴 말단 작업(리포트·진단용)
        self.force_render = force_render
        self.gate_results: list[gate.GateResult] = []   # 🚦 품질 게이트(work/gate.json · 편집리포트 첫 절)
        self.long_pieces: list[Piece] = []             # 롱폼 앵글 조각
        self.short_pieces: list[list[Piece]] = []
        self.hl_map: Optional[TimeMap] = None          # 🎬 오프닝 하이라이트(본편 앞 콜드 오픈) 컷
        self.hl_pieces: list[Piece] = []
        self.hl_segs: list[int] = []
        self.hl_duration = 0.0
        self.fps = 30
        self.utts: list[Utterance] = []
        self.tags: list[Tag] = []
        self.align_report: dict = {}
        self.vad: list[tuple[float, float]] = []
        self.face: list[dict] = []
        self.plan_long: dict = {}
        self.plan_shorts: list[dict] = []
        self.director_name = ""
        self.claude: Optional[ClaudeClient] = None
        self.studio: Optional[Studio] = None
        self.research: dict = {}       # 🔎 조사 노트(work/research.json)
        self.ctx = ""
        self.broll_log: list[dict] = []
        self.evidence_stats: dict[str, Any] = {}      # 자료 조달 깔때기(work/evidence.json)
        self._materials: list = []                    # ④ 자료 폴더 색인(studio/assets/local.py)
        self.qa_log: list[dict] = []
        self.grade_info: dict = {}
        self.look_plan: Optional[LookPlan] = None
        self.sounds: Optional[SoundLibrary] = None
        self.masters: list[dict] = []
        self.results: dict[str, Any] = {}
        self._render_prep: Optional[list[tuple[Path, str]]] = None
        self._ai_lock = threading.RLock()       # 동시에 도는 단계가 AI 연결·스튜디오·효과음 라이브러리를 한 번만 만들게
        self._sound_lock = threading.Lock()
        self._mix_job: Optional[Future] = None  # 렌더 중에 미리 만드는 음향 믹스

    # ------------------------------------------------------------------
    def _log(self, msg: str) -> None:
        msg = redact(msg)          # 키 값은 창에도 log.txt(진단 자료)에도 남기지 않는다
        self._user_log(msg)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        except OSError:
            pass

    def _log_file_only(self, msg: str) -> None:
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(redact(msg).rstrip() + "\n")
        except OSError:
            pass

    def _stage(self, key: str, frac: float) -> None:
        self.eta.update(key, frac)
        overall = self.eta.fraction()
        if overall is None:   # 시간 계획 전(영상 확인 중)에는 고정 가중치로
            idx = [k for k, _, _ in STAGES].index(key)
            total = sum(w for _, _, w in STAGES)
            before = sum(w for _, _, w in STAGES[:idx])
            overall = (before + STAGES[idx][2] * max(0.0, min(1.0, frac))) / total
        self._progress(key, frac, overall)

    def _preview(self, path: Path | str, caption: str) -> None:
        if self._preview_cb and Path(path).exists():
            try:
                self._preview_cb(str(path), caption)
            except Exception:  # noqa: BLE001 - 미리보기 실패가 작업을 멈추면 안 됨
                pass

    # ---- 남은 시간 예측(studio/eta.py) ----
    def _eta_features(self, long_s: Optional[float] = None, shorts_s: Optional[float] = None) -> dict:
        assert self.info
        if long_s is None:   # 기획 전: NG·반복을 조금만 걷어낸다고 보고 넉넉히
            long_s = self.info.duration * 0.85 if self.spec.make_long else 0.0
        if shorts_s is None:
            shorts_s = self.spec.shorts_count * self.spec.short_max_sec
        return features(src_s=self.info.duration, out_fps=self.fps, long_s=long_s, shorts_s=shorts_s,
                        thumbs=bool(self.spec.thumbnails),
                        video_s=sum(i.duration for i in self.infos.values()) or None)

    def _eta_plan(self, steps: list[list[list[str]]]) -> None:
        steps = [[[k for k in lane if k in STAGE_LABEL] for lane in st] for st in steps]
        keys = [k for st in steps for lane in st for k in lane]
        ai = self._use_api()
        gpu = gpu_expected(self.settings.whisper_device, self.log)
        variants = {"asr": "asr@gpu" if gpu else "asr@cpu", "verify": "verify@gpu" if gpu else "verify@cpu",
                    "director": "director@ai" if ai else "director@rule",
                    "research": "research@ai" if (ai and self.spec.studio_mode and self._research_on()) else "research@rule",
                    "align": "align@ai" if (ai and self.spec.studio_mode) else "align",
                    "qa": "qa@ai" if ai else "qa@rule",
                    "music": "music@ai" if (ai and self.spec.studio_mode) else "music@rule",
                    "export": "export@ai" if (ai and self.spec.studio_mode) else "export",
                    "stock": ("stock@ai" if ai else "stock@rule") if self._stock_enabled() else "stock@off"}
        self.eta.plan(keys, variants, self._eta_features(), steps=steps)

    def _eta_refine(self) -> None:
        """편집본을 만든 뒤: 롱폼·숏폼 길이가 정해졌으니 렌더·믹스 시간을 다시 잡는다."""
        tm = getattr(self, "timemap", None)
        long_s = tm.duration if (tm is not None and self.spec.make_long) else 0.0
        shorts_s = sum(t.duration for t in getattr(self, "short_maps", []) or [])
        feats = self._eta_features(long_s=long_s, shorts_s=shorts_s)
        for key in ("verify", "render", "master"):
            self.eta.refine(key, feats)

    def _sp(self, key: str):
        return lambda f: self._stage(key, f)

    def run(self, until: str = "all") -> dict[str, Any]:
        """until='plan' 이면 기획까지만, 'all' 이면 렌더·마스터링·마무리까지. 독립된 단계는 동시에(SCHEDULE)."""
        t0 = time.time()
        write_json(self.dir / "job.json", self.spec.to_dict())
        fns: dict[str, Callable[[], None]] = {k: getattr(self, f"stage_{k}") for k in STAGE_LABEL}
        fns["proxy"] = self._encode_proxies          # 컷은 AI 기획과 편집본이 모두 끝난 뒤(_make_edit)
        fns["bundle"] = self._prebundle
        schedule = schedule_for(until)
        self._resolve_sound()
        self.eta.begin()
        srcs = self.spec.sources()
        self.log(f"══ 작업 시작 {time.strftime('%Y-%m-%d %H:%M')} · 원본 {Path(srcs[0]).name}"
                 + (f" 외 {len(srcs) - 1}개" if len(srcs) > 1 else ""))
        try:
            for step in schedule:
                self.cancel.check()
                self._run_step(step, fns)
                keys = {k for lane in step for k in lane}
                if "probe" in keys:
                    self._eta_plan(schedule)
                elif "proxy" in keys:
                    self._make_edit()
                    self._gate_cut()
                    self._eta_refine()
        except Exception as e:
            self._drop_mix_job()
            tb = traceback.format_exc()
            self._log_file_only(tb)
            z = diag.write(self, error=f"{e}\n{tb}")
            if z:
                self.log(f"진단 자료: {z} — 문제를 알릴 때 이 파일을 보내 주세요.")
            raise
        mins = (time.time() - t0) / 60
        self.log(f"완료 ({mins:.1f}분) → {self.out}")
        diag.write(self)
        res = {"output": str(self.out), "job_dir": str(self.dir), "title": self.title, **self.results}
        write_json(self.work / "result.json", res)
        return res

    def _run_stage(self, key: str, fn: Callable[[], None]) -> None:
        if key not in STAGE_LABEL:     # 보이지 않는 준비 작업: 실패해도 나중 단계가 다시 한다
            try:
                fn()
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                self._log_file_only(f"   (미리 준비 {key} 실패 — 나중에 다시 합니다: {e})")
            return
        self.cancel.check()
        self.log(f"━━ {STAGE_LABEL[key]}")
        self.eta.start(key)
        t_stage = time.time()
        self._stage(key, 0.0)
        try:
            fn()
        except Cancelled:
            raise
        except Exception as e:
            if key not in SOFT_STAGES or self.cancel.cancelled or isinstance(e, gate.GateBlocked):
                raise           # 품질 게이트가 멈추라고 한 것은 말단 단계라도 삼키지 않는다
            self._log_file_only(traceback.format_exc())
            self.log(f"⚠️ {STAGE_LABEL[key]} 실패 — 이 단계만 건너뛰고 계속합니다: {e}")
            self.soft_failures.append({"stage": key, "label": STAGE_LABEL[key], "error": str(e)[:300]})
            try:
                getattr(self, f"_soft_{key}", lambda: None)()
            except Exception as e2:  # noqa: BLE001 - 대체 상태조차 못 만들면 원래 오류로
                self._log_file_only(traceback.format_exc())
                raise e from e2
        self._stage(key, 1.0)
        self.eta.finish(key)
        self._log_file_only(f"   ({STAGE_LABEL[key]} {time.time() - t_stage:.1f}s)")
        if key == "grade":
            self._preview(self.extras / "색보정_전후.jpg", "자동 색보정 · 왼쪽 원본 / 오른쪽 보정")

    def _run_step(self, step: list[list[str]], fns: dict[str, Callable[[], None]]) -> None:
        """한 칸: 줄이 하나면 그대로, 여럿이면 줄마다 스레드 하나(FFmpeg·Whisper·AI 호출은 GIL 밖에서 돈다).
        한 줄이 실패하면 나머지 줄을 멈추고(취소 신호) 그 오류를 그대로 올린다."""
        lanes = [lane for lane in step if lane]
        if len(lanes) == 1:
            for key in lanes[0]:
                self._run_stage(key, fns[key])
            return
        shown = [" → ".join(STAGE_LABEL[k] for k in lane if k in STAGE_LABEL) for lane in lanes]
        self._log_file_only("   (동시에: " + " ∥ ".join(x for x in shown if x) + ")")

        first: list[BaseException] = []      # 먼저 난 오류(멈추게 한 뒤 다른 줄에서 따라 난 오류가 아니라 원인)
        lock = threading.Lock()

        def lane_fn(lane: list[str]) -> None:
            try:
                for key in lane:
                    self._run_stage(key, fns[key])
            except BaseException as e:
                with lock:
                    if not first and not (isinstance(e, Cancelled) or self.cancel.cancelled):
                        first.append(e)
                raise

        with ThreadPoolExecutor(max_workers=len(lanes), thread_name_prefix="stage") as pool:
            futs = [pool.submit(lane_fn, lane) for lane in lanes]
            wait(futs, return_when=FIRST_EXCEPTION)
            if first and not self.cancel.cancelled:
                self.cancel.cancel()      # 함께 돌던 단계(인코딩·AI 호출 등)를 바로 멈춘다
        errors = [f.exception() for f in futs if f.exception() is not None]
        if first:
            raise first[0]
        if errors:
            raise errors[0]

    # ------------------------------------------------------------------
    def _sfx_mode(self) -> str:
        st = self.settings
        if getattr(st, "sfx_enabled", False):
            return "auto"
        mode = str(getattr(st, "sfx_mode", "directed") or "directed")
        return mode if mode in ("off", "directed", "auto") else "directed"

    def _directed_segments(self, seg_t: dict[int, tuple[float, float]], shift: float = 0.0) -> list[tuple[float, str]]:
        """트리트먼트 화면 구성표의 단락 효과음 → [(편집 시각, 효과음)]."""
        tr = (self.plan_long.get("studio") or {}).get("treatment") or {}
        out = []
        for s in tr.get("segments") or []:
            try:
                a = int(s.get("start_seg", -1))
            except (TypeError, ValueError):
                continue
            ids = sorted(i for i in seg_t if i >= a)
            if ids and s.get("sfx") and s["sfx"] != "none":
                out.append((seg_t[ids[0]][0] + shift, str(s["sfx"])))
        return out

    def _resolve_sound(self) -> None:
        """설정의 소리 방침 → 이번 작업: 효과음은 켰을 때만, 배경음악은 직접 고른 곡 → 내 음악 폴더(mine) →
        기본 라이브러리(library) → 없음(off). 내 음악 폴더가 비어 있으면 배경음악 없이(라이브러리로 몰래 넘어가지 않는다)."""
        st = self.settings
        if self._sfx_mode() == "off":
            self.spec.sfx = False
        mode = getattr(st, "music_mode", "mine")
        if self.spec.bgm and Path(self.spec.bgm).exists():
            return
        if mode == "off":
            self.spec.music = False
        elif mode == "mine" and self.spec.music:
            folder = Path(getattr(st, "music_dir", "") or (USER_DIR / "music"))
            tracks = sorted(p for p in folder.glob("*") if p.suffix.lower() in MUSIC_EXT) if folder.is_dir() else []
            if tracks:
                # 임시로 한 곡(같은 영상이면 같은 곡) — 곡이 둘 이상이면 🎼 음악 감독(Claude)이 측정값과 트리트먼트를 보고 고친다
                self._my_tracks = tracks
                self.spec.bgm = str(tracks[int(text_hash(self.spec.topic or self.spec.video), 16) % len(tracks)])
                self.log(f"🔊 배경음악: 내 음악 폴더 {len(tracks)}곡" + (" — 🎼 음악 감독이 이 영상에 맞는 곡을 고릅니다"
                                                                      if len(tracks) > 1 else f" 「{Path(self.spec.bgm).stem}」"))
            else:
                self.spec.music = False
                self.log(f"🔊 배경음악 없이(내 음악 폴더 {folder} 가 비어 있음 — 곡을 넣으면 그 곡을 씁니다)")
        if not self.spec.sfx:
            self._log_file_only("   (효과음 끔 — 고급 설정 › 소리에서 켤 수 있음)")

    # ------------------------------------------------------------------
    # 말단 작업이 실패했을 때의 대체 상태(SOFT_STAGES) — 영상은 끝까지 나온다
    def _soft_audio(self) -> None:
        """목소리 다듬기 실패 → 다듬지 않은 원본 목소리(잡음 제거·EQ 없이)."""
        voice, asr = self.work / "voice.wav", self.work / "asr16k.wav"
        src = self.spec.audio or self.spec.video
        if not self.smap.single and (self.work / "master_audio.wav").exists():
            src = str(self.work / "master_audio.wav")
        try:
            build_voice_track(self.ff, src, voice, external_audio=None, duration=self.info.duration, enhance=False,
                              denoise_model=None, av_offset=self.info.av_offset, log=self.log, cancel=self.cancel)
        except Exception as e:  # noqa: BLE001 - 그래도 안 되면 소리만 그대로 뽑는다
            self._log_file_only(f"   (원본 목소리 다듬기 없이 뽑기도 실패 → 소리만 추출: {e})")
            self.ff.extract_audio(src, voice, rate=48000, mono=True, cancel=self.cancel, duration=self.info.duration)
        self.ff.extract_audio(voice, asr, rate=16000, mono=True, cancel=self.cancel, duration=self.info.duration)
        self.log("   → 다듬지 않은 원본 목소리로 계속합니다")

    def _soft_face(self) -> None:
        self.face_cams, self.quality, self.face = {}, {}, []
        self.log("   → 얼굴 위치 없이(화면 가운데 기준) 계속합니다")

    def _soft_grade(self) -> None:
        self.grade_info = {}
        for c in self.smap.cams:
            self._cube(c.idx).unlink(missing_ok=True)
        self.log("   → 색보정 없이 원본 색으로 계속합니다")

    def _soft_broll(self) -> None:
        """찾지 못한(파일이 없는) 자료 사진은 뺀다 — 렌더가 없는 파일을 찾다 실패하지 않게."""
        for gl in [self.plan_long.get("graphics", [])] + [sh.get("graphics", []) for sh in self.plan_shorts]:
            gl[:] = [g for g in gl if g.get("template") != "photo" or str(g.get("image", "")).startswith("images/")]
        self.log("   → 자료 사진 없이 계속합니다")

    def _soft_stock(self) -> None:
        lists = [self.plan_long.get("graphics", [])] + [sh.get("graphics", []) for sh in self.plan_shorts]
        for gl in lists:
            gl[:] = [g for g in gl if g.get("template") != "broll" or g.get("src")]
        strip_stock_images(lists)
        self.log("   → 스톡 없이 계속합니다")

    def _soft_sound(self) -> None:
        self.spec.sfx = False
        self.spec.music = False
        self.log("   → 효과음·배경음악 없이(목소리만) 계속합니다")

    # ------------------------------------------------------------------
    def stage_probe(self) -> None:
        paths = self.spec.sources()
        probed = []
        for path in paths:
            info = self.ff.probe(path)
            if not info.has_video:
                raise RuntimeError("영상 스트림이 없습니다: " + path)
            probed.append((path, info))
        if len(probed) == 1 and not probed[0][1].has_audio and not self.spec.audio:
            raise RuntimeError("영상에 소리가 없습니다. 목소리가 녹음된 영상을 넣어 주세요.")
        if len(probed) > 1:
            if not any(i.has_audio for _, i in probed):
                raise RuntimeError("원본 영상 모두 소리가 없습니다. 목소리가 녹음된 영상을 넣어 주세요.")
            silent = [p for p, i in probed if not i.has_audio]
            if silent:   # 소리로 싱크를 맞추므로 소리 없는 카메라는 어디에 놓을지 알 수 없다
                self.log("⚠ 소리가 없는 영상은 싱크를 맞출 수 없어 뺍니다: " + ", ".join(Path(p).name for p in silent))
                probed = [(p, i) for p, i in probed if i.has_audio]
        paths = [p for p, _ in probed]
        self.infos = {i: info for i, (_, info) in enumerate(probed)}
        info0 = self.infos[0]
        self.fps = pick_output_fps(info0)
        for i, info in self.infos.items():
            w, h = info.display_size
            self.log(f"원본{f' {i + 1}' if len(paths) > 1 else ''} {w}x{h} · {info.fps:.2f}fps"
                     f"{' (VFR)' if info.vfr else ''} · {info.duration / 60:.1f}분 · {info.vcodec}"
                     f"{' · HDR' if info.is_hdr else ''}" + (f" → 출력 {self.fps}fps" if i == 0 else ""))
        if len(paths) == 1:
            self.smap = SourceMap.one(paths[0], info0.duration)
            self.info = info0
        else:
            if self.spec.audio:
                self.log("(원본이 여러 개일 때는 외부 녹음 파일 대신 카메라 소리 중 가장 깨끗한 것을 씁니다)")
            key = text_hash([file_fingerprint(p) for p in paths], self.fps, "sources-v2")
            cached = read_json(self.work / "sources.json", {})
            if cached.get("key") == key:
                self.smap = SourceMap.from_dict(cached)
                for c in self.smap.cams:      # 내용은 같고 이름·위치만 바뀐 파일(내용 지문이 같음)
                    c.path = paths[c.idx]
            else:
                self.smap = analyze_sources(self.ff, paths, [self.infos[i] for i in range(len(paths))], fps=self.fps,
                                            log=self.log, cancel=self.cancel)
                write_json(self.work / "sources.json", {"key": key, **self.smap.to_dict()})
            self.log("🎥 " + self.smap.summary())
            # 가상 타임라인: 0초 = 첫 묶음의 첫 영상 프레임, 목소리·영상 시작 차이는 묶음마다 이미 맞춤
            self.info = replace(self.infos[self.smap.groups[0].cams[0].idx], duration=self.smap.total,
                                v_start=0.0, a_start=0.0, has_audio=True)
        write_json(self.work / "probe.json", {**asdict(self.info), "sources": self.smap.to_dict()})

    def _sound_lib(self, *, full: bool = True) -> SoundLibrary:
        with self._sound_lock:
            if self.sounds is None or (full and not getattr(self.sounds, "_full", False)):
                lib = SoundLibrary(log=self.log)
                lib.ensure(download=bool(getattr(self.settings, "download_sounds", True)), cancel=self.cancel,
                           kinds=None if full else ("models",))
                lib._full = full  # type: ignore[attr-defined]
                self.sounds = lib
            return self.sounds

    def stage_audio(self) -> None:
        assert self.info
        model = None
        if self.spec.enhance_voice:
            try:
                model = self._sound_lib(full=False).rnnoise_model()
            except Exception as e:  # noqa: BLE001 - 잡음 제거 모델이 없으면 기본 필터로
                self.log(f"(잡음 제거 모델 준비 실패 → 기본 필터 사용: {e})")
        multi = not self.smap.single
        key = text_hash([file_fingerprint(p) for p in self.spec.sources()],
                        file_fingerprint(self.spec.audio) if (self.spec.audio and not multi) else "",
                        self.spec.enhance_voice, bool(model), round(self.info.av_offset, 3),
                        self.smap.to_dict() if multi else "", "v6")
        voice = self.work / "voice.wav"
        asr = self.work / "asr16k.wav"
        meta = read_json(self.work / "audio.json", {})
        if meta.get("key") == key and voice.exists() and asr.exists():
            self.log("목소리: 캐시 사용")
            return
        self.log("목소리: 원본 분석 → 필요한 만큼만 맞춤 보정(정상 범위면 손대지 않음)"
                 + ("" if model else " · RNNoise 모델 없음(잡음이 많을 때만 afftdn)"))
        src = self.spec.video
        if multi:   # 묶음마다 가장 깨끗한 카메라 소리를 가상 타임라인에 이어 붙인 원본 목소리
            src = str(self.work / "master_audio.wav")
            self.ff.run(master_audio_args(self.smap, self.infos, src), duration=self.info.duration, cancel=self.cancel,
                        what="원본 목소리 잇기")
        info = build_voice_track(self.ff, src, voice, external_audio=(self.spec.audio or None) if not multi else None,
                                 duration=self.info.duration, enhance=self.spec.enhance_voice, denoise_model=model,
                                 av_offset=self.info.av_offset,
                                 log=self.log, progress=lambda f: self._stage("audio", f * 0.85), cancel=self.cancel)
        self.ff.extract_audio(voice, asr, rate=16000, mono=True, cancel=self.cancel, duration=self.info.duration)
        write_json(self.work / "audio.json", {"key": key, **info})

    def stage_asr(self) -> None:
        assert self.info
        parsed = parse_script(self.spec.script)
        hints = glossary_terms(parsed, extra=list(self.settings.glossary.values()))
        key = text_hash(file_fingerprint(self.work / "asr16k.wav"), self.settings.whisper_model, hints, "v2")
        cached = read_json(self.work / "transcript.json", {})
        if cached.get("key") == key and cached.get("words"):
            self.log(f"음성 인식: 캐시 사용 ({len(cached['words'])}단어)")
            return
        # 음성 인식은 영상에 꼭 필요하다 — 설정대로 안 되면(GPU 드라이버·모델 내려받기·메모리) CPU, 더 작은 모델 순으로
        # 다시 시도한다. 하나라도 되면 작업은 계속된다
        s = self.settings
        tries = [(s.whisper_model, s.whisper_device, s.whisper_compute, s.whisper_batch)]
        if s.whisper_device != "cpu":
            tries.append((s.whisper_model, "cpu", "int8", max(1, s.whisper_batch // 2)))
        for small in ("medium", "small"):
            if small != s.whisper_model:
                tries.append((small, "cpu", "int8", 4))
        res = None
        for n, (model, device, compute, batch) in enumerate(tries):
            try:
                res = transcribe(self.work / "asr16k.wav", model_name=model, device=device, compute_type=compute,
                                 batch_size=batch, hint_terms=hints, duration=self.info.duration,
                                 log=self.log, progress=self._sp("asr"), cancel=self.cancel)
                break
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                self._log_file_only(traceback.format_exc())
                if n == len(tries) - 1:
                    raise
                nxt = tries[n + 1]
                self.log(f"⚠️ 음성 인식({model} · {device}) 실패 → {nxt[0]} · {nxt[1]} 로 다시: {e}")
                self.soft_failures.append({"stage": "asr", "label": "음성 인식", "error": f"{model}/{device}: {e}"[:300]})
        assert res is not None
        res["key"] = key
        write_json(self.work / "transcript.json", res)
        self.log(f"인식 완료: {len(res['words'])}단어")

    def _research_on(self) -> bool:
        return bool(self.spec.research)

    def stage_research(self) -> None:
        """🔎 주제 조사 — 대본·주제 설명만 보고 웹에서(소리·얼굴 작업과 동시에). 결과는 팀 전원의 공유 컨텍스트와
        조달 사다리(커먼즈 파일), 화자에게 주는 조사 노트(부가자료/조사노트.md)로 간다."""
        from .agents.research import clean_research, is_empty
        self.research = {}
        if not (self.spec.research and self.spec.studio_mode and self._use_api()):
            return
        topic, script = self.spec.topic_text, self.spec.script
        if not (topic.strip() or script.strip()):
            self.log("🔎 주제 설명·대본이 없어 조사를 건너뜁니다")
            return
        web = bool(getattr(self.settings, "research_web", True))
        key = text_hash(topic, script, self.title, self.settings.claude_model, self.spec.direction, web, "research-v1")
        path = self.work / "research.json"
        saved = read_json(path, {})
        if self.spec.reuse_plan and saved.get("key") == key and saved.get("research"):
            self.research = clean_research(saved["research"])
            self.log("🔎 저장된 조사 노트 사용")
            return
        studio = self._ensure_studio()
        if studio is None:
            return
        self._stage("research", 0.05)
        res = studio.research(title=self.title, topic=topic, script=script)
        self.research = res if not is_empty(res) else {}
        write_json(path, {"key": key, "research": self.research})
        self._stage("research", 1.0)

    def _soft_research(self) -> None:
        self.research = {}
        self.log("   → 조사 노트 없이(팀이 대본과 기억으로) 계속합니다")

    def stage_align(self) -> None:
        tr = read_json(self.work / "transcript.json", {})
        words = [Word.from_dict(w) for w in tr.get("words", [])]
        if not words:
            raise RuntimeError("인식된 음성이 없습니다(오디오를 확인하세요).")
        parsed = parse_script(self.spec.script)
        audio = load_audio_16k(self.work / "asr16k.wav")
        self.vad = speech_regions(audio)
        # 단어 단위 정리: 다시 말한 앞부분·추임새(쉼은 VAD 로 잰다 — Whisper 단어 시간이 쉼을 덮어도 잡힘)
        words, removed = clean_words(words, pause=vad_pause(self.vad))
        self.removed = [r.to_dict() for r in removed]
        n_re = sum(1 for r in removed if r.reason.startswith("되풀이"))
        self.log(f"✂️ 단어 정리: 다시 말한 앞부분 {n_re}곳 · 추임새 {len(removed) - n_re}곳 삭제")
        for r in removed:
            if r.reason.startswith("되풀이"):
                self.log(f"   - {fmt_ts(r.start)} 「{r.text[:40]}」")
        utts = build_utterances(words)
        groups = self.smap.groups
        source_of = (lambda u: groups.index(self.smap.group_at(u.start))) if len(groups) > 1 else None
        aligner = ScriptAligner(parsed, self.settings.glossary, audio=audio,
                                visual=visual_scorer(self.smap, self.quality), source_of=source_of)
        self.utts, self.tags, rep = aligner.run(utts)
        self.align_report = rep.to_dict()
        self._note_passes(rep)
        self._cut_review(parsed, [Word.from_dict(w) for w in tr.get("words", [])], audio, aligner)
        self.align_report["words_removed"] = self.removed
        write_json(self.work / "align.json", {"utterances": [u.to_dict() for u in self.utts],
                                              "tags": [t.to_dict() for t in self.tags],
                                              "report": self.align_report, "vad": self.vad})
        self.log(f"발화 {len(self.utts)}개 · 대본 일치 {rep.matched} · 반복 테이크 중 또렷한 것만 남김(제외 {rep.retakes})"
                 f" · NG {rep.meta}"
                 + (f" · 대본 커버리지 {rep.script_coverage * 100:.0f}%" if parsed.has_text else " (대본 없음)"))
        if rep.trimmed_takes:
            self.log(f"📜 대본 충실: 다시 말한 부분만 잘라 내고 고유한 앞부분을 살린 테이크 {rep.trimmed_takes}개")
        for t in rep.restored or []:
            self.log(f"📜 대본 충실: 되살린 문장 「{t[:40]}」")
        if parsed.has_text and rep.missing_sentences:
            self.log(f"📜 영상에서 찾지 못한 대본 문장 {len(rep.missing_sentences)}개(말하지 않았거나 인식 실패) — 편집리포트 참고")

    def _note_passes(self, rep) -> None:
        """대본 읽기 회차를 로그·리포트·원본 정보(sources.json role)에 남긴다 — 조용히 넘어가지 않는다."""
        passes = rep.passes or []
        if len(passes) < 2:
            return
        n = len(passes)
        if rep.pass_mode == "best_pass":
            self.log(f"📜 대본 전체를 {n}번 읽은 녹음입니다 — {rep.main_pass + 1}차를 주 테이크로 한 편으로 합칩니다"
                     f"(다른 회차는 빠진 문장 보강용). 회차별 대본 커버리지: "
                     + " · ".join(f"{p['idx'] + 1}차 {p['coverage'] * 100:.0f}%" for p in passes))
        else:
            self.log(f"📜 대본을 {n}번에 나눠 읽은 녹음입니다(어느 회차도 대본 전체가 아님) — 같은 문장은 가장 좋은 테이크 하나만")
        src = read_json(self.work / "sources.json", {})
        if src:
            roles = {}
            for p in passes:
                if p.get("source", -1) >= 0:
                    roles[str(p["source"])] = ("main" if p["idx"] == rep.main_pass else "alt_take") \
                        if rep.pass_mode == "best_pass" else "continue"
            src["roles"] = roles
            write_json(self.work / "sources.json", src)

    def _cut_review(self, parsed, raw: list[Word], audio=None, aligner=None) -> None:
        """✂️ 컷 편집 총괄(Opus) v2: 규칙이 만든 컷 초안(발화 남김/뺌 · 단어 정리)과 비언어 소리(기침·헛기침)를 대본과 함께
        보고 발화마다 최종 결정을 쓴다. AI 가 없거나 실패하면 규칙 초안 그대로 + 또렷이 떨어진 파열음만 자른다(대본 충실 보증은
        그대로 뒤에서 지킨다). 결과는 work/cut_review.json 캐시."""
        from .media.vocal_events import as_removals, default_cuts, vocal_events
        from .text import cut_review
        events = vocal_events(audio, self.vad, raw) if audio is not None else []
        self.align_report["vocal_events"] = len(events)
        studio = self._ensure_studio()
        if studio is None:
            ids = default_cuts(events)
            if ids:
                self.removed += as_removals(events, ids)
                self.log(f"✂️ 비언어 소리 {len(events)}곳 중 또렷이 떨어진 파열음 {len(ids)}곳 삭제(AI 없음 — 나머지는 둠)")
            return
        pass_of = getattr(aligner, "_pass_of", None) if aligner is not None else None
        draft = cut_review.draft_text(parsed.sentences, self.utts, self.removed, raw, events, pass_of)
        key = text_hash(draft, "cut-v2")
        cached = read_json(self.work / "cut_review.json", {})
        res = cached.get("result") if cached.get("key") == key else None
        if res is None:
            self.log("✂️ 컷 편집 총괄: 규칙 초안을 대본과 함께 검토")
            try:
                instr = load_prompt("agents/cut_editor.md")
                res = studio.call("cut_editor", draft, instr)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - 총괄 검토가 안 되면 규칙 초안 그대로
                self._log_file_only(traceback.format_exc())
                self.log(f"✂️ 컷 편집 총괄 실패 → 규칙 초안 그대로: {e}")
                return
            write_json(self.work / "cut_review.json", {"key": key, "result": res})
        rv, self.removed = cut_review.apply(res, self.utts, self.removed, raw)
        ids, reasons = cut_review.event_cuts(res, events)
        if ids:
            self.removed += as_removals(events, ids, reasons)
        issues = fidelity.apply_script_issues(self._script_sents(), rv.script_issues)
        if issues:
            self.log("📜 컷 총괄이 본 대본 자체의 문제(그 문장은 다시 넣지 않음): " + " · ".join(issues[:4]))
        self.align_report["cut_review"] = {"restored_utts": rv.restored_utts, "cut_utts": rv.cut_utts,
                                           "restored_removals": rv.restored_removals, "event_cuts": ids, "notes": rv.notes,
                                           "script_issues": rv.script_issues}
        self.log(f"✂️ 컷 편집 총괄: {rv.summary()}" + (f" · 비언어 소리 {len(ids)}/{len(events)}곳 삭제" if events else "")
                 + (f" — {rv.notes}" if rv.notes and rv.notes != rv.summary() else ""))

    def stage_face(self) -> None:
        """얼굴 추적 + 화면 품질 표본 — 카메라마다. 원본이 여러 개면 얼굴 트랙은 묶음 기준 카메라를 따라 잇는다
        (편집이 정해지면 앵글 조각을 따라 다시 잇는다)."""
        assert self.info
        cams = self.smap.cams
        key = text_hash([file_fingerprint(c.path) for c in cams], "face-v2")
        cached = read_json(self.work / "face.json", {})
        if cached.get("key") == key and "cams" in cached:
            self.log("얼굴 추적: 캐시 사용")
            res = cached
        else:
            res = {"key": key, "cams": {}}
            for n, cam in enumerate(cams):
                if len(cams) > 1:
                    self.log(f"얼굴 추적 {n + 1}/{len(cams)}: {Path(cam.path).name}")
                r = track_faces(self.ff, cam.path, self.infos[cam.idx], log=self.log, cancel=self.cancel,
                                progress=lambda f, n=n: self._stage("face", (n + f) / len(cams)))
                res["cams"][str(cam.idx)] = r
            write_json(self.work / "face.json", res)
        self._load_face(res)

    def _load_face(self, res: dict) -> None:
        cams = res.get("cams") or {"0": res}          # 예전 캐시(카메라 하나) 호환
        self.face_cams = {int(k): v.get("samples", []) for k, v in cams.items()}
        self.quality = {int(k): Quality(v["quality"]) for k, v in cams.items() if v.get("quality")}
        if self.smap.single:
            self.face = self.face_cams.get(0, [])
        else:
            base = [Piece(-1, g.start, g.end, g.cams[0].idx) for g in self.smap.groups]
            self.face = face_track(base, self.smap, self.face_cams)

    # ------------------------------------------------------------------
    def _cube(self, idx: int) -> Path:
        return self.media / ("grade.cube" if idx == 0 else f"grade_{idx + 1}.cube")

    def _grade_times(self, cam, vt: list[float]) -> list[float]:
        """남길 발화 시각(가상) → 이 카메라가 담은 순간의 카메라 시각(최대 16개)."""
        g = self.smap.group_of(cam.idx)
        times = [self.smap.to_cam(t, cam) for t in vt if g.start <= t <= g.end]
        times = [t for t in times if 0.2 <= t <= cam.duration - 0.2]
        if len(times) < 4:
            times = [cam.duration * (i + 0.5) / 8 for i in range(8)]
        if len(times) > 16:
            step = len(times) / 16
            times = [times[int(i * step)] for i in range(16)]
        return times

    def stage_grade(self) -> None:
        """🎨 자동 색보정(색보정 v3 — docs/upgrade/07_영상_룩_v2.md): 원본마다 분석·교정(벗어난 것만) → 🎨 컬러리스트가
        **모든 원본**의 비교 시트를 한 번에 보고 룩 하나(따뜻한 방 상한은 코드가) → 원본마다 레시피·검사(색 잡음 · 얼룩 F1 ·
        하이라이트 F4) → 원본 사이 얼굴 ΔE 가 3 을 넘으면 얼굴 기준 Lab 매칭(F3) → LUT."""
        assert self.info
        if self.spec.lut or not self.spec.auto_grade:
            self.grade_info = {}
            return
        # AI 기획과 동시에 돈다 — 편집 감독이 빼는 발화(director_drop)도 넣어 기획 결과와 상관없이 같은 표본·캐시 키
        kept = [u for u in self.utts if u.kept or u.status == "director_drop"] or self.utts
        vt = [((u.start + u.end) / 2) for u in kept]
        cams = self.smap.cams
        times = {c.idx: self._grade_times(c, vt) for c in cams}
        ref_lab = grade.reference_lab(USER_DIR / "reference_frames")
        key = text_hash([(file_fingerprint(c.path), [round(t, 1) for t in times[c.idx]]) for c in cams], self._use_api(),
                        [round(v, 1) for v in ref_lab], "grade-v5", grade.GRADE_VERSION)
        cached = read_json(self.work / "grade.json", {})
        luts = cached.get("luts") or {}
        if cached.get("key") == key and all(not luts.get(str(c.idx), True) or self._cube(c.idx).exists() for c in cams):
            self.grade_info = cached
            self.log("🎨 색보정: 캐시 사용(" + ("원본 그대로" if not any(luts.values()) else
                                             grade.LOOKS[cached['choice']['look']].label) + ")")
            return
        anas = [self._grade_analyze(cam, times[cam.idx]) for cam in cams]
        self._stage("grade", 0.3)
        base = self._grade_pick_look(anas, ref_lab)
        per_cam: dict[str, dict] = {}
        luts = {}
        done: list[tuple[Any, dict, Any, Any, dict]] = []
        for n, (cam, ana) in enumerate(zip(cams, anas)):
            plan, choice, corr = self._grade_finish(cam, ana, ref_lab, base, first=(n == 0))
            if n == 0:
                self.grade_info = {"key": key, **plan}
            done.append((cam, ana, corr, choice, plan))
            self._stage("grade", 0.3 + 0.6 * (n + 1) / len(cams))
        if len(cams) > 1:
            done = self._grade_match(done)
        for cam, ana, corr, choice, plan in done:
            luts[str(cam.idx)] = bool(plan.get("lut"))
            per_cam[str(cam.idx)] = {"filters": plan.get("filters", []), "lut": bool(plan.get("lut")),
                                     "notes": plan.get("correction", {}).get("notes", []),
                                     "match_lab": list(choice.match_lab or ())}
        self.grade_info["luts"] = luts
        self.grade_info["version"] = grade.GRADE_VERSION
        if len(cams) > 1:
            self.grade_info["cams"] = per_cam
        write_json(self.work / "grade.json", self.grade_info)

    def _grade_analyze(self, cam, times: list[float]) -> dict[str, Any]:
        """한 원본: 표본 프레임 · 얼굴 · 통계 · 스코프 판정 · 교정 · 비교용 프레임 · 장면 온기."""
        info = self.infos[cam.idx]
        frames = grade.sample_frames(self.ff, cam.path, times, info)
        track = self.face_cams.get(cam.idx) or []
        faces = [min(track, key=lambda s: abs(s["t"] - t)) if track else None for t, _ in frames]
        stats = grade.analyze(frames, faces)
        raw_frames = [f for _, f in frames]
        # 스코프(파형·벡터스코프 수치)로 먼저 판정 — 모든 항목이 정상 범위면 원본 그대로(LUT 도 걸지 않는다)
        checks = scopes.assess(scopes.metrics(raw_frames, faces))
        untouched = scopes.all_ok(checks)
        corr = grade.Correction(notes=["원본 정상 범위 — 보정 없음"]) if untouched else grade.correction_from_stats(stats)
        corrected = [grade.apply_correction(f, corr) for f in raw_frames]
        src_lab = grade.lab_stats(np.concatenate([f.reshape(-1, 3) for f in corrected]))
        # 비교용 3프레임: 얼굴이 크고 서로 떨어진 순간
        order = sorted(range(len(frames)), key=lambda i: -(faces[i] or {}).get("s", 0))
        picks: list[int] = []
        for i in order:
            if all(abs(i - j) >= max(1, len(frames) // 4) for j in picks):
                picks.append(i)
            if len(picks) == 3:
                break
        who = f"[{Path(cam.path).name}] " if not self.smap.single else ""
        self.log(f"🎨 {who}스코프: " + scopes.summary(checks))
        return {"frames": frames, "faces": faces, "stats": stats, "raw": raw_frames, "checks": checks,
                "untouched": untouched, "corr": corr, "src_lab": src_lab, "picks": sorted(picks or [0]),
                "skin": stats.get("face_rgb"), "scene": grade.scene_warmth(corrected, faces), "who": who}

    def _grade_pick_look(self, anas: list[dict[str, Any]], ref_lab) -> Optional["grade.GradeChoice"]:
        """🎨 컬러리스트 한 번 — 보정이 필요한 **모든 원본**을 행으로 한 비교 시트(07 문서 2-6). 룩·세기는 영상에 하나.
        반환: 기준 선택(룩·세기·미세 조정) 또는 None(AI 없음·전부 원본 그대로 → 규칙)."""
        need = [a for a in anas if not a["untouched"]]
        studio = self._ensure_studio() if need else None
        if studio is None:
            return None
        sheets = []
        for a in need:
            sheets.append(grade.comparison_sheet([a["frames"][i][1] for i in a["picks"]][: (3 if len(need) == 1 else 2)],
                                                 a["corr"], src_lab=a["src_lab"], ref_lab=ref_lab, skin_rgb=a["skin"],
                                                 row_label=Path(a["who"].strip("[] ")).stem if a["who"] else ""))
        sheet = grade.stack_sheets(sheets)
        (self.work / "grade_sheet.jpg").write_bytes(sheet)
        a0 = need[0]
        scope_sheet = scopes.draw([((a["who"] or "원본"), [a["raw"][i] for i in a["picks"]]) for a in need[:2]])
        faces = [grade.face_lab_after(a["skin"], a["corr"], grade.GradeChoice(), identity=True)
                 for a in need if a["skin"] is not None]
        de = max((grade.delta_e(p, q) for i, p in enumerate(faces) for q in faces[i + 1:]), default=0.0)
        notes = " / ".join(
            [f"{a['who'] or '원본'}스코프(범위 밖만): {scopes.summary(a['checks'])} · 교정: "
             f"{' · '.join(a['corr'].notes) or '적음'} · 장면: {grade.scene_note(a['scene'])}"
             + (" · 화면 속 전등 있음" if a["stats"].get("practical") else "") for a in need]
            + ([f"원본 사이 얼굴 ΔE {de:.1f}(3 을 넘으면 앱이 얼굴색을 맞춘다)"] if len(faces) > 1 else []))
        try:
            r = studio.grade(f"# 색보정\n주제: {self.title}", notes, ("grade_sheet", sheet, "image/jpeg"),
                             ("scopes", scope_sheet, "image/jpeg"))
            base = grade.plan_choice(a0["raw"], a0["corr"], str(r.get("look", "natural")), ref_lab,
                                     skin_rgb=a0["skin"], strength=float(r.get("strength", 0.6) or 0.0),
                                     exposure=float(r.get("exposure", 0) or 0), warmth=float(r.get("warmth", 0) or 0),
                                     saturation=float(r.get("saturation", 1) or 1), reason=str(r.get("reason", "")),
                                     by="ai").clamp()
            return base
        except (DirectorError, ValueError, TypeError) as e:
            self.log(f"🎨 컬러리스트 실패 → 규칙(내추럴 약하게): {e}")
            return None

    def _grade_finish(self, cam, ana: dict[str, Any], ref_lab, base: Optional["grade.GradeChoice"], *,
                      first: bool) -> tuple[dict, "grade.GradeChoice", "grade.Correction"]:
        """한 원본의 선택 → 따뜻한 방 상한 → 색 잡음 · 얼룩(F1) · 하이라이트(F4) 검사 → LUT · 전후 자료."""
        frames, faces, stats, raw_frames = ana["frames"], ana["faces"], ana["stats"], ana["raw"]
        corr, picks, skin_rgb, who, untouched = ana["corr"], ana["picks"], ana["skin"], ana["who"], ana["untouched"]
        checks = ana["checks"]
        if untouched:
            choice = grade.untouched_choice()
        elif base is not None:        # 같은 룩·세기·미세 조정, 레시피는 이 원본의 상태로
            choice = replace(grade.plan_choice(raw_frames, corr, base.look, ref_lab, skin_rgb=skin_rgb),
                             strength=base.strength, exposure=base.exposure, warmth=base.warmth,
                             saturation=base.saturation, reason=base.reason, by=base.by)
        else:
            # 규칙 기본: 벗어난 것만 고치는 레시피 + 내추럴 룩을 약하게(원본의 인상을 지킨다)
            choice = grade.plan_choice(raw_frames, corr, "natural", ref_lab, skin_rgb=skin_rgb, strength=0.5)
        if not untouched:
            before_scene = choice
            choice = grade.clamp_to_scene(choice, ana["scene"])
            if (choice.look, round(choice.strength, 2)) != (before_scene.look, round(before_scene.strength, 2)):
                self.log(f"🎨 {who}{grade.scene_note(ana['scene'])} → 룩 '{grade.LOOKS[choice.look].label}' "
                         f"세기 {choice.strength:.1f}")
        qc: dict[str, Any] = {"noise_gain": 1.0, "backoff": []}
        identity = untouched or grade.is_identity(corr, choice)
        cube = self._cube(cam.idx)
        gates: list[gate.GateResult] = []
        if identity:
            cube.unlink(missing_ok=True)      # 예전 실행의 LUT 이 남아 프록시에 걸리지 않게
        else:
            # 보정 뒤 검사: 압축 색 잡음을 1.5배 넘게 키우면(얼룩) 세기·채도를 줄인다
            choice, qc = grade.qc_backoff(raw_frames, corr, choice)
            for line in qc["backoff"]:
                self.log(f"🎨 {who}검사: {line}")
            corr, choice, gates = self._grade_gates(raw_frames, corr, choice, stats, who)
            identity = grade.is_identity(corr, choice)
            if identity:
                cube.unlink(missing_ok=True)
            else:
                grade.write_cube(cube, corr, choice)
        if gates:
            self._gate_record(gates, "색")
        graded = raw_frames if identity else [grade.grade(f, corr, choice) for f in raw_frames]
        after_checks = scopes.assess(scopes.metrics(graded, faces))
        filters = grade.cleanup_filters(stats)
        if first:
            # 전후 비교는 분석용 480px 프레임을 키우지 않고 1280px 로 다시 뽑아서(예전엔 흐릿해 보정이 화질을 낮춘 것처럼 보였다)
            try:
                big = grade.sample_frames(self.ff, cam.path, [frames[picks[0]][0]], self.infos[cam.idx], width=1280)[0][1]
            except Exception:  # noqa: BLE001 - 미리보기용 — 못 뽑으면 분석 프레임으로
                big = frames[picks[0]][1]
            grade.before_after(big, corr, choice, self.extras / "색보정_전후.jpg",
                               label="보정 없음 — 원본이 정상 범위" if identity else "")
            rows = [("원본 — " + scopes.summary(checks), [raw_frames[i] for i in picks])]
            if not identity:
                rows.append(("보정 — " + scopes.summary(after_checks), [graded[i] for i in picks]))
            (self.extras / "색보정_스코프.jpg").write_bytes(scopes.draw(rows))
        if identity:
            self.log(f"🎨 {who}색보정: 원본이 정상 범위 → 그대로 둠(LUT 없음"
                     + (", 디노이즈/샤픈만" if filters else "") + ")")
        else:
            after = grade.lab_stats(np.concatenate([g.reshape(-1, 3) for g in graded[:6]]))
            src_lab = ana["src_lab"]
            self.log(f"🎨 {who}색 변화: 따뜻함(b) {src_lab[2]:+.1f} → {after[2]:+.1f} · 진하기(C) {src_lab[3]:.1f} → "
                     f"{after[3]:.1f}")
            self.log(f"🎨 {who}색보정: {', '.join(corr.notes) or '교정 거의 없음'} → 룩 '{grade.LOOKS[choice.look].label}'"
                     f"(세기 {choice.strength:.1f}{', AI 선택' if choice.by == 'ai' else ''})"
                     + (f" — {choice.reason}" if choice.reason and first else ""))
            self.log(f"🎨 {who}이 영상에 맞춘 양: {grade.recipe_summary(choice.recipe)} · 보정 뒤 스코프: "
                     + scopes.summary(after_checks) + f" · 색 잡음 ×{qc['noise_gain']:.2f}")
        plan = grade.plan_to_dict(stats, corr, choice, filters)
        plan.update(lut=not identity, scene=ana["scene"], scopes={"before": [c.to_dict() for c in checks],
                                                                  "after": [c.to_dict() for c in after_checks], **qc})
        return plan, choice, corr

    def _grade_gates(self, raw: list, corr, choice, stats: dict, who: str):
        """색 게이트 F1(평평한 면의 얼룩) · F4(날아간 하이라이트) — 실패하면 고쳐서 다시 잰다.
        F1: 피부 보호를 끈 판(얼굴색 정보 없이) → 그래도 얼룩이면 룩·레시피를 반으로 → 그래도면 원본 그대로.
        F4: 화이트를 1.0 으로(늘리지 않는다)."""
        sample = raw[:4]
        graded = [grade.grade(f, corr, choice) for f in sample]
        bi = grade.blotch_index(sample, graded)
        r1 = gate.f1_blotch(bi)
        if not r1.ok:
            tries = [replace(choice, skin=()),
                     replace(choice, skin=(), strength=round(choice.strength * 0.5, 3),
                             recipe={k: (1.0 + (v - 1.0) * 0.5 if k in ("chroma_gain", "skin_gain") else
                                         v * 0.5 if k in ("contrast", "warmth", "black") else v)
                                     for k, v in (choice.recipe or {}).items()})]
            for ch in tries:
                bi2 = grade.blotch_index(sample, [grade.grade(f, corr, ch) for f in sample])
                r2 = gate.f1_blotch(bi2)
                if r2.ok:
                    self.log(f"🎨 {who}게이트 F1: 얼룩(색 잡음 ×{bi['ratio']:.2f}) → 줄여서 통과(×{bi2['ratio']:.2f})")
                    choice, r1 = ch, r2
                    r1.repaired = True
                    break
            else:
                self.log(f"🎨 {who}게이트 F1: 보정이 벽에 얼룩을 만든다 → 이 원본은 그대로 둔다")
                choice = grade.untouched_choice("색 게이트 F1 — 얼룩이 생겨 원본 그대로")
                corr = grade.Correction(notes=corr.notes + ["F1 얼룩 → 원본 그대로"])
                r1 = gate.f1_blotch(grade.blotch_index(sample, sample))
                r1.repaired = True
        clip0 = float(stats.get("clip") if stats.get("clip") is not None else grade.clip_frac(sample))
        clip1 = grade.clip_frac([grade.grade(f, corr, choice) for f in sample])
        r4 = gate.f4_clipping(clip0, clip1)
        if not r4.ok and corr.white < 1.0:
            corr = replace(corr, white=1.0, notes=corr.notes + ["F4 하이라이트 → 화이트 그대로"])
            clip2 = grade.clip_frac([grade.grade(f, corr, choice) for f in sample])
            r4b = gate.f4_clipping(clip0, clip2)
            self.log(f"🎨 {who}게이트 F4: 하이라이트 {clip1:.1%} → 화이트를 늘리지 않음({clip2:.1%})")
            r4 = r4b
            r4.repaired = r4.ok
        return corr, choice, [r1, r4]

    def _grade_match(self, done: list) -> list:
        """원본 사이 샷 매칭(07 문서 2-6 · 게이트 F3): 보정 뒤 얼굴 Lab 중앙값의 ΔE 가 3 을 넘으면 쓰인 길이로 가중한 평균
        얼굴로 원본마다 Lab 이동(중간톤 가중, 성분마다 ±6) → LUT 다시. 벽(배경) 차이는 고치지 않고 적는다."""
        faces = {}
        for cam, ana, corr, choice, plan in done:
            if ana["skin"] is not None:
                ident = not plan.get("lut")
                faces[cam.idx] = grade.face_lab_after(ana["skin"], corr, choice, identity=ident)
        if len(faces) < 2:
            return done
        keys = list(faces)
        before = max(grade.delta_e(faces[a], faces[b]) for i, a in enumerate(keys) for b in keys[i + 1:])
        if before <= grade.MATCH_DE:
            self._gate_record([gate.f3_sources(before, before)], "색")
            self.log(f"🎨 원본 사이 얼굴 ΔE {before:.1f} — 맞출 필요 없음")
            return done
        weight = {cam.idx: float(self.infos[cam.idx].duration or 1.0) for cam, *_ in done}
        shifts = grade.match_sources(faces, weight, k=1.0 / 0.8)
        out = []
        for cam, ana, corr, choice, plan in done:
            d = shifts.get(cam.idx)
            if d and any(abs(v) > 0.3 for v in d):
                choice = replace(choice, match_lab=tuple(round(v, 3) for v in d)).clamp()
                grade.write_cube(self._cube(cam.idx), corr, choice)
                plan = {**plan, "lut": True, "choice": {**plan.get("choice", {}), "match_lab": list(choice.match_lab)}}
            out.append((cam, ana, corr, choice, plan))
        after_faces = {cam.idx: grade.face_lab_after(ana["skin"], corr, choice, identity=not plan.get("lut"))
                       for cam, ana, corr, choice, plan in out if ana["skin"] is not None}
        ks = list(after_faces)
        after = max(grade.delta_e(after_faces[a], after_faces[b]) for i, a in enumerate(ks) for b in ks[i + 1:])
        self.log(f"🎨 원본 사이 얼굴 ΔE {before:.1f} → {after:.1f}(얼굴 기준 Lab 매칭)")
        self._gate_record([gate.f3_sources(before, after)], "색")
        return out

    # ------------------------------------------------------------------
    def _brief(self) -> JobBrief:
        local = [p.name for p in list_local_images(self.spec.images_dir)]
        return JobBrief(title=self.title, notes=self.spec.topic_text, episode=self.spec.episode,
                        subtitle=self.spec.subtitle, local_images=local, shorts_count=self.spec.shorts_count,
                        short_max_sec=self.spec.short_max_sec, presenter=self.settings.brand.presenter,
                        brand=self.settings.brand.name)

    def _pace(self):
        return PACES.get(self.spec.pace, PACES["calm"])

    def _initial_timemap(self) -> TimeMap:
        assert self.info
        keeps = build_keeps(self.utts, pace=self._pace(), vad=self.vad, media_duration=self.info.duration, fps=self.fps)
        return TimeMap(keeps)

    def _use_api(self) -> bool:
        """Claude 를 쓸 수 있는가(Claude Code 구독 또는 API 키)."""
        return self.spec.use_claude and resolve_backend(self.settings)[0] != "none"

    def _client(self):
        with self._ai_lock:
            return self._client_locked()

    def _client_locked(self):
        if self.claude is None:
            backend, why = resolve_backend(self.settings)
            if backend == "claude_code":
                exe = find_claude(self.settings.claude_code_path) or "claude"
                from .director.claude_code import scratch_dir
                self.claude = ClaudeCodeClient(exe, self.settings.claude_model, self.settings.claude_effort,
                                               log=self.log, workdir=scratch_dir(self.work.parent.name, log=self.log))
                self.log(f"AI 연결: Claude Code(Pro/Max 구독 사용량) · {exe}")
            else:
                self.claude = ClaudeClient(self.settings.anthropic_api_key, self.settings.claude_model,
                                           self.settings.claude_effort, log=self.log)
                self.log(f"AI 연결: {why}")
        return self.claude

    def _ai_label(self) -> str:
        backend = getattr(self.claude, "backend", "api")
        return "Claude Code · 구독" if backend == "claude_code" else "Claude API"

    def _ensure_studio(self) -> Optional[Studio]:
        """🎬 멀티 에이전트 스튜디오(Claude Code 구독 또는 API 키가 있을 때)."""
        with self._ai_lock:
            return self._ensure_studio_locked()

    def _ensure_studio_locked(self) -> Optional[Studio]:
        if self.studio is not None:
            return self.studio
        if not (self._use_api() and self.spec.studio_mode):
            return None
        self.studio = Studio(self._client(), log=self.log, cancel=self.cancel, workers=self.settings.studio_workers,
                             effort=self.settings.agent_effort, models=self.settings.agent_models,
                             user_direction=self.spec.direction, use_stock=self._stock_enabled(),
                             use_motion=self.spec.motion_scenes)
        self.studio.web = bool(getattr(self.settings, "research_web", True))
        return self.studio

    def _stock_enabled(self) -> bool:
        s = self.settings
        return self.spec.fetch_stock and (bool(getattr(s, "keyless_stock", True)) or any(
            [s.pixabay_api_key, s.unsplash_access_key, s.coverr_api_key, s.pexels_api_key]))

    def stage_director(self) -> None:
        assert self.info
        brief = self._brief()
        tm0 = self._initial_timemap()
        from .agents.research import research_block
        rblock = research_block(self.research)
        # 🔎 조사 노트는 공유 컨텍스트 끝에 — 모든 에이전트가 같은 사실·같은 커먼즈 파일 목록에서 출발한다(캐시도 함께)
        ctx = shared_context(brief, self.utts, self.tags, tm0, tm0.duration) + (f"\n\n{rblock}" if rblock else "")
        self.ctx = ctx
        mode = "studio" if (self.spec.studio_mode and self._use_api()) else "single"
        key = text_hash(shared_context(brief, self.utts, self.tags, None, 0.0), self.spec.shorts_count,
                        self.spec.short_max_sec, self.settings.claude_model, mode, self.spec.direction,
                        self._stock_enabled(), self.spec.motion_scenes, text_hash(rblock), "plan-v5")
        saved = read_json(self.work / "plan.json", {})
        use_api = self._use_api()
        studio = self._ensure_studio()
        raw_long = raw_shorts = None
        reused = False
        if self.spec.reuse_plan and saved.get("key") == key and saved.get("long"):
            self.log("기획: 저장된 계획 사용")
            reused = True
            raw_long, raw_shorts = saved["long"], {"shorts": saved.get("shorts", [])}
            self.director_name = saved.get("director", "saved")
        elif studio is not None:
            self.director_name = f"AI 스튜디오 · {self._ai_label()} ({self.settings.claude_model})"
            self.log("🎬 AI 스튜디오 가동: 총괄 감독 → 전문 에이전트 병렬 작업")
            try:
                from .assets import local as local_assets
                mats = local_assets.index(self.spec.images_dir)
                self._materials = mats
                raw_long, raw_shorts = studio.plan(brief, ctx, shorts_count=self.spec.shorts_count,
                                                   progress=lambda f: self._stage("director", 0.95 * f),
                                                   procure=self._procure_evidence
                                                   if (self.spec.fetch_broll or self._stock_enabled()) else None,
                                                   materials=(local_assets.listing(mats), local_assets.sheet(mats)),
                                                   refs=self._motion_refs if self.spec.motion_scenes else None)
                # 숏폼 PD 가 한 편도 못 냈을 때만 규칙으로 채운다 — 둘째 편을 억지로 채우지 않는다(제대로 된 한 편이 우선)
                if self.spec.shorts_count > 0 and not ((raw_shorts or {}).get("shorts") or []):
                    raw_shorts = fallback.shorts_plan(brief, self.utts, self.tags, count=1,
                                                      max_sec=self.spec.short_max_sec)
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 - AI 응답이 이상해도(형식 오류 등) 단일 디렉터 → 규칙으로
                self._log_file_only(traceback.format_exc())
                self.log(f"🎬 총괄 감독 실패 → 단일 디렉터로 진행: {e}")
                raw_long = raw_shorts = None
        if raw_long is not None:
            pass
        elif use_api:
            self._client()
            self.director_name = f"{self._ai_label()} ({self.settings.claude_model})"
            sys_prompt = system_prompt()
            try:
                self.log("Claude: 롱폼 편집 계획 요청")
                raw_long = self.claude.structured(system=sys_prompt, shared_context=ctx,
                                                  instruction=long_instruction(brief), schema=LONG_PLAN,
                                                  cancel=self.cancel, label="롱폼 계획")
                self._stage("director", 0.55)
                raw_shorts = {"shorts": []}
                if self.spec.shorts_count > 0:
                    self.log("Claude: 숏폼 기획 요청(후킹 구조 적용)")
                    raw_shorts = self.claude.structured(system=sys_prompt, shared_context=ctx,
                                                        instruction=shorts_instruction(brief), schema=SHORTS_PLAN,
                                                        cancel=self.cancel, label="숏폼 기획")
            except Cancelled:
                raise
            except Exception as e:  # noqa: BLE001
                self._log_file_only(traceback.format_exc())
                self.log(f"Claude 실패 → 규칙 기반 편집으로 진행: {e}")
                self.director_name = "규칙 기반(Claude 실패)"
                raw_long = fallback.long_plan(brief, self.utts, self.tags)
                raw_shorts = fallback.shorts_plan(brief, self.utts, self.tags, count=self.spec.shorts_count,
                                                  max_sec=self.spec.short_max_sec)
        else:
            if self.spec.use_claude:
                self.log("Claude Code(구독)도 API 키도 없어 규칙 기반 편집으로 진행합니다 — "
                         "setup_windows.bat 으로 Claude Code 를 설치하고 로그인하세요.")
            self.director_name = "규칙 기반"
            raw_long = fallback.long_plan(brief, self.utts, self.tags)
            raw_shorts = fallback.shorts_plan(brief, self.utts, self.tags, count=self.spec.shorts_count,
                                              max_sec=self.spec.short_max_sec)
        self.plan_long = normalize_long(raw_long, self.utts, self.tags)
        # 저장된 계획은 검사 → 수정 → 검수(아트 디렉터)를 이미 거쳤다 — 다시 고치면 검수가 고친 장면을 되돌리고
        # 검수 캐시까지 깨진다(재실행마다 모션 디자이너·아트 디렉터를 다시 부르던 것). 검사만 다시 하고 기록한다.
        self._check_cards(tm0, revise=not reused)
        self._lint_motion(tm0, revise=not reused)
        self._auto_photos()
        if saved.get("key") == key and saved.get("long", {}).get("qa"):
            self.plan_long["qa"] = saved["long"]["qa"]
        self.plan_shorts = normalize_shorts(raw_shorts, self.utts, count=self.spec.shorts_count,
                                            max_sec=self.spec.short_max_sec, log=self.log)
        for i, sh in enumerate(self.plan_shorts, 1):
            self.log(f"📱 숏폼 {i} 「{sh.get('title', '')}」: 발화 {len(sh['segments'])}개 · 점수 {sh.get('score')} · "
                     f"이해 가능성 {sh.get('coherence', 1):.1f}"
                     + (f" · 시청자가 얻는 것: {sh['viewer_takeaway']}" if sh.get("viewer_takeaway") else ""))
        if not self.spec.title.strip() and self.plan_long.get("title"):
            self.title = self.plan_long["title"]
            self.slug = slugify(self.title, 30)
        self._plan_key = key
        self._save_plan()
        write_json(self.work / "plan_raw.json", {"long": raw_long, "shorts": raw_shorts})
        # ✂️ 편집 감독의 drop — 대본에 있는 문장은 절대 빼지 않는다(대본 충실). 대본 밖 애드리브·혼잣말만 뺀다.
        # 예전엔 대본 일치 점수 80 이상만 지켜서, 인식이 틀려 점수가 낮은 대본 문장이 '애드리브'로 빠졌다
        drop_ids = {d["seg"] for d in self.plan_long.get("drop", [])}
        # 🎬 총괄 감독의 integrity.drop_ranges(대본을 두 번 읽은 녹음의 한 회차 등) — 범위 삭제
        integ = (self.plan_long.get("studio") or {}).get("integrity") or self.plan_long.get("integrity") or {}
        for r in integ.get("drop_ranges", []) or []:
            a, b = int(r.get("start_seg", -1)), int(r.get("end_seg", -1))
            drop_ids |= {u.id for u in self.utts if a <= u.id <= b}
        refused: list[str] = []
        script_n = norm(parse_script(self.spec.script).clean)
        for u in self.utts:
            if u.id in drop_ids and u.kept:
                un = norm(u.text)
                in_script = bool(script_n) and (u.script_span is not None or (
                    len(un) >= 6 and len(un) <= len(script_n) and fuzz.partial_ratio(un, script_n) >= 70))
                # 대본 문장이라도 그 대본 구간을 남는 다른 발화가 덮으면(같은 대본을 다시 읽은 회차) 받아들인다 —
                # 대본 충실은 '정확히 한 번'이지 '맞는 발화를 전부'가 아니다(10/1 테스트: 1차 테이크 삭제 28건 거절 → 두 배 길이)
                if in_script and not covered_elsewhere(u, self.utts, drop_ids):
                    refused.append(f"S{u.id} 「{u.text[:30]}」")
                    continue
                u.status = "director_drop"
                u.note = next((d["reason"] for d in self.plan_long["drop"] if d["seg"] == u.id), "")
        # 게이트 A0: 감독이 본 녹음 구조(integrity.passes)와 코드의 회차 감지가 다르면 둘 다 적고 코드 쪽을 따른다
        code_n = len(self.align_report.get("passes") or []) or 1
        if integ.get("passes") and int(integ["passes"]) != code_n:
            self.log(f"📜 녹음 구조 판단이 다릅니다 — 총괄 감독: 대본을 {integ['passes']}번 읽음 · 코드: {code_n}번 → 코드 쪽을 따릅니다"
                     + (f" · 감독 메모: {'; '.join(integ.get('issues') or [])[:120]}" if integ.get("issues") else ""))
            self.align_report["integrity_mismatch"] = {"director": int(integ["passes"]), "code": code_n}
        if refused:
            self.align_report["director_drop_refused"] = refused
            self.log(f"✂️ 편집 감독이 빼자고 한 발화 중 대본 문장 {len(refused)}개는 남깁니다(대본 충실): "
                     + " · ".join(refused[:4]))
        drop_ids = {u.id for u in self.utts if u.status == "director_drop"}
        n_motion = sum(1 for g in self.plan_long["graphics"] if g["template"] == "motion")
        n_broll = sum(1 for g in self.plan_long["graphics"] if g["template"] == "broll")
        self.log(f"🎬 제목 「{self.title}」 · 챕터 {len(self.plan_long['chapters'])} · 그래픽 {len(self.plan_long['graphics'])}"
                 f"(모션 장면 {n_motion} · 스톡 {n_broll}) · 강조 순간 {len(self.plan_long.get('moments', []))}"
                 f" · 숏폼 {len(self.plan_shorts)} · 추가 컷 {len(drop_ids)}")

    def _motion_refs(self, slugs: list[str]) -> dict[str, bytes]:
        """🎞 총괄 감독이 고른 모션 레퍼런스(Jitter 템플릿 slug) → 미리보기 프레임 시트(렌더와 같은 Chrome, 캐시)."""
        from .assets.motion_ref import capture_refs, known
        slugs = [s for s in slugs if known(s)]
        if not slugs:
            return {}
        rs = self.settings.render
        return capture_refs(slugs, node=find_node(self.settings.node_path), browser_executable=rs.browser_executable,
                            gl=rs.gl, work=self.work, log=self.log, cancel=self.cancel,
                            ignore_cert_errors=os.environ.get("CHOI_IGNORE_CERT") == "1")   # 프록시 인증서 시험 환경용

    def _auto_photos(self) -> None:
        """대본·전사의 고유명사(라틴 문자 이름 · 『』《》 제목 · 종교)를 규칙으로 찾아 photo 그래픽(wiki=True)으로 더한다 —
        AI 가 놓친 것의 안전망. 그 문장에 이미 그래픽이 있으면 건너뛰고, 위키백과에 이미지가 없으면 자료 사진 단계에서 빠진다."""
        if not self.spec.fetch_broll:
            return
        kept = [u for u in self.utts if u.kept]
        text = "\n".join(u.text for u in kept)
        ents = find_entities(text)
        if not ents:
            return
        used = {g.get("start_seg") for g in self.plan_long.get("graphics", [])}
        have = {norm(g.get("image") or g.get("title") or "") for g in self.plan_long.get("graphics", [])
                if g.get("template") in ("photo", "broll")}
        added = []
        for e in ents:
            key = norm(e.term)
            if not key or key in have:
                continue
            seg = next((u.id for u in kept if key in norm(u.text)), None)
            if seg is None or seg in used:
                continue
            g = blank_graphic("photo", seg)
            g.update({"layout": "pip", "start_word": e.term.split()[0], "title": e.term, "image": e.term,
                      "body": {"name": "인물·고유명사", "work": "작품", "religion": "종교"}.get(e.kind, ""),
                      "reason": f"고유명사 자동({e.kind}) — 위키백과", "wiki": True})
            self.plan_long["graphics"].append(g)
            used.add(seg)
            have.add(key)
            added.append(e.term)
        if added:
            self.log("📷 고유명사 자료 사진(위키백과) 후보: " + " · ".join(added[:8]))

    def _check_cards(self, tm: TimeMap, revise: bool = True) -> None:
        """🃏 자유 HTML 카드의 렌더 전 검사(renderer/scripts/check.mjs — 글꼴·넘침·크기·대비·런타임 오류).
        실패하면 카드 디자이너가 한 번 고치고(검사 결과를 그대로 줌), 그래도 실패하면 키워드 카드로 대체한다.
        결과는 plan.long.card_checks 에 남는다."""
        cards = [g for g in self.plan_long.get("graphics", []) if g.get("template") == "card" and isinstance(g.get("card"), dict)]
        if not cards:
            self.plan_long.pop("card_checks", None)
            return
        seg_t = seg_edit_times(self.utts, tm)
        t_card = TEMPLATES["card"]

        def dur_of(g: dict) -> float:
            # time_graphics 와 같은 셈: 발화 구간 + 0.45초, 적어도 정착 시각 + 1.2초(읽기), 최대 max_dur
            a = seg_t.get(g["start_seg"])
            b = seg_t.get(g.get("end_seg", g["start_seg"]), a)
            d = (b[1] - a[0]) if a and b else 6.0
            want = max(t_card.min_dur, d + 0.45, card_settle_time(g["card"]) + 1.2)
            return min(t_card.max_dur, want)

        rs = self.settings.render
        node = find_node(self.settings.node_path)
        out_dir = self.work / "cards"
        self.log(f"🃏 카드 {len(cards)}개 렌더 전 검사(글꼴·넘침·크기·대비)")
        results: dict[str, dict] = {}
        studio = self._ensure_studio() if revise else None
        for rnd in range(2):
            todo = [g for g in cards if not results.get(g["card"]["id"], {}).get("ok")]
            if not todo:
                break
            try:
                res = check_cards([dict(g["card"], layout=g["layout"]) for g in todo], node=node, out_dir=out_dir, fps=self.fps,
                                  durations={g["card"]["id"]: dur_of(g) for g in todo},
                                  browser_executable=rs.browser_executable, gl=rs.gl, log=self.log, cancel=self.cancel)
            except CheckError as e:
                self.log(f"🃏 카드 검사를 못 했습니다({str(e)[:200]}) — 검사 없이 진행")
                return
            results.update(res)
            for g in todo:
                tl_s = (res.get(g["card"]["id"], {}).get("metrics") or {}).get("timeline")
                if g["card"].get("timeline") and isinstance(tl_s, (int, float)) and tl_s > 0:
                    g["card"]["settle_s"] = round(float(tl_s), 2)      # 직접 쓴 타임라인의 정착 시각(검수 스틸·읽기 시간)
            failed = [g for g in todo if not res.get(g["card"]["id"], {}).get("ok")]
            # 글꼴 파일을 못 읽은 것(font load NetworkError · font_not_loaded 만)은 카드가 아니라 설치·환경 문제 — 디자이너에게
            # 고치라고 보내지도, 키워드 카드로 바꾸지도 않는다(2026-10-02 실제 실행: 5개 카드가 전부 이 이유로 두 번 실패할 뻔)
            env_only = failed and all(
                all(str(p.get("code", "")) in ("font_not_loaded", "font_family_not_bundled") or "font load" in str(p.get("detail", ""))
                    for p in res.get(g["card"]["id"], {}).get("problems", [])) for g in failed)
            if env_only:
                self.log("🃏 카드 검사: 글꼴 파일을 읽지 못했습니다(설치 문제 — renderer/assets/fonts 확인). 카드는 그대로 두고 진행")
                for g in failed:
                    results[g["card"]["id"]] = dict(res[g["card"]["id"]], ok=True, problems=[])
                break
            if not failed or rnd == 1 or studio is None:
                break
            for g in failed:
                lines = problem_lines(res[g["card"]["id"]])
                try:
                    new = studio.revise_card(self.ctx, g["card"], dur_of(g), "렌더 전 검사(check) 실패", "", None,
                                             layout=g["layout"], checks=tuple(lines))
                except DirectorError as e:
                    self.log(f"🃏 카드 수정 실패: {e}")
                    new = None
                if new:
                    g["card"] = new
        for g in cards:
            r = results.get(g["card"]["id"])
            if r and r.get("ok"):
                continue
            title = (g.get("title") or card_text(g["card"])[:12]).strip()
            self.log(f"🃏 카드 '{title}' 는 검사에 두 번 실패해 키워드 카드로 대체")
            g["template"], g["layout"] = "keyword", "split"
            g["title"] = title[:12] or "핵심"
            g["subtitle"] = card_text(g["card"])[:40]
            g.pop("card", None)
        self.plan_long["card_checks"] = {cid: {"ok": r["ok"], "problems": r["problems"][:6]} for cid, r in results.items()}

    def _lint_motion(self, tm: TimeMap, revise: bool = True) -> None:
        """🎨 모션 장면 타이밍·구도 린트(studio/motion/lint.py, docs/upgrade/06c 4장) — 렌더 전, 스펙과 실제 단어 시각만으로.
        error(0.5초 빈 무대 · 채움 · 작은 글자 · 정지 시간 · 동시 등장 · pop · 말보다 늦음)가 있으면 모션 디자이너가 위반 목록을 받아
        한 번 고치고(Studio.revise_scene), 그래도 남으면 규칙 보정(작은 글자 키우기)만 하고 그대로 둔다 — 결과는
        plan.long.motion_checks(카드의 card_checks 와 같은 모양)."""
        from .motion import lint as mlint
        gl = self.plan_long.get("graphics", [])
        scenes = [(i, g) for i, g in enumerate(gl) if g.get("template") == "motion" and isinstance(g.get("spec"), dict)]
        if not scenes:
            self.plan_long.pop("motion_checks", None)
            return
        kept = [u for u in self.utts if u.kept]
        words = [(tm.src_to_edit(w.start, snap=True), tm.src_to_edit(w.end, snap=True), w.text) for u in kept for w in u.words]
        words = [(a, b, t) for a, b, t in words if a is not None and b is not None]

        def window(g: dict) -> Optional[tuple[float, float]]:
            tg = time_graphics([g], self.utts, tm, total=tm.duration)
            return (tg[0].start, tg[0].end) if tg else None

        def check(g: dict) -> tuple[list, float, list]:
            w = window(g)
            if w is None:
                return [], 0.0, []
            dur = w[1] - w[0]
            ws = [(a - w[0], b - w[0], t) for a, b, t in words if w[0] - 0.5 <= a <= w[1]]
            # 계획의 spec 은 원본(기본값 없음) — 렌더러가 받을 모양으로 정리한 뒤 린트(lint_scene)
            return mlint.lint_scene(g["spec"], dur, ws, box=mlint.box_for(g.get("layout", "fullscreen"))), dur, ws

        studio = self._ensure_studio() if self.spec.studio_mode else None
        results: dict[str, dict] = {}
        todo = []
        for i, g in scenes:
            issues, dur, _ = check(g)
            if dur and mlint.errors(issues) and revise:
                todo.append((i, g, issues, dur))
            else:
                errs = mlint.errors(issues) if dur else []
                results[f"g{i}"] = {"ok": not errs, "errors": [x.rule for x in errs],
                                    "warns": sorted({x.rule for x in issues if x.level == "warn"})}
        if todo:
            self.log(f"🎨 모션 장면 {len(scenes)}개 타이밍 린트: 고칠 것 {len(todo)}개"
                     + (" → 모션 디자이너 수정" if studio else " → 규칙 보정"))

        def fix(item):
            i, g, issues, dur = item
            new = None
            if studio is not None:
                problem = "타이밍·구도 린트 위반(렌더 전 검사):\n" + "\n".join(f"- {x}" for x in mlint.describe(mlint.errors(issues)))
                try:
                    new = studio.revise_scene(self.ctx, g["spec"], dur, problem,
                                              "위반 규칙을 고친다: 0.5초 안에 제목·주 요소(또는 ghost 자리 표시), 상자 45% 채움, "
                                              "글자 28px 이상, 마지막 도착 뒤 정지 시간, 같은 0.1초 시작 둘까지, pop·back 금지.", None)
                except DirectorError as e:
                    self._log_file_only(f"   (모션 수정 실패 g{i}: {e})")
            return i, g, issues, dur, new

        if todo:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=4) as ex:
                done = list(ex.map(fix, todo))
            for i, g, issues, dur, new in done:
                if new:
                    old_spec = g["spec"]
                    g["spec"] = new
                    issues2, _, _ = check(g)
                    if len(mlint.errors(issues2)) > len(mlint.errors(issues)):
                        g["spec"] = old_spec          # 고친 것이 더 나쁘면 되돌린다
                    else:
                        issues = issues2
                if mlint.errors(issues):
                    bumped = mlint.bump_small_text(g["spec"], mlint.box_for(g.get("layout", "fullscreen"))[1])
                    if bumped:
                        issues, _, _ = check(g)
                errs = mlint.errors(issues)
                results[f"g{i}"] = {"ok": not errs, "errors": [x.rule for x in errs],
                                    "warns": sorted({x.rule for x in issues if x.level == "warn"}), "revised": True}
                if errs:
                    self._log_file_only(f"   (모션 g{i} 남은 위반: {', '.join(mlint.describe(errs))[:300]})")
        bad = sum(1 for r in results.values() if not r["ok"])
        self.plan_long["motion_checks"] = results
        if todo:
            self.log(f"🎨 모션 린트: 통과 {len(results) - bad}/{len(results)}" + (f" · 남은 위반 {bad}개(리포트)" if bad else ""))

    def _save_plan(self) -> None:
        prev = read_json(self.work / "plan.json", {})
        usage = (prev.get("usage", []) if prev.get("key") == getattr(self, "_plan_key", None) else []) \
            + (self.claude.usage if self.claude else [])
        seen, uniq = set(), []
        for u in usage:
            k = json.dumps(u, sort_keys=True)
            if k not in seen:
                seen.add(k)
                uniq.append(u)
        write_json(self.work / "plan.json", {"key": getattr(self, "_plan_key", ""), "director": self.director_name,
                                             "title": self.title, "long": self.plan_long, "shorts": self.plan_shorts,
                                             "usage": uniq})

    # ------------------------------------------------------------------
    def stage_proxy(self) -> None:
        """편집본: 카메라마다 프록시 인코딩 + 컷(기획이 끝난 뒤). run() 은 둘을 나눠, 인코딩은 AI 기획과 동시에 돌린다."""
        self._encode_proxies()
        self._make_edit()

    def _encode_proxies(self) -> None:
        """카메라마다 편집용 프록시(CFR · 색보정 LUT · 디노이즈/샤픈). 0초 = 그 카메라의 첫 영상 프레임."""
        assert self.info
        height = proxy_height_for(self.info, self.spec.out_height)
        cams = self.smap.cams
        meta = read_json(self.media / "proxy.json", {})
        keys = meta.get("keys") or ({"0": meta["key"]} if meta.get("key") else {})
        for n, cam in enumerate(cams):
            proxy = self.media / Path(cam.proxy).name
            cube = self._cube(cam.idx)
            lut = self.spec.lut or (str(cube) if cube.exists() and self.spec.auto_grade else "")
            gi = self.grade_info or {}
            filters = (gi.get("cams", {}).get(str(cam.idx), {}).get("filters") if gi.get("cams") else gi.get("filters")) or []
            pre = [f for f in filters if f.startswith("hqdn3d")]
            post = [f for f in filters if not f.startswith("hqdn3d")]
            key = text_hash(file_fingerprint(cam.path), self.fps, height, file_fingerprint(lut) if lut else "",
                            filters, "proxy-v3")
            who = f" {n + 1}/{len(cams)}({Path(cam.path).name})" if len(cams) > 1 else ""
            if keys.get(str(cam.idx)) == key and proxy.exists():
                self.log(f"편집본{who}: 캐시 사용")
                continue
            self.log(f"편집본{who}: {height}p · {self.fps}fps · {'NVENC' if self.ff.nvenc_ok else 'x264'}"
                     + (" · 색보정 LUT" if lut else "") + (" · 디노이즈/샤픈" if filters else ""))
            if not self.ff.nvenc_ok and getattr(self.ff, "nvenc_error", "") and n == 0:
                # 조용히 x264 로 떨어지지 않게 — 드라이버가 낮으면 업데이트만으로 편집본 인코딩이 빨라진다(07 문서 1-4)
                self.log(f"   (NVENC 를 못 씀: {self.ff.nvenc_error})")
            build_proxy(self.ff, cam.path, self.infos[cam.idx], proxy, fps=self.fps, height=height,
                        lut=lut or None, pre_filters=pre, post_filters=post, log=self.log,
                        progress=lambda f, n=n: self._stage("proxy", 0.8 * (n + f) / len(cams)), cancel=self.cancel)
            keys[str(cam.idx)] = key
            write_json(self.media / "proxy.json", {"keys": keys, "height": height})

    def _make_edit(self) -> None:
        """기획(편집 감독의 drop · 숏폼 · 하이라이트)으로 keep 구간과 컷 목소리를 만든다."""
        assert self.info
        self._ensure_script_utts()
        self.base_keeps = self.smap.clamp_keeps(
            build_keeps(self.utts, pace=self._pace(), vad=self.vad, media_duration=self.info.duration, fps=self.fps,
                        exclude=self._removed_spans()), self.fps)
        ver = read_json(self.work / "verify.json", {})
        self.edit_drops = [Span(a, b) for a, b in ver.get("drops", [])] \
            if ver.get("base") == self._keeps_key(self.base_keeps) else []
        self._make_cuts()
        if self.smap.multicam:
            self.log("🎥 앵글(롱폼): " + angle_summary(self.long_pieces, self.smap))

    # ------------------------------------------------------------------
    # 🚦 품질 게이트 — 이상하면 렌더하지 않는다(studio/gate.py, docs/upgrade/08_품질_게이트.md)
    def _gate_record(self, res: list[gate.GateResult], where: str) -> None:
        gate.demote(res)
        self.gate_results = gate.merge(self.gate_results, res)
        gate.write(self.work / "gate.json", self.gate_results, forced=self.force_render)
        self.log(gate.summary(res))
        bad = gate.blocking(res)
        if not bad:
            return
        if self.force_render:
            self.log("⚠️ 품질 게이트가 멈추라고 했지만 --force-render 로 계속합니다: " + " · ".join(r.id for r in bad))
            return
        err = gate.GateBlocked(bad, where)
        write_text(self.out / "품질게이트_중단.md",
                   f"# 렌더하지 않았습니다 — 품질 게이트({where})\n\n" + gate.report_section(self.gate_results)
                   + "같은 입력으로 다시 만들면 끝난 단계는 건너뜁니다. 원본·대본을 확인한 뒤에도 이대로 만들려면:\n\n"
                   + f"    python -m studio rerender \"{self.dir}\" --force-render\n")
        self.log(str(err))
        raise err

    def _cut_checks(self) -> list[gate.GateResult]:
        """게이트 A(컷): A1 길이 · A2 감독 예상 길이 · A3 대본 중복 · A5 인사 위치."""
        tm = getattr(self, "timemap", None)
        if tm is None:
            return []
        clean = parse_script(self.spec.script).clean if self.spec.script else ""
        edit_sec = tm.duration
        integ = (self.plan_long.get("studio") or {}).get("integrity") or self.plan_long.get("integrity") or {}
        starts = {i: a for i, (a, _) in seg_edit_times([u for u in self.utts if u.kept], tm).items()}
        return [gate.a1_length(self.utts, clean, edit_sec, coverage=float(self.align_report.get("script_coverage", 1.0))),
                gate.a2_planned(edit_sec, float(integ.get("expected_sec") or 0.0)),
                gate.a3_duplicates(self.utts, clean),
                gate.a5_greetings(self.utts, starts, edit_sec, len(clean))]

    def _gate_cut(self) -> None:
        """컷 확정 직후: 실패하면 수리(같은 대본 문장의 낮은 테이크 빼기 · 느슨한 회차 감지) 한 번 → 다시 컷 → 재검."""
        res = self._cut_checks()
        if not res:
            return
        if any(not r.ok and r.repair in ("passes", "drop_duplicates") for r in res):
            n = self._repair_duplicates(any(r.id == "A1_length" and not r.ok for r in res))
            if n:
                self.log(f"🚦 게이트 A 수리: 같은 대본을 한 번 더 말한 발화 {n}개를 다른 테이크로 → 컷을 다시 만듭니다")
                self._make_edit()
                res = gate.merge(res, self._cut_checks())
        self._gate_record(res, "컷")

    def _repair_duplicates(self, by_pass: bool) -> int:
        """A3: 같은 대본 구간을 덮는 남긴 발화 쌍에서 테이크 점수(같으면 대본 일치·더 앞의 것)가 낮은 쪽을 뺀다.
        A1(by_pass): 느슨한 기준(뒤로 25% · 회차 15%)으로 회차를 다시 찾아, 주 회차 밖에서 주 회차가 이미 덮는 발화를 뺀다."""
        from .text.passes import choose_main_pass, detect_passes
        drop: set[int] = set()
        for a, b in gate.duplicate_pairs(self.utts):
            if a.id in drop or b.id in drop:
                continue
            drop.add(min((a, b), key=lambda u: (u.take_score, u.score, u.start)).id)
        clean = parse_script(self.spec.script).clean if self.spec.script else ""
        if by_pass and clean:
            groups = self.smap.groups
            source_of = (lambda u: groups.index(self.smap.group_at(u.start))) if len(groups) > 1 else None
            passes = detect_passes(self.utts, len(clean), back_jump=0.25, min_cov=0.15, source_of=source_of, text=clean)
            if len(passes) > 1:
                main = choose_main_pass(passes, self.utts)
                keep_ids = set(passes[main].utts)
                other = {u.id for u in self.utts if u.kept and u.id not in keep_ids}
                for u in self.utts:
                    if u.id in other and u.id not in drop and covered_elsewhere(u, self.utts, other | drop):
                        drop.add(u.id)
        for u in self.utts:
            if u.id in drop and u.kept:
                u.status = "retake"
                u.note = "같은 대본을 한 번 더 말함(품질 게이트 A — 더 나은 테이크를 남김)"
        if drop:
            self.align_report["gate_dropped"] = sorted(drop)
        return len(drop)

    def _screen_checks(self, lp: dict, ed: EditDecisions) -> list[gate.GateResult]:
        """게이트 A(화면): A6 그래픽 분포 · A7 맨얼굴 최장 · A8 얼굴 비율 · A9 타이틀 위치 — 본편(하이라이트 붙이기 전) 시각."""
        total = self.timemap.duration
        gs = lp.get("graphics", [])
        holds = self._hold_spans()
        return [gate.a6_distribution(gs, total, ed.callouts),
                gate.a7_face_run(gs, total, ed.callouts),
                gate.a8_face_ratio(float(ed.stats.get("face_ratio", gate.face_ratio(gs, total)))),
                gate.a9_title(gs),
                # 리듬(docs/upgrade/05 4-2): 빠른 묶음 · 그래픽 사슬 · 길이 분포 · 홀드 보호 · 단계 싱크 · 홀드의 존재 · 박자 단조
                gate.a11_fast_runs(gs, total),
                gate.a12_chain(gs),
                gate.a13_duration_spread(gs),
                gate.a14_hold_guard(gs, holds, ed.callouts, ed.sfx),
                gate.a15_step_sync(gs),
                gate.a16_hold_presence(gs, lp.get("chapters", []), total, ed.callouts),
                gate.a17_monotony(gs),
                # 자료(03 문서 9절): 실물 비율 · 챕터마다 전면 자료 · 관련도
                gate.b1_media_ratio(gs, total),
                gate.b2_hero_per_chapter(gs, lp.get("chapters", []), total),
                gate.b6_pick_scores(gs),
                gate.b7_variety(gs),
                gate.b10_portraits(getattr(self, "_compose_plans", []))]

    def _compose_media(self, graphics: list[dict]) -> list[dict]:
        """사진(photo.image · broll 사진 src)마다 구도를 재서(`vision/compose.py`) data 에 safe(빈 쪽·어둠)·face·focus·fit 을 넣는다.
        측정은 파일마다 한 번(`work/compose.json`, 경로+크기 키). 영상 스톡은 재지 않는다(첫 프레임만으로는 구도가 안 맞는다)."""
        from .vision import compose
        cache_p = self.work / "compose.json"
        cache: dict[str, dict] = {}
        if cache_p.exists():
            try:
                cache = json.loads(cache_p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                cache = {}
        plans: list[dict] = []
        for g in graphics:
            d = g.get("data") or {}
            if g.get("template") == "photo":
                rel = d.get("image") or ""
            elif g.get("template") == "broll" and d.get("kind", "photo") == "photo":
                rel = d.get("src") or ""
            else:
                continue
            if not rel or str(rel).startswith(("pixabay:", "http")):
                continue
            p = self.public / rel
            if not p.exists():
                continue
            key = f"{rel}|{p.stat().st_size}"
            info = cache.get(key)
            if info is None:
                info = compose.analyze_image(p, self.log) or {"error": "unreadable"}
                cache[key] = info
            if info.get("error"):
                plans.append({"error": info["error"], "src": rel})
                continue
            # pip 액자는 face_safe_layouts 가 준 크기, 아니면 화면 전체
            pip = d.get("pip") if isinstance(d.get("pip"), dict) else None
            bw, bh = (float(pip.get("w", 700)), float(pip.get("h", 420))) if pip else (1920.0, 1080.0)
            plan = compose.plan_media(info, bw, bh)
            d.update(plan)
            g["data"] = d
            plans.append({**plan, "src": rel})
        try:
            cache_p.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        if plans:
            self.log(compose.media_report(plans))
        return plans

    def _gate_screen(self, lp: dict, ed: EditDecisions) -> tuple[dict, EditDecisions]:
        """렌더 props 확정 뒤: 그래픽 없는 칸·긴 맨얼굴은 그 자리의 핵심어 카드로 채우고, 늦은 타이틀은 앞으로 → props 다시."""
        res = self._screen_checks(lp, ed)
        added, moved, trimmed, merged = 0, False, 0, 0
        if any(not r.ok and r.repair == "fill_gaps" for r in res):
            added = self._fill_gaps(lp, ed)
        if any(not r.ok and r.repair == "retime_title" for r in res):
            moved = self._retime_title()
        if any(not r.ok and r.repair == "trim_chain" for r in res):
            trimmed = self._trim_chains(lp)
        if any(not r.ok and r.repair == "merge_steps" for r in res):
            merged = merge_step_runs(self.plan_long.get("graphics", []))
        promoted = 0
        b2 = next((r for r in res if r.id == "B2_hero" and not r.ok), None)
        if b2 is not None:
            promoted = gate.promote_hero(self.plan_long.get("graphics", []), lp.get("graphics", []),
                                         b2.measured.get("lacking", []))
        if added or moved or trimmed or merged or promoted:
            self.log(f"🚦 게이트 A 수리: " + " · ".join(x for x in [f"빈 구간에 핵심어 카드 {added}개" if added else "",
                                                               "타이틀을 앞으로" if moved else "",
                                                               f"이어 붙은 글자 카드 {trimmed}개 뺌" if trimmed else "",
                                                               f"단계 그래픽 {merged}개 합침" if merged else "",
                                                               f"자료 {promoted}장을 전면으로" if promoted else ""] if x))
            graphics, chapters = self._timed_long()
            self.long_chapters = chapters
            lp, ed = self._final_long_props(graphics, chapters)
            res = gate.merge(res, self._screen_checks(lp, ed))
        self._gate_record(res, "화면 구조")
        return lp, ed

    def _gap_keyword(self, u: Utterance) -> tuple[str, str]:
        """빈 구간을 채울 핵심어(화면 글자, 그 낱말) — 편집 감독의 강조어 → 콜아웃 문구 → 대본 용어 → 자주 나온 명사."""
        part = r"(은|는|이|가|을|를|의|에|에서|으로|로|와|과|도|만|까지|부터|이라는|라는|이란|란|입니다|이에요|예요|이죠|죠)$"
        for e in self.plan_long.get("emphasis", []) or []:
            w = str(e.get("word") or "").strip()
            if e.get("seg") == u.id and len(w) >= 2:
                return re.sub(part, "", w)[:12] or w[:12], w
        for m in self.plan_long.get("moments", []) or []:
            c = str(m.get("callout") or "").strip()
            if m.get("seg") == u.id and 2 <= len(c) <= 14:
                return c[:14], str(m.get("word") or "")
        terms = [t for t in glossary_terms(parse_script(self.spec.script))
                 if len(t) >= 2 and t in u.text] if self.spec.script else []
        if terms:
            t = max(terms, key=len)
            return t[:12], t
        kw = fallback._keywords([u.text], 1)
        return (kw[0][:12], kw[0]) if kw else ("", "")

    def _fill_gaps(self, lp: dict, ed: EditDecisions) -> int:
        """A6·A7 수리: 그래픽 없는 칸의 가운데와, 25초 넘는 맨얼굴 구간 안 18초마다 그 자리 문장의 핵심어 카드(얼굴 옆)를 계획에
        더한다(자리는 `gate.fill_targets` — 홀드 안이면 홀드 밖 가장 가까운 곳으로). 같은 발화에 두 번 넣지 않고, 다른 그래픽이
        있는 자리는 피한다."""
        total = self.timemap.duration
        gs = lp.get("graphics", [])
        holds = self._hold_spans()
        a6 = gate.a6_distribution(gs, total, ed.callouts)
        free = gate.face_only_spans(gs, ed.callouts, total)
        targets = gate.fill_targets(a6.measured.get("empty_at", []), free, holds)
        if not targets:
            return 0
        seg_t = seg_edit_times(self.utts, self.timemap)
        by_id = {u.id: u for u in self.utts}
        # 그래픽이 '실제로 화면에 나가는' 발화만 피한다(렌더 id g{i} = 계획 순서) — 계획에는 있지만 홀드·자료 부족으로 안 나가는
        # 것까지 피하면 채울 발화가 남지 않았다(2026-10-03)
        plan_gs = self.plan_long.get("graphics", [])
        used: set = set()
        for g in gs:
            m = re.fullmatch(r"g(\d+)", str(g.get("id", "")))
            if m and int(m.group(1)) < len(plan_gs):
                used.add(plan_gs[int(m.group(1))].get("start_seg"))
        added = 0
        for t in sorted(targets):
            cands = [(abs(a - t), i) for i, (a, b) in seg_t.items()
                     if i in by_id and by_id[i].kept and i not in used and b - a >= 1.5
                     and any(x <= a and a + 1.5 <= y for x, y in free) and abs(a - t) <= 12.0
                     and not any(h0 - 4.0 <= a <= h1 for h0, h1 in holds)]
            for _, i in sorted(cands):
                title, word = self._gap_keyword(by_id[i])
                if not title:
                    continue
                g = blank_graphic("keyword", i)
                g.update({"layout": "overlay", "title": title, "start_word": word if word in by_id[i].text else "",
                          "reason": "품질 게이트: 그래픽이 없던 구간을 그 문장의 핵심어로 채움", "source": "gate"})
                self.plan_long.setdefault("graphics", []).append(g)
                used.add(i)
                added += 1
                break
        return added

    def _trim_chains(self, lp: dict) -> int:
        """A12 수리: 시퀀스가 아닌 그래픽이 1초 안 간격으로 4개 넘게 이어지면 그 사슬 가운데의 글자 카드(대본 태그 아님,
        우선순위 낮은 것부터)를 계획에서 뺀다 — 사슬이 3개 이하가 될 때까지."""
        plan_g = self.plan_long.get("graphics", []) or []
        drop: list[int] = []
        for chain in gate.graphic_chains(lp.get("graphics", [])):
            extra = len(chain) - 3
            if extra <= 0:
                continue
            cands = [g for g in chain[1:-1] if g.get("template") in gate.TEXT_TEMPLATES and g.get("source") != "tag"]
            for g in sorted(cands, key=lambda g: g.get("priority", 5))[:extra]:
                gid = str(g.get("id", ""))
                if gid.startswith("g") and gid[1:].isdigit() and int(gid[1:]) < len(plan_g):
                    drop.append(int(gid[1:]))
        if drop:
            keep = [g for i, g in enumerate(plan_g) if i not in set(drop)]
            self.plan_long["graphics"] = keep
        return len(set(drop))

    def _retime_title(self) -> bool:
        """A9 수리: 타이틀 카드를 본편 4초 뒤 첫 문장(훅 다음)으로."""
        seg_t = seg_edit_times([u for u in self.utts if u.kept], self.timemap)
        order = sorted(seg_t.items(), key=lambda kv: kv[1][0])
        pick = next((i for i, (a, _) in order if a >= 4.0), order[1][0] if len(order) > 1 else None)
        if pick is None or pick == self.plan_long.get("title_card_seg"):
            return False
        self.plan_long["title_card_seg"] = pick
        return True

    def _gate_labels(self, graphic_lists: list[list[dict]], where: str) -> list[gate.GateResult]:
        """게이트 B3·B4·B5: 화면 글자에 검색어·연출 메모·내부 이름이 있으면 그 필드를 비운다(글자가 주인공인 그래픽은 뺀다)."""
        flat = [g for gl in graphic_lists for g in gl]
        res = [gate.b3_query_labels(flat), gate.b4_direction_notes(flat), gate.b5_internal_names(flat)]
        if any(not r.ok for r in res):
            fixed = 0
            for gl in graphic_lists:
                n, keep = gate.scrub_labels(gl)
                fixed += n
                gl[:] = keep
            if fixed:
                self.log(f"🚦 게이트 B 수리({where}): 화면 글자 {fixed}곳을 비움(검색어·연출 메모·내부 이름)")
            flat = [g for gl in graphic_lists for g in gl]
            res = gate.merge(res, [gate.b3_query_labels(flat), gate.b4_direction_notes(flat),
                                   gate.b5_internal_names(flat)])
        return res

    # ------------------------------------------------------------------
    # 📜 대본 충실 보증 — 대본 문장은 하나도 빠지지 않는다(studio/text/fidelity.py)
    def _script_sents(self) -> list["fidelity.Sentence"]:
        if getattr(self, "_fid_sents", None) is None:
            parsed = parse_script(self.spec.script)
            self._fid_sents = fidelity.sentences_of(parsed.sentences) if parsed.has_text else []
        return self._fid_sents

    def _raw_words(self) -> list[Word]:
        """단어 정리 전 인식 결과 전부(지운 되풀이·추임새 포함) — 무엇이 지워졌든 되살릴 수 있게."""
        if getattr(self, "_raw", None) is None:
            self._raw = [Word.from_dict(w) for w in read_json(self.work / "transcript.json", {}).get("words", [])]
        return self._raw

    def _ensure_script_utts(self) -> None:
        """1단계(발화): 대본 문장이 남긴 발화 어디에도 거의 없으면(들리는 비율 35% 미만) 그 문장을 담은 버린 발화
        (다른 테이크로 오인·편집 감독 drop·NG 오인)를 되살린다 — 그 문장 부분만 남겨서."""
        sents = self._script_sents()
        if not sents:
            return
        order = sorted(self.utts, key=lambda u: u.start)
        restored: list[str] = []
        for _ in range(3):
            kept_words = [w for u in order if u.kept for w in u.words]
            cov = fidelity.coverage(sents, kept_words)
            times = fidelity.sentence_times(sents, kept_words)
            cands = [u for u in order if not u.kept and u.status in ("retake", "director_drop", "editor_cut", "meta")
                     and u.words]
            if not cands:
                break
            owner = {id(w): u for u in cands for w in u.words}
            runs = fidelity.runs_of([u.words for u in cands])
            changed = False
            for i, s in enumerate(sents):
                if cov[i] >= 0.35 or not fidelity.restorable(s):
                    continue
                after, before = fidelity.neighbors(i, cov, times)
                r = fidelity.find_restore(s, runs, in_edit=lambda w: False, after=after, before=before)
                if r is None or r.ratio - cov[i] < fidelity.MIN_GAIN:
                    continue
                for u in {id(owner[id(w)]): owner[id(w)] for w in r.words if id(w) in owner}.values():
                    ws = [w for w in u.words if any(w is x for x in r.words)]
                    if not ws or u.kept:
                        continue
                    if len(ws) < len(u.words):          # 그 문장 부분만(나머지는 다른 테이크가 담고 있다)
                        u.words = ws
                        u.start, u.end = ws[0].start, ws[-1].end
                        u.text = u.asr_text = " ".join(w.text for w in ws)
                    u.note = f"대본 문장 복원(예전 판정: {u.status} {u.note[:40]})".strip()
                    u.status = "keep"
                    changed = True
                restored.append(s.text)
                cov[i] = 1.0
            if not changed:
                break
        if restored:
            self.align_report.setdefault("fidelity_restored", [])
            self.align_report["fidelity_restored"] = list(dict.fromkeys(self.align_report["fidelity_restored"] + restored))
            self.log(f"📜 대본 충실: 빠질 뻔한 대본 문장 {len(restored)}개를 되살렸습니다 — "
                     + " · ".join(f"「{t[:24]}」" for t in restored[:5]))

    def _ensure_script_keeps(self, keeps: list[Span]) -> list[Span]:
        """2단계(최종 편집본): 남긴 구간을 원본 인식 단어로 다시 읽어 대본 문장마다 들리는 비율을 재고, 60% 아래면 원본
        녹음에서 그 문장을 말한 곳(가장 잘 맞고 앞뒤 문장 사이·이미 일부 남은 테이크 우선)을 다시 넣는다 — 단어 정리·
        편집 검사·말 사이 다듬기가 지운 대본 단어까지. 결과는 리포트(대본 충실)에 남는다."""
        from bisect import bisect_right

        from .edit.cuts import quantize
        sents = self._script_sents()
        raw = self._raw_words()
        if not sents or not raw or not keeps:
            return keeps
        starts = [k.start for k in keeps]

        def in_edit(w: Word, ks=keeps, st=starts) -> bool:
            m = (w.start + w.end) / 2
            i = bisect_right(st, m) - 1
            return i >= 0 and ks[i].start <= m < ks[i].end

        # 편집본 글: 남긴 발화의 단어(대본으로 고친 글자 — '반영하세요'가 아니라 '안녕하세요') + 발화에 없는 인식 단어
        utt_words = sorted((w for u in self.utts if u.kept for w in u.words), key=lambda w: w.start)
        mids = [(w.start + w.end) / 2 for w in utt_words]

        def has_utt_word(w: Word) -> bool:
            j = bisect_right(mids, w.start - 0.05)
            return j < len(mids) and mids[j] <= w.end + 0.05

        edit_words = sorted([w for w in utt_words if in_edit(w)] + [w for w in raw if in_edit(w) and not has_utt_word(w)],
                            key=lambda w: w.start)
        cov = fidelity.coverage(sents, edit_words)
        times = fidelity.sentence_times(sents, edit_words)
        runs = fidelity.runs_of([u.words for u in build_utterances(raw)])
        # ✂️ 컷 총괄이 뺀 발화는 그 문장이 거의 없을 때(30% 미만)만 복원 후보 — 총괄이 다른 테이크를 골랐는데 규칙이 되돌려
        # 같은 말이 두 번 나오던 것(실제 실행 10/2, 검수 R18)
        ec = [(u.start - 0.05, u.end + 0.05) for u in self.utts if u.status == "editor_cut"]

        def in_ec(w: Word) -> bool:
            m = (w.start + w.end) / 2
            return any(a <= m <= b for a, b in ec)

        runs_strict = [[w for w in run if not in_ec(w)] for run in runs] if ec else runs
        adds: list[Span] = []
        restores: list[fidelity.Restore] = []
        for i, s in enumerate(sents):
            if cov[i] >= fidelity.COVERED or not fidelity.restorable(s):
                continue
            after, before = fidelity.neighbors(i, cov, times)
            r = fidelity.find_restore(s, runs if cov[i] < 0.3 else runs_strict, in_edit=in_edit, after=after, before=before)
            if r is None or r.ratio - cov[i] < fidelity.MIN_GAIN:
                continue
            adds.append(Span(max(0.0, r.start - 0.06), min(self.info.duration, r.end + 0.12)))
            restores.append(r)
        # 인식기가 받아 적지 못한 말(작게 말함·위스퍼가 건너뛰거나 다른 문장으로 잘못 받아 적음): 빠진 대본 문장(연달아
        # 빠졌으면 묶어서)의 앞뒤 문장이 편집본에 있고, 그 사이 원본에 편집본에 없는 말소리(VAD)가 그 문장들을 말할 만한
        # 길이로 있으면 그 말소리를 넣고 자막은 대본 문장으로
        rate = sum(len(norm(w.text)) for w in edit_words) / max(1.0, sum(w.end - w.start for w in edit_words))
        lost = [i for i, s in enumerate(sents) if cov[i] < fidelity.COVERED and fidelity.restorable(s)
                and not any(r.sentence == s.idx for r in restores)]
        groups: list[list[int]] = []
        for i in lost:
            if groups and groups[-1][-1] == i - 1:
                groups[-1].append(i)
            else:
                groups.append([i])
        for g in groups:
            after, _ = fidelity.neighbors(g[0], cov, times)
            _, before = fidelity.neighbors(g[-1], cov, times)
            if after < 0 or before >= 1e17 or before - after < 0.6:
                continue
            regions = [(max(a, after + 0.05), min(b, before - 0.05)) for a, b in (self.vad or [])
                       if b > after + 0.05 and a < before - 0.05]
            # 인식된 단어가 하나도 없는 말소리 덩어리만 — 일부라도 받아 적힌 덩어리(다른 문장의 다시 말하기 등)를 넣으면
            # 같은 말이 두 번 나온다
            regions = [(a, b) for a, b in regions if b - a >= 0.3 and _minus(a, b, raw) == [(a, b)]]
            regions = [(a, b) for a, b in regions if not in_edit(Word("", a, b, 1.0))]
            d = sum(b - a for a, b in regions)
            chars = sum(len(sents[i].n) for i in g)
            expected = chars / max(3.0, rate)
            if not regions or not (0.5 * expected <= d <= 2.2 * expected) or d < 0.6:
                continue
            adds += [Span(max(0.0, a - 0.06), min(self.info.duration, b + 0.12)) for a, b in regions]
            # 자막: 문장마다 글자 수만큼 말소리 시간을 나눠 대본 문장의 어절을 고르게 놓는다
            a0, b0 = regions[0][0], regions[-1][1]
            t = a0
            for i in g:
                dur = (b0 - a0) * len(sents[i].n) / max(1, chars)
                toks = sents[i].text.split()
                step = dur / max(1, len(toks))
                ws = [Word(tok, t + k * step, t + (k + 0.9) * step, 0.5) for k, tok in enumerate(toks)]
                restores.append(fidelity.Restore(sents[i].idx, sents[i].text, t, t + dur, ws, 0.0))
                t += dur
            self.log(f"📜 인식기가 받아 적지 못한 말소리 {d:.1f}초를 대본 문장 "
                     + " · ".join(f"「{sents[i].text[:20]}」" for i in g) + " 자리로 넣습니다")
        unresolved = [(i, s) for i, s in enumerate(sents) if cov[i] < fidelity.COVERED and fidelity.restorable(s)
                      and not any(r.sentence == s.idx for r in restores)]
        # 그 문장 자리(앞뒤 문장 사이)의 편집본 발화가 문장을 절반 넘게 담으면 '인식이 달라 확인 못 함'(소리는 들어 있다)
        uncertain = [s.text for i, s in unresolved
                     if fidelity.present_ratio(s, runs, in_edit=in_edit, after=fidelity.neighbors(i, cov, times)[0],
                                               before=fidelity.neighbors(i, cov, times)[1]) >= 0.5]
        unresolved = [s for _, s in unresolved]
        missing = [s.text for s in unresolved if s.text not in uncertain]
        self.fidelity = {"sentences": len(sents), "restored": [r.text for r in restores], "missing": missing,
                         "uncertain": uncertain,
                         "script_issues": [s.text for s in sents if not fidelity.restorable(s)],   # 대본 자체의 중복·뭉개짐
                         "coverage": round(sum(min(1.0, c) for c in cov) / max(1, len(cov)), 3)}
        self.align_report["fidelity"] = self.fidelity
        if missing and not getattr(self, "_fid_logged", False):
            self._fid_logged = True
            self.log(f"📜 녹음에서 찾지 못한 대본 문장 {len(missing)}개(말하지 않았거나 인식 실패 — 편집리포트 참고): "
                     + " · ".join(f"「{t[:20]}」" for t in missing[:4]))
        if not adds:
            return keeps
        out = quantize(merge(list(keeps) + adds), self.fps, self.info.duration)
        out = self.smap.clamp_keeps(out, self.fps)
        self._caption_restored(restores)
        self.log(f"📜 대본 충실(최종 확인): 편집본에서 빠진 대본 문장 {len(restores)}개를 원본에서 다시 넣었습니다 — "
                 + " · ".join(f"「{r.text[:24]}」" for r in restores[:5]))
        return out

    def _order_by_script(self, keeps: list[Span]) -> list[Span]:
        """대본을 여러 번 읽은 녹음: 주 회차의 구간은 시간순 그대로, 다른 회차에서 보강한 구간은 대본 위치에 맞는
        자리(대본 위치가 그보다 앞인 주 회차 구간 바로 뒤)로 옮긴다 — 시간순이면 앞 회차의 보강 문장이 영상 맨 앞에 나온다."""
        main = int(self.align_report.get("main_pass", 0))
        passes = self.align_report.get("passes") or []
        if self.align_report.get("pass_mode") != "best_pass" or not passes:
            return keeps
        by_id = {u.id: u for u in self.utts}
        p = next((x for x in passes if x["idx"] == main), None)
        if p and p.get("utts"):
            lo, hi = p["utts"][0], p["utts"][-1]
            t0, t1 = by_id[lo].start - 0.5 if lo in by_id else -1.0, by_id[hi].end + 0.5 if hi in by_id else 1e18
        else:
            return keeps
        kept = [u for u in self.utts if u.kept and u.script_span]

        def pos(k: Span) -> Optional[int]:
            hits = [u.script_span[0] for u in kept if u.start < k.end and k.start < u.end]   # type: ignore[index]
            return min(hits) if hits else None
        main_k = [k for k in keeps if t0 <= k.start <= t1]
        other = [k for k in keeps if not (t0 <= k.start <= t1)]
        if not other:
            return keeps
        out = list(main_k)
        for k in sorted(other, key=lambda k: (pos(k) is None, pos(k) or 0)):
            pk = pos(k)
            if pk is None:
                continue                      # 대본과 무관한 다른 회차 조각은 넣지 않는다
            idx = 0
            for i, m in enumerate(out):
                pm = pos(m)
                if pm is not None and pm <= pk:
                    idx = i + 1
            out.insert(idx, k)
        return out

    def _caption_restored(self, restores: list["fidelity.Restore"]) -> None:
        """되살린 단어가 자막에 보이게: 그 시각에 남긴 발화가 있으면 거기에 끼워 넣고, 없으면 그 시각의 버린 발화를
        되살리거나 새 발화로 만든다(인식 못 한 말소리는 대본 문장을 자막으로)."""
        def kept_sorted() -> list[Utterance]:
            return sorted((u for u in self.utts if u.kept and u.words), key=lambda u: u.start)

        for r in restores:
            kept = kept_sorted()
            # 이미 자막에 있는 단어(같은 시각의 발화 단어 — 대본으로 고친 글자일 수 있다)는 다시 넣지 않는다
            new = [w for w in r.words
                   if not any(x.start < w.end - 0.02 and w.start < x.end - 0.02 for u in kept for x in u.words)]
            if not new:
                continue
            host = next((u for u in kept if u.start - 0.3 <= r.start <= u.end + 0.3 or u.start - 0.3 <= r.end <= u.end + 0.3),
                        None)
            if host is not None:
                host.words = sorted(host.words + new, key=lambda x: x.start)
                host.start, host.end = host.words[0].start, host.words[-1].end
                continue
            other = next((u for u in self.utts if not u.kept and u.start - 0.3 <= r.start <= u.end + 0.3), None)
            if other is None:
                other = Utterance(max((u.id for u in self.utts), default=0) + 1, r.start, r.end, r.text, r.text)
                self.utts.append(other)
                self.utts.sort(key=lambda u: u.start)
            other.status, other.note = "keep", "대본 문장 복원(최종 확인)"
            other.words = sorted(new, key=lambda x: x.start)
            other.start, other.end = other.words[0].start, other.words[-1].end
            other.text = other.asr_text = " ".join(w.text for w in other.words)

    def _removed_spans(self) -> list[Span]:
        """단어 정리에서 지운 되풀이·추임새(원본 시간)."""
        rem = getattr(self, "removed", None)
        if rem is None:
            rem = (read_json(self.work / "align.json", {}).get("report") or {}).get("words_removed", [])
        return [Span(r["start"], r["end"]) for r in rem]

    def _keeps_key(self, keeps: list[Span]) -> str:
        return text_hash([(round(k.start, 3), round(k.end, 3)) for k in keeps], "verify-v1")

    def _make_cuts(self) -> None:
        """keep 구간(편집 검사에서 찾은 문제 구간은 뺀다) → 롱폼·숏폼 목소리 컷."""
        from .edit.cuts import quantize
        drops = getattr(self, "edit_drops", [])
        keeps = quantize(subtract(self.base_keeps, drops), self.fps, self.info.duration) if drops else self.base_keeps
        keeps = self._ensure_script_keeps(keeps)
        multipass = len(self.align_report.get("passes") or []) > 1
        if multipass:
            keeps = self._order_by_script(keeps)
        self.timemap = TimeMap(keeps, preserve_order=multipass)
        write_json(self.work / "keeps_long.json", self.timemap.to_list())
        starts = sorted(u.start for u in self.utts if u.kept)
        self.long_pieces = choose_angles(self.timemap.keeps, self.smap, self.quality, sentence_starts=starts)
        if self.spec.make_long:
            cut_audio(self.ff, self.work / "voice.wav", self.timemap.keeps, self.media / "long_voice.wav", self.work,
                      log=self.log, cancel=self.cancel)
            self._make_highlight_cuts(drops, starts)
        self.short_maps: list[TimeMap] = []
        self.short_pieces = []
        for i, s in enumerate(self.plan_shorts, 1):
            keeps = keeps_for_segments(self.utts, s["segments"], pace=PACES["shorts"], vad=self.vad,
                                       media_duration=self.info.duration, fps=self.fps, exclude=self._removed_spans())
            if drops:   # 롱폼처럼 다시 프레임 격자에 맞춘다(안 맞추면 클립마다 반 프레임까지 어긋남)
                keeps = quantize(subtract(keeps, drops), self.fps, self.info.duration)
            keeps = self._limit_short(self.smap.clamp_keeps(keeps, self.fps))
            tm = TimeMap(keeps, preserve_order=True)
            s["duration"] = tm.duration
            self.short_maps.append(tm)
            # 숏폼은 얼굴이 크게 보이는 앵글을 조금 더 선호(세로 화면 아래 절반이 얼굴)
            self.short_pieces.append(choose_angles(tm.keeps, self.smap, self.quality, sentence_starts=starts,
                                                   prefer_close=True, max_hold=7.0))
            cut_audio(self.ff, self.work / "voice.wav", keeps, self.media / f"short_{i}_voice.wav", self.work,
                      log=self.log, cancel=self.cancel)
            self.log(f"숏폼 {i}: {tm.duration:.1f}초 · 구간 {len(keeps)}개")
        if not self.smap.single:   # 진단·리포트용: 어느 구간에 어느 앵글을 썼나
            write_json(self.work / "angles.json", {
                "long": [vars(p) for p in self.long_pieces],
                "shorts": [[vars(p) for p in ps] for ps in self.short_pieces]})

    def _make_highlight_cuts(self, drops: list[Span], starts: list[float]) -> None:
        """🎬 오프닝 하이라이트: 편집 감독이 고른 임팩트 문장 2~4개(각 ≤7초, 합쳐 ≤highlight_max_sec)를 본편 앞에 붙일
        컷(원본 시각 순, 조각 사이 숨 한 번). 목소리는 하이라이트 + 본편을 이어 long_voice_full.wav 로."""
        self.hl_map, self.hl_pieces, self.hl_segs, self.hl_duration = None, [], [], 0.0
        if not self.spec.opening_highlight or self.timemap.duration < 45.0:     # 아주 짧은 영상은 하이라이트가 되풀이로 들린다
            return
        by_id = {u.id: u for u in self.utts}
        segs = [h["seg"] for h in self.plan_long.get("highlights", []) or [] if h.get("seg") in by_id and by_id[h["seg"]].kept]
        segs = [s for s in segs if by_id[s].end - by_id[s].start <= 7.5]
        segs = sorted(dict.fromkeys(segs), key=lambda i: by_id[i].start)[:4]
        if len(segs) < 2:
            return
        from .edit.cuts import quantize
        keeps: list[Span] = []
        total = 0.0
        used: list[int] = []
        for sid in segs:
            ks = keeps_for_segments(self.utts, [sid], pace=PACES["highlight"], vad=self.vad,
                                    media_duration=self.info.duration, fps=self.fps, exclude=self._removed_spans())
            if drops:
                ks = quantize(subtract(ks, drops), self.fps, self.info.duration)
            ks = self.smap.clamp_keeps(ks, self.fps)
            d = sum(k.dur for k in ks)
            if not ks or total + d > float(self.spec.highlight_max_sec):
                continue
            keeps += ks
            total += d
            used.append(sid)
        if len(used) < 2:
            return
        self.hl_map = TimeMap(keeps, preserve_order=True)
        self.hl_segs = used
        self.hl_duration = self.hl_map.duration
        self.hl_pieces = choose_angles(self.hl_map.keeps, self.smap, self.quality, sentence_starts=starts,
                                       prefer_close=True, max_hold=7.0)
        cut_audio(self.ff, self.work / "voice.wav", list(self.hl_map.keeps) + list(self.timemap.keeps),
                  self.media / "long_voice_full.wav", self.work, log=self.log, cancel=self.cancel)
        self.log("🎬 오프닝 하이라이트 " + f"{len(used)}조각 · {total:.1f}초: "
                 + " / ".join(f"「{by_id[i].text[:24]}」" for i in used))

    # ------------------------------------------------------------------
    def stage_verify(self) -> None:
        """🔎 편집 검사: 잘라 붙인 롱폼 목소리를 Whisper 로 다시 받아 적어, 남은 되풀이·추임새·긴 무음을 찾아 더 자른다."""
        if not (self.spec.make_long and self.spec.verify_edit and (self.media / "long_voice.wav").exists()):
            return
        base = self._keeps_key(self.base_keeps)
        ver = read_json(self.work / "verify.json", {})
        if ver.get("base") == base and ver.get("done"):
            self.log(f"🔎 편집 검사: 캐시 사용(추가로 자른 곳 {len(ver.get('drops', []))}곳)")
            return
        parsed = parse_script(self.spec.script)
        hints = glossary_terms(parsed, extra=list(self.settings.glossary.values()))
        rounds: list[dict] = []
        drops = list(getattr(self, "edit_drops", []))
        for rnd in (1, 2):
            wav = self.work / "verify16k.wav"
            self.ff.extract_audio(self.media / "long_voice.wav", wav, rate=16000, mono=True, cancel=self.cancel)
            res = transcribe(wav, model_name=self.settings.whisper_model, device=self.settings.whisper_device,
                             compute_type=self.settings.whisper_compute, batch_size=self.settings.whisper_batch,
                             hint_terms=hints,
                             duration=self.timemap.duration, log=lambda m: None,
                             progress=lambda f, r=rnd: self._stage("verify", (r - 1) * 0.5 + 0.45 * f),
                             cancel=self.cancel)
            words = [Word.from_dict(w) for w in res.get("words", [])]
            vad = speech_regions(load_audio_16k(wav))
            issues = find_issues(words, vad, max_silence=self._pace().max_silence, duration=self.timemap.duration)
            rounds.append({"round": rnd, "words": len(words), "issues": [i.to_dict() for i in issues]})
            if not issues:
                self.log(f"🔎 편집 검사 {rnd}차: 남은 되풀이·추임새·긴 무음 없음")
                break
            kinds = {}
            for it in issues:
                kinds[it.reason] = kinds.get(it.reason, 0) + 1
            self.log(f"🔎 편집 검사 {rnd}차: " + " · ".join(f"{k} {v}곳" for k, v in kinds.items()) + " → 더 자릅니다")
            for it in issues[:12]:
                self.log(f"   - {fmt_ts(it.start)} {it.reason}" + (f" 「{it.text[:40]}」" if it.text else ""))
            drops += to_source(issues, self.timemap)
            self.edit_drops = drops
            self._make_cuts()
        write_json(self.work / "verify.json", {"base": base, "done": True, "drops": [[d.start, d.end] for d in drops],
                                               "rounds": rounds})
        self.verify_report = rounds

    def _limit_short(self, keeps: list[Span]) -> list[Span]:
        limit = float(self.spec.short_max_sec) + 5.0
        out, acc = [], 0.0
        for k in keeps:
            if acc + k.dur > limit and out:
                break
            out.append(k)
            acc += k.dur
        return out

    # ------------------------------------------------------------------
    def stage_broll(self) -> None:
        """📷 자료 사진: 고유명사는 무엇인지(사람·브랜드·그 밖)를 먼저 알고 — 브랜드는 로고, 사람은 후보 중 가장 품위 있게
        나온 초상(비전 선택, 없으면 규칙 점수), 그 밖은 문서 대표 이미지 → 커먼즈 검색(studio/broll/resolve.py)."""
        local = list_local_images(self.spec.images_dir)
        online = self.spec.fetch_broll
        wm = Wikimedia(self.settings.wikimedia_contact, log=self.log, cache_dir=self.work / "wm_cache") if online else None
        wp = WikipediaImages(self.settings.wikimedia_contact, log=self.log, cache_dir=self.work / "wm_cache") \
            if online else None
        logos = SimpleIcons(USER_DIR / "cache", log=self.log) if online else None
        img_dir = self.public / "images"
        resolver = MediaResolver(local=local, dst_dir=img_dir, work_dir=self.work / "wm_cache", wikimedia=wm,
                                 wikipedia=wp, logos=logos, log=self.log)
        graphic_lists = [self.plan_long["graphics"]] + [s["graphics"] for s in self.plan_shorts]
        # 조달 사다리가 이미 파일로 바꾼 자료(resolved)는 다시 찾지 않는다
        photos = [g for gl in graphic_lists for g in gl if g["template"] == "photo" and not g.get("resolved")]
        total = len(photos) or 1
        plans: dict[str, MediaPlan] = {}
        for n, g in enumerate(photos):
            q = g.get("image", "").strip()
            if q in plans:
                continue
            kind = g.get("entity") or ""
            names = tuple(x for x in (g.get("name_en"), g.get("subtitle") if g.get("wiki") else "") if x)
            plans[q] = resolver.plan(q, kind, names)
            self._stage("broll", 0.7 * (n + 1) / total)
        self._pick_portraits(resolver, [p for p in plans.values() if p.candidates and p.result is None])
        for q, pl in plans.items():
            res = pl.result
            self.broll_log.append({"query": q, "kind": pl.kind, **(res.to_dict() if res else {"origin": "없음"})})
            if res is not None:
                self._preview(res.path, f"자료 사진 · {q}" + (" (로고)" if res.origin == "logo" else ""))
        for gl in graphic_lists:
            keep = []
            for g in gl:
                if g["template"] != "photo" or g.get("resolved"):
                    keep.append(g)
                    continue
                q = g.get("image", "").strip()
                pl = plans.get(q) or MediaPlan(q)
                res = pl.result
                if res is None and (g.get("wiki") or pl.kind == "brand") and pl.kind not in ("person", "brand"):
                    # 작품·사물·장소: 위키에 없으면 Openverse(상업·변형 허용 CC) 한 번 — 제목에 그 이름이 있는 것만
                    res = self._openverse_named(q, g.get("name_en") or "", img_dir)
                    if res is not None:
                        pl.result = res
                        self.broll_log.append({"query": q, "kind": pl.kind, **res.to_dict()})
                if res is None:
                    if g.get("wiki") or pl.kind == "brand":
                        # 고유명사·브랜드: 쓸 수 있는 이미지가 없으면 스톡으로 넘기지 않는다 — 틀린 사진보다 없는 게 낫다.
                        # 조용히 지우지도 않는다: 이름 카드(타이포 자료 카드)로 그 자리를 지킨다(P0-4)
                        card = type_card(g, (pl.info or {}).get("description", ""))
                        if card is not None:
                            self.log(f"자료 사진: '{q}' 는 쓸 수 있는 이미지가 없어 이름 카드로 대신합니다")
                            self.broll_log.append({"query": q, "kind": pl.kind, "origin": "type_card"})
                            keep.append(card)
                        else:
                            self.log(f"자료 사진: '{q}' 는 쓸 수 있는 이미지가 없어 뺍니다")
                            self.broll_log.append({"query": q, "kind": pl.kind, "origin": "lost"})
                        continue
                    # 위키미디어·내 폴더에 없으면 버리지 않고 스톡 사진(Pixabay 등) 요청으로 넘긴다 — 다음 단계가 찾는다
                    if q and self._stock_enabled():
                        g = copy.deepcopy(g)
                        g["template"] = "broll"
                        g["stock"] = {"kind": "photo", "query_en": q, "query_ko": g.get("title", ""),
                                      "purpose": g.get("body", ""), "must_show": "",
                                      "context": self._seg_text(g.get("start_seg"))}
                        g["title"] = g["body"] = g["subtitle"] = ""     # 검색어는 화면 라벨이 아니다(게이트 B3)
                        keep.append(g)
                    continue
                g = copy.deepcopy(g)
                g["image"] = f"images/{res.path.name}"
                g["credit"] = res.credit
                matted = mat_tall(res.path) if res.origin != "logo" else None
                if matted is not None:       # 세로 사진은 버리거나 가운데만 자르지 않고 크림 종이 여백 액자로(P0-11)
                    g["image"], g["mat"] = f"images/{matted.name}", True
                if res.origin == "logo":
                    g["logo"] = True        # 라벨 '브랜드'는 붙이지 않는다 — 로고가 곧 그 브랜드다
                elif pl.kind == "person" and pl.info and pl.info.get("description") and g.get("body") in ("", "인물"):
                    g["body"] = str(pl.info["description"])[:24]
                keep.append(g)
            gl[:] = keep
        self._stage("broll", 1.0)

    # ------------------------------------------------------------------
    # 🎞 자료 조달 v2 — 자료 리서처의 증거 계획 → 사다리 → 확보 목록(모션 디자이너 앞, 13 문서 2-2)
    # ------------------------------------------------------------------
    def _procure_evidence(self, res: dict[str, Any], rnd: int = 1) -> dict[str, Any]:
        """Studio.plan 의 콜백: EVIDENCE 결과 → 조달(studio/assets/ladder.py) → {outcomes, brief(확보 목록), sheet(컨택트 시트),
        backfill(1회차에서 실물 비율이 모자라면 자료 리서처 보충 요청 블록)}. work/evidence.json 에 기록."""
        from .assets import graphics as ev_graphics
        from .assets.ladder import Ladder, clean_item, summary
        items = [it for it in res.get("items", []) or [] if isinstance(it, dict)]
        if not items:
            return {"outcomes": [], "brief": "", "sheet": None, "backfill": ""}
        if self.research:
            # 🔎 리서처가 확인한 커먼즈 파일을 대상 이름으로 이어 준다(자료 리서처가 옮겨 적지 않았어도)
            from .agents.research import files_for
            for it in items:
                subj = it.get("subject") if isinstance(it.get("subject"), dict) else {}
                if not it.get("commons_files"):
                    fs = files_for(self.research, subj.get("name_ko"), subj.get("name_en"))
                    if fs:
                        it["commons_files"] = fs
        self.log(f"🎞 자료 조달 {rnd}회차: 증거 {len(items)}건 — 화자 자료 → 고유명사·출처 → 화면 → 스톡 순서로")
        ladder = Ladder(self._evidence_deps(), public=self.public, work=self.work, log=self.log)
        outcomes = ladder.run(items)
        st = summary([clean_item(i) for i in items], outcomes)
        self.log("🎞 조달: " + f"{st['acquired']}/{st['requests']}건 확보 · "
                 + " · ".join(f"{k} {v}" for k, v in sorted(st["rungs"].items())))
        _, drawn = ev_graphics.to_graphics(items, outcomes)
        old = read_json(self.work / "evidence.json", {})
        rounds = (old.get("rounds") if isinstance(old, dict) and rnd > 1 else None) or []
        rounds.append({"round": rnd, "items": items, "outcomes": outcomes, "summary": st, "notes": res.get("notes", "")})
        write_json(self.work / "evidence.json", {"rounds": rounds})
        self.evidence_stats = st
        back = self._backfill_block(items, outcomes) if rnd == 1 else ""
        return {"outcomes": outcomes, "brief": ev_graphics.brief_for_motion(items, outcomes, drawn),
                "sheet": self._evidence_sheet(outcomes), "backfill": back}

    def _evidence_deps(self) -> "Deps":
        from .assets.commons import EntityMedia
        from .assets.ladder import Deps
        from .assets.library import AssetLibrary
        from .assets.scholar import Scholar
        online = self.spec.fetch_broll
        cache = self.work / "wm_cache"
        wm = Wikimedia(self.settings.wikimedia_contact, log=self.log, cache_dir=cache) if online else None
        wp = WikipediaImages(self.settings.wikimedia_contact, log=self.log, cache_dir=cache) if online else None
        logos = SimpleIcons(USER_DIR / "cache", log=self.log) if online else None
        resolver = MediaResolver(local=list_local_images(self.spec.images_dir), dst_dir=self.public / "images",
                                 work_dir=cache, wikimedia=wm, wikipedia=wp, logos=logos, log=self.log) if online else None
        allow_quote = bool(getattr(self.settings, "allow_quote", False))
        studio = self._ensure_studio()
        capture = None
        if allow_quote and online:
            from .assets.screenshot import capture as shot
            rs = self.settings.render
            capture = lambda shots: shot(shots, node=find_node(self.settings.node_path), work=self.work,  # noqa: E731
                                         browser_executable=rs.browser_executable, gl=rs.gl, log=self.log)
        return Deps(resolver=resolver, media=EntityMedia(wp, log=self.log, allow_quote=allow_quote) if wp else None,
                    scholar=Scholar(cache_dir=cache, log=self.log) if online else None,
                    local=tuple(getattr(self, "_materials", None) or ()),
                    library=AssetLibrary(USER_DIR / "asset_library") if online else None,
                    openverse=self._openverse_named if online else None, capture=capture,
                    pick=(lambda text, sheets: studio.pick_evidence(self.ctx, text, sheets)) if studio else None,
                    pick_portraits=self._pick_portraits,
                    stock=self._stock_batch if self._stock_enabled() else None, allow_quote=allow_quote)

    def _stock_batch(self, reqs: list[dict[str, Any]]) -> list[Optional[dict[str, Any]]]:
        """스톡 요청 묶음 → StockResearcher(검색 → 비전 선택 → 받기·정리, work/stock.json 캐시) → 요청마다 {src, kind, credit, url}."""
        hub = StockHub.from_settings(self.settings, log=self.log, cache_dir=self.work / "stock_cache")
        tmp = [{"template": "broll", "start_seg": -1, "title": "", "stock": dict(r)} for r in reqs]
        studio = self._ensure_studio()
        pick = (lambda text, sheets: studio.pick_stock(self.ctx, text, sheets)) if studio else None
        res = StockResearcher(hub, self.ff, work=self.work, public=self.public, fps=self.fps, pick=pick, log=self.log,
                              cancel=self.cancel)
        lists = [tmp]
        res.run(lists)
        self.broll_log += res.credits
        out: list[Optional[dict[str, Any]]] = []
        by_key = {id(g): g for g in lists[0]}
        for g in tmp:
            g2 = by_key.get(id(g))
            if g2 is not None and g2.get("src") and g2.get("template") == "broll":
                out.append({"src": g2["src"], "kind": g2.get("kind", "photo"), "credit": g2.get("credit", ""),
                            "url": g2.get("stock_url", "")})
            else:
                out.append(None)
        return out

    def _evidence_sheet(self, outcomes: list[dict[str, Any]]) -> Optional[bytes]:
        """확보한 자료의 컨택트 시트(E번호) — 모션 디자이너가 무엇이 있는지 눈으로 본다."""
        cells: list[tuple[str, Optional[bytes]]] = []
        for n, o in enumerate(outcomes, start=1):
            a = (o.get("assets") or [None])[0]
            src = a.get("src") if a else ((o.get("stock") or {}).get("src") if (o.get("stock") or {}).get("kind") == "photo"
                                          else "")
            if not src:
                continue
            p = self.public / src
            try:
                from PIL import Image
                import io
                with Image.open(p) as im:
                    im = im.convert("RGB")
                    im.thumbnail((400, 400))
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=80)
                    cells.append((f"E{n}", buf.getvalue()))
            except Exception:  # noqa: BLE001 - SVG 로고 등은 시트에서 뺀다
                continue
            if len(cells) >= 18:
                break
        return contact_sheet(cells, contain=True) if cells else None

    def _backfill_block(self, items: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> str:
        """게이트 B1(실물 자료 화면 비율 ≥ 30%)을 기획 단계에서 어림 — 모자라면 자료 리서처 보충 요청 블록(13 문서 2-3).
        어림: 확보한 증거마다 트리트먼트 유지 시간(EVIDENCE_HOLD)을 그 발화 구간 길이로 자른 합 / 남긴 발화 길이."""
        from .director.plan import EVIDENCE_HOLD
        kept = [u for u in self.utts if u.kept]
        if not kept:
            return ""
        total = sum(u.end - u.start for u in kept)
        by_id = {u.id: u for u in kept}
        t_of = {u.id: u.start for u in kept}
        got_t: list[float] = []
        shown = 0.0
        for it, o in zip(items, outcomes):
            if not (o.get("assets") or o.get("stock")):
                continue
            a, b = by_id.get(it.get("start_seg")), by_id.get(it.get("end_seg", it.get("start_seg")))
            span = (b.end - a.start) if a and b and b.end > a.start else (a.end - a.start if a else 3.0)
            shown += min(max(span, 2.5), EVIDENCE_HOLD.get(str(it.get("treatment") or "hero"), 4.0) + 2.0)
            if a:
                got_t.append(a.start)
        ratio = shown / max(1.0, total)
        if ratio >= 0.40 or total < 90:                     # 디자인 v4: 실물 자료 목표 45~65%
            return ""
        gaps = []
        marks = sorted([kept[0].start] + got_t + [kept[-1].end])
        for x, y in zip(marks, marks[1:]):
            if y - x >= 30:
                segs = [u.id for u in kept if x <= u.start < y]
                if segs:
                    gaps.append(f"- [B1] {int(x // 60):02d}:{int(x % 60):02d}–{int(y // 60):02d}:{int(y % 60):02d}"
                                f"(S{segs[0]}–S{segs[-1]}): 실물 자료 0개")
        lost = []
        for it, o in zip(items, outcomes):
            if not (o.get("assets") or o.get("stock") or o.get("archive")) and o.get("rung") != "code_drawn":
                subj = it.get("subject") or {}
                lost.append(f"- [B6] S{it.get('start_seg')} 「{subj.get('name_ko') or it.get('label') or it.get('claim', '')[:20]}」"
                            f"({it.get('need')}): {o.get('why') or '못 구함'} — 다른 need·대상으로")
        used = {str(it.get("local_file") or "") for it in items}
        left = [m for m in getattr(self, "_materials", []) or [] if m.name not in used and m.key not in used]
        lines = ["## 이번 호출은 보충이다",
                 "아래 구간·항목만 낸다. 이미 낸 것은 다시 내지 않는다(같은 문장에 같은 자료를 또 내지 않는다).",
                 f"- [B1] 실물 자료가 보이는 시간 어림 {ratio:.0%}(목표 40~55%, 최소 30%)."]
        lines += gaps[:6] + lost[:8]
        if left:
            lines.append("- 자료 폴더에 아직 쓰지 않은 파일: " + ", ".join(f"{m.key} `{m.name}`" for m in left[:12]))
        return "\n".join(lines)

    def _openverse_named(self, name: str, alt: str, dst_dir: Path) -> Optional["ImageResult"]:
        """고유명사(작품·사물·장소)를 Openverse 에서 한 번 — 상업·변형 허용 라이선스이고 제목에 그 이름(원어 이름 우선)이
        통째로 들어 있는 첫 사진만. 키 없는 검색을 끈 설정이면 건너뛴다."""
        from .broll.images import ImageResult
        from .stock.openverse import Openverse
        from .stock.process import prepare_photo
        if not (self.spec.fetch_broll and getattr(self.settings, "keyless_stock", True)):
            return None
        q = (alt or name).strip()
        key = norm(q)
        if len(key) < 4:
            return None
        try:
            cands = Openverse(cache_dir=self.work / "stock_cache").search_photos(q, per_page=6)
        except Exception as e:  # noqa: BLE001 - 대체 경로라 실패해도 그만
            self._log_file_only(f"   (Openverse '{q}' 실패: {e})")
            return None
        for c in cands:
            if key not in norm(c.alt):
                continue
            try:
                raw = self.work / "stock_raw" / f"ov_{c.key}.bin"
                raw.parent.mkdir(parents=True, exist_ok=True)
                if not raw.exists():
                    net_download(c.download, raw, timeout=40)
                dst = dst_dir / f"ov_{c.key}.jpg"
                dst_dir.mkdir(parents=True, exist_ok=True)
                if not dst.exists():
                    prepare_photo(raw, dst)
            except Exception as e:  # noqa: BLE001
                self._log_file_only(f"   (Openverse 다운로드 실패 {c.id}: {e})")
                continue
            self.log(f"자료 사진(Openverse): '{name}' → {c.alt[:40]} ({c.credit})")
            return ImageResult(dst, c.credit, c.extra.get("license", ""), c.url, "openverse")
        return None

    def _seg_text(self, seg: Any) -> str:
        """그 그래픽이 붙은 발화(문맥) — 스톡 검색어·후보 선택이 낱말이 아니라 문장의 뜻을 보게."""
        u = next((u for u in self.utts if u.id == seg), None)
        return u.text.strip()[:160] if u else ""

    def _pick_portraits(self, resolver: MediaResolver, pending: list[MediaPlan]) -> None:
        """인물마다 후보 썸네일 → 규칙 점수 → (AI 가 있으면) 비전으로 '가장 품위 있게 나온 사진' 선택."""
        if not pending:
            return
        for p in pending:
            resolver.score_candidates(p)
        pending = [p for p in pending if p.candidates]
        if not pending:
            return
        choice = {id(p): resolver.best_by_rule(p) for p in pending}
        studio = self._ensure_studio()
        multi = [p for p in pending if len(p.candidates) > 1]
        if studio is not None and multi:
            sheets, lines = [], []
            for r, p in enumerate(multi, start=1):
                sheets.append((f"R{r}", contact_sheet(contact_rows(p), cell=(300, 380), contain=True), "image/jpeg"))
                lines.append(f"- R{r} {p.query}" + (f" ({p.info.get('title')})" if p.info else "") + " · 규칙 점수: "
                             + ", ".join(f"C{j} {c['score']:+.2f}" for j, c in enumerate(p.candidates, start=1)))
            try:
                picks = studio.pick_portrait(self.ctx, "\n".join(lines), sheets)
                for pk in picks:
                    r, c = int(pk.get("request", 0)), int(pk.get("candidate", 0))
                    if 1 <= r <= len(multi):
                        p = multi[r - 1]
                        choice[id(p)] = c - 1 if 1 <= c <= len(p.candidates) else -1
                        if pk.get("reason"):
                            self.log(f"📷 {p.query}: C{c} — {pk['reason']}")
            except (DirectorError, ValueError, TypeError) as e:
                self.log(f"📷 인물 사진 비전 선택 실패 → 규칙 점수: {e}")
        for p in pending:
            idx = choice[id(p)]
            if idx >= 0:
                c = p.candidates[idx]
                self.log(f"📷 인물 사진 '{p.query}': 후보 {len(p.candidates)}장 중 {c['name']}"
                         f"(점수 {c['score']:+.2f}" + (f" · {', '.join(c['why'][:3])}" if c.get("why") else "") + ")")
            p.result = resolver.finish(p, idx)

    def stage_stock(self) -> None:
        """🎞 B-roll 요청 → 무료 스톡 검색(Pixabay 등 + 키 없는 Openverse) → (Claude 비전으로) 선택 → 정리.
        모션 장면의 'pixabay:…' 이미지 요소도 여기서 파일로 바꾼다(스톡이 꺼져 있으면 요소를 뺀다)."""
        lists = [self.plan_long["graphics"]] + [s["graphics"] for s in self.plan_shorts]
        n = sum(1 for gl in lists for g in gl if g["template"] == "broll")
        imgs = sum(1 for gl in lists for g in gl if g["template"] == "motion" and isinstance(g.get("spec"), dict)
                   for e in g["spec"].get("elements", []) or []
                   if isinstance(e, dict) and str(e.get("src", "")).startswith("pixabay:"))
        self.stock_stats = {"requests": n, "image_requests": imgs}
        if not n and not imgs:
            self.log("🎞 기획에 스톡 B-roll·그래픽 이미지 요청이 없습니다(자료 리서처가 요청을 만들지 않음).")
            return
        if not self._stock_enabled():
            self.log(f"🎞 스톡 B-roll {n}건 · 그래픽 이미지 {imgs}건 건너뜀(꺼짐)")
            for gl in lists:
                gl[:] = [g for g in gl if g["template"] != "broll" or g.get("src")]
            strip_stock_images(lists)
            return
        hub = StockHub.from_settings(self.settings, log=self.log, cache_dir=self.work / "stock_cache")
        self.log("🎞 검색처: " + (", ".join(hub.names) or "없음") + " · " + hub.check())
        # 후보를 고를 때 검색어 낱말이 아니라 그 장면에서 하는 말(문맥)을 보게 한다 — '노트북으로 작업하는 디자이너'에
        # 종이 노트가 뽑히지 않게
        for gl in lists:
            for g in gl:
                if g["template"] == "broll" and isinstance(g.get("stock"), dict) and not g["stock"].get("context"):
                    g["stock"]["context"] = self._seg_text(g.get("start_seg"))
        studio = self._ensure_studio()
        pick = (lambda text, sheets: studio.pick_stock(self.ctx, text, sheets)) if studio else None
        res = StockResearcher(hub, self.ff, work=self.work, public=self.public, fps=self.fps, pick=pick, log=self.log,
                              cancel=self.cancel)
        if n:
            res.run(lists, progress=self._sp("stock"))
        res.resolve_images(lists)
        self.stock_stats = res.stats
        self.broll_log += res.credits + res.fallbacks
        left = hub.remaining()
        if left:
            self.log("🎞 남은 호출: " + " · ".join(f"{k} {v}회" for k, v in left.items()))

    def stage_sound(self) -> None:
        """🔊 효과음·배경음악 라이브러리 준비(처음 한 번 내려받고 이후 재사용, 실패 시 내장 효과음)."""
        if not (self.spec.sfx or (self.spec.music and not self.spec.bgm)):
            return
        lib = self._sound_lib(full=True)
        cats = sorted({s.category for s in lib.sfx if s.source != "synth"})
        self.log(f"🔊 효과음 {len(lib.sfx)}개(내려받은 카테고리 {len(cats)}) · 배경음악 {len(lib.bgm)}곡")

    def stage_music(self) -> None:
        """🎼 음악 감독의 큐 시트 — 편집 검사가 컷을 확정한 뒤(전사본의 편집 시각이 최종), 음악이 있을 때만."""
        lib = self.sounds if (self.spec.music and not self.spec.bgm) else None
        if self.spec.make_long and self._music_on(lib):
            self._music_sheet()

    def _soft_music(self) -> None:
        self._music = {}
        self.log("   → 큐 시트 없이(예전처럼 말 아래 덕킹) 계속합니다")

    def _music_on(self, lib=None) -> bool:
        if self.spec.bgm and Path(self.spec.bgm).exists():
            return True
        return bool(self.spec.music and lib is not None and lib.bgm)

    def _music_listing(self) -> str:
        """음악 감독이 읽는 전사본: 남은 발화의 편집 시각(본편 기준) + 챕터·홀드·강도 3 표시."""
        kept = [u for u in self.utts if u.kept]
        seg_t = seg_edit_times(kept, self.timemap)
        ch = {c["seg"]: c for c in self.plan_long.get("chapters", []) or []}
        holds = [(h["start_seg"], h["end_seg"]) for h in self.plan_long.get("holds", []) or []]
        strong = {m.get("seg") for m in self.plan_long.get("moments", []) or [] if int(m.get("intensity", 0) or 0) >= 3}
        hl = f" · 앞에 오프닝 하이라이트(약 {self.spec.highlight_max_sec:.0f}초 이내)" if self.spec.opening_highlight else ""
        lines = [f"본편 길이 {fmt_ts(self.timemap.duration)} · 남은 발화 {len(seg_t)}개{hl}"]
        for u in kept:
            if u.id not in seg_t:
                continue
            if u.id in ch:
                c = ch[u.id]
                lines.append(f"## 챕터: {c['title']}" + (f" — {c['claim']}" if c.get("claim") else ""))
            a, b = seg_t[u.id]
            marks = (" | 얼굴 홀드" if any(x <= u.id <= y for x, y in holds) else "") + (" | 강도 3" if u.id in strong else "")
            lines.append(f"[S{u.id} | 편집 {fmt_ts(a)}–{fmt_ts(b)}{marks}] {u.text}")
        return "\n".join(lines)

    def _music_sheet(self) -> dict:
        """🎼 큐 시트: 계획에 손으로 넣은 것(music_cues) → 캐시(work/music.json, 전사본·브리프가 같을 때) → 음악 감독 →
        실패하면 규칙 큐 시트(04 문서 10절 3단계). 결과는 self._music(계획 파일은 건드리지 않는다 — 편집 검사와 동시에 돈다)."""
        if self.plan_long.get("music_cues"):
            self._music = dict(self.plan_long["music_cues"], by=self.plan_long["music_cues"].get("by", "plan"))
            return self._music
        kept_ids = [u.id for u in self.utts if u.kept]
        listing = self._music_listing()
        brief = self.plan_long.get("studio") or {}
        my = getattr(self, "_my_tracks", []) or []
        tracks_text = track_listing(my, self.ff.ffmpeg, cache=USER_DIR / "cache" / "music_features.json") \
            if len(my) > 1 else ""
        key = text_hash(listing, json.dumps(self.plan_long.get("music") or {}, ensure_ascii=False), tracks_text,
                        "music-v2")
        cache = read_json(self.work / "music.json", {})
        sheet: dict = {}
        if cache.get("key") == key and cache.get("sheet"):
            sheet = cache["sheet"]
            self._log_file_only("   (🎼 큐 시트: 이전 결과 사용)")
        else:
            studio = self._ensure_studio() if (self._use_api() and self.spec.studio_mode) else None
            if studio is not None:
                b = dict(brief, music=self.plan_long.get("music") or {}, chapters=self.plan_long.get("chapters", []))
                try:
                    raw = studio.score(listing, b, tracks=tracks_text)
                    sheet = clean_music(raw, kept_ids)
                    sheet["by"] = "ai"
                    names = {p.name: p for p in getattr(self, "_my_tracks", []) or []}
                    if tracks_text and str(raw.get("track") or "") in names:
                        sheet["track"] = str(raw["track"])
                        sheet["track_reason"] = str(raw.get("track_reason") or "")[:200]
                    elif tracks_text:
                        sheet["track"] = ""         # 맞는 곡이 없다 — 아무 곡이나 쓰지 않는다
                except DirectorError as e:
                    self.log(f"🎼 음악 감독 실패 → 규칙 큐 시트: {e}")
            if not sheet:
                ch_segs = [c["seg"] for c in self.plan_long.get("chapters", []) or [] if c.get("seg") in kept_ids]
                seg_t = seg_edit_times([u for u in self.utts if u.kept], self.timemap)
                tail = [i for i in kept_ids if i in seg_t and seg_t[i][0] <= self.timemap.duration - 20.0]
                sheet = clean_music(fallback_music(ch_segs, self.plan_long.get("title_card_seg", -1),
                                                   kept_ids[-1] if kept_ids else -1,
                                                   reprise_seg=tail[-1] if tail else None), kept_ids)
                sheet["by"] = "rule"
            write_json(self.work / "music.json", {"key": key, "sheet": sheet})
        self._music = sheet
        if "track" in sheet:
            names = {p.name: p for p in getattr(self, "_my_tracks", []) or []}
            if sheet["track"] in names:
                self.spec.bgm = str(names[sheet["track"]])
                self.log(f"🎼 배경음악(음악 감독 선택): 「{names[sheet['track']].stem}」"
                         + (f" — {sheet['track_reason']}" if sheet.get("track_reason") else ""))
            else:
                self.spec.bgm = ""
                self.spec.music = False
                self.log("🎼 내 음악 폴더에 이 영상에 맞는 곡이 없다고 판단 → 배경음악 없이(아무 곡이나 쓰지 않는다)")
        n = len(sheet.get("cues") or [])
        self.log(f"🎼 큐 시트({'음악 감독' if sheet.get('by') == 'ai' else '규칙'}): {sheet.get('suite', '')} · 큐 {n}개 · "
                 f"침묵 {len(sheet.get('silences') or [])}곳 · 맞는 정도 {sheet.get('fit_score', '-')}/10")
        return sheet

    def _long_music_cues(self, sheet: dict, total: float) -> tuple[list[dict], list[tuple[float, float]]]:
        """큐 시트 → 롱폼 최종 시각(오프닝 하이라이트만큼 민다)의 큐. 홀드·강도 3 순간은 침묵(큐보다 우선)."""
        hd = self.hl_duration
        seg_t = {k: (a + hd, b + hd) for k, (a, b) in seg_edit_times([u for u in self.utts if u.kept], self.timemap).items()}
        chs = [float(c["start"]) for c in (getattr(self, "long_props", {}) or {}).get("chapters") or []]
        holds = [(a + hd, b + hd) for a, b in self._hold_spans()]
        strong = [(mo.t + hd, mo.end + hd) for mo in self._moments(self.timemap) if mo.intensity >= 3]
        cues, silences = resolve_cues(sheet, seg_t, total, chapter_starts=chs, holds=holds, strong=strong)
        if hd > 0 and cues and cues[0].start <= hd + 0.5 and sheet.get("cues") and sheet["cues"][0]["start_seg"] == -1:
            cues[0].start = 0.0               # 첫 큐가 맨 앞에서 시작하면 하이라이트부터
        return plan_cues(cues), silences

    # ------------------------------------------------------------------
    def stage_qa(self) -> None:
        """🧐 아트 디렉터: 실제 렌더된 스틸만 보고 검수(블라인드) → 계획 패치 → 필요하면 한 번 더."""
        rounds = max(0, int(self.spec.qa_rounds or 0))
        if not self.spec.make_long or rounds == 0:
            return
        studio = self._ensure_studio()
        if studio is None:
            self.log("🧐 아트 디렉터 검수 건너뜀(Claude Code 또는 API 키 필요)")
            return
        gkey = lambda: text_hash([{k: v for k, v in g.items() if k != "reason"} for g in self.plan_long["graphics"]],
                                 "qa-v2")
        if self.plan_long.get("qa", {}).get("key") == gkey():
            self.log("🧐 검수: 이전 검수 결과 사용(그래픽 변경 없음)")
            return
        links = self._prepare_render()
        node = find_node(self.settings.node_path)
        rs = self.settings.render
        changed: Optional[list[dict]] = None
        escalated: list[dict] = []
        for rnd in range(1, rounds + 1):
            self.cancel.check()
            graphics, chapters = self._timed_long()
            lp, _ = self._final_long_props(graphics, chapters)
            props_path = self.render_dir / "props_qa.json"
            write_json(props_path, lp)
            gl = self.plan_long["graphics"]
            by_id = {f"g{i}": g for i, g in enumerate(gl)}
            want_ids = None if changed is None else {f"g{gl.index(g)}" for g in changed if g in gl}
            targets = [g for g in graphics if g.id in by_id and (want_ids is None or g.id in want_ids)]
            order = {"motion": 0, "broll": 1, "photo": 3}
            targets.sort(key=lambda g: (order.get(g.template, 2), g.start))
            targets = sorted(targets[:12], key=lambda g: g.start)
            if not targets:
                break
            qa_dir = self.work / "qa" / f"r{rnd}"
            shutil.rmtree(qa_dir, ignore_errors=True)
            qa_dir.mkdir(parents=True, exist_ok=True)
            frames = [(int(self._settle_time(g) * self.fps), qa_dir / f"{g.id}.jpg") for g in targets]
            n_main = len(frames)
            # 움직임 스트립(docs/upgrade/06c 6-1): 모션 장면·자유 카드는 +0.5초 · 15% · 40% · 안착 · 사건 · 퇴장 직전 여섯 장
            strips: dict[str, list[tuple[float, Path]]] = {}
            (qa_dir / "strip").mkdir(exist_ok=True)
            for g in targets:
                if g.template in ("motion", "card") and g.end - g.start > 1.5:
                    for k, t in enumerate(qa_strip_times(g, self._settle_time(g))):
                        sp = qa_dir / "strip" / f"{g.id}_{k}.jpg"
                        frames.append((int(t * self.fps), sp))
                        strips.setdefault(g.id, []).append((t - g.start, sp))
            if rnd == 1:
                for j, t in enumerate(self._caption_moments(lp, graphics)):
                    frames.append((int(t * self.fps), qa_dir / f"captions{j + 1}.jpg"))
            self.log(f"🧐 검수 {rnd}라운드: 스틸 {len(frames)}장 렌더")
            item = RenderItem("frames", "LongForm", props_path, qa_dir / "frames", scale=0.6, frames=frames)
            job = RenderJob(public_dir=self.public, bundle_dir=self.render_dir / "bundle", links=links, items=[item],
                            browser_executable=rs.browser_executable, gl=rs.gl, concurrency=rs.concurrency,
                            reuse_bundle=True)
            base = (rnd - 1) / rounds
            run_render(job, self.render_dir / "job_qa.json", node=node, log=self.log, cancel=self.cancel,
                       progress=lambda f: self._stage("qa", base + 0.5 * f / rounds),
                       on_peek=lambda ev, r=rnd: self._preview(
                           ev["file"], f"🧐 아트 디렉터 검수 {r}라운드 · 장면 {ev.get('k', '')}/{ev.get('n', '')}"))
            main = [p for _, p in frames[:n_main]] + [p for _, p in frames if p.stem.startswith("captions")]
            stills = [(p.stem, p.read_bytes(), "image/jpeg") for p in main if p.exists()]
            for gid, items in strips.items():
                sheet = qa_strip_sheet(items, qa_dir / f"{gid}_seq.jpg")
                if sheet:
                    stills.append((f"{gid}#seq", sheet.read_bytes(), "image/jpeg"))
            phone = qa_phone_sheet([(p.stem, p) for p in main if p.exists() and not p.stem.startswith("captions")],
                                   qa_dir / "phone.jpg")
            try:
                res = studio.review(self.ctx, self._qa_text(targets, lp),
                                    stills + ([("phone", phone.read_bytes(), "image/jpeg")] if phone else []))
            except DirectorError as e:
                self.log(f"🧐 검수 실패 → 그대로 진행: {e}")
                break
            issues = qa_actionable(res.get("issues", []) or [])
            escalated += [i for i in res.get("issues", []) or [] if i.get("action") == "escalate_edit"]
            self.log(f"🧐 {res.get('verdict', '')}: {res.get('summary', '')}")
            for i in issues:
                self.log(f"🧐 {i.get('target')} [{i.get('severity')}] {i.get('problem')} → {i.get('action')}")
            still_by_id = {s[0]: s for s in stills}
            changed = self._apply_qa(issues, by_id, {g.id: g for g in graphics}, still_by_id, studio)
            self.qa_log.append({"round": rnd, "verdict": res.get("verdict"), "summary": res.get("summary", ""),
                                "issues": res.get("issues", []), "applied": len(changed)})
            self._stage("qa", rnd / rounds)
            if res.get("verdict") == "pass" or not changed:
                break
        self.plan_long["qa"] = {"key": gkey(), "rounds": self.qa_log}
        self._save_plan()
        self._qa_escalate(escalated)

    def _qa_escalate(self, items: list[dict]) -> None:
        """🧐 아트 디렉터가 그래픽으로 풀 수 없다고 올린 편집·컷·음향·원본 문제(escalate_edit, docs/upgrade/08 7절):
        기록하고(리포트·work/gate_feedback.json — 게이트가 놓친 것), blocking 이면 게이트 A 를 다시 돌려 통과하지 못하면 멈춘다."""
        if not items:
            return
        for i in items:
            self.log(f"🧐 편집 지적({i.get('scope') or 'edit'}{' · 막음' if i.get('blocking') else ''}) "
                     f"{i.get('check', '')} {i.get('problem', '')} → {i.get('direction', '')}")
        fb = [{"from": "art_director", "gate": "A", "check": i.get("check", ""), "scope": i.get("scope", ""),
               "blocking": bool(i.get("blocking")), "problem": i.get("problem", ""), "direction": i.get("direction", "")}
              for i in items]
        old = read_json(self.work / "gate_feedback.json", [])
        write_json(self.work / "gate_feedback.json", (old if isinstance(old, list) else []) + fb)
        self.results["qa_escalations"] = fb
        if any(i.get("blocking") for i in items):
            self._gate_record(self._cut_checks(), "아트 디렉터 편집 지적")

    def _settle_time(self, g: TimedGraphic) -> float:
        """진입 애니메이션이 끝나 화면이 '정지'한 순간(움직이는 중간 프레임을 결함으로 오판하지 않도록)."""
        dur = g.end - g.start
        if g.template == "motion" and isinstance(g.data.get("spec"), dict):
            t = spec_settle_time(g.data["spec"]) + 0.3
        elif g.template == "card" and isinstance(g.data.get("card"), dict):
            t = card_settle_time(g.data["card"]) + 0.3
        elif g.template in ("list", "process", "cycle", "timeline", "pyramid", "compare", "matrix", "double_diamond"):
            t = dur * 0.75
        else:
            t = min(1.8, dur * 0.6)
        return g.start + max(0.5, min(t, dur - 0.35))

    def _caption_moments(self, lp: dict, graphics: list[TimedGraphic], n: int = 2) -> list[float]:
        busy = [(g.start - 0.5, g.end + 0.5) for g in graphics]
        cands = [(c["start"] + c["end"]) / 2 for c in lp.get("captions", [])
                 if c["end"] - c["start"] > 1.2 and not any(a <= (c["start"] + c["end"]) / 2 <= b for a, b in busy)]
        cands = [t for t in cands if t > 8]
        if not cands:
            return []
        step = max(1, len(cands) // (n + 1))
        return [cands[min(len(cands) - 1, step * (k + 1))] for k in range(n)]

    def _qa_text(self, targets: list[TimedGraphic], lp: dict) -> str:
        lines = []
        for g in targets:
            d = g.data
            content = " / ".join(x for x in [d.get("title") or "", d.get("body") or "",
                                              ", ".join(map(str, d.get("items") or []))] if x)
            if g.template == "motion":
                content = (d.get("title") or "") + " (모션 장면)"
            if g.template == "card" and isinstance(d.get("card"), dict):
                content = f"{d.get('title') or ''} (HTML 카드 · {d['card'].get('style') or 'card'}): {card_text(d['card'])[:90]}"
            if g.template == "broll":
                content = f"스톡 {d.get('kind', '')}: {d.get('title', '')}"
            if g.template == "photo" and d.get("logo"):
                content = f"브랜드 로고: {d.get('title', '')}"
            spoken = " ".join(w["text"] for c in lp.get("captions", []) for line in c["lines"] for w in line
                              if g.start - 0.3 <= w["start"] <= g.end)
            lines.append(f"- {g.id} · {g.template} · {g.layout} · {g.end - g.start:.1f}초 · 내용: {content[:120]}"
                         f" · 그 구간 발화: \"{spoken[:140]}\"")
        lines.append("- captions1, captions2 · 그래픽 없는 구간의 자막(프리셋 "
                     f"{lp.get('captionPreset', '')})")
        return "\n".join(lines)

    def _apply_qa(self, issues: list[dict], by_id: dict[str, dict], timed: dict[str, TimedGraphic],
                  stills: dict[str, tuple], studio: Studio) -> list[dict]:
        changed: list[dict] = []
        drop: list[dict] = []
        for iss in issues:
            g = by_id.get(str(iss.get("target", "")))
            if g is None:
                continue
            act = iss.get("action")
            if act == "drop":
                drop.append(g)
            elif act == "shorten_text":
                if iss.get("new_title"):
                    g["title"] = iss["new_title"]
                if iss.get("new_body"):
                    g["body"] = iss["new_body"]
                if iss.get("new_items"):
                    g["items"] = [str(x) for x in iss["new_items"]][:8]
                changed.append(g)
            elif act == "change_layout" and iss.get("new_layout") in TEMPLATES[g["template"]].layouts:
                g["layout"] = iss["new_layout"]
                changed.append(g)
            elif act == "revise_scene" and g["template"] == "motion":
                tg = timed.get(str(iss["target"]))
                dur = (tg.end - tg.start) if tg else 8.0
                try:
                    new = studio.revise_scene(self.ctx, g.get("spec") or {}, dur, iss.get("problem", ""),
                                              iss.get("direction", ""), stills.get(str(iss["target"])))
                except DirectorError as e:
                    self.log(f"🎨 수정 실패: {e}")
                    new = None
                if new:
                    g["spec"] = new
                    changed.append(g)
            elif act == "revise_card" and g["template"] == "card":
                tg = timed.get(str(iss["target"]))
                dur = (tg.end - tg.start) if tg else 8.0
                try:
                    new = studio.revise_card(self.ctx, g.get("card") or {}, dur, iss.get("problem", ""),
                                             iss.get("direction", ""), stills.get(str(iss["target"])), layout=g["layout"])
                except DirectorError as e:
                    self.log(f"🃏 카드 수정 실패: {e}")
                    new = None
                if new:
                    g["card"] = new
                    changed.append(g)
        if drop:
            self.plan_long["graphics"] = [g for g in self.plan_long["graphics"] if not any(g is d for d in drop)]
            self.log(f"🧐 그래픽 {len(drop)}개 삭제")
        return [g for g in changed if not any(g is d for d in drop)]

    # ------------------------------------------------------------------
    def _episode(self) -> Episode:
        return Episode(self.title, self.spec.episode, self.spec.subtitle, self.spec.series)

    def _timed_long(self) -> tuple[list[TimedGraphic], list[dict]]:
        tm = self.timemap
        total = tm.duration
        seg_t = seg_edit_times(self.utts, tm)
        chapters = []
        for i, c in enumerate(sorted(self.plan_long["chapters"], key=lambda c: c["seg"])):
            if c["seg"] not in seg_t:
                continue
            start = 0.0 if not chapters else seg_t[c["seg"]][0]
            chapters.append({"start": round(start, 3), "title": c["title"], "number": f"{len(chapters) + 1:02d}",
                             "claim": c.get("claim", "")})
        reserved: list[TimedGraphic] = []
        tseg = self.plan_long.get("title_card_seg", -1)
        t_title = seg_t[tseg][0] if tseg in seg_t else 0.2
        t_title = max(0.2, t_title - 0.1)
        reserved.append(TimedGraphic("title", "title", "fullscreen", t_title, min(total, t_title + 3.4),
                                     {"title": self.title}, priority=12, source="auto"))
        for c in chapters[1:]:
            if c["start"] < t_title + 4:
                continue
            # 챕터 카드 부제 = 그 챕터의 주장 한 문장(총괄 감독 claim) — 시청자가 '지금 무슨 이야기인지' 바로 안다
            reserved.append(TimedGraphic(f"ch{c['number']}", "chapter", "fullscreen", max(0.0, c["start"] - 0.1),
                                         min(total, c["start"] + (3.2 if c.get("claim") else 2.6)),
                                         {"title": c["title"], "number": c["number"], "subtitle": c.get("claim", "")},
                                         priority=11, source="auto"))
        graphics = time_graphics(self.plan_long["graphics"], self.utts, tm, total=total, reserved=reserved)
        graphics = self._respect_holds(graphics)
        # 편집 감독이 콜아웃을 붙인 강조 순간은 '오늘의 주제'보다 우선 — 그 자리를 비워 둔다(같은 빈 자리를 다툰다)
        callouts = [(m.t - 0.5, m.end + 0.5) for m in self._moments(tm)
                    if m.callout and m.intensity >= 2]
        lower = self._lower_third(graphics, after=min(total, t_title + 3.4), total=total,
                                  avoid=callouts + self._hold_spans())
        if lower is not None:
            graphics = sorted(graphics + [lower], key=lambda g: g.start)
        kept: list[TimedGraphic] = []
        for g in graphics:
            g.end = min(g.end, total - 0.1)
            if g.end - g.start >= 1.5:
                kept.append(g)
        return kept, chapters

    def _rhythm_spans(self, seg_t: dict[int, tuple[float, float]]) -> list[tuple[float, float, str]]:
        """편집 감독의 rhythm(발화 범위 → slow·steady·fast) → 편집 시각 구간."""
        out = []
        for r in self.plan_long.get("rhythm", []) or []:
            ids = [i for i in seg_t if r["start_seg"] <= i <= r["end_seg"]]
            if ids:
                out.append((min(seg_t[i][0] for i in ids), max(seg_t[i][1] for i in ids), r["level"]))
        return out

    def _hold_spans(self, tag_spans: Optional[list[tuple[float, float]]] = None) -> list[tuple[float, float]]:
        """🙂 편집 감독의 holds → 본편 편집 시각 구간(끝에 hold_pad 1.5초, 한 곳 최대 25초). 대본 태그 그래픽과 겹치면
        홀드를 그 태그 앞까지 줄인다(태그는 명령). docs/upgrade/05 4-3."""
        tm = getattr(self, "timemap", None)
        if tm is None:
            return []
        if tag_spans is None:
            tag_spans = getattr(self, "_tag_spans", [])
        seg_t = seg_edit_times([u for u in self.utts if u.kept], tm)
        out: list[tuple[float, float]] = []
        for h in self.plan_long.get("holds", []) or []:
            ids = [i for i in seg_t if h["start_seg"] <= i <= h["end_seg"]]
            if not ids:
                continue
            a = min(seg_t[i][0] for i in ids)
            b = min(max(seg_t[i][1] for i in ids) + PARAMS["hold_pad"], a + PARAMS["hold_max"], tm.duration)
            for x, y in sorted(tag_spans):
                if x < b and y > a:
                    b = min(b, x - 0.3) if x > a else a
            if b - a >= 3.0:
                out.append((round(a, 3), round(b, 3)))
        # 홀드끼리 hold_gap(20초) 안에 잇달으면 뒤 것을 뺀다 — 한 곳 25초 이하라는 전제는 홀드가 떨어져 있을 때만 A7 과 안 부딪친다
        # (2026-10-03: 04:47–05:03 · 05:12–05:26 · 05:36–05:46 셋이 이어져 얼굴만 71초, 보충 카드는 홀드를 피해 못 채움)
        kept: list[tuple[float, float]] = []
        gone: list[tuple[float, float]] = []
        for a, b in sorted(out):
            if kept and a < kept[-1][1] + PARAMS["hold_gap"]:
                gone.append((a, b))
            else:
                kept.append((a, b))
        self._holds_dropped = gone
        return kept

    def _respect_holds(self, graphics: list[TimedGraphic]) -> list[TimedGraphic]:
        """홀드 안에서 시작하는 그래픽은 뺀다(대본 태그는 남고 홀드가 줄어든다), 홀드로 들어가는 그래픽은 홀드 앞에서 끝낸다."""
        self._tag_spans = [(g.start, g.end) for g in graphics if g.source == "tag"]
        holds = self._hold_spans(self._tag_spans)
        if not holds:
            return graphics
        out: list[TimedGraphic] = []
        dropped = 0
        shifted: list[tuple[TimedGraphic, float]] = []
        for g in graphics:
            if g.source == "tag" or g.template in ("title", "chapter"):
                out.append(g)
                continue
            hit = next(((a, b) for a, b in holds if g.start < b and g.end > a), None)
            if hit is None:
                out.append(g)
                continue
            a, b = hit
            min_d = TEMPLATES[g.template].min_dur if g.template in TEMPLATES else 1.5
            if g.start < a and a - 0.2 - g.start >= min_d * 0.8:
                g.end = a - 0.2
                out.append(g)
            elif g.template in EVIDENCE_TEMPLATES and g.end - (b + 0.05) >= min_d * 0.8:
                # 실물 자료(사진·스톡·증거)는 버리지 않고 홀드가 끝난 뒤로 민다 — 얼굴보다 자료(디자인 v3). 홀드 꼬리 여유(1.5초)
                # 안에서 시작하던 스톡 영상이 통째로 빠지던 것
                g.start = b + 0.05
                out.append(g)
                shifted.append((g, min_d))
            else:
                dropped += 1
        moved = 0
        for g, min_d in shifted:       # 옮긴 자료가 다음 그래픽을 덮지 않게 — 짧아지면 뺀다
            nxt = min((o.start for o in out if o is not g and o.start >= g.start), default=float("inf"))
            if g.end > nxt - 0.2:
                g.end = nxt - 0.2
            if g.end - g.start < min_d * 0.8:
                out.remove(g)
                dropped += 1
            else:
                moved += 1
        gone = getattr(self, "_holds_dropped", [])
        if dropped or moved or gone:
            self.log(f"🙂 얼굴 홀드 {len(holds)}곳(" + " · ".join(f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in holds)
                     + f") — 그 안의 그래픽 {dropped}개를 뺌" + (f" · 실물 자료 {moved}개는 홀드 뒤로 옮김" if moved else "")
                     + (f" · 앞 홀드와 {PARAMS['hold_gap']:.0f}초 안이라 뺀 홀드 {len(gone)}곳("
                        + " · ".join(f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in gone) + ")" if gone else ""))
        return sorted(out, key=lambda g: g.start)

    def _lower_third(self, graphics: list[TimedGraphic], *, after: float, total: float,
                     avoid: Optional[list[tuple[float, float]]] = None) -> Optional[TimedGraphic]:
        """타이틀 뒤 화자 이름 + '오늘의 주제'(레퍼런스 채널 레퍼런스: 이 영상이 답할 질문을 5~6초 한 줄로 — 총괄 감독의 논지).
        얼굴만 보이는 첫 빈 자리(타이틀 뒤 60초 안, 4초 이상)에 둔다 — 예전엔 자리를 미리 잡아 두었다가 바로 뒤 그래픽에 밀려
        대개 빠졌다. 말에 맞춘 그래픽과 콜아웃 강조 순간(avoid)을 밀어내지 않으므로 빈 자리가 없으면 넣지 않는다."""
        topic = topic_line(self.plan_long.get("summary", ""))
        want, need = (5.6, 4.0) if topic else (4.5, 3.0)
        t = after + 0.8
        for a, b in sorted([(g.start, g.end) for g in graphics if g.end > after] + [(total - 0.3, total)]
                           + [(x, y) for x, y in (avoid or []) if y > after]):
            if t > after + 60.0:
                return None
            if a - 0.3 - t >= need:
                return TimedGraphic("lower", "lower_third", "overlay", round(t, 3), round(min(t + want, a - 0.3), 3),
                                    {"subtitle": "오늘의 주제", "title": topic} if topic else {}, priority=4,
                                    source="auto")
            t = max(t, b + 0.6)
        return None

    def _prepare_render(self) -> list[tuple[Path, str]]:
        """폰트·그레인 준비 + 번들 public 에 연결할 큰 미디어 목록(한 번만)."""
        if self._render_prep is not None:
            return self._render_prep
        copy_fonts(self.public / "fonts")
        self._grain = make_grain(self.public / "fx") if self.spec.grain else []
        self._paper = make_paper(self.public / "fx") if self.spec.skin != "classic" else ""
        links: list[tuple[Path, str]] = [(self.media / Path(c.proxy).name, c.proxy) for c in self.smap.cams] \
            or [(self.media / "proxy.mp4", "media/proxy.mp4")]
        self._render_prep = links
        return links

    def _caption_presets(self) -> tuple[str, str]:
        """기본은 사용자 템플릿 자막(흰 종이 박스 · 핵심어 굵게) — 따로 고르지 않았으면 롱폼·숏폼 모두."""
        lp = self.spec.caption_preset if self.spec.caption_preset != "auto" else "paper"
        sp = self.spec.short_caption_preset if self.spec.short_caption_preset != "auto" else "paper"
        return lp, sp

    def _edit_onsets(self, tm: TimeMap) -> list[float]:
        """말소리 시작(VAD) → 편집 시간. 자막 시작을 여기에 맞춘다."""
        import bisect
        out = [tm.edit_span_of(i).start + 0.06 for i in range(len(tm.keeps))]
        # keep 을 원본 시각 순으로 한 번 정렬해 두고 이분 탐색(숏폼은 순서가 바뀌기도 함) — 긴 영상에서 VAD × keep 이중 반복이 느림
        order = sorted(range(len(tm.keeps)), key=lambda i: tm.keeps[i].start)
        starts = [tm.keeps[i].start for i in order]
        for a, _ in getattr(self, "vad", []) or []:
            j = bisect.bisect_left(starts, a) - 1
            while j >= 0 and tm.keeps[order[j]].end > a:     # 겹치는 keep(숏폼)까지
                i = order[j]
                if tm.keeps[i].start < a:
                    out.append(tm.edit_span_of(i).start + (a - tm.keeps[i].start))
                j -= 1
        return sorted(set(round(x, 3) for x in out))

    def _short_graphics(self, s: dict[str, Any]) -> list[dict[str, Any]]:
        """숏폼 그래픽 = 숏폼 기획의 그래픽 + 이 구간에 있던 롱폼 그래픽(도식·사진·스톡·모션). 예전엔 숏폼 기획의 0~3개뿐이라
        같은 도식이 13초씩 떠 있거나 아무것도 없었다."""
        segs = set(s["segments"])
        out = [dict(g) for g in s.get("graphics", [])]
        have = {(g.get("template"), g.get("start_seg")) for g in out}
        for g in self.plan_long.get("graphics", []) or []:
            if g.get("template") in ("chapter", "title", "lower_third") or g.get("start_seg") not in segs:
                continue
            if g.get("template") == "broll" and not g.get("src"):
                continue
            k = (g.get("template"), g.get("start_seg"))
            if k not in have:
                have.add(k)
                c = short_retype(g)
                if c is not None:
                    out.append(c)
        return out

    def _punch_spans(self, seg_t: dict[int, tuple[float, float]], segs: Optional[set[int]] = None) -> list[tuple[float, float]]:
        """⚡ 편집 감독의 energy_spans(발화 ID 범위) → 편집 시각 구간. 합쳐서 전체의 25% 를 넘으면 앞에서부터 자른다."""
        out: list[tuple[float, float]] = []
        total = max(0.0, *[b for _, b in seg_t.values()]) if seg_t else 0.0
        budget = total * 0.25
        for e in self.plan_long.get("energy_spans", []) or []:
            ids = [i for i in range(int(e.get("start_seg", -1)), int(e.get("end_seg", -1)) + 1)
                   if i in seg_t and (segs is None or i in segs)]
            if not ids:
                continue
            a, b = min(seg_t[i][0] for i in ids), max(seg_t[i][1] for i in ids)
            if b - a <= 0.5:
                continue
            if sum(y - x for x, y in out) + (b - a) > budget:
                b = a + max(0.0, budget - sum(y - x for x, y in out))
                if b - a <= 0.5:
                    break
            out.append((round(a, 3), round(b, 3)))
        return out

    def _moments(self, tm: TimeMap, segs: Optional[set[int]] = None) -> list[Moment]:
        by_id = {u.id: u for u in self.utts}
        out = []
        for m in self.plan_long.get("moments", []) or []:
            u = by_id.get(m.get("seg"))
            if not u or not u.words or (segs is not None and u.id not in segs):
                continue
            t = word_edit_time(u, m.get("word", ""), tm) if m.get("word") else None
            if t is None:
                t = tm.src_to_edit(u.words[0].start, snap=True)
            end = tm.src_to_edit(u.words[-1].end, snap=True)
            if t is None or end is None:
                continue
            out.append(Moment(t=t, end=max(end, t + 0.4), kind=m.get("kind", "punchline"),
                              intensity=int(m.get("intensity", 2)), seg=u.id, word=m.get("word", ""),
                              callout=m.get("callout", ""), label=m.get("label", "")))
        return out

    @property
    def _hybrid(self) -> bool:
        return self.spec.skin in ("auto", "hybrid")

    def _angles(self, pieces: list[Piece], tm: TimeMap) -> tuple[Optional[list[dict]], list[dict], list[float]]:
        """(렌더 클립, 얼굴 트랙(가상 시각), 앵글이 바뀌는 편집 시각). 원본이 하나면 (None, 얼굴 트랙, [])."""
        if self.smap.single or not pieces:
            return None, self.face, []
        return (clips_for(pieces, tm, self.smap), face_track(pieces, self.smap, self.face_cams),
                angle_cut_times(pieces, tm))

    def _final_long_props(self, graphics: list[TimedGraphic], chapters: list[dict]) -> tuple[dict, EditDecisions]:
        """롱폼 props + 편집 문법 엔진 결과(카메라·소프트 컷·강조 글라이드·전환·콜아웃·강조 자막) + 화면 그래픽과
        같은 말인 자막 숨김. 음향은 따로 믹스. 원본이 여러 개면 클립은 앵글 조각대로."""
        self._prepare_render()
        clips, face_src, angle_cuts = self._angles(self.long_pieces, self.timemap)
        lp = long_props(fps=self.fps, brand=self.settings.brand, episode=self._episode(), utts=self.utts,
                        timemap=self.timemap, graphics=graphics, chapters=chapters, clips=clips,
                        emphasis=self.plan_long.get("emphasis", []), face_src=face_src,
                        voice_src="media/long_voice.wav", bgm_src=None, sfx={}, grain_frames=self._grain,
                        skin="classic" if self._hybrid else self.spec.skin, paper_texture=self._paper,
                        grain=0.05 if self._grain else 0.0, caption_preset=self._caption_presets()[0],
                        endcard=self.spec.endcard, use_sfx=False, speech_onsets=self._edit_onsets(self.timemap))
        # 자료 사진 바로 뒤(또는 안)의 키워드는 사진 위 키워드 슬램으로(사진이 어두워지며 큰 키워드)
        folded = fold_keywords_into_media(lp["graphics"])
        if folded:
            self.log(f"📸 자료 사진 위 키워드 슬램 {folded}개(사진이 이어진 채 어두워지며 키워드)")
        # 얼굴을 가리지 않게: 얼굴 옆 사진 액자·개념 텍스트는 빈 쪽으로, 자리가 없으면 화자 패널로
        ps = face_safe_layouts(lp["graphics"], lp["face"])
        if ps["placed"] or ps["to_split"]:
            self.log(f"🙂 얼굴 옆 배치: 액자·메모 {ps['placed']}개(줄임 {ps['shrunk']}, 위 소제목 바 {ps.get('top', 0)})"
                     f" · 자리가 없어 패널로 {ps['to_split']}개")
        # 사진·스톡 위 구도(채널 주인 2026-10-02): 이미지를 분석해 글자·칩은 빈 쪽, 얼굴은 잘리지 않게
        self._compose_plans = self._compose_media(lp["graphics"])
        seg_t = seg_edit_times(self.utts, self.timemap)
        punch_spans = self._punch_spans(seg_t)
        moments = self._moments(self.timemap)
        # 롱폼 무대 편집법: 챕터 카드에 목차, 챕터 끝에 그 챕터의 핵심 개념을 모은 정리 보드(7초) — 편집 감독이 얼굴로 힘을
        # 주는 강조 순간·펀치 구간은 덮지 않는다
        chapter_maps(lp["graphics"], lp["chapters"])
        holds = self._hold_spans()
        recaps = chapter_recaps(lp["graphics"], lp["chapters"], self.timemap.duration,
                                avoid=punch_spans + holds + [(m.t - 0.5, m.end + 0.5) for m in moments if m.intensity >= 2])
        if recaps:
            self.log("📋 챕터 정리 보드 " + " · ".join(
                f"{fmt_ts(g['start'])}–{fmt_ts(g['end'])} {len(g['data']['items'])}개" for g in recaps))
        looks = None
        if self._hybrid:
            by_id = {u.id: u for u in self.utts}

            def text_between(a: float, b: float) -> str:
                return " ".join(by_id[i].text for i, (s0, _) in seg_t.items() if a <= s0 < b and i in by_id)

            looks = choose_looks(lp["graphics"], lp["chapters"], self.timemap.duration, text_between)
            apply_looks(lp, looks)
            self.look_plan = looks
            self.log("🎨 화면 구성(자동 · 하이브리드): " + looks.summary())
        bridged = bridge_split_gaps(lp["graphics"])
        if bridged:
            self._log_file_only(f"   (판 사이 1초 미만 틈 {bridged}곳을 앞 그래픽으로 메움 — 화자가 줄어든 채 옆이 비지 않게)")
        if punch_spans:
            self.log("⚡ 펀치 구간(하드 펀치인·단어 슬램·휩·임팩트 허용): "
                     + " · ".join(f"{fmt_ts(a)}–{fmt_ts(b)}" for a, b in punch_spans))
        ed = build_long_edit(timemap=self.timemap, total=lp["duration"], speech_total=self.timemap.duration,
                             graphics=lp["graphics"], chapters=lp["chapters"], moments=moments,
                             cues=lp["captions"], sentence_starts=sorted(a for a, _ in seg_t.values()),
                             text_graphic_spans=text_graphic_spans(lp["graphics"]), endcard=self.spec.endcard,
                             face=lp.get("face"),
                             P=PARAMS if (self.spec.skin == "paper" or looks) else {**PARAMS, "framed_every": 0},
                             framed_ranges=looks.paper_ranges() if looks else None, angle_cuts=angle_cuts,
                             punch_spans=punch_spans, holds=holds, rhythm=self._rhythm_spans(seg_t))
        if self._sfx_mode() == "directed":
            # 🎬 효과음은 총괄 감독이 고른 곳에만(트리트먼트의 단락·시그니처 장면) — 규칙이 템플릿마다 뿌리지 않는다
            ed.sfx = directed_sfx(lp["graphics"], self._directed_segments(seg_t), holds=holds or [],
                                  speech_starts=sorted(a for a, _ in seg_t.values()), total=lp["duration"],
                                  auto=bool(getattr(self.settings, "sfx_motion_auto", True)), transitions=ed.transitions)
            ed.stats["sfx"] = len(ed.sfx)
        apply_edit(lp, ed)
        hid = dedupe_captions(lp["captions"], caption_overlays(lp))
        seq_types = {q["id"]: q["type"] for q in self.plan_long.get("sequences", []) or []}
        hid += hide_over(lp["captions"], high_load_spans(lp, seq_types))
        n_seq = mark_sequences(lp, seq_types)
        if n_seq:
            self.log(f"🎞 시퀀스 {n_seq}개 — 같은 틀 안의 컷으로(둘째 샷부터 등장 애니메이션 없음)")
        stacks = mark_stack_cues(lp["captions"], min_gap=18.0, avoid=stack_avoid_spans(lp))
        self.log(f"💬 자막: 한두 마디 {len(lp['captions'])}개 · 두 층 강조 {stacks}개"
                 + (f" · 화면 그래픽과 같은 말이라 숨김 {hid}개(SRT 에는 남김)" if hid else ""))
        strip_audio(lp)
        return lp, ed

    def _add_highlight(self, lp: dict, ed: EditDecisions) -> float:
        """🎬 오프닝 하이라이트를 본편 props·편집 결정 앞에 붙인다(본편은 그만큼 뒤로). 하이라이트 자체도 편집 문법 엔진을
        거친다(펀치 구간 = 전체: 조각마다 하드 펀치인·큰 자막·휩) → 그 구간의 그래픽·자막·얼굴 트랙 그대로, 마지막에 빛샘
        전환으로 타이틀(본편 처음)로. 반환: 하이라이트 길이(없으면 0)."""
        tm = self.hl_map
        if tm is None or not (self.media / "long_voice_full.wav").exists():
            return 0.0
        segs = set(self.hl_segs)
        plan_g = self.plan_long.get("graphics", []) or []
        subset = [(i, g) for i, g in enumerate(plan_g)
                  if g.get("start_seg") in segs and g.get("template") not in ("chapter", "title", "lower_third")]
        seg_t = seg_edit_times([u for u in self.utts if u.id in segs], tm)
        timed = time_graphics([g for _, g in subset], self.utts, tm, total=tm.duration, min_start=0.2, id_prefix="h")
        # 그래픽은 자기 문장 조각 안에서만(읽기 시간으로 다음 조각까지 늘어나면 다른 문장 위에 남는다)
        kept_t: list[TimedGraphic] = []
        for g in timed:
            k = int(g.id[1:]) if g.id[1:].isdigit() else -1
            sid = subset[k][1].get("start_seg") if 0 <= k < len(subset) else None
            if sid in seg_t:
                g.end = min(g.end, seg_t[sid][1] + 0.15)
            if g.end - g.start >= 1.5:
                kept_t.append(g)
        timed = kept_t
        clips, face_src, angle_cuts = self._angles(self.hl_pieces, tm)
        hp = long_props(fps=self.fps, brand=self.settings.brand, episode=self._episode(), utts=self.utts, timemap=tm,
                        graphics=timed, chapters=[], clips=clips, emphasis=self.plan_long.get("emphasis", []),
                        face_src=face_src, voice_src="", bgm_src=None, sfx={}, grain_frames=[],
                        skin=lp.get("skin", "classic") if lp.get("skin") != "hybrid" else "classic",
                        paper_texture=self._paper, grain=0.0, caption_preset=lp.get("captionPreset", "paper"),
                        endcard=False, use_sfx=False, speech_onsets=self._edit_onsets(tm))
        # 스킨은 본편에서 같은 그래픽이 받은 것을 따른다(하이브리드)
        by_main = {g["id"]: g for g in lp.get("graphics", [])}
        for g in hp["graphics"]:
            k = int(g["id"][1:]) if g["id"][1:].isdigit() else -1
            src = by_main.get(f"g{subset[k][0]}") if 0 <= k < len(subset) else None
            g["skin"] = src["skin"] if src and src.get("skin") else "classic"
        face_safe_layouts(hp["graphics"], hp["face"])
        self._compose_media(hp["graphics"])
        # 조각마다 강조 순간 하나(트레일러 느낌: 펀치인 + 큰 자막). 편집 문법 엔진은 분할 패널·전체화면 그래픽 ±0.4초 안의
        # 강조를 버리므로, 그 조각의 그래픽이 끝난 뒤(또는 조각 시작 0.5초 뒤)로 옮겨 놓는다
        planned = {m.seg: m for m in self._moments(tm, segs)}
        moments: list[Moment] = []
        for sid, (a, b) in seg_t.items():
            t = a + 0.5
            for g in hp["graphics"]:
                if g.get("layout") in ("split", "fullscreen") and g["start"] < b and g["end"] > a:
                    t = max(t, g["end"] + 0.45)
            if b - t < 0.6:
                continue
            m = planned.get(sid)
            moments.append(Moment(t=round(t, 3), end=round(b, 3), kind=m.kind if m else "punchline",
                                  intensity=max(2, m.intensity) if m else 2, seg=sid, word="",
                                  callout="", label=""))
        hd = tm.duration
        ed_h = build_long_edit(timemap=tm, total=hp["duration"], speech_total=hd, graphics=hp["graphics"], chapters=[],
                               moments=moments, cues=hp["captions"], sentence_starts=sorted(a for a, _ in seg_t.values()),
                               text_graphic_spans=text_graphic_spans(hp["graphics"]), endcard=False, face=hp.get("face"),
                               P={**PARAMS, "framed_every": 0}, angle_cuts=angle_cuts, punch_spans=[(0.0, hd)], seed=7)
        if self._sfx_mode() == "directed":
            ed_h.sfx = []             # 하이라이트에는 규칙 효과음을 뿌리지 않는다(본편으로 넘어가는 종이 소리 하나만 아래에서)
        apply_edit(hp, ed_h)
        dedupe_captions(hp["captions"], caption_overlays(hp))
        mark_stack_cues(hp["captions"], min_gap=4.0, avoid=stack_avoid_spans(hp))
        strip_audio(hp)
        # 본편을 뒤로 밀고 앞에 붙인다
        shift_props(lp, hd)
        shift_decisions(ed, hd)
        prepend_props(lp, hp)
        ed.sfx = list(ed_h.sfx) + ed.sfx
        ed.bgm_swells = list(ed_h.bgm_swells) + ed.bgm_swells
        ed.bgm_dips = list(ed_h.bgm_dips) + ed.bgm_dips
        ed.bgm_anchors = [round(hd, 3)] + ed.bgm_anchors        # 한 곡 그대로 — 곡이 끝났으면 본편 시작에서 다시
        # 하이라이트 → 본편(타이틀): 빛샘 전환 + 페이지 넘김 한 번(04c 6절 — 라이저는 팔레트에서 뺐다)
        fps = float(self.fps)
        lp["transitions"] = sorted(lp["transitions"] + [{"t": round(hd, 3), "type": "leak",
                                                         "dur": round(PARAMS["tx_frames"]["leak"] / fps, 3)}],
                                   key=lambda t: t["t"])
        ed.sfx.append({"t": round(max(0.0, hd - 0.15), 3), "category": "page_turn",
                       "gain_db": PARAMS["sfx_gain"].get("page_turn", -26), "prio": 5, "why": "하이라이트 → 본편"})
        ed.sfx.sort(key=lambda x: x["t"])
        ed.stats["highlight_sec"] = round(hd, 1)
        ed.stats["shots"] = len(lp["camera"])
        self.log(f"🎬 오프닝 하이라이트 {hd:.1f}초를 본편 앞에 붙임(그래픽 {len(hp['graphics'])} · 강조 "
                 f"{len(ed_h.punches)} · 자막 {len(hp['captions'])}) → 본편 시작 {fmt_ts(hd)}")
        return hd

    def stage_render(self) -> None:
        assert self.info
        links = self._prepare_render()
        items: list[RenderItem] = []
        rs = self.settings.render
        scale = max(1.0, self.spec.out_height / 1080)
        self.long_props: dict = {}
        self.masters = []
        raw_dir = self.render_dir / "raw"
        # 진행 화면 미리보기: 2초(영상 시간)마다 렌더된 프레임 한 장
        peek_dir = self.render_dir / "peek"
        shutil.rmtree(peek_dir, ignore_errors=True)
        peek_every = max(1, int(round(self.fps * 2)))
        labels: list[tuple[str, float]] = []   # items 와 같은 순서: (이름, 길이 초)
        # 🚦 게이트 B: 계획의 화면 글자(검색어·연출 메모·내부 이름)부터 비운다 — props 는 계획에서 나온다
        label_res = self._gate_labels([self.plan_long.setdefault("graphics", [])]
                                      + [s.setdefault("graphics", []) for s in self.plan_shorts], "계획")
        if self.spec.make_long:
            graphics, chapters = self._timed_long()
            self.long_chapters = chapters
            lp, ed = self._final_long_props(graphics, chapters)
            lp, ed = self._gate_screen(lp, ed)          # 🚦 게이트 A(화면): 그래픽 분포·맨얼굴·얼굴 비율·타이틀
            voice = self.media / "long_voice.wav"
            if self._add_highlight(lp, ed):
                voice = self.media / "long_voice_full.wav"
            label_res += self._gate_labels([lp["graphics"]], "롱폼 화면")
            self.long_props = lp
            lp["peekEvery"] = peek_every
            p = self.render_dir / "props_long.json"
            write_json(p, lp)
            raw = raw_dir / "long.mp4"
            items.append(RenderItem("video", "LongForm", p, raw, scale=scale, crf=rs.crf, x264_preset=rs.x264_preset,
                                    weight=lp["duration"], muted=True, peek_dir=str(peek_dir)))
            labels.append(("롱폼", lp["duration"]))
            self.masters.append({"name": "롱폼", "raw": raw, "voice": voice,
                                 "dst": self.out / f"1_롱폼_{self.slug}.mp4", "edit": ed, "total": lp["duration"],
                                 "moods": MOODS_LONG, "mood": self.plan_long.get("bgm_mood", ""), "short": False,
                                 "speech_end": round(self.timemap.duration + self.hl_duration, 3)})
            self.log(f"✂️ 롱폼 편집: 샷 {ed.stats['shots']} · 전환 {ed.stats['transitions']} · 강조 글라이드 "
                     f"{ed.stats['punches']} · 강조 자막 {ed.stats['impact_captions']} · 효과음 {ed.stats['sfx']}"
                     f" · 콜아웃 {ed.stats['callouts']} · 얼굴 화면 비율 {ed.stats['face_ratio'] * 100:.0f}%"
                     f" · 얼굴만 이어진 최장 {ed.stats['max_face_run']:.0f}초"
                     + (f"(25초 넘는 곳 {ed.stats['face_runs_over_25s']}곳)" if ed.stats['face_runs_over_25s'] else ""))
        self.short_props: list[dict] = []
        short_pieces = getattr(self, "short_pieces", []) or []
        for i, (s, tm) in enumerate(zip(self.plan_shorts, getattr(self, "short_maps", [])), 1):
            clips, face_src, angle_cuts = self._angles(short_pieces[i - 1] if i <= len(short_pieces) else [], tm)
            sg = time_graphics(self._short_graphics(s), self.utts, tm, total=tm.duration, min_start=3.0,
                               id_prefix=f"s{i}g")
            for g in sg:
                g.layout = "split"
            series = f"{self.spec.series} #{self.spec.episode}" if self.spec.episode else self.spec.series
            sp = short_props(fps=self.fps, brand=self.settings.brand, episode=self._episode(), spec=s, utts=self.utts,
                             timemap=tm, graphics=sg, face_src=face_src, clips=clips,
                             voice_src=f"media/short_{i}_voice.wav",
                             bgm_src=None, sfx={}, grain_frames=self._grain, grain=0.04 if self._grain else 0.0,
                             skin="hybrid" if self._hybrid else self.spec.skin, paper_texture=self._paper,
                             layout=self.spec.shorts_layout, progress_bar=self.spec.progress_bar,
                             series_label=series, caption_preset=self._caption_presets()[1],
                             extra_emphasis=self.plan_long.get("emphasis", []), speech_onsets=self._edit_onsets(tm))
            ed = build_short_edit(timemap=tm, total=sp["duration"], graphics=sp["graphics"], cues=sp["captions"],
                                  moments=self._moments(tm, set(s["segments"])), seed=i, angle_cuts=angle_cuts,
                                  punch_spans=self._punch_spans(seg_edit_times(self.utts, tm), set(s["segments"])))
            if self._sfx_mode() == "directed":
                # 숏폼도 감독이 고른 그래픽(시그니처 장면 등)에만
                ed.sfx = directed_sfx(sp["graphics"], [], total=sp["duration"],
                                      speech_starts=sorted(a for a, _ in seg_edit_times(self.utts, tm).values()),
                                      auto=bool(getattr(self.settings, "sfx_motion_auto", True)), transitions=ed.transitions)
            sp["camera"] = ed.camera
            sp["transitions"] = ed.transitions
            sp["punches"] = sorted(sp.get("punches", [])[:1] + ed.punches, key=lambda p: p["t"])
            mark_soft_cuts(sp["clips"], ed.camera, ed.transitions, ed.soft_cut)
            if self.spec.skin == "paper" or self.spec.shorts_layout == "reel":
                sp["beats"] = short_beats(s, self.utts, tm, sp["captions"], self._moments(tm, set(s["segments"])),
                                          sp["duration"])
            dedupe_captions(sp["captions"], caption_overlays(sp))
            mark_stack_cues(sp["captions"], min_gap=3.5, max_chars=12)
            strip_audio(sp)
            label_res += self._gate_labels([sp["graphics"]], f"숏폼 {i} 화면")
            sp["peekEvery"] = peek_every
            self.short_props.append(sp)
            p = self.render_dir / f"props_short_{i}.json"
            write_json(p, sp)
            name = slugify(s.get("title") or f"short{i}", 20)
            raw = raw_dir / f"short_{i}.mp4"
            items.append(RenderItem("video", "Short", p, raw, scale=1.0, crf=rs.crf, x264_preset=rs.x264_preset,
                                    weight=sp["duration"], muted=True, peek_dir=str(peek_dir)))
            labels.append((f"숏폼 {i}", sp["duration"]))
            self.masters.append({"name": f"숏폼 {i}", "raw": raw, "voice": self.media / f"short_{i}_voice.wav",
                                 "dst": self.out / f"{i + 1}_숏폼{i}_{name}.mp4", "edit": ed, "total": sp["duration"],
                                 "moods": MOODS_SHORT, "mood": self.plan_long.get("shorts_bgm_mood", ""),
                                 "short": True})
        self._gate_record(gate.combine(label_res), "화면 글자")
        if self.spec.thumbnails:
            thumbs = self._thumbnail_items()
            items += thumbs
            labels += [(f"썸네일 {k}", 0.0) for k in range(1, len(thumbs) + 1)]
        if not items:
            self.log("렌더할 항목이 없습니다.")
            return
        job = RenderJob(public_dir=self.public, bundle_dir=self.render_dir / "bundle", links=links, items=items,
                        browser_executable=rs.browser_executable, gl=rs.gl, concurrency=rs.concurrency,
                        reuse_bundle=True)
        node = find_node(self.settings.node_path)
        shown: dict[int, int] = {}

        def on_peek(ev: dict) -> None:
            i, fr = int(ev.get("index", -1)), int(ev.get("frame", 0))
            if not 0 <= i < len(labels) or fr < shown.get(i, -1):   # 동시 렌더로 순서가 섞여 오면 앞 프레임은 건너뜀
                return
            shown[i] = fr
            name, total = labels[i]
            self._preview(ev["file"], f"{name} 렌더링 · {fmt_ts(fr / self.fps)} / {fmt_ts(total)}" if total else name)

        self._start_mix_job()
        run_render(job, self.render_dir / "job.json", node=node, log=self.log, progress=self._sp("render"),
                   cancel=self.cancel, on_peek=on_peek)

    # ------------------------------------------------------------------
    def stage_master(self) -> None:
        """🎚 음향: 컷 편집된 목소리 + 배경음악(자동 덕킹) + 효과음 → -14 LUFS 마스터 → 영상과 합치기.
        믹스는 렌더하는 동안 미리 만들어 두었다(stage_render) — 여기서는 기다렸다가 영상과 합치기만."""
        job, self._mix_job = self._mix_job, None
        if job is not None:
            job.result()
        else:
            self._mix_all(progress=lambda f: self._stage("master", 0.8 * f))
        self._gate_sound()          # 🚦 게이트 D — D9(라이선스 미확인 음원)만 멈춘다
        n = len(self.masters)
        for k, m in enumerate(self.masters):
            self.cancel.check()
            mux_final(self.ff, m["raw"], m["mix"], m["dst"], log=self.log, cancel=self.cancel)
            self.log(f"🎚 {m['name']}: 효과음 {m['n_sfx']}개 · 배경음악 "
                     f"{m['bgm_title'] or '없음'} · -14 LUFS 마스터 → {m['dst'].name}")
            self._stage("master", 0.8 + 0.2 * (k + 1) / max(1, n))
        self.results["long"] = str(self.masters[0]["dst"]) if self.masters and not self.masters[0]["short"] else ""
        self.results["shorts"] = [str(m["dst"]) for m in self.masters if m["short"]]

    def _mix_all(self, progress: Callable[[float], None] = lambda f: None) -> None:
        """편집 결정(효과음 큐 · 음악 스웰/교체/비우기)대로 목소리 + 음악 + 효과음 → 마스터 WAV(m['mix'])."""
        lib = self._sound_lib(full=True) if (self.spec.sfx or (self.spec.music and not self.spec.bgm)) else None
        n = len(self.masters)
        for k, m in enumerate(self.masters):
            self.cancel.check()
            ed: EditDecisions = m["edit"]
            cues: list[SfxCue] = []
            attrs: set[str] = set()
            if lib is not None and self.spec.sfx:
                for j, e in enumerate(ed.sfx):
                    snd = lib.pick(e["category"], seed=j)
                    if snd is None or snd.source == "synth":     # 절차적으로 만든 효과음은 완성본에 쓰지 않는다
                        continue
                    if snd.license_class not in ("A", "A-sa", "B", "C"):   # 등급이 확인 안 된 효과음은 쓰지 않는다(D9)
                        continue
                    if snd.attribution:                          # CC BY 효과음 — 업로드 정보에 출처
                        attrs.add(snd.attribution)
                    cues.append(SfxCue(t=e["t"], path=str(snd.path), gain_db=e["gain_db"], peak=snd.peak,
                                       name=e["category"], fade_out=2.5 if e["category"] == "riser" else 0.0))
            bgm: Optional[BgmPlan] = None
            track = None
            sheet = getattr(self, "_music", None) or {}
            # 한 영상 한 곡, 숏폼은 롱폼 곡을 물려받는다(04 11절 2·5번) — 레벨은 목소리 실측 기준(롱 −20 · 숏 −18 LU)
            common = dict(swells=ed.bgm_swells, dips=ed.bgm_dips, rel_lu=-18.0 if m["short"] else -20.0,
                          short=m["short"], restart_at=list(getattr(ed, "bgm_anchors", []) or []),
                          fade_out=1.2 if m["short"] else 3.0, end_at=m.get("speech_end"))
            if self.spec.bgm and Path(self.spec.bgm).exists():
                bgm = BgmPlan(path=self.spec.bgm, **common)
            elif lib is not None and self.spec.music:
                if getattr(self, "_bgm_track", None) is None:
                    long_m = next((x for x in self.masters if not x["short"]), m)
                    self._bgm_track = lib.pick_bgm(long_m["moods"], wanted=long_m["mood"], min_duration=60,
                                                   seed=int(text_hash(str(self.dir)), 16) % 997)
                    if self._bgm_track is None:
                        self.log("🔊 맞는 무드의 배경음악이 없어 음악 없이 갑니다(아무 곡이나 고르지 않는다)")
                track = self._bgm_track
                if track is not None:
                    bgm = BgmPlan(path=str(track.path), lufs=track.lufs, start_offset=track.lead_silence, **common)
            if bgm is not None and sheet:
                bgm = self._apply_music_sheet(bgm, sheet, m)
            mix_wav = self.work / f"mix_{k}.wav"
            rep = mix(self.ff, m["voice"], mix_wav, total=m["total"], sfx=cues, bgm=bgm, log=self.log,
                      cancel=self.cancel)
            m["mix_report"] = rep
            m["sfx_used"] = [(c.t, c.path) for c in cues]
            m["music_license"] = ("own" if self.spec.bgm and bgm is not None else
                                  (getattr(track, "license_class", "") if track is not None and bgm is not None else None))
            m["mix"] = mix_wav
            m["n_sfx"] = len(cues)
            m["bgm_title"] = track.credit if track else (Path(self.spec.bgm).name if self.spec.bgm else "")
            m["sfx_credits"] = sorted(attrs)
            progress((k + 1) / max(1, n))

    def _apply_music_sheet(self, bgm: BgmPlan, sheet: dict, m: dict) -> Optional[BgmPlan]:
        """🎼 큐 시트를 믹스에: 롱폼은 큐 안에서만 음악(나머지는 침묵이 곧 큐), 숏폼은 shorts.role(none = 없음 · air ·
        bed = 지금처럼). fit_score 7 미만이면 air 판만(게이트 D6 수리)."""
        air_only = int(sheet.get("fit_score", 10) or 0) < 7
        if m["short"]:
            role = (sheet.get("shorts") or {}).get("role", "air")
            if role == "none":
                return None
            if role == "air" or air_only:
                bgm.cues = [{"id": "s1", "start": 0.0, "end": float(m["total"]), "role": "air", "energy": 1,
                             "entry": "fade_in", "exit": "ending"}]
            return bgm
        cues, silences = self._long_music_cues(sheet, float(m["total"]))
        if not cues:
            self.log("🎼 큐 시트에 남은 큐가 없어 음악 없이 갑니다")
            return None
        if air_only:
            for q in cues:
                q["role"] = "air"
        bgm.cues = cues
        m["music_cues"] = cues
        m["music_silences"] = [[round(a, 2), round(b, 2)] for a, b in silences]
        return bgm

    def _gate_sound(self) -> None:
        """🚦 게이트 D(04 문서 9절) — 믹스가 끝난 뒤 수치로: D1 목소리−음악 · D3 한 곡 · D5 효과음 밀도 · D6 맞는 정도 ·
        D8 점유율 · D9 라이선스 · D10 목소리 레벨 → work/sound_report.json. 실패해도 소리는 그대로(경고·리포트)."""
        main = next((m for m in self.masters if not m["short"] and m.get("mix_report") is not None), None)
        if main is None:
            return
        rep = main["mix_report"]
        sheet = getattr(self, "_music", None) or {}
        ed: EditDecisions = main["edit"]
        hd = self.hl_duration
        punch = ([(0.0, hd)] if hd > 0 else []) + [(a + hd, b + hd) for a, b in self._punch_spans(
            seg_edit_times([u for u in self.utts if u.kept], self.timemap))]
        voice_lufs = rep.get("voice_lufs")
        if voice_lufs is None:
            try:
                voice_lufs = measure_lufs(self.ff, main["voice"])
            except Exception:  # noqa: BLE001 - 측정 실패는 건너뛴다
                voice_lufs = None
        used = []
        for m in self.masters:
            if m.get("music_license") is not None:
                used.append((m.get("bgm_title") or "배경음악", m["music_license"]))
        snd = {Path(p).name: p for m in self.masters for _, p in m.get("sfx_used", [])}
        lib = self.sounds
        lic = {str(s.path): ("synth" if s.source == "synth" else s.license_class) for s in (lib.sfx if lib else [])}
        used += [(n, lic.get(p, "")) for n, p in snd.items()]
        has_music = bool(rep.get("bgm"))
        results = [
            gate.d1_voice_over_music(voice_lufs if has_music else None, rep.get("bgm_under_db") if has_music else None),
            gate.d3_one_track(int(rep.get("bgm_tracks", 0) or 0)),
            gate.d5_sfx_density(main.get("sfx_used", []), punch=punch,
                                cap=PARAMS["sfx_per_min_auto"] if getattr(self.settings, "sfx_motion_auto", True) else PARAMS["sfx_per_min"]),
            gate.d6_fit(int(sheet["fit_score"]) if has_music and sheet.get("fit_score") is not None else None),
            gate.d8_occupancy(rep.get("music_share") if has_music else None, main.get("music_cues") or []),
            gate.d9_license(used),
            gate.d10_voice_level(voice_lufs),
        ]
        write_json(self.work / "sound_report.json", {
            "voice_lufs": voice_lufs, "mix": rep, "music_sheet_by": sheet.get("by", ""),
            "suite": sheet.get("suite", ""), "fit_score": sheet.get("fit_score"),
            "cues": main.get("music_cues") or [], "silences": main.get("music_silences") or [],
            "shorts": [{"name": m["name"], **(m.get("mix_report") or {})} for m in self.masters if m["short"]],
            "used": [{"name": n, "license": c} for n, c in used],
            "gates": [r.to_dict() for r in results]})
        self._gate_record(results, "소리")

    def _start_mix_job(self) -> None:
        """렌더(Chrome·인코더)가 도는 동안 음향 믹스(FFmpeg)를 옆에서 만든다 — 마스터링 단계가 합치기만 남는다."""
        self._drop_mix_job()
        if not self.masters:
            return
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mix")
        self._mix_job = pool.submit(self._mix_all)
        pool.shutdown(wait=False)

    def _drop_mix_job(self) -> None:
        self._mix_job = None

    def _prebundle(self) -> None:
        """렌더 번들(webpack)을 편집 검사·자료 찾기와 함께 미리 만든다 — 검수 스틸과 본 렌더가 그대로 다시 쓴다
        (렌더러 소스가 같으면 render.mjs 가 재사용하고, 그 사이 생긴 이미지·스톡은 public 동기화로 들어간다)."""
        self._prepare_render()
        rs = self.settings.render
        job = RenderJob(public_dir=self.public, bundle_dir=self.render_dir / "bundle", links=[], items=[],
                        browser_executable=rs.browser_executable, gl=rs.gl, concurrency=rs.concurrency,
                        reuse_bundle=True)
        t0 = time.time()
        run_render(job, self.render_dir / "job_bundle.json", node=find_node(self.settings.node_path),
                   log=self._log_file_only, cancel=self.cancel)
        self._log_file_only(f"   (렌더 번들 미리 만들기 {time.time() - t0:.1f}s)")

    def _cam_at(self, t: float):
        """가상 시각 t 에 롱폼이 쓰는 카메라(원본이 여러 개일 때)."""
        for p in self.long_pieces:
            if p.start - 1e-6 <= t <= p.end + 1e-6:
                return self.smap.cam(p.cam)
        return self.smap.group_at(t).cams[0]

    def _thumb_frames(self, face: list[dict], inside: Callable[[float], bool], n: int = 3) -> list[dict]:
        """썸네일 프레임 고르기(docs/upgrade/10 3-1): ① 최종 타임라인(주 테이크)에서만 ② 말의 틈 — 낱말 끝 0.25초 뒤이고
        그 뒤 쉼이 0.25초 이상(말하는 중간은 눈이 반쯤 감기고 입이 벌어진다) ③ 얼굴이 가운데·정면(fr ≥ 0.8)·선명·날아감 없음
        ④ 편집 감독의 강조 순간 ±1초 가산 ⑤ 서로 15초 이상 → 상위 8장을 작게 떠서 눈 대비가 후보 중앙값의 75% 미만(감은 눈)인
        것을 뺀다. 반환 [{t, x}](원본 가상 시각)."""
        import bisect
        words = sorted((w for u in self.utts if u.kept for w in u.words), key=lambda w: w.start)
        fs = [f["t"] for f in face]
        if not words or not fs:
            return []
        moments = [m.t for m in self._moments(self.timemap) if m.intensity >= 2]
        cands: list[tuple[float, float, dict]] = []
        for w, nxt in zip(words, words[1:] + [None]):
            t = w.end + 0.25
            if nxt is not None and nxt.start - t < 0.25:
                continue
            if not inside(t):
                continue
            f = face[min(len(face) - 1, bisect.bisect_left(fs, t))]
            if not 0.25 < f.get("x", 0.5) < 0.75:
                continue
            cam = self._cam_at(t)
            q = self.quality.get(cam.idx)
            score = float(f.get("s", 0.0)) * 2.0
            if q is not None and len(q.t):
                ct = self.smap.to_cam(t, cam)
                j = int(np.clip(np.searchsorted(q.t, ct), 0, len(q.t) - 1))
                if q.f[j] < 0.6 or q.fr[j] < 0.8 or q.cl[j] > 0.01 or not 0.18 <= q.sz[j] <= 0.65:
                    continue
                sh_rank = float((q.sh <= q.sh[j]).mean())
                if sh_rank < 0.5:
                    continue
                score += sh_rank + float(q.fr[j])
            et = self.timemap.src_to_edit(t, snap=True)
            if et is not None and any(abs(et - mt) <= 1.0 for mt in moments):
                score += 0.5
            cands.append((score, t, f))
        picked: list[tuple[float, float, dict]] = []
        for c in sorted(cands, key=lambda c: -c[0]):
            if all(abs(c[1] - p[1]) >= 15.0 for p in picked):
                picked.append(c)
            if len(picked) >= 8:
                break
        if not picked:
            return []
        # 눈: 작게 떠서 눈 대비를 잰다 — 감은 눈(후보 중앙값의 75% 미만)은 뺀다
        eyes: dict[float, Optional[float]] = {}
        try:
            import cv2

            from .vision.face import eye_openness
            tmp = self.work / "thumb_cands"
            tmp.mkdir(parents=True, exist_ok=True)
            for _, t, _ in picked:
                cam = self._cam_at(t)
                dst = tmp / f"c_{int(t * 1000)}.jpg"
                self.ff.grab_frame(cam.path, self.smap.to_cam(t, cam), dst, width=960)
                img = cv2.imread(str(dst))
                eyes[t] = eye_openness(img) if img is not None else None
        except Exception as e:  # noqa: BLE001 - 눈 검사는 덤(실패하면 수치 기준만)
            self._log_file_only(f"   (썸네일 눈 검사 생략: {e})")
        vals = [v for v in eyes.values() if v is not None]
        med = float(np.median(vals)) if len(vals) >= 3 else None
        good = [c for c in picked if med is None or eyes.get(c[1]) is None or eyes[c[1]] >= 0.75 * med]
        dropped = len(picked) - len(good)
        out = [{"t": t, "x": f.get("x", 0.5)} for _, t, f in (good or picked)[:n]]
        self.log(f"🖼 썸네일 프레임: 말의 틈·정면 후보 {len(cands)}곳 → {len(out)}장"
                 + (f"(눈 감은 듯한 {dropped}장 제외)" if dropped else "") + " · "
                 + ", ".join(fmt_ts(self.timemap.src_to_edit(x['t'], snap=True) or 0) for x in out))
        return out

    def _thumbnail_items(self) -> list[RenderItem]:
        assert self.info
        kept = self.timemap.keeps
        face = self._angles(self.long_pieces, self.timemap)[1]
        import bisect
        ks = [k.start for k in kept]

        def inside(t: float) -> bool:
            j = bisect.bisect_right(ks, t - 0.5) - 1
            return j >= 0 and t <= kept[j].end - 0.5
        picks = self._thumb_frames(face, inside)
        if not picks:            # 예전 방식(얼굴이 가장 큰 곳)
            cands = sorted([s for s in face if 0.25 < s["x"] < 0.75 and inside(s["t"])], key=lambda s: -s["s"])
            for s in cands:
                if all(abs(s["t"] - p["t"]) > 20 for p in picks):
                    picks.append(s)
                if len(picks) == 3:
                    break
        if not picks and kept:
            picks = [{"t": kept[0].start + 1.0, "x": 0.5}]
        texts = [t for t in (self.plan_long.get("youtube") or {}).get("thumbnail_texts", []) if t.strip()] \
            or [self.title]
        variants = ["signal", "ink", "photo"]
        items = []
        img_dir = self.public / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            pk = picks[i % len(picks)]
            frame = img_dir / f"thumb_frame_{i + 1}.jpg"
            cam = self._cam_at(pk["t"])
            cube = self._cube(cam.idx)
            vf = hdr_to_sdr_filter() if self.infos.get(cam.idx, self.info).is_hdr else ""
            if cube.exists() and self.spec.auto_grade and not self.spec.lut:
                from .edit.assemble import _escape_filter_path
                vf = (vf + "," if vf else "") + f"format=gbrp,lut3d=file={_escape_filter_path(cube)}:interp=tetrahedral"
            try:
                self.ff.grab_frame(cam.path, self.smap.to_cam(pk["t"], cam), frame, width=1920, extra_vf=vf)
            except Exception as e:  # noqa: BLE001
                self.log(f"썸네일 프레임 추출 실패: {e}")
                continue
            text = texts[i % len(texts)]
            words = [w for w in text.replace("\n", " ").split() if len(w) >= 2]
            if "\n" not in text and len(text) > 7:
                mid = len(text) // 2
                sp = text.find(" ", max(0, mid - 3))
                if sp > 0:
                    text = text[:sp] + "\n" + text[sp + 1:]
            props = {"width": 1280, "height": 720, "brand": brand_props(self.settings.brand),
                "episode": self._episode().to_props(), "image": f"images/{frame.name}", "text": text,
                "highlight": words[-1] if words else "", "variant": variants[i], "faceX": pk.get("x", 0.5)}
            p = self.render_dir / f"props_thumb_{i + 1}.json"
            write_json(p, props)
            items.append(RenderItem("still", "Thumbnail", p, self.extras / f"썸네일{i + 1}_{variants[i]}.jpg",
                                    scale=1.0, weight=0.5))
        return items

    # ------------------------------------------------------------------
    def stage_export(self) -> None:
        assert self.info
        # CC 라이선스 자료는 라이선스가 요구하는 출처 전문(Openverse attribution)을 그대로
        credits = sorted({(b.get("attribution") if b.get("attribution") and b.get("attribution") != b.get("credit")
                           else b["credit"] + (f" ({b['url']})" if b.get("url") else "")) for b in self.broll_log
                          if b.get("credit")})
        # 🎞 자료 조달 v2 의 증거 자료(설명란 전문 출처) + 자료 대장(화면에 실제로 나간 자료만)
        from .assets.graphics import ledger_rows, props_credits
        from .assets.license import write_ledger
        all_props = ([("롱폼", self.long_props)] if self.long_props else []) + \
            [(f"숏폼{i}", sp) for i, sp in enumerate(self.short_props, 1)]
        logged = {b.get("credit") for b in self.broll_log}
        for _, pp in all_props:
            credits += [c for c in props_credits(pp.get("graphics", [])) if c not in credits]
            credits += [g["data"]["credit"] for g in pp.get("graphics", []) if g.get("template") == "photo"
                        and (g.get("data") or {}).get("credit") and g["data"]["credit"] not in logged
                        and g["data"]["credit"] not in credits]
        credits = sorted(set(credits))
        ledger = [r for where, pp in all_props for r in ledger_rows(pp.get("graphics", []), where)]
        if ledger:
            write_ledger(self.extras / "자료_대장.csv", ledger)
        # 🔎 조사 노트(출처·대본 확인) — 화자가 고정 댓글·다음 녹화에 쓴다
        from .agents.research import research_notes
        notes = research_notes(self.research, title=self.title)
        if notes:
            write_text(self.extras / "조사노트.md", notes)
        music = sorted({m.get("bgm_title", "") for m in self.masters if m.get("bgm_title")})
        sfx_credits = sorted({c for m in self.masters for c in m.get("sfx_credits", []) or []})
        chapters = getattr(self, "long_chapters", [])
        if self.long_props:
            write_text(self.extras / "롱폼_자막.srt", cues_to_srt(self.long_props["captions"]))
        for i, sp in enumerate(self.short_props, 1):
            write_text(self.extras / f"숏폼{i}_자막.srt", cues_to_srt(sp["captions"]))
        self._review_sheets()
        self._color_tags()
        self._timeline_review()
        text = youtube_text(self.plan_long, chapters, self.plan_shorts, credits)
        if music:
            text += "\n## 배경음악\n" + "\n".join(f"- {m}" for m in music) + "\n"
        if sfx_credits:     # CC BY 효과음은 라이선스 문구 그대로(04b 7절 4번)
            text += "\n## 효과음 출처\n" + "\n".join(f"- {c}" for c in sfx_credits) + "\n"
        write_text(self.out / "업로드정보.txt", text)
        if self.spec.export_xml:
            w, h = self.info.display_size
            voice = self.work / "voice.wav"
            # 키는 Path 로 한 번 정규화(창에서 받은 'C:/…' 와 Path 가 만든 'C:\\…' 가 달라 못 찾던 것)
            files = {str(Path(c.path)): (self.infos[c.idx].duration, *self.infos[c.idx].display_size)
                     for c in self.smap.cams}

            def xml_pieces(pieces: list[Piece]) -> Optional[list[tuple[Path, float, float, float]]]:
                if self.smap.single:
                    return None
                return [(Path(self.smap.cam(p.cam).path), self.smap.to_cam(p.start, self.smap.cam(p.cam)), p.start,
                         p.end - p.start) for p in pieces]
            if self.spec.make_long:
                markers = [(c["start"], f"챕터 {c['number']} {c['title']}", "") for c in chapters]
                markers += [(g["start"], g["template"], str(g["data"].get("title") or g["data"].get("body") or ""))
                            for g in self.long_props.get("graphics", [])]
                hl_keeps = list(self.hl_map.keeps) if self.hl_map is not None else []
                export_xml(self.extras / "롱폼_premiere.xml", name=f"{self.title} (자동 컷)",
                           video=Path(self.spec.video), audio=voice, src_fps=self.info.fps, src_duration=self.info.duration,
                           width=w, height=h, seq_width=w, seq_height=h, keeps=hl_keeps + list(self.timemap.keeps),
                           markers=markers, pieces=xml_pieces(self.hl_pieces + self.long_pieces), files=files)
            short_pieces = getattr(self, "short_pieces", []) or []
            for i, tm in enumerate(getattr(self, "short_maps", []), 1):
                export_xml(self.extras / f"숏폼{i}_premiere.xml", name=f"숏폼 {i}", video=Path(self.spec.video),
                           audio=voice, src_fps=self.info.fps, src_duration=self.info.duration, width=w, height=h,
                           seq_width=1080, seq_height=1920, keeps=tm.keeps, markers=[],
                           pieces=xml_pieces(short_pieces[i - 1]) if i <= len(short_pieces) else None, files=files)
        report = edit_report(title=self.title, source_duration=self.info.duration,
                             long_duration=self.timemap.duration + self.hl_duration, align_report=self.align_report,
                             utts=self.utts,
                             graphics=self.long_props.get("graphics", []) if self.long_props else [],
                             chapters=chapters, shorts=self.plan_shorts, director=self.director_name,
                             usage=self.claude.usage if self.claude else read_json(self.work / "plan.json", {}).get("usage", []),
                             broll=self.broll_log, studio=self.plan_long.get("studio") or None,
                             qa=self.qa_log or (self.plan_long.get("qa") or {}).get("rounds"),
                             gate=gate.report_section(self.gate_results),
                             sound=read_json(self.work / "sound_report.json", {}) or None)
        report += self._craft_report()
        if self.soft_failures:
            report += "\n## ⚠️ 건너뛴 작업(실패했지만 영상은 끝까지 만들었습니다)\n\n" + "".join(
                f"- {f['label']}: {f['error']}\n" for f in self.soft_failures)
        write_text(self.extras / "편집리포트.md", report)
        # 📊 사용량 장부(user/usage.json): 이 작업의 호출·토큰·API 환산 + 마지막 한도 창(설정 창 '사용량')
        try:
            from .settings import record_usage
            if self.claude is not None and getattr(self.claude, "usage", None):
                agg = record_usage(self.title, self.claude.usage, getattr(self.claude, "rate_limit", {}) or {})
                from .director.claude_code import format_quota
                q = format_quota(getattr(self.claude, "rate_limit", {}) or {})
                self.log(f"📊 Claude 호출 {agg['calls']}회 · 입력 {agg['input'] + agg['cache_read']:,} · 출력 {agg['output']:,} 토큰"
                         f" · API 환산 약 ${agg['api_equiv_usd']:.2f}" + (f" · {q}" if q else ""))
        except Exception as e:  # noqa: BLE001 - 장부는 덤
            self._log_file_only(f"사용량 장부 실패: {e}")
        shutil.copyfile(self.work / "plan.json", self.extras / "plan.json")
        self.results["extras"] = str(self.extras)
        self.results["upload_info"] = str(self.out / "업로드정보.txt")

    def _color_tags(self) -> None:
        """게이트 F6 — 완성본의 색 태그가 BT.709 · tv · yuv420p 인가(07 문서 2-7: 10/1 완성본은 풀레인지 BT.601 로 나갔다)."""
        probs: dict[str, list[str]] = {}
        for m in self.masters:
            try:
                if Path(m["dst"]).exists():
                    probs[Path(m["dst"]).name] = self.ff.assert_bt709(m["dst"])
            except Exception as e:  # noqa: BLE001 - 검사 실패는 결과물에 영향 없음
                self._log_file_only(f"   (색 태그 검사 실패 {m.get('dst')}: {e})")
        if probs:
            self._gate_record([gate.f6_tags(probs)], "완성본 색")

    def _timeline_review(self) -> None:
        """🧐 게이트 E — 완성본을 처음 보는 눈으로: 검토 시트(2.5초 간격) 전부 + 자막 + 이벤트 목록 + 감독의 계획 + 게이트 결과를
        타임라인 검수 에이전트가 루브릭(R1~R6)으로 채점한다(docs/upgrade/05b). 가중 평균·판정은 코드. high·blocking 발견이 있으면
        결과에 '검토 필요'(output/⚠검토필요.md · 창 · 리포트 첫 절). 실패해도 결과물은 그대로(게이트 수치만으로 판정)."""
        from .export.events import event_list
        if not (self.long_props and self.masters and self._use_api() and self.spec.studio_mode):
            return
        sheets = sorted(self.extras.glob("검토시트_롱폼*.jpg"))[:20]
        if not sheets:
            return
        hd = self.hl_duration
        main = next((m for m in self.masters if not m["short"]), None)
        ed = main["edit"] if main else None
        seg_t = seg_edit_times([u for u in self.utts if u.kept], self.timemap)
        peak = self.plan_long.get("peak_seg", -1)
        events = event_list(self.long_props, holds=[(a + hd, b + hd) for a, b in self._hold_spans()],
                            sequences={q["id"]: q["type"] for q in self.plan_long.get("sequences", []) or []},
                            sfx=ed.sfx if ed else [], peak_t=(seg_t[peak][0] + hd) if peak in seg_t else None)
        key = text_hash(events + "".join(str(p.stat().st_size) for p in sheets))
        cache = read_json(self.work / "timeline_qa.json", {})
        if cache.get("key") == key and cache.get("result"):
            tl = cache["result"]
            self._log_file_only("   (타임라인 검수: 이전 결과 사용)")
        else:
            studio = self._ensure_studio()
            if studio is None:
                return
            brief = self.plan_long.get("studio") or {}
            plan_text = "\n".join([f"논지: {brief.get('thesis', '')}",
                                    f"훅의 질문: {self.plan_long.get('central_question', '')}",
                                    "챕터: " + " / ".join(f"{c['title']} — {c.get('claim', '')}"
                                                          for c in self.plan_long.get("chapters", []))])
            gate_text = "\n".join(f"- {r.id}: {'통과' if r.ok else r.level} — {r.message}" for r in self.gate_results)
            imgs = [(p.stem, p.read_bytes(), "image/jpeg") for p in sheets]
            srt_p = self.extras / "롱폼_자막.srt"
            try:
                tl = studio.review_timeline(self.ctx, events, srt_p.read_text(encoding="utf-8") if srt_p.exists() else "",
                                            plan_text, gate_text, imgs)
            except DirectorError as e:
                self.log(f"🧐 타임라인 검수 실패 → 게이트 수치만으로 판정: {e}")
                return
            write_json(self.work / "timeline_qa.json", {"key": key, "result": tl, "events": events})
        r = gate.gate_e(tl)
        self.gate_results = gate.merge(self.gate_results, [r])
        gate.write(self.work / "gate.json", self.gate_results, forced=self.force_render)
        fb = gate.gate_feedback(self.gate_results, tl)
        if fb:
            old = read_json(self.work / "gate_feedback.json", [])
            write_json(self.work / "gate_feedback.json", (old if isinstance(old, list) else []) + fb)
        verdict = r.measured.get("verdict")
        self.results["timeline_review"] = {"verdict": verdict, "weighted": r.measured.get("weighted")}
        self.log(f"🧐 타임라인 검수: {r.message}")
        flag = self.out / "⚠검토필요.md"
        if verdict == "needs_review":
            self.results["needs_review"] = True
            lines = [f"# 검토 필요 — {self.title}", "", r.message, "", "## 발견", ""]
            lines += [f"- {f.get('start', '')}~{f.get('end', '')} [{f.get('severity')}] {f.get('kind')}: {f.get('direction', '')}"
                      for f in r.measured.get("findings", [])]
            write_text(flag, "\n".join(lines) + "\n")
        elif flag.exists():
            flag.unlink()

    def _review_sheets(self) -> None:
        """부가자료/검토시트_*.jpg — 완성 영상을 2.5초마다 한 장씩(시간·자막 포함). 실패해도 작업은 계속."""
        from .review import review_sheets
        jobs = []
        if self.long_props and self.masters and not self.masters[0]["short"]:
            jobs.append((self.masters[0]["dst"], self.long_props["captions"], "검토시트_롱폼", "롱폼"))
        shorts = [m for m in self.masters if m["short"]]
        for i, (m, sp) in enumerate(zip(shorts, self.short_props), 1):
            jobs.append((m["dst"], sp["captions"], f"검토시트_숏폼{i}", f"숏폼 {i}"))
        n = 0
        for video, cues, name, title in jobs:
            try:
                if Path(video).exists():
                    n += len(review_sheets(self.ff, Path(video), cues, self.extras / name, title=title))
            except Exception as e:  # noqa: BLE001 - 검토용 부가자료
                self.log(f"검토 시트 생략({title}): {e}")
        if n:
            self.log(f"🗂 검토 시트 {n}장 → 부가자료/검토시트_*.jpg (2.5초마다 한 장, 시간·자막 포함)")

    def _craft_report(self) -> str:
        """리포트 뒤에 붙일 '어떻게 편집했나' 요약(색·소리·편집 기술)."""
        lines = ["", "## 🎛 자동 후반 작업", ""]
        if not self.smap.single:
            lines.append("- 원본 " + str(len(self.smap.cams)) + "개: " + self.smap.summary())
            if self.smap.multicam and self.long_pieces:
                lines.append("- 앵글(롱폼): " + angle_summary(self.long_pieces, self.smap))
        if self.hl_map is not None and self.hl_segs:
            by_id = {u.id: u for u in self.utts}
            lines.append(f"- 오프닝 하이라이트 {self.hl_duration:.1f}초: "
                         + " / ".join(f"「{by_id[i].text[:30]}」" for i in self.hl_segs if i in by_id) + " → 처음부터")
        if self.look_plan:
            lines.append("- 화면 구성(자동 · 하이브리드): " + self.look_plan.summary())
        au = read_json(self.work / "audio.json", {})
        if au.get("recipe_summary"):
            vs = au.get("voice_stats", {})
            lines.append(f"- 목소리(분석 → 최소 보정): SNR {vs.get('snr', 0):.0f}dB · 다이내믹 {vs.get('dynamics', 0):.0f}dB → "
                         + au["recipe_summary"] + (f" · 게인 {au.get('gain_db', 0):+.1f}dB" if "gain_db" in au else ""))
        g = self.grade_info or {}
        if g:
            ch = g.get("choice", {})
            sc = g.get("scopes") or {}
            bad = [c for c in sc.get("before", []) if not c.get("ok")]
            scope_txt = ("스코프 모두 정상" if not bad else "범위 밖: " + ", ".join(
                f"{c['label']} {c['value']:.1f}" for c in bad))
            if not g.get("lut", True):
                lines.append(f"- 색보정: {scope_txt} → 원본 그대로(LUT 없음)")
            else:
                lines.append(f"- 색보정: {scope_txt} → {', '.join(g.get('correction', {}).get('notes', [])) or '교정 거의 없음'}"
                             f" → 룩 {grade.LOOKS.get(ch.get('look', 'natural'), grade.LOOKS['natural']).label}"
                             f"(세기 {ch.get('strength', 1):.1f}) · 색 잡음 ×{sc.get('noise_gain', 1.0):.2f} "
                             f"{ch.get('reason', '')}")
        for m in self.masters:
            st = m["edit"].stats
            lines.append(f"- {m['name']}: " + " · ".join(f"{k} {v}" for k, v in st.items())
                         + f" · 배경음악 {m.get('bgm_title') or '없음'}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------


def short_retype(g: dict) -> Optional[dict]:
    """롱폼 그래픽을 숏폼 위 카드(880×610)에 옮길 때: 1920×1080 으로 짠 자유 카드·모션 장면은 0.46배로 줄면 36px 본문이
    16px 가 된다(10/1) — 줄여 넣지 않고 숏폼의 개념 카드로 다시 짠다(제목 + 핵심 한 줄). 도식·사진·스톡·글자 그래픽은
    상자에 맞춰 스스로 배치하므로 그대로. 다시 짤 글이 없으면 None(넣지 않음)."""
    if g.get("template") == "evidence":
        # 증거 자료: 숏폼은 기존 사진 경로로(위 카드에 사진·로고) — 사진이 없는 출처 카드는 개념 카드(제목 + 저자·연도)로
        c = copy.deepcopy(g)
        a = next((x for x in g.get("assets") or [] if x.get("kind") in ("photo", "logo", "screen", "document")), None)
        for k in ("assets", "archive", "treatment", "tier", "caption"):
            c.pop(k, None)
        if a is not None:
            c.update(template="photo", layout="pip", image=a.get("mat_src") or a["src"], credit=a.get("credit", ""),
                     title=(g.get("title") or "")[:14], body=(g.get("caption") or g.get("body") or "")[:24], resolved=True)
            if a.get("kind") == "logo":
                c["logo"] = True
            if a.get("mat_src"):
                c["mat"] = True
            return c
        arc = g.get("archive") or {}
        title = str(g.get("title") or arc.get("title") or "").strip()
        if not title:
            return None
        sub = " · ".join(str(r.get("v", "")) for r in (arc.get("rows") or [])[:2] if r.get("v"))
        # 한글 제목은 14자, 영문(논문 제목)은 24자까지 — 'Design fixation' 이 잘리지 않게
        c.update(template="keyword", layout="split", title=title[:24 if title.isascii() else 14], subtitle=sub[:40], body="")
        return c
    if g.get("template") not in ("card", "motion"):
        return copy.deepcopy(g)
    texts: list[str] = []
    if g.get("template") == "card" and isinstance(g.get("card"), dict):
        import html as _html
        texts = [" ".join(_html.unescape(t).split()) for t in re.split(r"<[^>]+>", g["card"].get("html") or "")]
        texts = [t for t in texts if t]
    elif isinstance(g.get("spec"), dict):
        els = [e for e in g["spec"].get("elements", []) or [] if isinstance(e, dict) and str(e.get("text", "")).strip()]
        texts = [str(e["text"]).strip() for e in sorted(els, key=lambda e: -float(e.get("size", 0) or 0))]
    title = str(g.get("title") or (texts[0] if texts else "")).strip()
    rest = [t for t in texts if t.strip() and t.strip() != title]
    if not title:
        return None
    c = copy.deepcopy(g)
    for k in ("card", "spec"):
        c.pop(k, None)
    c.update(template="keyword", layout="split", title=title[:14], subtitle=(rest[0] if rest else "")[:40], body="")
    return c


QA_ALWAYS = ("shorten_text", "drop")    # 글자 줄이기·빼기는 싸고 안전하다 — low 여도 반영(10/1: 검색어 라벨 지적 4건이 low 라 0건 반영)


def qa_actionable(issues: list[dict]) -> list[dict]:
    """아트 디렉터 지적 중 그래픽에 반영할 것: high·medium 은 모두, low 는 글자 줄이기·빼기만(편집 지적은 _qa_escalate)."""
    return [i for i in issues if i.get("action") not in (None, "", "none", "escalate_edit")
            and (i.get("severity") in ("high", "medium") or i.get("action") in QA_ALWAYS)]


def qa_strip_times(g: TimedGraphic, settle: float) -> list[float]:
    """움직임 스트립의 여섯 순간(docs/upgrade/06c 6-1): +0.5초(무대가 섰나) · 15%(뼈대) · 40%(채움 진행) · 안착 +2f ·
    사건(keys·groupAt 구간 가운데, 없으면 70%) · 퇴장 직전(끝 −0.4초). 0%는 뽑지 않는다(판이 쓸려 들어오는 중)."""
    a, b = g.start, g.end
    d = b - a
    ev = None
    spec = g.data.get("spec") if g.template == "motion" else None
    if isinstance(spec, dict):
        ts = [k["t"] for e in spec.get("elements") or [] for k in e.get("keys") or [] if isinstance(k, dict) and "t" in k]
        ts += [e["groupAt"] + 0.4 for e in spec.get("elements") or [] if "groupAt" in e]
        if ts:
            ev = a + (min(ts) + max(ts)) / 2
    raw = [a + 0.5, a + 0.15 * d, a + 0.40 * d, settle + 2 / 30, ev if ev is not None else a + 0.70 * d, b - 0.4]
    return [min(b - 0.1, max(a + 0.1, t)) for t in raw]


def qa_strip_sheet(items: list[tuple[float, Path]], dst: Path, *, tile=(640, 360), cols: int = 3) -> Optional[Path]:
    """스트립 여섯 장을 640×360 칸 3×2 로 한 장에 — 칸마다 그래픽 시작 기준 상대 시각(진행 중 프레임은 흐림·잘림이 결함이 아니다)."""
    from PIL import Image, ImageDraw
    ims = []
    for rel, p in items:
        try:
            ims.append((rel, Image.open(p).convert("RGB").resize(tile, Image.LANCZOS)))
        except OSError:
            continue
    if not ims:
        return None
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile[0], rows * tile[1]), (30, 27, 25))
    d = ImageDraw.Draw(sheet)
    for k, (rel, im) in enumerate(ims):
        x, y = (k % cols) * tile[0], (k // cols) * tile[1]
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + 92, y + 22], fill=(30, 27, 25))
        d.text((x + 6, y + 5), f"+{rel:.1f}s", fill=(245, 242, 234))
    sheet.save(dst, quality=86)
    return dst


def qa_phone_sheet(stills: list[tuple[str, Path]], dst: Path, *, tile: int = 480, cols: int = 3) -> Optional[Path]:
    """R2·R3(art_director.md): 정지 프레임을 폭 480px 로 줄여 한 장에 — 폰 화면에서 헤드라인이 읽히는가를 본다."""
    from PIL import Image, ImageDraw
    ims = []
    for name, p in stills[:12]:
        try:
            im = Image.open(p).convert("RGB")
        except OSError:
            continue
        ims.append((name, im.resize((tile, max(1, round(im.height * tile / im.width))), Image.LANCZOS)))
    if not ims:
        return None
    th = max(im.height for _, im in ims) + 26
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tile + 12) + 12, rows * (th + 12) + 12), (30, 27, 25))
    d = ImageDraw.Draw(sheet)
    for k, (name, im) in enumerate(ims):
        x, y = 12 + (k % cols) * (tile + 12), 12 + (k // cols) * (th + 12)
        d.text((x + 2, y + 4), name, fill=(245, 242, 234))
        sheet.paste(im, (x, y + 26))
    sheet.save(dst, quality=88)
    return dst


def covered_elsewhere(u: Utterance, utts: list[Utterance], drop_ids: set[int], *, need: float = 0.85) -> bool:
    """u 의 대본 구간을 남아 있을(kept 이고 지울 대상이 아닌) 다른 발화들이 85% 이상 덮는가 — 덮으면 u 를 지워도 대본
    문장이 사라지지 않는다(docs/upgrade/02 3-4)."""
    if not u.script_span:
        return False
    a, b = u.script_span
    n = max(1, b - a)
    marks = bytearray(n)
    for v in utts:
        if v is u or not v.kept or v.id in drop_ids or not v.script_span:
            continue
        x, y = max(a, v.script_span[0]), min(b, v.script_span[1])
        if y > x:
            marks[x - a:y - a] = b"\x01" * (y - x)
    return sum(marks) / n >= need


def _minus(a: float, b: float, words: list[Word], pad: float = 0.08) -> list[tuple[float, float]]:
    """[a, b) 에서 인식된 단어가 차지한 시간을 뺀 조각들."""
    out, t = [], a
    for w in sorted((w for w in words if w.end + pad > a and w.start - pad < b), key=lambda w: w.start):
        if w.start - pad > t:
            out.append((t, min(b, w.start - pad)))
        t = max(t, w.end + pad)
    if t < b:
        out.append((t, b))
    return out


def topic_line(text: str, limit: int = 28) -> str:
    """'오늘의 주제' 한 줄: 논지의 첫 문장, 길면 어절 경계에서 자른다(끝 마침표 없이). 너무 짧거나 비면 ''."""
    import re
    first = re.split(r"(?<=[.!?。])\s+|\n", (text or "").strip())[0].strip().rstrip(".。")
    if len(first) <= limit:
        return first if len(first) >= 6 else ""
    cut = first[:limit + 1]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp >= limit * 0.6 else first[:limit]).rstrip(" ,·") + "…"

