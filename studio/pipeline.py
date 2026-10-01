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

from . import diag
from .agents.studio import Studio
from .asr.transcribe import gpu_expected, load_audio_16k, speech_regions, transcribe
from .broll.entities import find_entities
from .broll.images import Wikimedia, list_local_images
from .broll.logos import SimpleIcons
from .broll.resolve import MediaPlan, MediaResolver, contact_rows
from .broll.wikipedia import WikipediaImages
from .director import fallback
from .director.catalog import TEMPLATES
from .director.claude import ClaudeClient, DirectorError
from .director.claude_code import ClaudeCodeClient, find_claude, resolve_backend
from .director.context import JobBrief, long_instruction, shared_context, shorts_instruction, system_prompt
from .motion.card import card_settle_time, card_text
from .motion.check import CheckError, check_cards, problem_lines
from .director.plan import (TimedGraphic, blank_graphic, normalize_long, normalize_shorts, seg_edit_times,
                            spec_settle_time, time_graphics, word_edit_time)
from .director.schema import LONG_PLAN, SHORTS_PLAN
from .edit.assemble import build_proxy, cut_audio, proxy_height_for
from .edit.cuts import PACES, build_keeps, keeps_for_segments
from .edit.grammar import PARAMS, EditDecisions, Moment, build_long_edit, build_short_edit
from .edit.style import LookPlan, apply_looks, choose_looks
from .edit.verify import find_issues, merge, subtract, to_source
from .eta import Eta, features
from .export.premiere import export_xml
from .export.report import edit_report, write_text, youtube_text
from .grade import auto as grade
from .grade import scopes
from .media.audio import build_voice_track
from .media.ffmpeg import FFmpeg, MediaInfo, hdr_to_sdr_filter, pick_output_fps
from .media.mix import BgmPlan, SfxCue, mix, mux_final
from .media.sources import (Piece, Quality, SourceMap, analyze_sources, angle_cut_times, angle_summary, choose_angles,
                            clips_for, face_track, master_audio_args, visual_scorer)
from .models import Span, Tag, TimeMap, Utterance, Word
from .net import redact
from .paths import USER_DIR
from .render.assets import copy_fonts, make_grain, make_paper
from .render.props import (Episode, apply_edit, caption_overlays, dedupe_captions, face_safe_layouts, long_props,
                           mark_soft_cuts, mark_stack_cues, prepend_props, shift_decisions, shift_props, short_beats,
                           short_props, strip_audio, text_graphic_spans, chapter_maps, chapter_recaps,
                           fold_keywords_into_media)
from .render.remotion import RenderItem, RenderJob, find_node, run_render
from .settings import Settings
from .sound.library import MOODS_LONG, MOODS_SHORT, SoundLibrary
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
    ("align", "대본 맞추기 · 가장 또렷한 테이크 고르기", 2),
    ("grade", "자동 색보정", 3),
    ("director", "AI 기획(감독 + 전문 팀)", 9),
    ("proxy", "편집본 만들기(컷·색)", 8),
    ("verify", "편집 오류 검사(음성 다시 인식)", 5),
    ("broll", "자료 사진", 2),
    ("stock", "스톡 영상·사진", 3),
    ("sound", "효과음·배경음악 준비", 2),
    ("qa", "아트 디렉터 검수", 4),
    ("render", "렌더링", 30),
    ("master", "음향 믹스·마스터링", 5),
    ("export", "마무리(썸네일·자막·검토 시트·업로드 정보)", 2),
]
STAGE_LABEL = {k: v for k, v, _ in STAGES}
EXTRAS = "부가자료"

