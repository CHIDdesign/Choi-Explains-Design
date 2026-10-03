"""자료 조달 사다리(docs/upgrade/03_자료_조달_엔진_v2.md 3·4·7절) — 자료 리서처의 EVIDENCE 항목마다 need 가 시작 칸을 정하고,
못 구하면 **빼지 않고 다음 칸으로**, 어디서 끝났는지 기록한다(rung).

  own_material   ④ 자료 폴더 → 채널 라이브러리 → (fallback: code_drawn → 모션 디자이너 / type_card)
  entity         자료 폴더 → 라이브러리 → 위키데이터·커먼즈 후보 여러 장(P18·문서 대표·문서 안 이미지·depicts·분류)
                 · 사람 = 품위 있는 초상 · 브랜드·서비스 = 로고 → 위키백과 대표/커먼즈 검색 → Openverse(상업·변형 허용) → 자료 카드
  primary_source 서지 확인(Crossref) → 출처 카드(자체 제작) (+ allow_quote 면 DOI 첫 화면 캡처, C)
  screenshot     화면 캡처(C — allow_quote 일 때만) → 로고 → 자료 카드
  code_drawn     조달하지 않는다 — 모션 디자이너에게 claim·must_show 로 넘긴다
  stock          스톡 허브(StockResearcher) → 탈락하면 얼굴로 둔다
비전 선택은 EVIDENCE_PICK(0~3점, 2점 이상만 — 게이트 B6). AI 가 없으면 좋은 출처 순(점수 -1).
결과(outcome)는 JSON 으로 계획에 남고, merge_plan 이 그래픽으로 바꾼다(studio/agents/studio.py).
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .. import net
from ..broll.images import ImageResult
from ..broll.resolve import MediaPlan, MediaResolver, _thumb_url
from ..broll.wikipedia import _safe
from ..util import LogFn, noop_log
from . import scholar as sch
from .commons import EntityMedia, pick_by_rule
from .library import AssetLibrary
from .license import AssetMeta, License, classify, finish
from .local import LocalItem, find as find_local

NEEDS = ("own_material", "entity", "primary_source", "screenshot", "code_drawn", "stock")
TREATMENTS = ("hero", "full", "pip", "sequence", "grid", "stack", "cutout", "archive_card", "doc_highlight",
              "browser_frame", "detail_zoom", "annotate", "compare_pair", "collage")
# 지금 렌더러가 그리는 것(나머지는 hero 로 — detail_zoom·annotate·stack·sequence 는 03b 의 P2, cutout 은 콜라주로)
DRAWN = ("hero", "full", "pip", "archive_card", "doc_highlight", "browser_frame", "grid", "compare_pair", "collage")
FULLSCREEN = ("hero", "full", "archive_card", "doc_highlight", "browser_frame", "grid", "compare_pair", "collage",
              "cutout")
LOGO_KINDS = ("brand", "site_app")
SUBJECT_KINDS = ("site_app", "product", "work", "brand")     # 이 대상이 주 피사체가 아니면 0점
PickFn = Callable[[str, list[tuple[str, bytes, str]]], list[dict[str, Any]]]


def clean_item(it: dict[str, Any]) -> dict[str, Any]:
    """리서처 항목을 사다리가 믿을 수 있게: enum·범위·빈 칸."""
    d = dict(it or {})
    d["need"] = d.get("need") if d.get("need") in NEEDS else "entity"
    d["treatment"] = d.get("treatment") if d.get("treatment") in TREATMENTS else "hero"
    try:
        d["count"] = max(1, min(5, int(d.get("count") or 1)))
    except (TypeError, ValueError):
        d["count"] = 1
    d["tier_max"] = d.get("tier_max") if d.get("tier_max") in ("A", "B", "C") else "A"
    d["fallback"] = d.get("fallback") if d.get("fallback") in ("type_card", "code_drawn", "stock", "face") else "type_card"
    for k in ("subject", "source", "stock", "pair"):
        d[k] = dict(d.get(k) or {}) if isinstance(d.get(k), dict) else {}
    d["label"] = clip_words(d.get("label"), 14)
    d["caption"] = clip_words(d.get("caption"), 24)
    d["commons_files"] = [str(x).strip() for x in d.get("commons_files") or [] if str(x).strip()][:6]
    d["display"] = str(d.get("display") or "").strip()[:8]
    d["quote"] = clip_words(d.get("quote"), 36)
    return d


def clip_words(s: Any, n: int) -> str:
    """화면 글자를 n 자 안으로 — 낱말 가운데서 자르지 않는다(2026-10-04 캡션 'Leahy 외 · J. Mech. Desig').
    n 자 안의 마지막 낱말 경계(공백·가운뎃점·쉼표)에서 자르고, 그러면 너무 짧아질 때만 글자로 자른다."""
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(t) <= n:
        return t
    cut = t[: n + 1]
    k = max(cut.rfind(" "), cut.rfind("·"), cut.rfind(","))
    out = cut[:k].rstrip(" ·,") if k >= n * 0.5 else t[:n]
    return out.strip()


def drawn_treatment(t: str, n_assets: int, tier: str, kind: str = "photo") -> str:
    """요청한 트리트먼트 → 지금 그릴 수 있는 것. C 등급은 풀블리드 금지(정책 4절 3)."""
    t = "collage" if t == "cutout" else t if t in DRAWN else "hero"
    if t == "collage" and kind != "photo":
        t = "hero"
    if t == "grid" and n_assets < 4:
        t = "hero"
    if t == "compare_pair" and n_assets < 2:
        t = "hero"
    if t == "browser_frame" and kind != "screen":
        t = "hero"
    if t == "doc_highlight" and kind != "document":
        t = "hero"
    if t == "full" and (tier == "C" or kind in ("logo", "screen", "document")):
        t = "hero"
    return t


@dataclass
class Deps:
    resolver: Optional[MediaResolver] = None
    media: Optional[EntityMedia] = None
    scholar: Optional[sch.Scholar] = None
    local: tuple[LocalItem, ...] = ()
    library: Optional[AssetLibrary] = None
    openverse: Optional[Callable[[str, str, Path], Optional[ImageResult]]] = None
    capture: Optional[Callable[[list[dict[str, Any]]], dict[str, dict[str, Any]]]] = None   # allow_quote 일 때만
    pick: Optional[PickFn] = None
    pick_portraits: Optional[Callable[[MediaResolver, list[MediaPlan]], None]] = None
    stock: Optional[Callable[[list[dict[str, Any]]], list[Optional[dict[str, Any]]]]] = None
    allow_quote: bool = False
    context: Optional[Callable[[Any], str]] = None      # 발화 id → 그 문장(스톡 후보를 문장의 뜻으로 고르게)


class Ladder:
    def __init__(self, deps: Deps, *, public: Path, work: Path, log: LogFn = noop_log):
        self.d = deps
        self.public = public
        self.img_dir = public / "images"
        self.thumbs = work / "evidence_thumbs"
        self.work = work
        self.log = log

    # ------------------------------------------------------------------
    def run(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        items = [clean_item(it) for it in items]
        outs: list[dict[str, Any]] = [{"i": i, "need": it["need"], "rung": "", "assets": [], "archive": None,
                                       "stock": None, "why": ""} for i, it in enumerate(items)]
        pending_pick: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []   # (i, item, 후보)
        portraits: list[tuple[int, MediaPlan]] = []
        for i, it in enumerate(items):
            try:
                self._first_pass(i, it, outs[i], pending_pick, portraits)
            except Exception as e:  # noqa: BLE001 - 한 항목의 오류로 나머지를 버리지 않는다
                outs[i]["why"] = f"오류: {e}"
                self.log(f"🎞 자료 '{self._name(it)}' 조달 오류: {e}")
        if pending_pick:
            self._pick_and_fetch(pending_pick, items, outs)
        if portraits and self.d.resolver is not None:
            plans = [p for _, p in portraits]
            if self.d.pick_portraits is not None:
                self.d.pick_portraits(self.d.resolver, plans)
            else:
                for p in plans:
                    p.result = self.d.resolver.finish(p, 0)
            for i, p in portraits:
                if p.result is not None:
                    self._add_result(outs[i], items[i], p.result, rung="portrait", kind="photo", role="portrait")
        # 스톡: need=stock + 위 칸에서 못 구했고 fallback=stock 인 항목(검색어가 있을 때)
        stock_ix = [i for i, it in enumerate(items) if not outs[i]["assets"] and not outs[i]["archive"]
                    and (it["need"] == "stock" or (it["fallback"] == "stock" and it["need"] != "code_drawn"))
                    and (it["stock"].get("query_en") or it["stock"].get("query_ko"))]
        if stock_ix and self.d.stock is not None:
            reqs = [{"kind": items[i]["stock"].get("kind") or "photo", "query_en": items[i]["stock"].get("query_en", ""),
                     "query_ko": items[i]["stock"].get("query_ko", ""), "purpose": items[i].get("claim", ""),
                     "must_show": items[i].get("must_show", ""), "avoid": items[i].get("avoid", ""),
                     # 역추상화(자료 리서처): 같은 장면을 다른 각도(손·과정·장소·질감)로 찾는 검색어와 화면 전략
                     "alt_queries": [str(q) for q in items[i]["stock"].get("alt_queries") or [] if str(q).strip()][:3],
                     "angle": str(items[i]["stock"].get("angle") or ""),
                     "context": self.d.context(items[i].get("start_seg")) if self.d.context else ""}
                    for i in stock_ix]
            try:
                got = self.d.stock(reqs)
            except Exception as e:  # noqa: BLE001
                self.log(f"🎞 스톡 조달 실패: {e}")
                got = [None] * len(reqs)
            for i, res in zip(stock_ix, got):
                if res:
                    outs[i]["stock"] = res
                    outs[i]["rung"] = "stock"
        for i, it in enumerate(items):
            o = outs[i]
            if o["assets"] or o["archive"] or o["stock"]:
                continue
            o["rung"] = {"code_drawn": "code_drawn", "face": "face", "type_card": "type_card",
                         "stock": "face"}.get("code_drawn" if it["need"] == "code_drawn" else it["fallback"], "type_card")
            o["why"] = o["why"] or "못 구함"
        return outs

    # ------------------------------------------------------------------
    @staticmethod
    def _name(it: dict[str, Any]) -> str:
        s = it.get("subject") or {}
        return str(s.get("name_ko") or s.get("name_en") or it.get("label") or it.get("claim") or "")[:40]

    def _first_pass(self, i: int, it: dict[str, Any], o: dict[str, Any], pending: list, portraits: list) -> None:
        need, subj = it["need"], it["subject"]
        names = [x for x in (subj.get("name_ko"), subj.get("name_en")) if x]
        if need == "code_drawn" or need == "stock":
            return
        if need == "own_material":
            hit = find_local(list(self.d.local), it.get("local_file", ""), *names, it.get("label", ""))
            if hit is not None:
                self._add_file(o, it, hit.path, origin="user", rung="local", kind="photo", role="subject",
                               title=hit.path.stem)
                return
            if self._from_library(o, it, names):
                return
            o["why"] = "자료 폴더에 맞는 파일 없음"
            return
        if need == "primary_source":
            src = it["source"]
            meta = self.d.scholar.resolve(src.get("citation", ""), src.get("doi", "")) if self.d.scholar else None
            if not meta:
                o["why"] = "서지 확인 실패(출처 카드를 만들지 않음)"
                return
            o["archive"] = sch.source_card(meta, label=it.get("label", ""), locator=src.get("locator", ""))
            o["source_meta"] = meta
            o["credit"] = sch.short_credit(meta)
            o["credit_full"] = sch.full_credit(meta)
            o["rung"] = "scholar"
            if self.d.capture is not None and meta.get("url") and it["treatment"] == "doc_highlight" \
                    and it["tier_max"] == "C":
                self._capture(o, it, meta["url"], kind="document")
            return
        if need == "screenshot":
            url = str(it["source"].get("url") or "").strip()
            if self.d.capture is not None and url and it["tier_max"] == "C":
                if self._capture(o, it, url, kind="screen", as_of=str(it["source"].get("as_of") or "")):
                    return
            if names and self.d.resolver is not None:            # 화면 대신 로고(P154·Simple Icons)
                p = self.d.resolver.plan(names[0], "brand", tuple(names[1:]))
                if p.result is not None:
                    self._add_result(o, it, p.result, rung="logo", kind="logo", role="logo")
                    return
            o["why"] = "화면 캡처 꺼짐(C 등급)·로고 없음" if self.d.capture is None else "화면 캡처 실패·로고 없음"
            return
        # entity
        if not names:
            o["why"] = "대상 이름 없음"
            return
        hit = find_local(list(self.d.local), it.get("local_file", ""), *names) if self.d.local else None
        if hit is not None:
            self._add_file(o, it, hit.path, origin="user", rung="local", kind="photo", role="subject", title=hit.path.stem)
            return
        if self._from_library(o, it, names, qid=str(subj.get("qid") or "")):
            return
        if self.d.resolver is None:
            o["why"] = "온라인 자료 꺼짐"
            return
        kind, shot = subj.get("kind") or "other", subj.get("shot") or "subject"
        if self._research_files(i, it, o, pending, names, kind, shot):
            return
        if kind in LOGO_KINDS or shot == "logo" or (kind == "organization" and shot in ("logo", "screen")):
            p = self.d.resolver.plan(names[0], "brand", tuple(names[1:]))
            if p.result is not None:
                self._add_result(o, it, p.result, rung="logo", kind="logo", role="logo")
            else:
                o["why"] = "로고 없음(사람 사진으로 대신하지 않는다)"
            return
        if kind == "person":
            p = self.d.resolver.plan(names[0], "person", tuple(names[1:]))
            if p.result is not None:
                self._add_result(o, it, p.result, rung=p.kind if p.kind == "local" else "wiki", kind="photo",
                                 role="portrait")
            elif p.candidates:
                portraits.append((i, p))
            else:
                o["why"] = "쓸 수 있는 초상 없음"
            return
        # 작품·제품·장소·기관·출판물·그 밖: 후보 여러 장
        info = None
        if self.d.resolver.wp is not None:
            try:
                info = self.d.resolver.wp.entity(names[0], tuple(names[1:]))
            except Exception as e:  # noqa: BLE001
                self.log(f"위키데이터 조회 실패({names[0]}): {e}")
        if info and self.d.media is not None:
            cands = self.d.media.candidates(info, kind=kind, tier_max=it["tier_max"],
                                            min_long=1600 if it["treatment"] in ("hero", "full") else 900)
            if not cands and it["treatment"] in ("hero", "full"):
                cands = self.d.media.candidates(info, kind=kind, tier_max=it["tier_max"], min_long=900)
            if cands:
                pending.append((i, it, cands))
                o["info"] = {k: info.get(k) for k in ("qid", "title", "description", "page")}
                return
        res = self.d.resolver._lead_or_search(names[0], tuple(names[1:]))
        if res is None and self.d.openverse is not None:
            res = self.d.openverse(names[0], subj.get("name_en") or "", self.img_dir)
        if res is not None:
            self._add_result(o, it, res, rung="openverse" if res.origin == "openverse" else "wiki", kind="photo",
                             role="subject")
            return
        o["why"] = "위키미디어·Openverse 에 쓸 수 있는 이미지 없음"

    # ------------------------------------------------------------------
    def _from_library(self, o: dict[str, Any], it: dict[str, Any], names: list[str], qid: str = "") -> bool:
        if self.d.library is None:
            return False
        hits = self.d.library.find(*names, qid=qid)[: it["count"]]
        for e in hits:
            m = e.get("meta") or {}
            self._add_file(o, it, self.d.library.path_of(e), origin=m.get("origin") or "library", rung="library",
                           kind="logo" if m.get("role") == "logo" else "photo", role=m.get("role", "subject"),
                           title=m.get("title", ""), lic_text=((m.get("license") or {}).get("name") or ""),
                           creator=m.get("creator", ""), source_url=m.get("source_url", ""),
                           tier=str((m.get("license") or {}).get("tier") or ""))
        return bool(hits)

    def _capture(self, o: dict[str, Any], it: dict[str, Any], url: str, *, kind: str, as_of: str = "") -> bool:
        from .screenshot import credit, wayback_url
        target = wayback_url(url, as_of) if as_of else ""
        sid = f"s{o['i']}"
        out = self.img_dir / f"cap_{_safe(url, 40)}.jpg"
        res = self.d.capture([{"id": sid, "url": target or url, "out": out}]) if self.d.capture else {}
        if not ((res.get(sid) or {}).get("ok") and out.exists()):
            return False
        cs, cf = credit(url, as_of)
        self._add_file(o, it, out, origin="screenshot", rung="screenshot", kind=kind, role="screen",
                       title=url, source_url=url, credit=(cs, cf), copy=False)
        return True

    def _research_files(self, i: int, it: dict[str, Any], o: dict[str, Any], pending: list, names: list[str],
                        kind: str, shot: str) -> bool:
        """🔎 조사 노트가 직접 확인한 커먼즈 파일이 있으면 그것부터(라이선스·크기는 여기서 다시 확인) — 위키데이터·문서 검색보다
        먼저. 로고 자리에는 쓰지 않는다(로고는 로고 칸이 맡는다)."""
        from ..agents.research import commons_name
        files = [f for f in (commons_name(x) for x in it.get("commons_files") or []) if f]
        if not files or self.d.media is None or shot == "logo" or kind in LOGO_KINDS:
            return False
        try:
            metas = self.d.media.wp.files_meta(files[:6])
        except Exception as e:  # noqa: BLE001 - 네트워크 오류면 예전 칸으로
            self.log(f"🔎 조사 노트의 커먼즈 파일 확인 실패({names[0]}): {e}")
            return False
        cands = self.d.media.usable([{**m, "src": "research"} for m in metas], kind=kind, tier_max=it["tier_max"],
                                    min_long=900)
        if not cands:
            self.log(f"🔎 조사 노트의 커먼즈 파일 {len(files)}개 — 라이선스·크기에 맞는 것이 없어 다른 칸으로({names[0]})")
            return False
        pending.append((i, it, cands))
        o["info"] = {"title": names[0], "qid": str((it.get("subject") or {}).get("qid") or "")}
        o["research"] = True
        return True

    def _pick_and_fetch(self, pending: list[tuple[int, dict[str, Any], list[dict[str, Any]]]],
                        items: list[dict[str, Any]], outs: list[dict[str, Any]]) -> None:
        """후보 썸네일 → (AI) 시트로 채점 → 2점 이상만 count 장 → 1920px 받기."""
        self.thumbs.mkdir(parents=True, exist_ok=True)
        ua = self.d.resolver.wp.ua if self.d.resolver and self.d.resolver.wp else "ChoiStudio"
        live = []
        for i, it, cands in pending:
            keep = []
            for j, m in enumerate(cands):
                dst = self.thumbs / f"{_safe(self._name(it), 24)}_{j}{Path(m['name']).suffix.lower() or '.jpg'}"
                try:
                    net.download(_thumb_url(m["url"]), dst, timeout=40, headers={"User-Agent": ua}, rounds=2)
                    keep.append({**m, "thumb": dst})
                except Exception as e:  # noqa: BLE001
                    self.log(f"자료 후보 썸네일 실패({m['name']}): {e}")
            if keep:
                live.append((i, it, keep))
            else:
                outs[i]["why"] = "후보 썸네일을 받지 못함"
        if not live:
            return
        chosen: dict[int, list[tuple[int, dict[str, Any]]]] = {i: [(j, {"score": -1}) for j in pick_by_rule(c, it["count"])]
                                                               for i, it, c in live}
        if self.d.pick is not None:
            from ..stock.research import contact_sheet
            sheets, lines = [], []
            for r, (i, it, cands) in enumerate(live, start=1):
                cells = []
                for j, m in enumerate(cands, start=1):
                    try:
                        data = Path(m["thumb"]).read_bytes()
                    except OSError:
                        data = None
                    cells.append((f"C{j} {m.get('src', '')[:8]} {m.get('width', 0)}x{m.get('height', 0)}", data))
                sheets.append((f"R{r}", contact_sheet(cells, cell=(320, 320), contain=True), "image/jpeg"))
                s = it["subject"]
                lines.append(f"- R{r} [{it['need']}/{s.get('kind')}/{s.get('shot')}] {s.get('name_ko', '')} "
                             f"({s.get('name_en', '')}) · claim: {it.get('claim', '')} · must_show: {it.get('must_show', '')}"
                             f" · avoid: {it.get('avoid', '')} · label: {it.get('label', '')} · count {it['count']}"
                             + "".join(f"\n  C{j}: {m['name'][:60]} — {str(m.get('description', ''))[:70]}"
                                       f" ({m.get('src')}, {m.get('lic', {}).get('name', '')})"
                                       for j, m in enumerate(cands, start=1)))
            try:
                picks = self.d.pick("\n".join(lines), sheets)
                for pk in picks or []:
                    r = int(pk.get("request", 0) or 0)
                    if not 1 <= r <= len(live):
                        continue
                    i, it, cands = live[r - 1]
                    chosen[i] = choose(pk, len(cands), it["count"], (it["subject"].get("kind") or ""))
                    if not chosen[i]:
                        outs[i]["why"] = "비전 선택: 2점 이상 후보 없음 — " + str(pk.get("reason", ""))[:120]
                        self.log(f"🎞 R{r} '{self._name(it)}': 쓸 후보 없음 ({pk.get('reason', '')})")
            except Exception as e:  # noqa: BLE001 - 선택 실패면 좋은 출처 순
                self.log(f"🎞 자료 비전 선택 실패 → 좋은 출처 순: {e}")
        for i, it, cands in live:
            for j, ch in chosen.get(i, []):
                m = cands[j]
                ext = ".png" if "png" in (m.get("mime") or "") else ".jpg"
                dst = self.img_dir / f"ev_{_safe(self._name(it), 30)}_{_safe(Path(m['name']).stem, 24)}{ext}"
                try:
                    self.img_dir.mkdir(parents=True, exist_ok=True)
                    if not dst.exists():
                        net.download(m["url"], dst, timeout=60, headers={"User-Agent": ua})
                except Exception as e:  # noqa: BLE001
                    self.log(f"자료 다운로드 실패({m['name']}): {e}")
                    continue
                lic = License(**m["lic"]) if isinstance(m.get("lic"), dict) else classify(m.get("license", ""))
                self._add_file(outs[i], it, dst, origin="commons", rung="commons", kind="photo",
                               role=it["subject"].get("shot") or "subject", title=Path(m["name"]).stem,
                               creator=re.sub(r"\s+", " ", m.get("artist") or ""), source_url=m.get("page", ""),
                               lic_obj=lic, copy=False, focus=ch.get("focus_box") or [], shows=ch.get("shows", ""),
                               score=int(ch.get("score", -1)))

    # ------------------------------------------------------------------
    def _add_result(self, o: dict[str, Any], it: dict[str, Any], res: ImageResult, *, rung: str, kind: str,
                    role: str) -> None:
        origin = {"logo": "logo", "local": "user"}.get(res.origin, res.origin or "wikipedia")
        lic_text = res.license or ""
        lic = classify(lic_text, origin=origin) if origin not in ("logo",) else classify(lic_text or "public domain")
        if res.origin == "logo" and lic.tier == "D":
            lic = License("trademark", "상표(지칭 사용)", "", "A", True, False, False, False)
        self._add_file(o, it, res.path, origin=origin, rung=rung, kind=kind, role=role, title=self._name(it),
                       source_url=res.source_url, lic_obj=lic, copy=False,
                       credit=(res.credit, res.credit) if res.credit else None)

    def _add_file(self, o: dict[str, Any], it: dict[str, Any], path: Path, *, origin: str, rung: str, kind: str,
                  role: str, title: str = "", creator: str = "", source_url: str = "", lic_text: str = "",
                  lic_obj: Optional[License] = None, tier: str = "", copy: bool = True, focus: list | None = None,
                  shows: str = "", score: int = -1, credit: Optional[tuple[str, str]] = None) -> None:
        from PIL import Image
        if copy:
            self.img_dir.mkdir(parents=True, exist_ok=True)
            dst = self.img_dir / f"own_{re.sub(r'[^0-9A-Za-z가-힣._-]+', '_', path.name)[-60:]}"
            if not dst.exists():
                if path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".svg"):
                    # SVG(로고 카드)는 그대로 — 렌더러가 그린다. 자산 라이브러리에서 꺼낸 로고를 prepare_photo(PIL)로 바꾸려다
                    # 'cannot identify image file' 로 조달이 실패하던 것(2026-10-03)
                    shutil.copyfile(path, dst)
                else:
                    from ..stock.process import prepare_photo
                    dst = dst.with_suffix(".jpg")
                    prepare_photo(path, dst)
            path = dst
        lic = lic_obj or (License(tier=tier, name=lic_text) if tier else classify(lic_text, origin=origin))
        orig = path
        if kind == "photo" and origin in ("commons", "wikipedia", "openverse") and lic.tier != "C" \
                and path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            # 하우스 트리트먼트 T1(07b): 색이 정보인 실물(작품·제품·건물)이라 색은 그대로 두고 레벨만 [잉크, 종이] 안으로
            from ..grade.house import HOUSE_VERSION, treat_file
            base = path.with_name(f"{path.stem}.full.h{HOUSE_VERSION}")
            try:
                path = base.with_suffix(".jpg") if base.with_suffix(".jpg").exists() else \
                    treat_file(path, base, kind="photo", keep_color=True, surface="full")[0]
            except Exception as e:  # noqa: BLE001
                self.log(f"자료 톤 처리 실패({path.name}): {e}")
        w = h = 0
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:  # noqa: BLE001 - SVG(로고) 등은 크기 없이
            pass
        if lic.tier == "C" and max(w, h) > 1600:             # 인용은 긴 변 1600px 이하(정책 4절 5)
            try:
                with Image.open(path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((1600, 1600))
                    im.save(path, quality=88, format="JPEG")
                    w, h = im.size
            except Exception:  # noqa: BLE001
                pass
        meta = finish(AssetMeta(path=str(path), origin=origin, source_url=source_url, title=title, creator=creator,
                                license=lic, shows=shows, role=role, width=w, height=h, focus_box=list(focus or []),
                                score=score))
        if credit:
            meta.credit_short, meta.credit_full = credit
        rel = path.relative_to(self.public).as_posix() if path.is_relative_to(self.public) else f"images/{path.name}"
        mat = ""
        if kind == "photo" and w and h and w / h < 1.0:      # 세로 사진: 얼굴 옆 액자에는 크림 종이 여백 액자 사본(P0-11)
            from ..broll.mat import mat_tall
            try:
                m = mat_tall(path)
                mat = m.relative_to(self.public).as_posix() if m is not None and m.is_relative_to(self.public) else ""
            except Exception:  # noqa: BLE001
                mat = ""
        cut = ""
        if kind == "photo" and lic.tier not in ("C", "D") and w and h:
            # 디자인 v3 콜라주: 바탕이 고른 판화·스캔·제품 사진은 오려서 바닥 타원 위에 세운다(못 오리면 프린트로)
            from .cutout import cutout
            try:
                c = cutout(path)
                cut = c.relative_to(self.public).as_posix() if c is not None and c.is_relative_to(self.public) else ""
            except Exception as e:  # noqa: BLE001 - 오리기는 덤
                self.log(f"오려 내기 실패({path.name}): {e}")
        o["assets"].append({"src": rel, "kind": kind, "w": w, "h": h, "focus": meta.focus_box or None, "mat_src": mat,
                            "cut": cut,
                            "credit": meta.credit_short, "credit_full": meta.credit_full, "tier": lic.tier,
                            "origin": origin, "shows": shows, "score": score,
                            "meta": {"title": title[:80], "creator": creator[:60], "ref": source_url}})
        o["rung"] = o["rung"] or rung
        if self.d.library is not None and lic.tier in ("own", "A", "A-sa") and origin not in ("library",):
            names = [x for x in ((it.get("subject") or {}).get("name_ko"), (it.get("subject") or {}).get("name_en"),
                                 it.get("local_file")) if x]
            try:
                self.d.library.add(orig, meta.to_dict(), names, qid=str(((o.get("info") or {}).get("qid")) or ""))
            except Exception as e:  # noqa: BLE001 - 라이브러리는 덤
                self.log(f"자산 라이브러리 등록 실패: {e}")


def choose(pick: dict[str, Any], n: int, count: int, kind: str) -> list[tuple[int, dict[str, Any]]]:
    """EVIDENCE_PICK 한 요청 → [(후보 번호 0부터, 선택 정보)] — 2점 이상만, 뻔한 스톡은 1점 상한, 이름 붙은 대상이 주 피사체가
    아니면 0점(사이트·제품·작품·브랜드), 점수 높은 순으로 count 장."""
    out: list[tuple[int, dict[str, Any]]] = []
    seen: set[int] = set()
    for ch in pick.get("choices") or []:
        try:
            c, score = int(ch.get("candidate", 0)), int(ch.get("score", 0))
        except (TypeError, ValueError):
            continue
        if not 1 <= c <= n or c in seen:
            continue
        if ch.get("cliche"):
            score = min(score, 1)
        if kind in SUBJECT_KINDS and ch.get("main_subject") is False:
            score = 0
        if score >= 2:
            seen.add(c)
            fb = ch.get("focus_box") or []
            ok_box = isinstance(fb, list) and len(fb) == 4 and all(isinstance(v, (int, float)) for v in fb) \
                and fb[2] > 0 and fb[3] > 0
            out.append((c - 1, {"score": score, "shows": str(ch.get("shows") or "")[:40],
                                "focus_box": [max(0.0, min(1.0, float(v))) for v in fb] if ok_box else []}))
    out.sort(key=lambda x: -x[1]["score"])
    return out[:count]


def summary(items: list[dict[str, Any]], outs: list[dict[str, Any]]) -> dict[str, Any]:
    """깔때기 통계(진단·리포트): need 별 요청·확보, 끝난 칸."""
    st: dict[str, Any] = {"requests": len(items), "acquired": 0, "rungs": {}, "by_need": {}}
    for it, o in zip(items, outs):
        need = (it or {}).get("need") or o.get("need")
        b = st["by_need"].setdefault(need, {"n": 0, "got": 0})
        b["n"] += 1
        got = bool(o.get("assets") or o.get("archive") or o.get("stock"))
        b["got"] += int(got)
        st["acquired"] += int(got)
        st["rungs"][o.get("rung") or "?"] = st["rungs"].get(o.get("rung") or "?", 0) + 1
    return st
