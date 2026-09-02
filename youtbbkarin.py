import sys
import subprocess
import threading
import os
import time
from pathlib import Path
import streamlit.components.v1 as components

# Install streamlit jika belum ada
try:
    import streamlit as st
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "streamlit"])
    import streamlit as st


APP_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = APP_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Dipakai agar tombol Stop bisa menghentikan proses FFmpeg yang sedang aktif.
FFMPEG_PROCESS = None
PROCESS_LOCK = threading.Lock()


def safe_filename(name: str) -> str:
    """Buat nama file aman untuk disimpan di server."""
    name = Path(name).name
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- ()"
    cleaned = "".join(c if c in allowed else "_" for c in name).strip()
    return cleaned or "video.mp4"


def save_uploaded_file(uploaded_file, slot: int) -> str:
    """Simpan upload ke folder uploads dengan nama slot agar urutannya jelas."""
    original = safe_filename(uploaded_file.name)
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    filename = f"video_{slot}_{stem}{suffix}"
    path = UPLOAD_DIR / filename
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(path)


def save_uploaded_audio(uploaded_file, slot: int) -> str:
    """Simpan MP3 berdasarkan slot agar urutan playlist selalu 1 -> 5."""
    original = safe_filename(uploaded_file.name)
    stem = Path(original).stem
    suffix = Path(original).suffix.lower()
    filename = f"audio_{slot}_{stem}{suffix}"
    path = UPLOAD_DIR / filename
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(path)



def make_concat_playlist(video_paths):
    """Buat file playlist FFmpeg dalam urutan upload 1 -> 4."""
    playlist = UPLOAD_DIR / "playlist.txt"
    with open(playlist, "w", encoding="utf-8") as f:
        for path in video_paths:
            # Escape single quote untuk format concat FFmpeg.
            p = Path(path).resolve().as_posix().replace("'", "'\\''")
            f.write(f"file '{p}'\n")
    return str(playlist)