# 서로 기다릴 필요가 없는 단계는 동시에 돈다 — 칸(차례로) → 줄(동시에) → 단계(줄 안에서 차례로).
#  · 얼굴 추적(영상 디코딩)은 목소리 다듬기 → 음성 인식(소리·GPU)과 함께
#  · 🎬 AI 기획(네트워크)은 색보정 → 편집본 인코딩(GPU/CPU)과 함께 — 컷은 둘 다 끝난 뒤(_make_edit)
#  · 🔎 편집 검사(Whisper)는 자료 사진 → 스톡(네트워크) · 효과음 준비 → 렌더 번들 미리 만들기와 함께
#  · 렌더 중에 음향 믹스를 미리 만들어 두고(stage_render) 마스터링 단계는 합치기만 한다
# STAGES 에 없는 키(bundle)는 화면·남은 시간에 나오지 않는 준비 작업이다(실패해도 작업은 계속).
SCHEDULE: list[list[list[str]]] = [
    [["probe"]],
    [["audio", "asr"], ["face"]],
    [["align"]],
    [["director"], ["grade", "proxy"]],
    [["verify"], ["broll", "stock"], ["sound", "bundle"]],
    [["qa"]],
    [["render"]],
    [["master"]],
    [["export"]],
]
PLAN_ONLY = ("probe", "audio", "asr", "face", "align", "grade", "director")


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
                 eta: Optional[Eta] = None, preview: Optional[Callable[[str, str], None]] = None):
        """preview(이미지 경로, 설명): 진행 화면 미리보기 — 색보정 전후 · 자료 사진 · 검수 장면 · 렌더 중 프레임 · 썸네일."""
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
        self.ctx = ""
        self.broll_log: list[dict] = []
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
                    "qa": "qa@ai" if ai else "qa@rule",
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
        fn()
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
        res = transcribe(self.work / "asr16k.wav", model_name=self.settings.whisper_model,
                         device=self.settings.whisper_device, compute_type=self.settings.whisper_compute,
                         batch_size=self.settings.whisper_batch, hint_terms=hints, duration=self.info.duration,
                         log=self.log, progress=self._sp("asr"), cancel=self.cancel)
        res["key"] = key
        write_json(self.work / "transcript.json", res)
        self.log(f"인식 완료: {len(res['words'])}단어")

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
        aligner = ScriptAligner(parsed, self.settings.glossary, audio=audio,
                                visual=visual_scorer(self.smap, self.quality))
        self.utts, self.tags, rep = aligner.run(utts)
        self.align_report = rep.to_dict()
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
        """🎨 자동 색보정: 남길 구간의 프레임 분석 → 교정 + 레퍼런스 색 매칭 + 룩(기본 웜 리치, 컬러리스트가 비교 시트에서
        선택) → LUT. 원본이 여러 개면 카메라마다 교정·색 매칭을 따로 하고(같은 레퍼런스로 모아 앵글끼리 색이 맞는다),
        룩은 첫 카메라에서 한 번 고른다."""
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
                        [round(v, 1) for v in ref_lab], "grade-v5")
        cached = read_json(self.work / "grade.json", {})
        luts = cached.get("luts") or {}
        if cached.get("key") == key and all(not luts.get(str(c.idx), True) or self._cube(c.idx).exists() for c in cams):
            self.grade_info = cached
            self.log("🎨 색보정: 캐시 사용(" + ("원본 그대로" if not any(luts.values()) else
                                             grade.LOOKS[cached['choice']['look']].label) + ")")
            return
        base: Optional[grade.GradeChoice] = None
        per_cam: dict[str, dict] = {}
        luts = {}
        for n, cam in enumerate(cams):
            plan, choice = self._grade_cam(cam, times[cam.idx], ref_lab, base, first=(n == 0))
            if n == 0:
                base = choice
                self.grade_info = {"key": key, **plan}
            luts[str(cam.idx)] = bool(plan.get("lut"))
            per_cam[str(cam.idx)] = {"filters": plan.get("filters", []), "lut": bool(plan.get("lut")),
                                     "notes": plan.get("correction", {}).get("notes", [])}
            self._stage("grade", (n + 1) / len(cams))
        self.grade_info["luts"] = luts
        if len(cams) > 1:
            self.grade_info["cams"] = per_cam
        write_json(self.work / "grade.json", self.grade_info)

    def _grade_cam(self, cam, times: list[float], ref_lab, base: Optional["grade.GradeChoice"], *,
                   first: bool) -> tuple[dict, "grade.GradeChoice"]:
        info = self.infos[cam.idx]
        frames = grade.sample_frames(self.ff, cam.path, times, info)
        track = self.face_cams.get(cam.idx) or []
        faces = [min(track, key=lambda s: abs(s["t"] - t)) if track else None for t, _ in frames]
        stats = grade.analyze(frames, faces)
        raw_frames = [f for _, f in frames]
        # 스코프(파형·벡터스코프 수치)로 먼저 판정 — 모든 항목이 정상 범위면 원본 그대로(LUT 도 걸지 않는다)
        before = scopes.metrics(raw_frames, faces)
        checks = scopes.assess(before)
        untouched = scopes.all_ok(checks)
        corr = grade.Correction(notes=["원본 정상 범위 — 보정 없음"]) if untouched else grade.correction_from_stats(stats)
        # 교정 후 평균색 → 레퍼런스(사용자가 좋아하는 따뜻하고 풍부한 색) 쪽으로 옮길 기준
        src_lab = grade.lab_stats(np.concatenate([grade.apply_correction(f, corr).reshape(-1, 3) for _, f in frames]))
        # 비교용 3프레임: 얼굴이 크고 서로 떨어진 순간
        order = sorted(range(len(frames)), key=lambda i: -(faces[i] or {}).get("s", 0))
        picks: list[int] = []
        for i in order:
            if all(abs(i - j) >= max(1, len(frames) // 4) for j in picks):
                picks.append(i)
            if len(picks) == 3:
                break
        picks = sorted(picks or [0])
        skin_rgb = stats.get("face_rgb")      # 피부 보호는 이 카메라의 얼굴색 근처만, 벗어난 만큼만 고친다
        who = f"[{Path(cam.path).name}] " if not self.smap.single else ""
        self.log(f"🎨 {who}스코프: " + scopes.summary(checks))
        if untouched:
            choice = grade.untouched_choice()
        elif base is not None:        # 두 번째 카메라부터: 같은 룩·세기, 레시피는 이 카메라의 상태로 다시
            choice = replace(grade.plan_choice(raw_frames, corr, base.look, ref_lab, skin_rgb=skin_rgb),
                             strength=base.strength,
                             exposure=base.exposure, warmth=base.warmth, saturation=base.saturation, reason=base.reason,
                             by=base.by)
        else:
            # 규칙 기본: 벗어난 것만 고치는 레시피 + 내추럴 룩을 약하게(원본의 인상을 지킨다)
            choice = grade.plan_choice(raw_frames, corr, "natural", ref_lab, skin_rgb=skin_rgb, strength=0.5)
            studio = self._ensure_studio()
            if studio is not None:
                sheet = grade.comparison_sheet([frames[i][1] for i in picks], corr, src_lab=src_lab, ref_lab=ref_lab,
                                               skin_rgb=skin_rgb)
                (self.work / "grade_sheet.jpg").write_bytes(sheet)
                scope_sheet = scopes.draw([("원본", [raw_frames[i] for i in picks])])
                try:
                    notes = ("스코프(정상 범위 밖만): " + scopes.summary(checks) + " / 교정: "
                             + (" · ".join(corr.notes) or "교정 필요 적음") + " / 이 영상 레시피(웜 리치 기준): "
                             + grade.recipe_summary(choice.recipe))
                    r = studio.grade(f"# 색보정\n주제: {self.title}", notes, ("grade_sheet", sheet, "image/jpeg"),
                                     ("scopes", scope_sheet, "image/jpeg"))
                    choice = grade.plan_choice(raw_frames, corr, str(r.get("look", "natural")), ref_lab,
                                               skin_rgb=skin_rgb, strength=float(r.get("strength", 0.6) or 0.0),
                                               exposure=float(r.get("exposure", 0) or 0),
                                               warmth=float(r.get("warmth", 0) or 0),
                                               saturation=float(r.get("saturation", 1) or 1),
                                               reason=str(r.get("reason", "")), by="ai").clamp()
                except (DirectorError, ValueError, TypeError) as e:
                    self.log(f"🎨 컬러리스트 실패 → 규칙(내추럴 약하게): {e}")
        qc: dict[str, Any] = {"noise_gain": 1.0, "backoff": []}
        identity = untouched or grade.is_identity(corr, choice)
        cube = self._cube(cam.idx)
        if identity:
            cube.unlink(missing_ok=True)      # 예전 실행의 LUT 이 남아 프록시에 걸리지 않게
        else:
            # 보정 뒤 검사: 압축 색 잡음을 1.5배 넘게 키우면(얼룩) 세기·채도를 줄인다
            choice, qc = grade.qc_backoff(raw_frames, corr, choice)
            for line in qc["backoff"]:
                self.log(f"🎨 {who}검사: {line}")
            grade.write_cube(cube, corr, choice)
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
            self.log(f"🎨 {who}색 변화: 따뜻함(b) {src_lab[2]:+.1f} → {after[2]:+.1f} · 진하기(C) {src_lab[3]:.1f} → "
                     f"{after[3]:.1f}")
            self.log(f"🎨 {who}색보정: {', '.join(corr.notes) or '교정 거의 없음'} → 룩 '{grade.LOOKS[choice.look].label}'"
                     f"(세기 {choice.strength:.1f}{', AI 선택' if choice.by == 'ai' else ''})"
                     + (f" — {choice.reason}" if choice.reason and first else ""))
            self.log(f"🎨 {who}이 영상에 맞춘 양: {grade.recipe_summary(choice.recipe)} · 보정 뒤 스코프: "
                     + scopes.summary(after_checks) + f" · 색 잡음 ×{qc['noise_gain']:.2f}")
        plan = grade.plan_to_dict(stats, corr, choice, filters)
        plan.update(lut=not identity, scopes={"before": [c.to_dict() for c in checks],
                                              "after": [c.to_dict() for c in after_checks], **qc})
        return plan, choice

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
                self.claude = ClaudeCodeClient(exe, self.settings.claude_model, self.settings.claude_effort,
                                               log=self.log, workdir=self.work / "claude_code")
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
        return self.studio

    def _stock_enabled(self) -> bool:
        s = self.settings
        return self.spec.fetch_stock and (bool(getattr(s, "keyless_stock", True)) or any(
            [s.pixabay_api_key, s.unsplash_access_key, s.coverr_api_key, s.pexels_api_key]))

    def stage_director(self) -> None:
        assert self.info
        brief = self._brief()
        tm0 = self._initial_timemap()
        ctx = shared_context(brief, self.utts, self.tags, tm0, tm0.duration)
        self.ctx = ctx
        mode = "studio" if (self.spec.studio_mode and self._use_api()) else "single"
        key = text_hash(shared_context(brief, self.utts, self.tags, None, 0.0), self.spec.shorts_count,
                        self.spec.short_max_sec, self.settings.claude_model, mode, self.spec.direction,
                        self._stock_enabled(), self.spec.motion_scenes, "plan-v4")
        saved = read_json(self.work / "plan.json", {})
        use_api = self._use_api()
        studio = self._ensure_studio()
        raw_long = raw_shorts = None
        if self.spec.reuse_plan and saved.get("key") == key and saved.get("long"):
            self.log("기획: 저장된 계획 사용")
            raw_long, raw_shorts = saved["long"], {"shorts": saved.get("shorts", [])}
            self.director_name = saved.get("director", "saved")
        elif studio is not None:
            self.director_name = f"AI 스튜디오 · {self._ai_label()} ({self.settings.claude_model})"
            self.log("🎬 AI 스튜디오 가동: 총괄 감독 → 전문 에이전트 병렬 작업")
            try:
                raw_long, raw_shorts = studio.plan(brief, ctx, shorts_count=self.spec.shorts_count,
                                                   progress=lambda f: self._stage("director", 0.95 * f))
                # 숏폼 PD 가 한 편도 못 냈을 때만 규칙으로 채운다 — 둘째 편을 억지로 채우지 않는다(제대로 된 한 편이 우선)
                if self.spec.shorts_count > 0 and not ((raw_shorts or {}).get("shorts") or []):
                    raw_shorts = fallback.shorts_plan(brief, self.utts, self.tags, count=1,
                                                      max_sec=self.spec.short_max_sec)
            except DirectorError as e:
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
            except DirectorError as e:
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
        self._check_cards(tm0)
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
        refused: list[str] = []
        script_n = norm(parse_script(self.spec.script).clean)
        for u in self.utts:
            if u.id in drop_ids and u.kept:
                un = norm(u.text)
                in_script = bool(script_n) and (u.script_span is not None or (
                    len(un) >= 6 and len(un) <= len(script_n) and fuzz.partial_ratio(un, script_n) >= 70))
                if in_script:
                    refused.append(f"S{u.id} 「{u.text[:30]}」")
                    continue
                u.status = "director_drop"
                u.note = next((d["reason"] for d in self.plan_long["drop"] if d["seg"] == u.id), "")
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

    def _check_cards(self, tm: TimeMap) -> None:
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
        studio = self._ensure_studio()
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
            failed = [g for g in todo if not res.get(g["card"]["id"], {}).get("ok")]
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
            cands = [u for u in order if not u.kept and u.status in ("retake", "director_drop", "meta") and u.words]
            if not cands:
                break
            owner = {id(w): u for u in cands for w in u.words}
            runs = fidelity.runs_of([u.words for u in cands])
            changed = False
            for i, s in enumerate(sents):
                if cov[i] >= 0.35:
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
        adds: list[Span] = []
        restores: list[fidelity.Restore] = []
        for i, s in enumerate(sents):
            if cov[i] >= fidelity.COVERED:
                continue
            after, before = fidelity.neighbors(i, cov, times)
            r = fidelity.find_restore(s, runs, in_edit=in_edit, after=after, before=before)
            if r is None or r.ratio - cov[i] < fidelity.MIN_GAIN:
                continue
            adds.append(Span(max(0.0, r.start - 0.06), min(self.info.duration, r.end + 0.12)))
            restores.append(r)
        # 인식기가 받아 적지 못한 말(작게 말함·위스퍼가 건너뛰거나 다른 문장으로 잘못 받아 적음): 빠진 대본 문장(연달아
        # 빠졌으면 묶어서)의 앞뒤 문장이 편집본에 있고, 그 사이 원본에 편집본에 없는 말소리(VAD)가 그 문장들을 말할 만한
        # 길이로 있으면 그 말소리를 넣고 자막은 대본 문장으로
        rate = sum(len(norm(w.text)) for w in edit_words) / max(1.0, sum(w.end - w.start for w in edit_words))
        lost = [i for i, s in enumerate(sents) if cov[i] < fidelity.COVERED
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
        unresolved = [(i, s) for i, s in enumerate(sents) if cov[i] < fidelity.COVERED
                      and not any(r.sentence == s.idx for r in restores)]
        # 그 문장 자리(앞뒤 문장 사이)의 편집본 발화가 문장을 절반 넘게 담으면 '인식이 달라 확인 못 함'(소리는 들어 있다)
        uncertain = [s.text for i, s in unresolved
                     if fidelity.present_ratio(s, runs, in_edit=in_edit, after=fidelity.neighbors(i, cov, times)[0],
                                               before=fidelity.neighbors(i, cov, times)[1]) >= 0.5]
        unresolved = [s for _, s in unresolved]
        missing = [s.text for s in unresolved if s.text not in uncertain]
        self.fidelity = {"sentences": len(sents), "restored": [r.text for r in restores], "missing": missing,
                         "uncertain": uncertain,
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
        self.timemap = TimeMap(keeps)
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
        photos = [g for gl in graphic_lists for g in gl if g["template"] == "photo"]
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
                if g["template"] != "photo":
                    keep.append(g)
                    continue
                q = g.get("image", "").strip()
                pl = plans.get(q) or MediaPlan(q)
                res = pl.result
                if res is None:
                    if g.get("wiki") or pl.kind == "brand":
                        # 고유명사·브랜드: 쓸 수 있는 이미지가 없으면 스톡으로 넘기지 않는다 — 틀린 사진보다 없는 게 낫다
                        self.log(f"자료 사진: '{q}' 는 쓸 수 있는 이미지가 없어 뺍니다")
                        continue
                    # 위키미디어·내 폴더에 없으면 버리지 않고 스톡 사진(Pixabay 등) 요청으로 넘긴다 — 다음 단계가 찾는다
                    if q and self._stock_enabled():
                        g = copy.deepcopy(g)
                        g["template"] = "broll"
                        g["stock"] = {"kind": "photo", "query_en": q, "query_ko": g.get("title", ""),
                                      "purpose": g.get("body", ""), "must_show": "",
                                      "context": self._seg_text(g.get("start_seg"))}
                        keep.append(g)
                    continue
                g = copy.deepcopy(g)
                g["image"] = f"images/{res.path.name}"
                g["credit"] = res.credit
                if res.origin == "logo":
                    g["logo"] = True
                    g["body"] = g.get("body") or "브랜드"
                elif pl.kind == "person" and pl.info and pl.info.get("description") and g.get("body") in ("", "인물"):
                    g["body"] = str(pl.info["description"])[:24]
                keep.append(g)
            gl[:] = keep
        self._stage("broll", 1.0)

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
        self.broll_log += res.credits
        left = hub.remaining()
        if left:
            self.log("🎞 남은 호출: " + " · ".join(f"{k} {v}회" for k, v in left.items()))

    def stage_sound(self) -> None:
        """🔊 효과음·배경음악 라이브러리 준비(처음 한 번 내려받고 이후 재사용, 실패 시 내장 효과음)."""
        if not (self.spec.sfx or self.spec.music):
            return
        lib = self._sound_lib(full=True)
        cats = sorted({s.category for s in lib.sfx if s.source != "synth"})
        self.log(f"🔊 효과음 {len(lib.sfx)}개(내려받은 카테고리 {len(cats)}) · 배경음악 {len(lib.bgm)}곡")

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
            stills = [(p.stem, p.read_bytes(), "image/jpeg") for _, p in frames if p.exists()]
            try:
                res = studio.review(self.ctx, self._qa_text(targets, lp), stills)
            except DirectorError as e:
                self.log(f"🧐 검수 실패 → 그대로 진행: {e}")
                break
            issues = [i for i in res.get("issues", []) or [] if i.get("action") != "none"
                      and i.get("severity") in ("high", "medium")]
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
        lower = self._lower_third(graphics, after=min(total, t_title + 3.4), total=total)
        if lower is not None:
            graphics = sorted(graphics + [lower], key=lambda g: g.start)
        kept: list[TimedGraphic] = []
        for g in graphics:
            g.end = min(g.end, total - 0.1)
            if g.end - g.start >= 1.5:
                kept.append(g)
        return kept, chapters

    def _lower_third(self, graphics: list[TimedGraphic], *, after: float, total: float) -> Optional[TimedGraphic]:
        """타이틀 뒤 화자 이름 + '오늘의 주제'(셜록현준 레퍼런스: 이 영상이 답할 질문을 5~6초 한 줄로 — 총괄 감독의 논지).
        얼굴만 보이는 첫 빈 자리(타이틀 뒤 60초 안, 4초 이상)에 둔다 — 예전엔 자리를 미리 잡아 두었다가 바로 뒤 그래픽에 밀려
        대개 빠졌다. 말에 맞춘 그래픽을 밀어내지 않으므로 그래픽이 아주 촘촘하면(빈 자리가 없으면) 넣지 않는다."""
        topic = topic_line(self.plan_long.get("summary", ""))
        want, need = (5.6, 4.0) if topic else (4.5, 3.0)
        t = after + 0.8
        for a, b in sorted([(g.start, g.end) for g in graphics if g.end > after] + [(total - 0.3, total)]):
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
                out.append(copy.deepcopy(g))
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
        seg_t = seg_edit_times(self.utts, self.timemap)
        punch_spans = self._punch_spans(seg_t)
        moments = self._moments(self.timemap)
        # 롱폼 무대 편집법: 챕터 카드에 목차, 챕터 끝에 그 챕터의 핵심 개념을 모은 정리 보드(7초) — 편집 감독이 얼굴로 힘을
        # 주는 강조 순간·펀치 구간은 덮지 않는다
        chapter_maps(lp["graphics"], lp["chapters"])
        recaps = chapter_recaps(lp["graphics"], lp["chapters"], self.timemap.duration,
                                avoid=punch_spans + [(m.t - 0.5, m.end + 0.5) for m in moments if m.intensity >= 2])
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
                             punch_spans=punch_spans)
        apply_edit(lp, ed)
        hid = dedupe_captions(lp["captions"], caption_overlays(lp))
        stacks = mark_stack_cues(lp["captions"], min_gap=18.0, avoid=text_graphic_spans(lp["graphics"]))
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
        apply_edit(hp, ed_h)
        dedupe_captions(hp["captions"], caption_overlays(hp))
        mark_stack_cues(hp["captions"], min_gap=4.0, avoid=text_graphic_spans(hp["graphics"]))
        strip_audio(hp)
        # 본편을 뒤로 밀고 앞에 붙인다
        shift_props(lp, hd)
        shift_decisions(ed, hd)
        prepend_props(lp, hp)
        ed.sfx = list(ed_h.sfx) + ed.sfx
        ed.bgm_swells = list(ed_h.bgm_swells) + ed.bgm_swells
        ed.bgm_dips = list(ed_h.bgm_dips) + ed.bgm_dips
        ed.bgm_switch = [round(hd, 3)] + ed.bgm_switch          # 본편은 새 곡으로
        # 하이라이트 → 본편(타이틀): 빛샘 전환 + 라이저
        fps = float(self.fps)
        lp["transitions"] = sorted(lp["transitions"] + [{"t": round(hd, 3), "type": "leak",
                                                         "dur": round(PARAMS["tx_frames"]["leak"] / fps, 3)}],
                                   key=lambda t: t["t"])
        ed.sfx.append({"t": round(max(0.0, hd - 2.5), 3), "category": "riser",
                       "gain_db": PARAMS["sfx_gain"].get("riser", -28), "prio": 5, "why": "하이라이트 → 본편"})
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
        if self.spec.make_long:
            graphics, chapters = self._timed_long()
            self.long_chapters = chapters
            lp, ed = self._final_long_props(graphics, chapters)
            voice = self.media / "long_voice.wav"
            if self._add_highlight(lp, ed):
                voice = self.media / "long_voice_full.wav"
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
                                 "moods": MOODS_LONG, "mood": self.plan_long.get("bgm_mood", ""), "short": False})
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
        lib = self._sound_lib(full=True) if (self.spec.sfx or self.spec.music) else None
        n = len(self.masters)
        for k, m in enumerate(self.masters):
            self.cancel.check()
            ed: EditDecisions = m["edit"]
            cues: list[SfxCue] = []
            if lib is not None and self.spec.sfx:
                for j, e in enumerate(ed.sfx):
                    snd = lib.pick(e["category"], seed=j)
                    if snd is None:
                        continue
                    cues.append(SfxCue(t=e["t"], path=str(snd.path), gain_db=e["gain_db"], peak=snd.peak,
                                       name=e["category"], fade_out=2.5 if e["category"] == "riser" else 0.0))
            bgm: Optional[BgmPlan] = None
            track = None
            songs: list = []
            if self.spec.bgm and Path(self.spec.bgm).exists():
                bgm = BgmPlan(path=self.spec.bgm, swells=ed.bgm_swells, dips=ed.bgm_dips)
            elif lib is not None and self.spec.music:
                track = lib.pick_bgm(m["moods"], wanted=m["mood"], min_duration=30 if m["short"] else 90,
                                     seed=len(self.title) + k)
                if track is not None:
                    songs = lib.playlist(track, len(ed.bgm_switch) + 1, seed=k) if ed.bgm_switch else [track]
                    bgm = BgmPlan(path=str(track.path), lufs=track.lufs, swells=ed.bgm_swells, dips=ed.bgm_dips,
                                  # 참고 채널 실측: 목소리 아래 계속 깔리는 잔잔한 음악(숏폼 15~20dB, 롱폼 24~28dB 아래),
                                  # 쉼에서 크게 부풀지 않게
                                  under_db=-18.0 if m["short"] else -25.0, gap_db=-14.0 if m["short"] else -15.0,
                                  fade_out=1.2 if m["short"] else 3.0,
                                  playlist=[(str(t.path), t.lufs) for t in songs], switch_at=ed.bgm_switch)
            mix_wav = self.work / f"mix_{k}.wav"
            mix(self.ff, m["voice"], mix_wav, total=m["total"], sfx=cues, bgm=bgm, log=self.log,
                cancel=self.cancel)
            m["mix"] = mix_wav
            m["n_sfx"] = len(cues)
            m["bgm_title"] = (" / ".join(dict.fromkeys(t.credit for t in songs)) if track else
                              (Path(self.spec.bgm).name if self.spec.bgm else ""))
            progress((k + 1) / max(1, n))

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

    def _thumbnail_items(self) -> list[RenderItem]:
        assert self.info
        kept = self.timemap.keeps
        face = self._angles(self.long_pieces, self.timemap)[1]
        import bisect
        ks = [k.start for k in kept]

        def inside(t: float) -> bool:
            j = bisect.bisect_right(ks, t - 0.5) - 1
            return j >= 0 and t <= kept[j].end - 0.5
        cands = [s for s in face if 0.25 < s["x"] < 0.75 and inside(s["t"])]
        cands.sort(key=lambda s: -s["s"])
        picks: list[dict] = []
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
            props = {"width": 1280, "height": 720, "brand": {
                "name": self.settings.brand.name, "shortName": self.settings.brand.short_name,
                "handle": self.settings.brand.handle, "presenter": self.settings.brand.presenter,
                "presenterTitle": self.settings.brand.presenter_title, "accent": self.settings.brand.accent,
                "ink": self.settings.brand.ink, "paper": self.settings.brand.paper, "year": self.settings.brand.year},
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
        credits = sorted({b["credit"] + (f" ({b['url']})" if b.get("url") else "") for b in self.broll_log
                          if b.get("credit")})
        music = sorted({m.get("bgm_title", "") for m in self.masters if m.get("bgm_title")})
        chapters = getattr(self, "long_chapters", [])
        if self.long_props:
            write_text(self.extras / "롱폼_자막.srt", cues_to_srt(self.long_props["captions"]))
        for i, sp in enumerate(self.short_props, 1):
            write_text(self.extras / f"숏폼{i}_자막.srt", cues_to_srt(sp["captions"]))
        self._review_sheets()
        text = youtube_text(self.plan_long, chapters, self.plan_shorts, credits)
        if music:
            text += "\n## 배경음악\n" + "\n".join(f"- {m}" for m in music) + "\n"
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
                             qa=self.qa_log or (self.plan_long.get("qa") or {}).get("rounds"))
        report += self._craft_report()
        write_text(self.extras / "편집리포트.md", report)
        shutil.copyfile(self.work / "plan.json", self.extras / "plan.json")
        self.results["extras"] = str(self.extras)
        self.results["upload_info"] = str(self.out / "업로드정보.txt")

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


def template_names() -> list[str]:
    return list(TEMPLATES.keys())
