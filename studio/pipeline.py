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
import time
import traceback
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from . import diag
from .agents.studio import Studio
from .asr.transcribe import gpu_expected, load_audio_16k, speech_regions, transcribe
from .broll.entities import find_entities
from .broll.images import Wikimedia, list_local_images, resolve_image
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
from .edit.verify import find_issues, subtract, to_source
from .eta import Eta, features
from .export.premiere import export_xml
from .export.report import edit_report, write_text, youtube_text
from .grade import auto as grade
from .media.audio import build_voice_track
from .media.ffmpeg import FFmpeg, MediaInfo, hdr_to_sdr_filter, pick_output_fps
from .media.mix import BgmPlan, SfxCue, mix, mux_final
from .media.sources import (Piece, Quality, SourceMap, analyze_sources, angle_cut_times, angle_summary, choose_angles,
                            clips_for, face_track, master_audio_args, visual_scorer)
from .models import Span, Tag, TimeMap, Utterance, Word
from .net import redact
from .paths import USER_DIR
from .render.assets import copy_fonts, make_grain, make_paper
from .render.props import (Episode, apply_edit, caption_overlays, dedupe_captions, long_props, mark_soft_cuts,
                           mark_stack_cues, short_beats, short_props, strip_audio, text_graphic_spans)
from .render.remotion import RenderItem, RenderJob, find_node, run_render
from .settings import Settings
from .sound.library import MOODS_LONG, MOODS_SHORT, SoundLibrary
from .stock.providers import StockHub
from .stock.research import StockResearcher, strip_stock_images
from .text.align import ScriptAligner, build_utterances, norm
from .text.takes import clean_words, vad_pause
from .text.captions import cues_to_srt
from .text.script import glossary_terms, parse_script
from .util import (CancelToken, LogFn, file_fingerprint, fmt_ts, noop_log, read_json, slugify, text_hash,
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
    shorts_count: int = 2
    short_max_sec: int = 55
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

    def _eta_plan(self, keys: list[str]) -> None:
        ai = self._use_api()
        gpu = gpu_expected(self.settings.whisper_device, self.log)
        variants = {"asr": "asr@gpu" if gpu else "asr@cpu", "verify": "verify@gpu" if gpu else "verify@cpu",
                    "director": "director@ai" if ai else "director@rule",
                    "qa": "qa@ai" if ai else "qa@rule",
                    "stock": ("stock@ai" if ai else "stock@rule") if self._stock_enabled() else "stock@off"}
        self.eta.plan(keys, variants, self._eta_features())

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
        """until='plan' 이면 기획까지만, 'all' 이면 렌더·마스터링·마무리까지."""
        t0 = time.time()
        write_json(self.dir / "job.json", self.spec.to_dict())
        steps: list[tuple[str, Callable[[], None]]] = [
            ("probe", self.stage_probe), ("audio", self.stage_audio), ("face", self.stage_face),
            ("asr", self.stage_asr), ("align", self.stage_align), ("grade", self.stage_grade),
            ("director", self.stage_director),
        ]
        if until != "plan":
            steps += [("proxy", self.stage_proxy), ("verify", self.stage_verify), ("broll", self.stage_broll),
                      ("stock", self.stage_stock),
                      ("sound", self.stage_sound), ("qa", self.stage_qa), ("render", self.stage_render),
                      ("master", self.stage_master), ("export", self.stage_export)]
        self.eta.begin()
        srcs = self.spec.sources()
        self.log(f"══ 작업 시작 {time.strftime('%Y-%m-%d %H:%M')} · 원본 {Path(srcs[0]).name}"
                 + (f" 외 {len(srcs) - 1}개" if len(srcs) > 1 else ""))
        try:
            for key, fn in steps:
                self.cancel.check()
                self.log(f"━━ {STAGE_LABEL[key]}")
                self.eta.start(key)
                t_stage = time.time()
                self._stage(key, 0.0)
                fn()
                self._stage(key, 1.0)
                self.eta.finish(key)
                self._log_file_only(f"   ({STAGE_LABEL[key]} {time.time() - t_stage:.1f}s)")
                if key == "probe":
                    self._eta_plan([k for k, _ in steps])
                elif key == "proxy":
                    self._eta_refine()
                elif key == "grade":
                    self._preview(self.extras / "색보정_전후.jpg", "자동 색보정 · 왼쪽 원본 / 오른쪽 보정")
        except Exception as e:
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
                        self.smap.to_dict() if multi else "", "v5")
        voice = self.work / "voice.wav"
        asr = self.work / "asr16k.wav"
        meta = read_json(self.work / "audio.json", {})
        if meta.get("key") == key and voice.exists() and asr.exists():
            self.log("목소리: 캐시 사용")
            return
        self.log("목소리: " + ("신경망 잡음 제거(RNNoise) + 방송용 EQ·컴프레서" if model
                              else "잡음 제거 + 방송용 EQ·컴프레서"))
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
                         hint_terms=hints, duration=self.info.duration, log=self.log, progress=self._sp("asr"),
                         cancel=self.cancel)
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
        kept = [u for u in self.utts if u.kept] or self.utts
        vt = [((u.start + u.end) / 2) for u in kept]
        cams = self.smap.cams
        times = {c.idx: self._grade_times(c, vt) for c in cams}
        ref_lab = grade.reference_lab(USER_DIR / "reference_frames")
        key = text_hash([(file_fingerprint(c.path), [round(t, 1) for t in times[c.idx]]) for c in cams], self._use_api(),
                        [round(v, 1) for v in ref_lab], "grade-v3")
        cached = read_json(self.work / "grade.json", {})
        if cached.get("key") == key and all(self._cube(c.idx).exists() for c in cams):
            self.grade_info = cached
            self.log(f"🎨 색보정: 캐시 사용({grade.LOOKS[cached['choice']['look']].label})")
            return
        base: Optional[grade.GradeChoice] = None
        per_cam: dict[str, dict] = {}
        for n, cam in enumerate(cams):
            plan, choice = self._grade_cam(cam, times[cam.idx], ref_lab, base, first=(n == 0))
            if n == 0:
                base = choice
                self.grade_info = {"key": key, **plan}
            per_cam[str(cam.idx)] = {"filters": plan.get("filters", []),
                                     "notes": plan.get("correction", {}).get("notes", [])}
            self._stage("grade", (n + 1) / len(cams))
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
        corr = grade.correction_from_stats(stats)
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
        raw_frames = [f for _, f in frames]
        if base is not None:          # 두 번째 카메라부터: 같은 룩·세기, 레시피는 이 카메라의 상태로 다시
            choice = replace(grade.plan_choice(raw_frames, corr, base.look, ref_lab), strength=base.strength,
                             exposure=base.exposure, warmth=base.warmth, saturation=base.saturation, reason=base.reason,
                             by=base.by)
        else:
            choice = grade.plan_choice(raw_frames, corr, "warm_rich", ref_lab)
            studio = self._ensure_studio()
            if studio is not None:
                sheet = grade.comparison_sheet([frames[i][1] for i in picks], corr, src_lab=src_lab, ref_lab=ref_lab)
                (self.work / "grade_sheet.jpg").write_bytes(sheet)
                try:
                    notes = (" · ".join(corr.notes) or "교정 필요 적음") + " / 이 영상 레시피(웜 리치 기준): " + \
                        grade.recipe_summary(choice.recipe)
                    r = studio.grade(f"# 색보정\n주제: {self.title}", notes, ("grade_sheet", sheet, "image/jpeg"))
                    choice = grade.plan_choice(raw_frames, corr, str(r.get("look", "warm_rich")), ref_lab,
                                               strength=float(r.get("strength", 0.9) or 0.9),
                                               exposure=float(r.get("exposure", 0) or 0),
                                               warmth=float(r.get("warmth", 0) or 0),
                                               saturation=float(r.get("saturation", 1) or 1),
                                               reason=str(r.get("reason", "")), by="ai").clamp()
                except (DirectorError, ValueError, TypeError) as e:
                    self.log(f"🎨 컬러리스트 실패 → 웜 리치: {e}")
        grade.write_cube(self._cube(cam.idx), corr, choice)
        filters = grade.cleanup_filters(stats)
        if first:
            grade.before_after(frames[picks[0]][1], corr, choice, self.extras / "색보정_전후.jpg")
        after = grade.lab_stats(np.concatenate([grade.grade(f, corr, choice).reshape(-1, 3) for _, f in frames[:6]]))
        who = f"[{Path(cam.path).name}] " if not self.smap.single else ""
        self.log(f"🎨 {who}색 변화: 따뜻함(b) {src_lab[2]:+.1f} → {after[2]:+.1f} · 진하기(C) {src_lab[3]:.1f} → "
                 f"{after[3]:.1f} (레퍼런스 b {ref_lab[2]:+.1f} · C {ref_lab[3]:.1f})")
        self.log(f"🎨 {who}색보정: {', '.join(corr.notes) or '교정 거의 없음'} → 룩 '{grade.LOOKS[choice.look].label}'"
                 f"(세기 {choice.strength:.1f}{', AI 선택' if choice.by == 'ai' else ''})"
                 + (f" — {choice.reason}" if choice.reason and first else ""))
        self.log(f"🎨 {who}이 영상에 맞춘 양: {grade.recipe_summary(choice.recipe)}")
        return grade.plan_to_dict(stats, corr, choice, filters), choice

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
                        self._stock_enabled(), self.spec.motion_scenes, "plan-v3")
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
                if self.spec.shorts_count > 0 and len((raw_shorts or {}).get("shorts") or []) < self.spec.shorts_count:
                    extra = fallback.shorts_plan(brief, self.utts, self.tags, count=self.spec.shorts_count,
                                                 max_sec=self.spec.short_max_sec)
                    have = (raw_shorts or {}).get("shorts") or []
                    raw_shorts = {"shorts": have + extra["shorts"][: self.spec.shorts_count - len(have)]}
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
        self.plan_shorts = normalize_shorts(raw_shorts, self.utts, count=self.spec.shorts_count)
        if not self.spec.title.strip() and self.plan_long.get("title"):
            self.title = self.plan_long["title"]
            self.slug = slugify(self.title, 30)
        self._plan_key = key
        self._save_plan()
        write_json(self.work / "plan_raw.json", {"long": raw_long, "shorts": raw_shorts})
        drop_ids = {d["seg"] for d in self.plan_long.get("drop", [])}
        for u in self.utts:
            if u.id in drop_ids and u.kept:
                u.status = "director_drop"
                u.note = next((d["reason"] for d in self.plan_long["drop"] if d["seg"] == u.id), "")
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
        self.base_keeps = self.smap.clamp_keeps(
            build_keeps(self.utts, pace=self._pace(), vad=self.vad, media_duration=self.info.duration, fps=self.fps,
                        exclude=self._removed_spans()), self.fps)
        ver = read_json(self.work / "verify.json", {})
        self.edit_drops = [Span(a, b) for a, b in ver.get("drops", [])] \
            if ver.get("base") == self._keeps_key(self.base_keeps) else []
        self._make_cuts()
        if self.smap.multicam:
            self.log("🎥 앵글(롱폼): " + angle_summary(self.long_pieces, self.smap))

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
        self.timemap = TimeMap(keeps)
        write_json(self.work / "keeps_long.json", self.timemap.to_list())
        starts = sorted(u.start for u in self.utts if u.kept)
        self.long_pieces = choose_angles(self.timemap.keeps, self.smap, self.quality, sentence_starts=starts)
        if self.spec.make_long:
            cut_audio(self.ff, self.work / "voice.wav", self.timemap.keeps, self.media / "long_voice.wav", self.work,
                      log=self.log, cancel=self.cancel)
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
                             compute_type=self.settings.whisper_compute, hint_terms=hints,
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
        local = list_local_images(self.spec.images_dir)
        wm = Wikimedia(self.settings.wikimedia_contact, log=self.log, cache_dir=self.work / "wm_cache") \
            if self.spec.fetch_broll else None
        # 고유명사(인물·종교·사물·브랜드·작품)는 위키백과 문서의 대표 이미지가 커먼즈 검색·스톡보다 정확하다
        wp = WikipediaImages(self.settings.wikimedia_contact, log=self.log, cache_dir=self.work / "wm_cache") \
            if self.spec.fetch_broll else None
        img_dir = self.public / "images"
        graphic_lists = [self.plan_long["graphics"]] + [s["graphics"] for s in self.plan_shorts]
        total = sum(1 for gl in graphic_lists for g in gl if g["template"] == "photo") or 1
        n = 0
        cache: dict[str, Any] = {}
        for gl in graphic_lists:
            keep = []
            for g in gl:
                if g["template"] != "photo":
                    keep.append(g)
                    continue
                q = g.get("image", "").strip()
                if q not in cache:
                    cache[q] = resolve_image(q, local=local, dst_dir=img_dir, wikimedia=wm, wikipedia=wp, log=self.log)
                    res = cache[q]
                    self.broll_log.append({"query": q, **(res.to_dict() if res else {"origin": "없음"})})
                    if res is not None:
                        self._preview(res.path, f"자료 사진 · {q}")
                res = cache[q]
                n += 1
                self._stage("broll", n / total)
                if res is None:
                    if g.get("wiki"):
                        # 위키백과 전용(고유명사): 문서·자유 이미지가 없으면 스톡으로 넘기지 않는다 — 틀린 사진보다 없는 게 낫다
                        self.log(f"자료 사진: '{q}' 는 위키백과에 쓸 수 있는 이미지가 없어 뺍니다")
                        continue
                    # 위키미디어·내 폴더에 없으면 버리지 않고 스톡 사진(Pixabay 등) 요청으로 넘긴다 — 다음 단계가 찾는다
                    if q and self._stock_enabled():
                        g = copy.deepcopy(g)
                        g["template"] = "broll"
                        g["stock"] = {"kind": "photo", "query_en": q, "query_ko": g.get("title", ""),
                                      "purpose": g.get("body", ""), "must_show": ""}
                        keep.append(g)
                    continue
                g = copy.deepcopy(g)
                g["image"] = f"images/{res.path.name}"
                g["credit"] = res.credit
                keep.append(g)
            gl[:] = keep

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
            chapters.append({"start": round(start, 3), "title": c["title"], "number": f"{len(chapters) + 1:02d}"})
        reserved: list[TimedGraphic] = []
        tseg = self.plan_long.get("title_card_seg", -1)
        t_title = seg_t[tseg][0] if tseg in seg_t else 0.2
        t_title = max(0.2, t_title - 0.1)
        reserved.append(TimedGraphic("title", "title", "fullscreen", t_title, min(total, t_title + 3.4),
                                     {"title": self.title}, priority=12, source="auto"))
        lt = t_title + 4.2
        if lt + 4.5 < total:
            reserved.append(TimedGraphic("lower", "lower_third", "overlay", lt, lt + 4.5, {}, priority=4, source="auto"))
        for c in chapters[1:]:
            if c["start"] < t_title + 4:
                continue
            reserved.append(TimedGraphic(f"ch{c['number']}", "chapter", "fullscreen", max(0.0, c["start"] - 0.1),
                                         min(total, c["start"] + 2.6), {"title": c["title"], "number": c["number"]},
                                         priority=11, source="auto"))
        graphics = time_graphics(self.plan_long["graphics"], self.utts, tm, total=total, reserved=reserved)
        kept: list[TimedGraphic] = []
        for g in graphics:
            g.end = min(g.end, total - 0.1)
            if g.end - g.start >= 1.5:
                kept.append(g)
        return kept, chapters

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
        seg_t = seg_edit_times(self.utts, self.timemap)
        looks = None
        if self._hybrid:
            by_id = {u.id: u for u in self.utts}

            def text_between(a: float, b: float) -> str:
                return " ".join(by_id[i].text for i, (s0, _) in seg_t.items() if a <= s0 < b and i in by_id)

            looks = choose_looks(lp["graphics"], lp["chapters"], self.timemap.duration, text_between)
            apply_looks(lp, looks)
            self.look_plan = looks
            self.log("🎨 화면 구성(자동 · 하이브리드): " + looks.summary())
        ed = build_long_edit(timemap=self.timemap, total=lp["duration"], speech_total=self.timemap.duration,
                             graphics=lp["graphics"], chapters=lp["chapters"], moments=self._moments(self.timemap),
                             cues=lp["captions"], sentence_starts=sorted(a for a, _ in seg_t.values()),
                             text_graphic_spans=text_graphic_spans(lp["graphics"]), endcard=self.spec.endcard,
                             face=lp.get("face"),
                             P=PARAMS if (self.spec.skin == "paper" or looks) else {**PARAMS, "framed_every": 0},
                             framed_ranges=looks.paper_ranges() if looks else None, angle_cuts=angle_cuts)
        apply_edit(lp, ed)
        hid = dedupe_captions(lp["captions"], caption_overlays(lp))
        stacks = mark_stack_cues(lp["captions"], min_gap=18.0, avoid=text_graphic_spans(lp["graphics"]))
        self.log(f"💬 자막: 한두 마디 {len(lp['captions'])}개 · 두 층 강조 {stacks}개"
                 + (f" · 화면 그래픽과 같은 말이라 숨김 {hid}개(SRT 에는 남김)" if hid else ""))
        strip_audio(lp)
        return lp, ed

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
            self.long_props = lp
            lp["peekEvery"] = peek_every
            p = self.render_dir / "props_long.json"
            write_json(p, lp)
            raw = raw_dir / "long.mp4"
            items.append(RenderItem("video", "LongForm", p, raw, scale=scale, crf=rs.crf, x264_preset=rs.x264_preset,
                                    weight=lp["duration"], muted=True, peek_dir=str(peek_dir)))
            labels.append(("롱폼", lp["duration"]))
            self.masters.append({"name": "롱폼", "raw": raw, "voice": self.media / "long_voice.wav",
                                 "dst": self.out / f"1_롱폼_{self.slug}.mp4", "edit": ed, "total": lp["duration"],
                                 "moods": MOODS_LONG, "mood": self.plan_long.get("bgm_mood", ""), "short": False})
            self.log(f"✂️ 롱폼 편집: 샷 {ed.stats['shots']} · 전환 {ed.stats['transitions']} · 강조 글라이드 "
                     f"{ed.stats['punches']} · 강조 자막 {ed.stats['impact_captions']} · 효과음 {ed.stats['sfx']}"
                     f" · 얼굴 화면 비율 {ed.stats['face_ratio'] * 100:.0f}%")
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
                                  moments=self._moments(tm, set(s["segments"])), seed=i, angle_cuts=angle_cuts)
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

        run_render(job, self.render_dir / "job.json", node=node, log=self.log, progress=self._sp("render"),
                   cancel=self.cancel, on_peek=on_peek)

    # ------------------------------------------------------------------
    def stage_master(self) -> None:
        """🎚 음향: 컷 편집된 목소리 + 배경음악(자동 덕킹) + 효과음 → -14 LUFS 마스터 → 영상과 합치기."""
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
            mux_final(self.ff, m["raw"], mix_wav, m["dst"], log=self.log, cancel=self.cancel)
            m["bgm_title"] = (" / ".join(dict.fromkeys(t.credit for t in songs)) if track else
                              (Path(self.spec.bgm).name if self.spec.bgm else ""))
            self.log(f"🎚 {m['name']}: 효과음 {len(cues)}개 · 배경음악 "
                     f"{m['bgm_title'] or '없음'} · -14 LUFS 마스터 → {m['dst'].name}")
            self._stage("master", (k + 1) / max(1, n))
        self.results["long"] = str(self.masters[0]["dst"]) if self.masters and not self.masters[0]["short"] else ""
        self.results["shorts"] = [str(m["dst"]) for m in self.masters if m["short"]]

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
                export_xml(self.extras / "롱폼_premiere.xml", name=f"{self.title} (자동 컷)",
                           video=Path(self.spec.video), audio=voice, src_fps=self.info.fps, src_duration=self.info.duration,
                           width=w, height=h, seq_width=w, seq_height=h, keeps=self.timemap.keeps, markers=markers,
                           pieces=xml_pieces(self.long_pieces), files=files)
            short_pieces = getattr(self, "short_pieces", []) or []
            for i, tm in enumerate(getattr(self, "short_maps", []), 1):
                export_xml(self.extras / f"숏폼{i}_premiere.xml", name=f"숏폼 {i}", video=Path(self.spec.video),
                           audio=voice, src_fps=self.info.fps, src_duration=self.info.duration, width=w, height=h,
                           seq_width=1080, seq_height=1920, keeps=tm.keeps, markers=[],
                           pieces=xml_pieces(short_pieces[i - 1]) if i <= len(short_pieces) else None, files=files)
        report = edit_report(title=self.title, source_duration=self.info.duration,
                             long_duration=self.timemap.duration, align_report=self.align_report, utts=self.utts,
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
        if self.look_plan:
            lines.append("- 화면 구성(자동 · 하이브리드): " + self.look_plan.summary())
        g = self.grade_info or {}
        if g:
            ch = g.get("choice", {})
            lines.append(f"- 색보정: {', '.join(g.get('correction', {}).get('notes', [])) or '교정 거의 없음'} → 룩 "
                         f"{grade.LOOKS.get(ch.get('look', 'natural'), grade.LOOKS['natural']).label}"
                         f"(세기 {ch.get('strength', 1):.1f}) {ch.get('reason', '')}")
        for m in self.masters:
            st = m["edit"].stats
            lines.append(f"- {m['name']}: " + " · ".join(f"{k} {v}" for k, v in st.items())
                         + f" · 배경음악 {m.get('bgm_title') or '없음'}")
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------


def template_names() -> list[str]:
    return list(TEMPLATES.keys())
