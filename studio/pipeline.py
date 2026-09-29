"""전체 파이프라인: 원본 영상 + 대본 + 메모 → 롱폼/숏폼/썸네일/자막/프리미어 XML/리포트.

각 단계 결과는 작업 폴더(work/)에 캐시되어, 재실행하면 바뀐 단계부터만 다시 한다.
"""
from __future__ import annotations

import copy
import datetime as dt
import shutil
import time
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Optional

from .asr.transcribe import load_audio_16k, speech_regions, transcribe
from .broll.images import Wikimedia, list_local_images, resolve_image
from .director import fallback
from .director.catalog import TEMPLATES
from .director.claude import ClaudeClient, DirectorError
from .director.context import JobBrief, long_instruction, shared_context, shorts_instruction, system_prompt
from .director.plan import TimedGraphic, normalize_long, normalize_shorts, resolve_overlaps, seg_edit_times, time_graphics
from .director.schema import LONG_PLAN, SHORTS_PLAN
from .edit.assemble import build_proxy, cut_audio, proxy_height_for
from .edit.cuts import PACES, build_keeps, keeps_for_segments
from .export.premiere import export_xml
from .export.report import edit_report, write_text, youtube_text
from .media.audio import build_voice_track
from .media.ffmpeg import FFmpeg, MediaInfo, hdr_to_sdr_filter, pick_output_fps
from .models import Span, Tag, TimeMap, Utterance, Word
from .render.assets import copy_fonts, make_grain, make_sfx
from .render.props import Episode, long_props, short_props
from .render.remotion import RenderItem, RenderJob, find_node, run_render
from .settings import Settings
from .text.align import ScriptAligner, build_utterances
from .text.captions import cues_to_srt
from .text.script import glossary_terms, parse_script
from .util import (CancelToken, LogFn, file_fingerprint, noop_log, read_json, slugify, text_hash, write_json)
from .vision.face import track_faces

StageProgress = Callable[[str, float, float], None]  # (단계 키, 단계 진행률, 전체 진행률)

STAGES: list[tuple[str, str, float]] = [
    ("probe", "영상 정보 확인", 1),
    ("audio", "보이스 정리(노이즈·라우드니스)", 4),
    ("asr", "음성 인식(Whisper)", 22),
    ("align", "대본 정렬 · NG/리테이크 제거", 2),
    ("face", "얼굴 추적", 6),
    ("director", "편집 계획(Claude)", 8),
    ("proxy", "렌더용 프록시·오디오 컷", 10),
    ("broll", "자료 사진 확보", 3),
    ("render", "렌더링(Remotion)", 42),
    ("export", "자막·XML·리포트 내보내기", 2),
]
STAGE_LABEL = {k: v for k, v, _ in STAGES}


@dataclass
class JobSpec:
    video: str
    title: str
    audio: str = ""
    episode: str = ""
    subtitle: str = ""
    series: str = "디자인 이론"
    notes: str = ""
    script: str = ""
    images_dir: str = ""
    bgm: str = ""
    lut: str = ""
    # 옵션
    make_long: bool = True
    shorts_count: int = 2
    short_max_sec: int = 55
    out_height: int = 1080
    pace: str = "calm"
    use_claude: bool = True
    fetch_broll: bool = True
    grain: bool = True
    caption_style: str = "shadow"
    thumbnails: bool = True
    sfx: bool = True
    enhance_voice: bool = True
    shorts_layout: str = "full"
    progress_bar: bool = False
    endcard: bool = True
    reuse_plan: bool = True
    export_xml: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "JobSpec":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


def new_job_dir(settings: Settings, title: str) -> Path:
    base = Path(settings.projects_dir)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M")
    d = base / f"{stamp}_{slugify(title, 30)}"
    d.mkdir(parents=True, exist_ok=True)
    return d


