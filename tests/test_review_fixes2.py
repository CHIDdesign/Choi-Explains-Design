"""코드 점검(스톡·소리·창·AI) 회귀 테스트."""
import numpy as np

from studio.net import redact
from studio.settings import DEFAULT_PROJECTS_DIR, Settings
from studio.sound.library import Sound, SoundLibrary


def test_keys_never_reach_logs():
    msg = ("ConnectionError: HTTPSConnectionPool(host='pixabay.com'): Max retries exceeded with url: "
           "/api/videos/?key=SECRETKEY-1234567890abcdef&q=office")
    assert "SECRETKEY" not in redact(msg) and "q=office" in redact(msg)
    for header in ("Authorization: Client-ID abcdef1234567890XYZ", "Authorization: Bearer sk-ant-abcdefghijklmnop"):
        assert "abcdef" not in redact(header)
    assert redact("pixabay:photo:office desk") == "pixabay:photo:office desk"


def test_bgm_playlist_cycles_instead_of_repeating_first():
    lib = SoundLibrary(log=lambda m: None)
    lib.bgm = [Sound(i, "bgm", None, 0, 200, "t", None, mood="calm") for i in "ABC"]
    pl = [s.id for s in lib.playlist(lib.bgm[0], 6, seed=1)]
    assert pl[0] == "A" and len(set(pl[:3])) == 3 and pl[3:] == pl[:3]


def test_moved_program_folder_uses_default_projects_dir():
    assert Settings.from_dict({"projects_dir": "C:/옛폴더/ChoiStudio/projects"}).projects_dir == str(DEFAULT_PROJECTS_DIR)
    assert Settings.from_dict({"projects_dir": ""}).projects_dir == str(DEFAULT_PROJECTS_DIR)


def test_riser_keeps_its_peak(tmp_path):
    """라이저: 정점(컷에 맞출 곳)까지는 그대로, 뒤 꼬리만 줄인다."""
    import wave

    from studio.media import mix
    sr = mix.SR
    x = np.zeros((int(6 * sr), 2), np.float32)
    pk = int(3.3 * sr)
    x[:pk] = np.linspace(0, 0.5, pk)[:, None]
    x[pk:] = 0.5
    voice = tmp_path / "v.wav"
    with wave.open(str(voice), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(np.zeros((sr * 8, 2), np.int16).tobytes())
    src = tmp_path / "r.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    from studio.media.ffmpeg import FFmpeg
    out = tmp_path / "m.wav"
    mix.mix(FFmpeg(), voice, out, total=8.0, sfx=[mix.SfxCue(path=str(src), t=5.0, gain_db=0.0, peak=3.3,
                                                              fade_out=2.5)], bgm=None)
    with wave.open(str(out)) as r:
        y = np.abs(np.frombuffer(r.readframes(r.getnframes()), np.int16).reshape(-1, 2)[:, 0]).astype(float)
    env = np.array([y[i:i + sr // 20].mean() for i in range(0, len(y) - sr // 20, sr // 20)])
    assert abs(np.argmax(env) * 0.05 - 5.0) < 0.35          # 가장 큰 곳이 컷(5초) 근처