def resolve_youtube_live_url(source_url, log_callback):
    """Resolve URL YouTube (watch/live) menjadi URL media langsung untuk FFmpeg."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "-g", "-f", "best[height<=720]/best", source_url],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        direct_url = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not direct_url:
            raise RuntimeError("yt-dlp tidak menghasilkan URL media.")
        return direct_url
    except FileNotFoundError:
        raise RuntimeError("Python/yt-dlp tidak tersedia di environment.")
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip()[-1000:]
        raise RuntimeError(f"Gagal mengambil stream YouTube: {detail}")
    except Exception as e:
        raise RuntimeError(str(e))


def make_audio_playlist(audio_paths):
    """Buat playlist concat FFmpeg untuk MP3 1-5."""
    playlist = UPLOAD_DIR / "audio_playlist.txt"
    with open(playlist, "w", encoding="utf-8") as f:
        for path in audio_paths:
            p = Path(path).resolve().as_posix().replace("'", "'\\''")
            f.write(f"file '{p}'\n")
    return str(playlist)

def run_ffmpeg(mode, video_paths, audio_paths, source_url, stream_key, is_shorts, loop_playlist, log_callback):
    global FFMPEG_PROCESS

    output_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"

    if mode == "Re-stream Live YouTube":
        if not source_url:
            log_callback("ERROR: URL live YouTube harus diisi.")
            return

        log_callback("Mode: Re-stream Live YouTube")
        log_callback(f"Sumber: {source_url}")
        try:
            direct_url = resolve_youtube_live_url(source_url, log_callback)
        except Exception as e:
            log_callback(f"ERROR: {e}")
            return

        cmd = [
            "ffmpeg", "-hide_banner", "-re",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", direct_url,
        ]

        if audio_paths:
            audio_playlist = make_audio_playlist(audio_paths)
            # Sumber video live dari channel lain dipakai sebagai video.
            # MP3 sendiri menjadi audio utama dan di-loop 1 -> 5 -> 1...
            cmd += [
                "-stream_loop", "-1",
                "-f", "concat", "-safe", "0", "-i", audio_playlist,
                "-map", "0:v:0", "-map", "1:a:0",
            ]
            log_callback("MP3 sendiri aktif: 1 → 2 → 3 → 4 → 5 → kembali ke 1.")
            log_callback("Audio dari live sumber diganti dengan MP3 sendiri.")
        else:
            cmd += ["-map", "0:v:0", "-map", "0:a:0?"]
            log_callback("Tidak ada MP3 sendiri: audio dari live sumber diteruskan.")

        cmd += [
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", "2500k", "-maxrate", "2500k", "-bufsize", "5000k",
            "-g", "60", "-keyint_min", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        ]
        if is_shorts:
            cmd += ["-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2"]
        cmd += ["-f", "flv", output_url]

    elif mode == "Video + MP3":
        if not video_paths or not audio_paths:
            log_callback("ERROR: Mode Video + MP3 membutuhkan 1 video dan minimal 1 MP3.")
            return

        # Video di-loop terus dan playlist MP3 1 -> 5 juga di-loop terus.
        # Audio asli dari video tidak digunakan.
        audio_playlist = make_audio_playlist(audio_paths)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-re",
            "-stream_loop", "-1",
            "-i", video_paths[0],
            "-stream_loop", "-1",
            "-f", "concat",
            "-safe", "0",
            "-i", audio_playlist,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
        ]

        if is_shorts:
            cmd += [
                "-vf",
                "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            ]

        cmd += ["-f", "flv", output_url]

        log_callback("Mode: Video + MP3")
        log_callback(f"Video loop: {Path(video_paths[0]).name}")
        log_callback("Urutan MP3:")
        for i, path in enumerate(audio_paths, 1):
            log_callback(f"  {i}. {Path(path).name}")
        log_callback("Video di-loop terus.")
        log_callback("MP3: 1 → 2 → 3 → 4 → 5 → kembali ke 1, loop terus.")
        log_callback("Streaming berjalan terus sampai tombol Hentikan Streaming ditekan.")
        log_callback("Audio asli video tidak digunakan; MP3 menjadi audio utama.")
        log_callback("Menjalankan FFmpeg ke YouTube...")

    else:
        if not video_paths:
            log_callback("ERROR: Minimal 1 video diperlukan.")
            return

        playlist = make_concat_playlist(video_paths)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-re",
        ]

        if loop_playlist:
            cmd += ["-stream_loop", "-1"]

        cmd += [
            "-f", "concat",
            "-safe", "0",
            "-i", playlist,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", "2500k",
            "-maxrate", "2500k",
            "-bufsize", "5000k",
            "-g", "60",
            "-keyint_min", "60",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
        ]

        if is_shorts:
            cmd += [
                "-vf",
                "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
            ]

        cmd += ["-f", "flv", output_url]

        log_callback("Mode: 4 Video Playlist")
        log_callback("Urutan video:")
        for i, path in enumerate(video_paths, 1):
            log_callback(f"  {i}. {Path(path).name}")
        log_callback("Playlist: Video 1 → Video 2 → Video 3 → Video 4")
        if loop_playlist:
            log_callback("Setelah video terakhir selesai, playlist kembali ke Video 1.")
        log_callback("Menjalankan FFmpeg ke YouTube...")

    try:
        with PROCESS_LOCK:
            FFMPEG_PROCESS = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

        process = FFMPEG_PROCESS
        for line in process.stdout:
            line = line.strip()
            if line:
                log_callback(line)
        process.wait()
        log_callback(f"FFmpeg berhenti dengan kode: {process.returncode}")
    except FileNotFoundError:
        log_callback("ERROR: FFmpeg tidak ditemukan. Pastikan FFmpeg sudah terpasang dan tersedia di PATH.")
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        with PROCESS_LOCK:
            FFMPEG_PROCESS = None
        log_callback("Streaming selesai atau dihentikan.")

def stop_ffmpeg():
    global FFMPEG_PROCESS
    with PROCESS_LOCK:
        process = FFMPEG_PROCESS
        if process and process.poll() is None:
            try:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            except Exception:
                pass
        FFMPEG_PROCESS = None


def main():
    st.set_page_config(
        page_title="YouTube Live Streaming",
        page_icon="🎥",
        layout="wide"
    )
    st.title("Live Streaming YouTube")

    # Bagian iklan (optional)
    show_ads = st.checkbox("Tampilkan Iklan", value=True)
    if show_ads:
        st.subheader("Iklan Sponsor")
        components.html(
            """
            <div style="background:#f0f2f6;padding:20px;border-radius:10px;text-align:center">
                <script type='text/javascript'
                        src='//pl26562103.profitableratecpm.com/28/f9/95/28f9954a1d5bbf4924abe123c76a68d2.js'>
                </script>
                <p style="color:#888">Iklan akan muncul di sini</p>
            </div>
            """,
            height=300
        )

    mode = st.radio(
        "Pilih Mode Streaming",
        ["4 Video Playlist", "Video + MP3", "Re-stream Live YouTube"],
        horizontal=True,
    )

    selected_paths = []
    audio_paths = []
    source_url = ""

    if mode == "4 Video Playlist":
        st.subheader("Upload Playlist — 4 Video")
        st.caption("Video akan dimainkan sesuai urutan: Video 1 → Video 2 → Video 3 → Video 4.")

        for slot in range(1, 5):
            uploaded_file = st.file_uploader(
                f"Video {slot}",
                type=["mp4", "flv", "mov", "mkv", "webm"],
                key=f"video_uploader_{slot}",
                help=f"Video ke-{slot} dalam urutan playlist."
            )
            if uploaded_file is not None:
                save_uploaded_file(uploaded_file, slot)
                st.success(f"Video {slot} siap: {uploaded_file.name}")

        # Ambil file terbaru dari masing-masing slot sehingga urutan tetap 1-4.
        for slot in range(1, 5):
            candidates = sorted(
                UPLOAD_DIR.glob(f"video_{slot}_*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_paths.append(str(candidates[0]))

        if selected_paths:
            st.write("**Playlist aktif:**")
            for i, path in enumerate(selected_paths, 1):
                st.write(f"{i}. {Path(path).name}")
        else:
            st.info("Belum ada video. Upload minimal 1 video untuk memulai streaming.")

    elif mode == "Re-stream Live YouTube":
        st.subheader("Re-stream Live YouTube")
        st.caption("Masukkan URL live YouTube yang Anda berhak untuk menyiarkan ulang. Video live akan diteruskan ke channel Anda.")
        source_url = st.text_input(
            "URL Live YouTube Sumber",
            placeholder="https://www.youtube.com/watch?v=...",
            help="Gunakan live stream yang Anda miliki izinnya untuk di-re-stream."
        )

        st.markdown("**Opsional: gunakan MP3 sendiri**")
        st.caption("Jika diisi, audio dari live sumber diganti dengan playlist MP3 1 → 5 → 1 terus-menerus. Jika kosong, audio sumber diteruskan.")
        for slot in range(1, 6):
            uploaded_audio = st.file_uploader(
                f"MP3 {slot} (opsional)",
                type=["mp3"],
                key=f"restream_mp3_uploader_{slot}",
            )
            if uploaded_audio is not None:
                audio_saved = save_uploaded_audio(uploaded_audio, slot)
                st.success(f"MP3 {slot} siap: {uploaded_audio.name}")

        for slot in range(1, 6):
            candidates = sorted(
                UPLOAD_DIR.glob(f"audio_{slot}_*.mp3"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                audio_paths.append(str(candidates[0]))

        if audio_paths:
            st.write("**MP3 sendiri aktif:**")
            for i, path in enumerate(audio_paths, 1):
                st.write(f"{i}. {Path(path).name}")

    else:
        st.subheader("Upload Video + MP3 — Playlist 5 MP3")
        st.caption("1 video di-loop terus + MP3 1 → 2 → 3 → 4 → 5 → kembali ke MP3 1 terus-menerus.")

        uploaded_video = st.file_uploader(
            "Video Background",
            type=["mp4", "flv", "mov", "mkv", "webm"],
            key="single_video_uploader",
            help="Video yang akan di-loop terus selama playlist MP3 berjalan.",
        )
        if uploaded_video is not None:
            video_saved = save_uploaded_file(uploaded_video, 1)
            st.success(f"Video siap: {uploaded_video.name}")
        else:
            video_saved = None

        for slot in range(1, 6):
            uploaded_audio = st.file_uploader(
                f"MP3 {slot}",
                type=["mp3"],
                key=f"mp3_uploader_{slot}",
                help=f"MP3 ke-{slot}. Setelah MP3 {slot} selesai, lanjut ke MP3 berikutnya.",
            )
            if uploaded_audio is not None:
                audio_saved = save_uploaded_audio(uploaded_audio, slot)
                st.success(f"MP3 {slot} siap: {uploaded_audio.name}")

        if video_saved:
            selected_paths = [video_saved]
        else:
            candidates = sorted(
                UPLOAD_DIR.glob("video_1_*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                selected_paths = [str(candidates[0])]

        for slot in range(1, 6):
            candidates = sorted(
                UPLOAD_DIR.glob(f"audio_{slot}_*.mp3"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if candidates:
                audio_paths.append(str(candidates[0]))

        if selected_paths:
            st.write(f"**Video:** {Path(selected_paths[0]).name}")
        if audio_paths:
            st.write("**Playlist MP3 aktif:**")
            for i, path in enumerate(audio_paths, 1):
                st.write(f"{i}. {Path(path).name}")

    stream_key = st.text_input("Stream Key YouTube", type="password")
    is_shorts = st.checkbox("Mode Shorts (720x1280)")
    loop_playlist = st.checkbox(
        "Ulangi playlist setelah video terakhir",
        value=True,
        disabled=(mode in ["Video + MP3", "Re-stream Live YouTube"]),
        help="Mode Video + MP3 me-loop video dan MP3 terus-menerus.",
    )

    log_placeholder = st.empty()
    logs = st.session_state.get("logs", [])

    def log_callback(msg):
        logs.append(msg)
        st.session_state["logs"] = logs[-100:]
        try:
            log_placeholder.text("\n".join(st.session_state["logs"][-20:]))
        except Exception:
            print(msg)

    streaming = FFMPEG_PROCESS is not None and FFMPEG_PROCESS.poll() is None

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Mulai Streaming", disabled=streaming, use_container_width=True):
            if mode == "Re-stream Live YouTube" and not source_url:
                st.error("URL live YouTube sumber harus diisi!")
            elif mode != "Re-stream Live YouTube" and not selected_paths:
                st.error("Upload video terlebih dahulu!")
            elif mode == "Video + MP3" and not audio_paths:
                st.error("Upload minimal 1 file MP3 terlebih dahulu!")
            elif not stream_key:
                st.error("Stream Key YouTube harus diisi!")
            else:
                st.session_state["logs"] = []
                thread = threading.Thread(
                    target=run_ffmpeg,
                    args=(mode, selected_paths, audio_paths, source_url, stream_key, is_shorts, loop_playlist, log_callback),
                    daemon=True,
                )
                thread.start()
                time.sleep(0.5)
                st.success("Streaming dimulai ke YouTube!")

    with col2:
        if st.button("⏹️ Hentikan Streaming", disabled=not streaming, use_container_width=True):
            stop_ffmpeg()
            st.warning("Streaming dihentikan!")

    if FFMPEG_PROCESS is not None and FFMPEG_PROCESS.poll() is None:
        st.info("🔴 Streaming sedang berjalan...")

    if st.session_state.get("logs"):
        log_placeholder.text("\n".join(st.session_state["logs"][-20:]))


if __name__ == '__main__':
    main()