class Pipeline:
    def __init__(self, spec: JobSpec, settings: Settings, job_dir: Path, *, log: LogFn = noop_log,
                 progress: Optional[StageProgress] = None, cancel: Optional[CancelToken] = None):
        self.spec = spec
        self.settings = settings
        self.dir = Path(job_dir)
        self.work = self.dir / "work"
        self.media = self.dir / "media"
        self.render_dir = self.dir / "render"
        self.public = self.render_dir / "public_src"
        self.out = self.dir / "output"
        for d in (self.work, self.media, self.public, self.out):
            d.mkdir(parents=True, exist_ok=True)
        self.log = log
        self._progress = progress or (lambda *_: None)
        self.cancel = cancel or CancelToken()
        self.ff = FFmpeg(settings.ffmpeg_path, settings.ffprobe_path)
        self.slug = slugify(spec.title, 30)
        # 단계 사이에 공유하는 상태
        self.info: Optional[MediaInfo] = None
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
        self.broll_log: list[dict] = []

    # ------------------------------------------------------------------
    def _stage(self, key: str, frac: float) -> None:
        idx = [k for k, _, _ in STAGES].index(key)
        total = sum(w for _, _, w in STAGES)
        before = sum(w for _, _, w in STAGES[:idx])
        overall = (before + STAGES[idx][2] * max(0.0, min(1.0, frac))) / total
        self._progress(key, frac, overall)

    def _sp(self, key: str):
        return lambda f: self._stage(key, f)

    def run(self, until: str = "all") -> dict[str, Any]:
        """until='plan' 이면 편집 계획까지만(검토용), 'all' 이면 렌더/내보내기까지."""
        t0 = time.time()
        write_json(self.dir / "job.json", self.spec.to_dict())
        steps: list[tuple[str, Callable[[], None]]] = [
            ("probe", self.stage_probe), ("audio", self.stage_audio), ("asr", self.stage_asr),
            ("align", self.stage_align), ("face", self.stage_face), ("director", self.stage_director),
        ]
        if until != "plan":
            steps += [("proxy", self.stage_proxy), ("broll", self.stage_broll), ("render", self.stage_render),
                      ("export", self.stage_export)]
        for key, fn in steps:
            self.cancel.check()
            self.log(f"━━ {STAGE_LABEL[key]}")
            self._stage(key, 0.0)
            fn()
            self._stage(key, 1.0)
        self.log(f"완료 ({(time.time() - t0) / 60:.1f}분) → {self.out}")
        return {"output": str(self.out), "job_dir": str(self.dir)}

    # ------------------------------------------------------------------
    def stage_probe(self) -> None:
        self.info = self.ff.probe(self.spec.video)
        if not self.info.has_video:
            raise RuntimeError("영상 스트림이 없습니다: " + self.spec.video)
        if not self.info.has_audio and not self.spec.audio:
            raise RuntimeError("오디오가 없습니다. 별도 녹음 파일을 지정하세요.")
        self.fps = pick_output_fps(self.info)
        w, h = self.info.display_size
        self.log(f"원본 {w}x{h} · {self.info.fps:.2f}fps{' (VFR)' if self.info.vfr else ''} · "
                 f"{self.info.duration / 60:.1f}분 · {self.info.vcodec}{' · HDR' if self.info.is_hdr else ''}"
                 f" → 출력 {self.fps}fps")
        write_json(self.work / "probe.json", asdict(self.info))

    def stage_audio(self) -> None:
        assert self.info
        key = text_hash(file_fingerprint(self.spec.video),
                        file_fingerprint(self.spec.audio) if self.spec.audio else "", self.spec.enhance_voice, "v2")
        voice = self.work / "voice.wav"
        asr = self.work / "asr16k.wav"
        meta = read_json(self.work / "audio.json", {})
        if meta.get("key") == key and voice.exists() and asr.exists():
            self.log("보이스 트랙: 캐시 사용")
            return
        info = build_voice_track(self.ff, self.spec.video, voice, external_audio=self.spec.audio or None,
                                 duration=self.info.duration, enhance=self.spec.enhance_voice, log=self.log,
                                 progress=lambda f: self._stage("audio", f * 0.85), cancel=self.cancel)
        self.ff.extract_audio(voice, asr, rate=16000, mono=True, cancel=self.cancel, duration=self.info.duration)
        write_json(self.work / "audio.json", {"key": key, **info})

    def stage_asr(self) -> None:
        assert self.info
        parsed = parse_script(self.spec.script)
        hints = glossary_terms(parsed, extra=list(self.settings.glossary.values()))
        key = text_hash(file_fingerprint(self.work / "asr16k.wav"), self.settings.whisper_model, hints, "v1")
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
        utts = build_utterances(words)
        aligner = ScriptAligner(parsed, self.settings.glossary)
        self.utts, self.tags, rep = aligner.run(utts)
        self.align_report = rep.to_dict()
        audio = load_audio_16k(self.work / "asr16k.wav")
        self.vad = speech_regions(audio)
        write_json(self.work / "align.json", {"utterances": [u.to_dict() for u in self.utts],
                                              "tags": [t.to_dict() for t in self.tags],
                                              "report": self.align_report, "vad": self.vad})
        self.log(f"발화 {len(self.utts)}개 · 대본 일치 {rep.matched} · 리테이크 {rep.retakes} · NG {rep.meta}"
                 + (f" · 대본 커버리지 {rep.script_coverage * 100:.0f}%" if parsed.has_text else " (대본 없음)"))

    def stage_face(self) -> None:
        assert self.info
        key = text_hash(file_fingerprint(self.spec.video), "face-v1")
        cached = read_json(self.work / "face.json", {})
        if cached.get("key") == key:
            self.face = cached.get("samples", [])
            self.log("얼굴 추적: 캐시 사용")
            return
        res = track_faces(self.ff, self.spec.video, self.info, log=self.log, progress=self._sp("face"),
                          cancel=self.cancel)
        res["key"] = key
        write_json(self.work / "face.json", res)
        self.face = res["samples"]

    # ------------------------------------------------------------------
    def _brief(self) -> JobBrief:
        local = [p.name for p in list_local_images(self.spec.images_dir)]
        return JobBrief(title=self.spec.title, notes=self.spec.notes, episode=self.spec.episode,
                        subtitle=self.spec.subtitle, local_images=local, shorts_count=self.spec.shorts_count,
                        short_max_sec=self.spec.short_max_sec, presenter=self.settings.brand.presenter,
                        brand=self.settings.brand.name)

    def _pace(self):
        return PACES.get(self.spec.pace, PACES["calm"])

    def _initial_timemap(self) -> TimeMap:
        assert self.info
        keeps = build_keeps(self.utts, pace=self._pace(), vad=self.vad, media_duration=self.info.duration, fps=self.fps)
        return TimeMap(keeps)

    def stage_director(self) -> None:
        assert self.info
        brief = self._brief()
        tm0 = self._initial_timemap()
        ctx = shared_context(brief, self.utts, self.tags, tm0, tm0.duration)
        # 캐시 키는 내용만으로(템포 옵션을 바꿔도 Claude 를 다시 부르지 않도록 편집 시간은 제외)
        key = text_hash(shared_context(brief, self.utts, self.tags, None, 0.0), self.spec.shorts_count,
                        self.spec.short_max_sec, self.settings.claude_model, "plan-v1")
        saved = read_json(self.work / "plan.json", {})
        edited = self.out / "plan.json"
        if saved and edited.exists() and edited.stat().st_mtime > (self.work / "plan.json").stat().st_mtime + 1:
            # output/plan.json 을 사용자가 직접 고친 경우 그 내용을 우선
            user = read_json(edited, {})
            if user.get("long"):
                self.log("output/plan.json 의 수정 내용을 반영합니다.")
                saved = {**user, "key": saved.get("key")}
        use_api = self.spec.use_claude and bool(self.settings.anthropic_api_key)
        if self.spec.reuse_plan and saved.get("key") == key and saved.get("long"):
            self.log("편집 계획: 저장된 plan.json 사용 (직접 수정한 내용 반영)")
            raw_long, raw_shorts = saved["long"], {"shorts": saved.get("shorts", [])}
            self.director_name = saved.get("director", "saved")
        elif use_api:
            self.director_name = f"Claude ({self.settings.claude_model})"
            self.claude = ClaudeClient(self.settings.anthropic_api_key, self.settings.claude_model,
                                       self.settings.claude_effort, log=self.log)
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
                self.log("API 키가 없어 규칙 기반 편집으로 진행합니다(설정에서 Claude API 키 입력).")
            self.director_name = "규칙 기반"
            raw_long = fallback.long_plan(brief, self.utts, self.tags)
            raw_shorts = fallback.shorts_plan(brief, self.utts, self.tags, count=self.spec.shorts_count,
                                              max_sec=self.spec.short_max_sec)
        self.plan_long = normalize_long(raw_long, self.utts, self.tags)
        self.plan_shorts = normalize_shorts(raw_shorts, self.utts, count=self.spec.shorts_count)
        write_json(self.work / "plan.json", {"key": key, "director": self.director_name, "long": self.plan_long,
                                             "shorts": self.plan_shorts,
                                             "usage": self.claude.usage if self.claude else []})
        write_json(self.work / "plan_raw.json", {"long": raw_long, "shorts": raw_shorts})
        # 디렉터가 추가로 버린 발화
        drop_ids = {d["seg"] for d in self.plan_long.get("drop", [])}
        for u in self.utts:
            if u.id in drop_ids and u.kept:
                u.status = "director_drop"
                u.note = next((d["reason"] for d in self.plan_long["drop"] if d["seg"] == u.id), "")
        self.log(f"계획: 챕터 {len(self.plan_long['chapters'])} · 그래픽 {len(self.plan_long['graphics'])} · "
                 f"숏폼 {len(self.plan_shorts)} · 추가 컷 {len(drop_ids)}")

    # ------------------------------------------------------------------
    def stage_proxy(self) -> None:
        assert self.info
        height = proxy_height_for(self.info, self.spec.out_height)
        proxy = self.media / "proxy.mp4"
        key = text_hash(file_fingerprint(self.spec.video), self.fps, height,
                        file_fingerprint(self.spec.lut) if self.spec.lut else "", "proxy-v1")
        meta = read_json(self.media / "proxy.json", {})
        if meta.get("key") == key and proxy.exists():
            self.log("프록시: 캐시 사용")
        else:
            self.log(f"프록시 생성: {height}p · {self.fps}fps · {'NVENC' if self.ff.nvenc_ok else 'x264'}")
            build_proxy(self.ff, self.spec.video, self.info, proxy, fps=self.fps, height=height,
                        lut=self.spec.lut or None, log=self.log, progress=lambda f: self._stage("proxy", 0.8 * f),
                        cancel=self.cancel)
            write_json(self.media / "proxy.json", {"key": key, "height": height})
        # 최종 컷
        self.timemap = TimeMap(build_keeps(self.utts, pace=self._pace(), vad=self.vad,
                                           media_duration=self.info.duration, fps=self.fps))
        write_json(self.work / "keeps_long.json", self.timemap.to_list())
        if self.spec.make_long:
            cut_audio(self.ff, self.work / "voice.wav", self.timemap.keeps, self.media / "long_voice.wav", self.work,
                      log=self.log, cancel=self.cancel)
        self.short_maps: list[TimeMap] = []
        for i, s in enumerate(self.plan_shorts, 1):
            keeps = keeps_for_segments(self.utts, s["segments"], pace=PACES["shorts"], vad=self.vad,
                                       media_duration=self.info.duration, fps=self.fps)
            keeps = self._limit_short(keeps)
            tm = TimeMap(keeps, preserve_order=True)
            s["duration"] = tm.duration
            self.short_maps.append(tm)
            cut_audio(self.ff, self.work / "voice.wav", keeps, self.media / f"short_{i}_voice.wav", self.work,
                      log=self.log, cancel=self.cancel)
            self.log(f"숏폼 {i}: {tm.duration:.1f}초 · 구간 {len(keeps)}개")

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
                    cache[q] = resolve_image(q, local=local, dst_dir=img_dir, wikimedia=wm, log=self.log)
                    res = cache[q]
                    self.broll_log.append({"query": q, **(res.to_dict() if res else {"origin": "없음"})})
                res = cache[q]
                n += 1
                self._stage("broll", n / total)
                if res is None:
                    continue
                g = copy.deepcopy(g)
                g["image"] = f"images/{res.path.name}"
                g["credit"] = res.credit
                keep.append(g)
            gl[:] = keep

    # ------------------------------------------------------------------
    def _episode(self) -> Episode:
        return Episode(self.spec.title, self.spec.episode, self.spec.subtitle, self.spec.series)

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
                                     {"title": self.spec.title}, priority=12, source="auto"))
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

    def stage_render(self) -> None:
        assert self.info
        fonts_dir = self.public / "fonts"
        copy_fonts(fonts_dir)
        grain = make_grain(self.public / "fx") if self.spec.grain else []
        sfx = make_sfx(self.public / "sfx") if self.spec.sfx else {}
        links: list[tuple[Path, str]] = [(self.media / "proxy.mp4", "media/proxy.mp4")]
        bgm_src = None
        if self.spec.bgm and Path(self.spec.bgm).exists():
            ext = Path(self.spec.bgm).suffix.lower()
            links.append((Path(self.spec.bgm), f"media/bgm{ext}"))
            bgm_src = f"media/bgm{ext}"
        brand = self.settings.brand
        episode = self._episode()
        items: list[RenderItem] = []
        rs = self.settings.render
        scale = max(1.0, self.spec.out_height / 1080)
        self.long_props: dict = {}
        if self.spec.make_long:
            links.append((self.media / "long_voice.wav", "media/long_voice.wav"))
            graphics, chapters = self._timed_long()
            self.long_chapters = chapters
            lp = long_props(fps=self.fps, brand=brand, episode=episode, utts=self.utts, timemap=self.timemap,
                            graphics=graphics, chapters=chapters, emphasis=self.plan_long.get("emphasis", []),
                            face_src=self.face, voice_src="media/long_voice.wav", bgm_src=bgm_src, sfx=sfx,
                            grain_frames=grain, grain=0.06 if grain else 0.0,
                            caption_style=self.spec.caption_style, endcard=self.spec.endcard, use_sfx=self.spec.sfx)
            self.long_props = lp
            p = self.render_dir / "props_long.json"
            write_json(p, lp)
            items.append(RenderItem("video", "LongForm", p, self.out / f"{self.slug}_롱폼.mp4", scale=scale,
                                    crf=rs.crf, x264_preset=rs.x264_preset, weight=lp["duration"]))
        self.short_props: list[dict] = []
        for i, (s, tm) in enumerate(zip(self.plan_shorts, getattr(self, "short_maps", [])), 1):
            links.append((self.media / f"short_{i}_voice.wav", f"media/short_{i}_voice.wav"))
            sg = time_graphics(s["graphics"], self.utts, tm, total=tm.duration, min_start=3.0, id_prefix=f"s{i}g")
            for g in sg:
                g.layout = "split"
            series = f"{self.spec.series} #{self.spec.episode}" if self.spec.episode else self.spec.series
            sp = short_props(fps=self.fps, brand=brand, episode=episode, spec=s, utts=self.utts, timemap=tm,
                             graphics=sg, face_src=self.face, voice_src=f"media/short_{i}_voice.wav", bgm_src=bgm_src,
                             sfx=sfx, grain_frames=grain, grain=0.05 if grain else 0.0, layout=self.spec.shorts_layout,
                             progress_bar=self.spec.progress_bar, series_label=series)
            self.short_props.append(sp)
            p = self.render_dir / f"props_short_{i}.json"
            write_json(p, sp)
            name = slugify(s.get("title") or f"short{i}", 20)
            items.append(RenderItem("video", "Short", p, self.out / f"{self.slug}_숏폼{i}_{name}.mp4", scale=1.0,
                                    crf=rs.crf, x264_preset=rs.x264_preset, weight=sp["duration"]))
        if self.spec.thumbnails:
            items += self._thumbnail_items()
        if not items:
            self.log("렌더할 항목이 없습니다.")
            return
        job = RenderJob(public_dir=self.public, bundle_dir=self.render_dir / "bundle", links=links, items=items,
                        browser_executable=rs.browser_executable, gl=rs.gl, concurrency=rs.concurrency)
        node = find_node(self.settings.node_path)
        run_render(job, self.render_dir / "job.json", node=node, log=self.log, progress=self._sp("render"),
                   cancel=self.cancel)

    def _thumbnail_items(self) -> list[RenderItem]:
        assert self.info
        # 얼굴이 크고 화면 안쪽에 있는 순간 3곳(서로 20초 이상 떨어지게, 남긴 구간 안에서)
        kept = self.timemap.keeps
        cands = [s for s in self.face if 0.25 < s["x"] < 0.75 and any(k.start + 0.5 <= s["t"] <= k.end - 0.5 for k in kept)]
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
            or [self.spec.title]
        variants = ["signal", "ink", "photo"]
        items = []
        img_dir = self.public / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for i in range(3):
            pk = picks[i % len(picks)]
            frame = img_dir / f"thumb_frame_{i + 1}.jpg"
            vf = hdr_to_sdr_filter() if self.info.is_hdr else ""
            try:
                self.ff.grab_frame(self.spec.video, pk["t"], frame, width=1920, extra_vf=vf)
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
            items.append(RenderItem("still", "Thumbnail", p, self.out / f"{self.slug}_썸네일{i + 1}_{variants[i]}.jpg",
                                    scale=1.0, weight=0.5))
        return items

    # ------------------------------------------------------------------
    def stage_export(self) -> None:
        assert self.info
        credits = sorted({b.get("credit", "") for b in self.broll_log if b.get("credit")})
        chapters = getattr(self, "long_chapters", [])
        if self.long_props:
            write_text(self.out / f"{self.slug}_롱폼.srt", cues_to_srt(self.long_props["captions"]))
        for i, sp in enumerate(self.short_props, 1):
            write_text(self.out / f"{self.slug}_숏폼{i}.srt", cues_to_srt(sp["captions"]))
        write_text(self.out / f"{self.slug}_업로드정보.txt",
                   youtube_text(self.plan_long, chapters, self.plan_shorts, credits))
        if self.spec.export_xml:
            w, h = self.info.display_size
            voice = self.work / "voice.wav"
            if self.spec.make_long:
                markers = [(c["start"], f"챕터 {c['number']} {c['title']}", "") for c in chapters]
                markers += [(g["start"], g["template"], str(g["data"].get("title") or g["data"].get("body") or ""))
                            for g in self.long_props.get("graphics", [])]
                export_xml(self.out / f"{self.slug}_롱폼_premiere.xml", name=f"{self.spec.title} (자동 컷)",
                           video=Path(self.spec.video), audio=voice, src_fps=self.info.fps, src_duration=self.info.duration,
                           width=w, height=h, seq_width=w, seq_height=h, keeps=self.timemap.keeps, markers=markers)
            for i, tm in enumerate(getattr(self, "short_maps", []), 1):
                export_xml(self.out / f"{self.slug}_숏폼{i}_premiere.xml", name=f"숏폼 {i}", video=Path(self.spec.video),
                           audio=voice, src_fps=self.info.fps, src_duration=self.info.duration, width=w, height=h,
                           seq_width=1080, seq_height=1920, keeps=tm.keeps, markers=[])
        report = edit_report(title=self.spec.title, source_duration=self.info.duration,
                             long_duration=self.timemap.duration, align_report=self.align_report, utts=self.utts,
                             graphics=self.long_props.get("graphics", []) if self.long_props else [],
                             chapters=chapters, shorts=self.plan_shorts, director=self.director_name,
                             usage=self.claude.usage if self.claude else read_json(self.work / "plan.json", {}).get("usage", []),
                             broll=self.broll_log)
        write_text(self.out / f"{self.slug}_편집리포트.md", report)
        # 사용자가 계획을 직접 고칠 수 있도록 사본을 출력 폴더에도
        shutil.copyfile(self.work / "plan.json", self.out / "plan.json")

    # ------------------------------------------------------------------
    def load_state(self) -> None:
        """저장된 분석 결과를 다시 읽어 렌더만 다시 할 때 사용."""
        self.stage_probe()
        data = read_json(self.work / "align.json", {})
        self.utts = [Utterance.from_dict(u) for u in data.get("utterances", [])]
        self.tags = [Tag.from_dict(t) for t in data.get("tags", [])]
        self.align_report = data.get("report", {})
        self.vad = [tuple(v) for v in data.get("vad", [])]
        self.face = read_json(self.work / "face.json", {}).get("samples", [])


def template_names() -> list[str]:
    return list(TEMPLATES.keys())
