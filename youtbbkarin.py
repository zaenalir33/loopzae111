import os
import subprocess
import threading
import static_ffmpeg
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# 1. Konfigurasi direktori pengunduhan ffmpeg di folder /tmp (Akses Write/Execute penuh)
temp_ffmpeg_dir = "/tmp/ffmpeg_bin"
os.makedirs(temp_ffmpeg_dir, exist_ok=True)
static_ffmpeg.add_paths(download_dir=temp_ffmpeg_dir)

# 2. Inisialisasi Session State di alur utama Streamlit
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

if 'streaming' not in st.session_state:
    st.session_state['streaming'] = False

def log_callback(msg):
    """Fungsi callback aman untuk memperbarui log di session_state."""
    if 'logs' in st.session_state:
        st.session_state['logs'].append(msg)

def run_ffmpeg(cmd):
    """Menjalankan perintah FFmpeg di background thread."""
    try:
        log_callback(f"Menjalankan perintah FFmpeg...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Membaca log output FFmpeg secara real-time
        for line in process.stdout:
            log_callback(line.strip())
            
        process.wait()
        log_callback("Streaming selesai atau dihentikan.")
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        if 'streaming' in st.session_state:
            st.session_state['streaming'] = False

# --- Antarmuka Aplikasi Streamlit ---
st.set_page_config(page_title="YouTube Live Streamer", layout="wide")
st.title("📹 YouTube Auto Live Streamer")

st.markdown("Aplikasi streaming otomatis ke YouTube Live menggunakan **FFmpeg**.")

# Form Input
col1, col2 = st.columns(2)

with col1:
    video_file = st.text_input("Nama File Video", "video.mp4", help="Pastikan file video ini sudah di-upload ke repositori GitHub Anda.")

with col2:
    stream_key = st.text_input("YouTube Stream Key", type="password", help="Masukkan Stream Key dari Dashboard YouTube Live.")

shorts_mode = st.checkbox("Mode Shorts (Resolusi 720x1280)")

# Tombol Eksekusi
if st.button("🚀 Mulai Streaming", disabled=st.session_state['streaming']):
    if not stream_key:
        st.error("Harap masukkan Stream Key YouTube terlebih dahulu!")
    elif not os.path.exists(video_file):
        st.error(f"File video '{video_file}' tidak ditemukan di repositori GitHub!")
    else:
        st.session_state['streaming'] = True
        rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
        
        # Perintah FFmpeg dengan opsi reconnect otomatis jika sinyal terputus
        if shorts_mode:
            cmd = [
                "ffmpeg", "-re", "-stream_loop", "-1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
                "-i", video_file,
                "-vf", "scale=720:1280",
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
                "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
                "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
                "-f", "flv", rtmp_url
            ]
        else:
            cmd = [
                "ffmpeg", "-re", "-stream_loop", "-1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
                "-i", video_file,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
                "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
                "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
                "-f", "flv", rtmp_url
            ]
        
        # Jalankan background thread dengan ScriptRunContext aman
        thread = threading.Thread(target=run_ffmpeg, args=(cmd,), name="run_ffmpeg")
        add_script_run_ctx(thread)
        thread.start()
        
        st.success("Proses streaming telah berjalan di background!")

# Area Log Aktivitas
st.divider()
st.subheader("📋 Log Aktivitas Streaming")

if st.button("🔄 Perbarui Log"):
    st.rerun()

if st.session_state['logs']:
    st.code("\n".join(st.session_state['logs'][-50:]), language="bash")
else:
    st.info("Belum ada log aktivitas. Klik 'Mulai Streaming' untuk memulai.")
