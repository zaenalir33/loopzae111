import os
import subprocess
import threading
import ffdl
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# 1. Unduh biner FFmpeg langsung ke folder /tmp tanpa PermissionError/Lockfile
temp_ffmpeg_dir = "/tmp/ffmpeg_bin"
os.makedirs(temp_ffmpeg_dir, exist_ok=True)

# Cek apakah biner ffmpeg sudah ada di /tmp, jika belum maka unduh otomatis
ffmpeg_executable = os.path.join(temp_ffmpeg_dir, "ffmpeg")
if not os.path.exists(ffmpeg_executable):
    ffdl.install(temp_ffmpeg_dir)

# Masukkan folder /tmp/ffmpeg_bin ke PATH sistem
os.environ["PATH"] += os.pathsep + temp_ffmpeg_dir

# 2. Inisialisasi Session State
if 'logs' not in st.session_state:
    st.session_state['logs'] = []

if 'streaming' not in st.session_state:
    st.session_state['streaming'] = False

def log_callback(msg):
    """Callback aman untuk memperbarui log di session_state."""
    if 'logs' in st.session_state:
        st.session_state['logs'].append(msg)

def run_ffmpeg(cmd):
    """Menjalankan proses FFmpeg di background thread."""
    try:
        log_callback("Menjalankan perintah FFmpeg...")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        for line in process.stdout:
            log_callback(line.strip())
            
        process.wait()
        log_callback("Streaming selesai atau dihentikan.")
    except Exception as e:
        log_callback(f"Error: {e}")
    finally:
        if 'streaming' in st.session_state:
            st.session_state['streaming'] = False

# --- Tampilan Antarmuka Streamlit ---
st.set_page_config(page_title="YouTube Live Streamer", layout="wide")
st.title("📹 YouTube Auto Live Streamer")

col1, col2 = st.columns(2)

with col1:
    video_file = st.text_input("Nama File Video", "video.mp4")

with col2:
    stream_key = st.text_input("YouTube Stream Key", type="password")

shorts_mode = st.checkbox("Mode Shorts (720x1280)")

if st.button("🚀 Mulai Streaming", disabled=st.session_state['streaming']):
    if not stream_key:
        st.error("Harap masukkan Stream Key YouTube terlebih dahulu!")
    elif not os.path.exists(video_file):
        st.error(f"File video '{video_file}' tidak ditemukan di repositori!")
    else:
        st.session_state['streaming'] = True
        rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
        
        # Lokasi penuh biner ffmpeg yang telah diunduh di /tmp
        ffmpeg_bin = os.path.join(temp_ffmpeg_dir, "ffmpeg")
        
        if shorts_mode:
            cmd = [
                ffmpeg_bin, "-re", "-stream_loop", "-1",
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
                ffmpeg_bin, "-re", "-stream_loop", "-1",
                "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
                "-i", video_file,
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k",
                "-maxrate", "2500k", "-bufsize", "5000k", "-g", "60",
                "-keyint_min", "60", "-c:a", "aac", "-b:a", "128k",
                "-f", "flv", rtmp_url
            ]
        
        thread = threading.Thread(target=run_ffmpeg, args=(cmd,), name="run_ffmpeg")
        add_script_run_ctx(thread)
        thread.start()
        
        st.success("Proses streaming telah dijalankan di background!")

st.divider()
st.subheader("📋 Log Aktivitas Streaming")

if st.button("🔄 Perbarui Log"):
    st.rerun()

if st.session_state['logs']:
    st.code("\n".join(st.session_state['logs'][-50:]), language="bash")
else:
    st.info("Belum ada log aktivitas.")
