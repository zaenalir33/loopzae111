import os
import re
import shlex
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="YouTube Live Streamer", layout="wide")
st.title("📹 YouTube Auto Live Streamer")

video_count = st.radio(
    "Jumlah video",
    [1, 5],
    format_func=lambda x: "1 Video" if x == 1 else "5 Video Playlist",
    horizontal=True,
    key="video_count",
)

BASE = Path("/tmp/youtube_streamer")
UPLOAD_DIR = BASE / "uploads"
LOG_FILE = BASE / "ffmpeg.log"
FFMPEG_DIR = BASE / "ffmpeg_bin"
FFMPEG_BIN = FFMPEG_DIR / "ffmpeg"
BASE.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def find_ffmpeg():
    system = shutil_which("ffmpeg")
    if system:
        return system
    if FFMPEG_BIN.exists():
        return str(FFMPEG_BIN)
    FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
    archive_cmd = (
        "curl -fsSL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz "
        f"| tar -xJ -C {shlex.quote(str(FFMPEG_DIR))} --strip-components=1"
    )
    subprocess.run(archive_cmd, shell=True, check=True, timeout=180)
    if not FFMPEG_BIN.exists():
        raise RuntimeError("FFmpeg tidak ditemukan setelah proses instalasi.")
    return str(FFMPEG_BIN)


def shutil_which(name):
    import shutil
    return shutil.which(name)


try:
    FFMPEG = find_ffmpeg()
except Exception as exc:
    st.error(f"Gagal menyiapkan FFmpeg: {exc}")
    st.stop()


def init_state():
    defaults = {
        "pid": None,
        "mode": None,
        "log_text": "",
        "saved_videos": {},
        "saved_mp3": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def process_running():
    pid = st.session_state.get("pid")
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        st.session_state["pid"] = None
        return False


def read_logs():
    if LOG_FILE.exists():
        try:
            text = LOG_FILE.read_text(errors="replace")
            st.session_state["log_text"] = text[-16000:]
        except Exception:
            pass


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120]


def save_upload(uploaded, prefix):
    if uploaded is None:
        return None
    path = UPLOAD_DIR / f"{prefix}_{safe_name(uploaded.name)}"
    with open(path, "wb") as f:
        f.write(uploaded.getbuffer())
    return str(path)


def download_url(url, prefix):
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        raise ValueError("Link harus diawali http:// atau https://")
    if "drive.google.com" in url or "docs.google.com" in url:
        try:
            import gdown
        except ImportError:
            raise RuntimeError("Library gdown belum tersedia. Tambahkan gdown ke requirements.txt.")
        out = UPLOAD_DIR / f"{prefix}_drive"
        result = gdown.download(url=url, output=str(out), quiet=True, fuzzy=True)
        if not result:
            raise RuntimeError("Download Google Drive gagal. Pastikan file dapat diakses publik.")
        return str(result)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    suffix = Path(url.split("?")[0]).suffix or ".mp4"
    out = UPLOAD_DIR / f"{prefix}_link{suffix}"
    with urllib.request.urlopen(req, timeout=60) as response, open(out, "wb") as f:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
    return str(out)


def source_widget(label, key_prefix, file_types):
    source = st.radio("Sumber", ["Upload dari perangkat", "Link langsung", "Google Drive"], horizontal=True, key=f"src_{key_prefix}")
    if source == "Upload dari perangkat":
        up = st.file_uploader(label, type=file_types, key=f"up_{key_prefix}")
        return save_upload(up, key_prefix) if up else None
    url = st.text_input("URL", key=f"url_{key_prefix}", placeholder="https://...")
    if st.button("⬇️ Ambil file", key=f"get_{key_prefix}"):
        if not url.strip():
            st.error("Masukkan URL terlebih dahulu.")
        else:
            try:
                with st.spinner("Mengambil file..."):
                    path = download_url(url, key_prefix)
                st.session_state["saved_videos"][key_prefix] = path
                st.success("File berhasil diambil.")
            except Exception as exc:
                st.error(f"Gagal mengambil file: {exc}")
    return st.session_state["saved_videos"].get(key_prefix)


