import os
import subprocess
import threading
import static_ffmpeg
import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx

# 1. Konfigurasi direktori pengunduhan ffmpeg agar memiliki izin tulis penuh
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
        log_callback(f"Menjalankan: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        # Membaca output log FFmpeg secara real-time
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

st.markdown("""
Aplikasi ini menggunakan **FFmpeg** untuk melakukan streaming video loop ke YouTube Live secara otomatis.
""")

# Input Form
col1, col2 = st.columns(2)

with col1:
    video_file = st.text_input("Nama File Video", "video.mp4", help="Pastikan file video berada di folder repositori yang sama.")

with col2:
    stream_key = st.text_input("YouTube Stream Key", type="password", help="Masukkan Stream Key dari Dashboard YouTube Live Anda.")

# Checkbox Mode Shorts
shorts_mode = st.checkbox("Mode Shorts (720x1280)")

# Tombol Eksekusi
col_btn1, col_btn2 = st.columns([1, 4])

with col_btn1:
    start_btn = st.button("🚀 Mulai Streaming", disabled=st.session_state['streaming'])

if start_btn:
    if not stream_key:
        st.error("Harap masukkan Stream Key YouTube terlebih dahulu!")
    elif not os.path.exists(video_file):
        st.error(f"File video '{video_file}' tidak ditemukan di repositori!")
    else:
        st.session_state['streaming'] = True
        rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
        
        # Opsi argumen FFmpeg berdasarkan pilihan Mode Shorts
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
        
        # Jalankan thread dengan ScriptRunContext
        thread = threading.Thread(target=run_ffmpeg, args=(cmd,), name="run_ffmpeg")
        add_script_run_ctx(thread)
        thread.start()
        
        st.success("Proses streaming telah dijalankan di background!")

# Area Log Output
st.divider()
st.subheader("📋 Log Aktivitas Streaming")

if st.button("🔄 Perbarui Log"):
    st.rerun()

# Menampilkan isi log
if st.session_state['logs']:
    st.code("\n".join(st.session_state['logs'][-50:]), language="bash")
else:
    st.info("Belum ada log aktivitas.")