def write_concat_file(paths, repeat_count, filename):
    target = BASE / filename
    lines = []
    for _ in range(repeat_count):
        for p in paths:
            lines.append("file " + shlex.quote(os.path.abspath(p)))
    target.write_text("\n".join(lines) + "\n")
    return str(target)


def start_process(cmd, mode):
    if process_running():
        st.error("Streaming masih berjalan. Hentikan streaming sebelumnya terlebih dahulu.")
        return False
    LOG_FILE.write_text("Menjalankan perintah FFmpeg...\n" + " ".join(shlex.quote(x) for x in cmd) + "\n\n", encoding="utf-8")
    with open(LOG_FILE, "a", buffering=1) as log:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    st.session_state["pid"] = proc.pid
    st.session_state["mode"] = mode
    return True


def stop_process():
    pid = st.session_state.get("pid")
    if not pid:
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass
    st.session_state["pid"] = None


def encoding_args(shorts=False):
    # 1080p dengan CPU rendah: ultrafast + 2 thread + 20fps.
    args = [
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-r", "20",
        "-pix_fmt", "yuv420p",
        "-profile:v", "main",
        "-b:v", "2500k",
        "-maxrate", "2500k",
        "-bufsize", "5000k",
        "-g", "40",
        "-keyint_min", "40",
        "-sc_threshold", "0",
        "-tune", "zerolatency",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-af", "aresample=async=1:first_pts=0",
        "-f", "flv",
    ]
    if shorts:
        return ["-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2"] + args
    return args


def rtmp_url(key):
    return f"rtmp://a.rtmp.youtube.com/live2/{key.strip()}"


read_logs()
running = process_running()
if running:
    st.warning(f"🔴 Streaming sedang berjalan (PID {st.session_state['pid']}).")
else:
    if st.session_state.get("pid"):
        st.info("Streaming sudah berhenti. Lihat log untuk penyebabnya.")
        st.session_state["pid"] = None

with st.sidebar:
    st.header("⚙️ Kontrol")
    if running:
        if st.button("🛑 Hentikan Streaming", type="primary"):
            stop_process()
            st.rerun()
    if st.button("🔄 Refresh Log"):
        read_logs()
        st.rerun()

stream_key = st.text_input("YouTube Stream Key", type="password")
mode = st.radio("Mode Streaming", ["5 Video Playlist", "Video + MP3"], horizontal=True)

if mode == "5 Video Playlist":
    st.subheader("🎬 Video Playlist")
    st.caption("Pilih 1 video untuk loop satu video, atau 5 video untuk diputar berurutan.")

    video_paths = []
    for i in range(1, video_count + 1):
        with st.expander(f"Video {i}", expanded=(i == 1)):
            p = source_widget(f"File Video {i}", f"video{i}", ["mp4", "mkv", "mov", "webm"])
            if p:
                video_paths.append(p)

    repeat_option = st.radio(
        "Pengulangan",
        ["Tanpa batas", "Jumlah pengulangan"],
        horizontal=True,
        key="video_repeat_mode",
    )
    if repeat_option == "Jumlah pengulangan":
        repeat = st.number_input(
            "Jumlah putaran",
            min_value=1,
            max_value=100000,
            value=1,
            step=1,
            key="video_repeat",
        )
    else:
        repeat = None

    shorts = st.checkbox("Mode Shorts 720×1280", key="video_shorts")

    if st.button(
        "🚀 Mulai 1 Video" if video_count == 1 else "🚀 Mulai 5 Video",
        disabled=running,
        type="primary",
    ):
        if not stream_key:
            st.error("Masukkan Stream Key YouTube.")
        elif len(video_paths) != video_count:
            st.error(f"Isi {video_count} video terlebih dahulu.")
        else:
            if video_count == 1:
                # Paling stabil untuk satu video: jangan lewat concat demuxer.
                cmd = [
                    FFMPEG, "-hide_banner", "-loglevel", "info",
                    "-re",
                    "-thread_queue_size", "512",
                ]
                if repeat is None:
                    cmd += ["-stream_loop", "-1"]
                elif int(repeat) > 1:
                    cmd += ["-stream_loop", str(int(repeat) - 1)]
                cmd += [
                    "-i", video_paths[0],
                    "-map", "0:v:0",
                    "-map", "0:a:0?",
                ]
                cmd += encoding_args(shorts) + [
                    "-rtmp_live", "live",
                    "-flvflags", "no_duration_filesize",
                    rtmp_url(stream_key),
                ]
            else:
                if repeat is None:
                    playlist = BASE / "video_playlist.txt"
                    playlist.write_text(
                        "\n".join(
                            "file " + shlex.quote(os.path.abspath(p))
                            for p in video_paths
                        ) + "\n"
                    )
                    loop_args = ["-stream_loop", "-1"]
                else:
                    playlist = Path(
                        write_concat_file(
                            video_paths, int(repeat), "video_playlist_repeat.txt"
                        )
                    )
                    loop_args = []

                cmd = [
                    FFMPEG, "-hide_banner", "-loglevel", "info",
                    "-re",
                    "-thread_queue_size", "512",
                    "-f", "concat", "-safe", "0",
                ] + loop_args + [
                    "-i", str(playlist),
                    "-map", "0:v:0",
                    "-map", "0:a:0?",
                ]
                cmd += encoding_args(shorts) + [
                    "-rtmp_live", "live",
                    "-flvflags", "no_duration_filesize",
                    rtmp_url(stream_key),
                ]

            if start_process(
                cmd,
                "1 Video" if video_count == 1 else "5 Video Playlist",
            ):
                st.success("FFmpeg sudah dijalankan. Tunggu YouTube menerima sinyal live.")

else:
    st.subheader("🎵 Video + MP3")
    st.caption("Video terus berulang; MP3 diputar berurutan sesuai jumlah putaran yang dipilih.")
    video_path = source_widget("Video", "mp3mode_video", ["mp4", "mkv", "mov", "webm"])
    mp3_files = st.file_uploader("Upload 1–5 MP3", type=["mp3", "m4a", "aac", "wav", "ogg"], accept_multiple_files=True, key="audio_uploads")
    if mp3_files and len(mp3_files) > 5:
        st.warning("Maksimal 5 MP3. Hanya 5 pertama yang digunakan.")
        mp3_files = mp3_files[:5]
    audio_paths = []
    if mp3_files:
        for idx, f in enumerate(mp3_files, 1):
            audio_paths.append(save_upload(f, f"audio{idx}"))

    repeat_option = st.radio("Pengulangan MP3", ["Tanpa batas", "Jumlah pengulangan"], horizontal=True, key="audio_repeat_mode")
    if repeat_option == "Jumlah pengulangan":
        repeat = st.number_input("Jumlah putaran playlist MP3", min_value=1, max_value=100000, value=1, step=1, key="audio_repeat")
    else:
        repeat = None
    shorts = st.checkbox("Mode Shorts 720×1280", key="audio_shorts")

    if st.button("🚀 Mulai Video + MP3", disabled=running, type="primary"):
        if not stream_key:
            st.error("Masukkan Stream Key YouTube.")
        elif not video_path:
            st.error("Pilih video terlebih dahulu.")
        elif not audio_paths:
            st.error("Upload minimal 1 MP3.")
        else:
            if repeat is None:
                audio_playlist = BASE / "audio_playlist.txt"
                audio_playlist.write_text("\n".join("file " + shlex.quote(os.path.abspath(p)) for p in audio_paths) + "\n")
                audio_loop = ["-stream_loop", "-1"]
            else:
                audio_playlist = Path(write_concat_file(audio_paths, int(repeat), "audio_playlist_repeat.txt"))
                audio_loop = []

            cmd = [
                FFMPEG, "-hide_banner", "-loglevel", "info",
                "-re", "-thread_queue_size", "512", "-stream_loop", "-1", "-i", video_path,
                "-re", "-thread_queue_size", "512", "-f", "concat", "-safe", "0",
            ] + audio_loop + ["-i", str(audio_playlist), "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
            cmd += encoding_args(shorts) + [rtmp_url(stream_key)]
            if start_process(cmd, "Video + MP3"):
                st.success("Streaming Video + MP3 sudah dimulai. Jangan tutup/redeploy aplikasi.")

st.divider()
st.subheader("📋 Log FFmpeg")
read_logs()
if st.session_state.get("log_text"):
    st.code(st.session_state["log_text"][-12000:], language="text")
else:
    st.info("Belum ada log.")
