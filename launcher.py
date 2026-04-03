import json
import os
import re
import subprocess
import psutil
import random
import threading
import urllib.request
import urllib.error
import urllib.parse
import time
import shutil
import webbrowser
import http.server
import socket
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QScrollArea, QGridLayout, QFrame, QGraphicsDropShadowEffect,
    QLineEdit, QDialog, QComboBox, QStackedWidget,
    QColorDialog, QFileDialog, QSlider, QSizePolicy, QGraphicsBlurEffect,
    QGraphicsOpacityEffect, QGraphicsScene, QGraphicsView,
)
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QPainterPath, QMovie, QFont,
    QLinearGradient, QBrush, QFontDatabase, QPen, QRegion,
)
from PySide6.QtCore import (
    Qt, QRect, QTimer, QSize, Signal, QObject, QPropertyAnimation,
    QEasingCurve, QRectF, QPoint, QPointF, QThread, QParallelAnimationGroup,
    QSequentialAnimationGroup, QAbstractAnimation, Property,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

_HAS_MULTIMEDIA = True
try:
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except Exception:
    _HAS_MULTIMEDIA = False


# ═══════════════════════════════════════════════════════════════════════════════
#  SMOOTH PROGRESS BAR WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class SmoothProgressBar(QWidget):
    """A progress bar that animates smoothly between values."""

    def __init__(self, width=360, height=8, parent=None):
        super().__init__(parent)
        self._bar_width = width
        self._bar_height = height
        self.setFixedSize(width, height)
        self._fill_pct = 0.0  # 0.0 to 100.0
        self._anim = QPropertyAnimation(self, b"fillPct", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ── FIX #1: Proper PySide6 Property pattern ───────────────────────────────
    def _get_fillPct(self):
        return self._fill_pct

    def _set_fillPct(self, val):
        self._fill_pct = max(0.0, min(100.0, val))
        self.update()

    fillPct = Property(float, _get_fillPct, _set_fillPct)
    # ─────────────────────────────────────────────────────────────────────────

    def set_value(self, pct, duration_ms=400):
        self._anim.stop()
        self._anim.setDuration(duration_ms)
        self._anim.setStartValue(self._fill_pct)
        self._anim.setEndValue(float(pct))
        self._anim.start()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self._bar_width
        h = self._bar_height
        # Track
        p.setBrush(QBrush(QColor("#2a1a40")))
        p.setPen(QPen(QColor("#534ab7"), 1))
        p.drawRoundedRect(0, 0, w, h, h // 2, h // 2)
        # Fill
        fill_w = int(w * self._fill_pct / 100.0)
        if fill_w > 0:
            grad = QLinearGradient(0, 0, fill_w, 0)
            grad.setColorAt(0.0, QColor("#534ab7"))
            grad.setColorAt(0.5, QColor("#afa9ec"))
            grad.setColorAt(1.0, QColor("#7f77dd"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            # clip to rounded rect
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
            p.setClipPath(clip)
            p.drawRect(0, 0, fill_w, h)
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  LOADING SCREEN WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class LoadingScreen(QWidget):
    """Full-window loading overlay — smooth bar, full fade-out."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAutoFillBackground(True)
        self._progress = 0
        self._status   = "Initializing..."
        self._done     = False

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("background: #0d0010;")
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        inner.setFixedWidth(400)
        iv = QVBoxLayout(inner)
        iv.setAlignment(Qt.AlignCenter)
        iv.setSpacing(0)
        iv.setContentsMargins(0, 0, 0, 0)

        icon_lbl = QLabel("⬡")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 72px; color: #534ab7; background: transparent; "
            "letter-spacing: 0px;"
        )
        iv.addWidget(icon_lbl)
        iv.addSpacing(18)

        title = QLabel("GAMEVAULT")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 38px; font-weight: 700; letter-spacing: 10px; "
            "color: #eeedfe; background: transparent; font-family: 'Consolas', monospace;"
        )
        iv.addWidget(title)
        iv.addSpacing(6)

        subtitle = QLabel("LOADING YOUR LIBRARY")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 10px; letter-spacing: 5px; color: #7f77dd; "
            "background: transparent; font-family: 'Consolas', monospace;"
        )
        iv.addWidget(subtitle)
        iv.addSpacing(44)

        # ── Smooth progress bar ───────────────────────────────────────────────
        self._progress_bar = SmoothProgressBar(width=360, height=8)
        iv.addWidget(self._progress_bar, alignment=Qt.AlignCenter)
        iv.addSpacing(12)

        # Bottom row: status + percent
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        self._status_lbl = QLabel("Initializing...")
        self._status_lbl.setStyleSheet(
            "font-size: 11px; color: #534ab7; font-family: 'Consolas', monospace; "
            "background: transparent;"
        )

        self._pct_lbl = QLabel("0%")
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._pct_lbl.setStyleSheet(
            "font-size: 11px; color: #7f77dd; font-family: 'Consolas', monospace; "
            "background: transparent;"
        )

        bottom_row.addWidget(self._status_lbl)
        bottom_row.addStretch()
        bottom_row.addWidget(self._pct_lbl)

        bottom_w = QWidget()
        bottom_w.setFixedWidth(360)
        bottom_w.setStyleSheet("background: transparent;")
        bottom_w.setLayout(bottom_row)
        iv.addWidget(bottom_w, alignment=Qt.AlignCenter)

        self._done_lbl = QLabel("Launching  ↗")
        self._done_lbl.setAlignment(Qt.AlignCenter)
        self._done_lbl.setStyleSheet(
            "font-size: 12px; letter-spacing: 3px; color: #afa9ec; "
            "background: transparent; font-family: 'Consolas', monospace;"
        )
        self._done_lbl.setVisible(False)
        iv.addSpacing(18)
        iv.addWidget(self._done_lbl)

        root.addWidget(inner)

        # Title shimmer timer
        self._shimmer_timer = QTimer(self)
        self._shimmer_timer.setInterval(1200)
        self._shimmer_timer.timeout.connect(self._shimmer)
        self._shimmer_timer.start()
        self._shimmer_phase = 0

    def set_progress(self, pct: int, status: str = "", anim_ms: int = 400):
        self._progress = max(0, min(100, pct))
        if status:
            self._status = status
        self._status_lbl.setText(self._status)
        self._pct_lbl.setText(f"{self._progress}%")
        # Animate bar smoothly
        self._progress_bar.set_value(self._progress, duration_ms=anim_ms)

    def finish_and_hide(self, on_done=None):
        """Animate bar to 100%, show 'Launching', then fade the overlay out."""
        self._done = True
        self._done_lbl.setVisible(True)
        self._shimmer_timer.stop()

        def _do_fade():
            self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
            self._fade_anim.setDuration(700)
            self._fade_anim.setStartValue(1.0)
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
            if on_done:
                self._fade_anim.finished.connect(on_done)
            self._fade_anim.start()

        QTimer.singleShot(900, _do_fade)

    def _shimmer(self):
        self._shimmer_phase = (self._shimmer_phase + 1) % 2
        colors = ["#eeedfe", "#afa9ec"]
        for child in self.findChildren(QLabel):
            if child.text() == "GAMEVAULT":
                c = colors[self._shimmer_phase]
                child.setStyleSheet(
                    f"font-size: 38px; font-weight: 700; letter-spacing: 10px; "
                    f"color: {c}; background: transparent; font-family: 'Consolas', monospace;"
                )
                break


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCORD OAUTH2 CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
DISCORD_CLIENT_ID     = "1489421720753279098"
DISCORD_CLIENT_SECRET = "w8CSyqD7tEHUwoQe3DUqIejVDxHKyvcG"
DISCORD_REDIRECT_URI  = "http://localhost:7483/callback"
DISCORD_OAUTH_SCOPE   = "identify"
DISCORD_AUTH_URL = (
    f"https://discord.com/api/oauth2/authorize"
    f"?client_id={DISCORD_CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(DISCORD_REDIRECT_URI)}"
    f"&response_type=code"
    f"&scope={DISCORD_OAUTH_SCOPE}"
)

# ═══════════════════════════════════════════════════════════════════════════════
#  GLOBAL RUNNING GAME TRACKER
# ═══════════════════════════════════════════════════════════════════════════════
_currently_running_game = {"name": None, "pid": None, "card": None}
_running_lock = threading.Lock()


def _kill_current_game():
    with _running_lock:
        pid  = _currently_running_game.get("pid")
        card = _currently_running_game.get("card")
        name = _currently_running_game.get("name")
        if pid:
            try:
                p = psutil.Process(pid)
                p.terminate()
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    p.kill()
            except Exception:
                pass
            _currently_running_game["pid"]  = None
            _currently_running_game["name"] = None
            _currently_running_game["card"] = None
            if card and not getattr(card, '_destroyed', True):
                try:
                    QTimer.singleShot(0, card._on_game_killed)
                except Exception:
                    pass
            return True
        return False


def _resume_launcher_processes():
    launcher_names = [
        "steam.exe", "steamwebhelper.exe",
        "EpicGamesLauncher.exe", "EpicWebHelper.exe",
    ]
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname in [n.lower() for n in launcher_names]:
                try:
                    proc.resume()
                except Exception:
                    pass
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCORD LOGIN DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class DiscordOAuthHandler(http.server.BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if code:
            DiscordOAuthHandler.auth_code = code
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
<html><body style="background:#07070d;color:#00ff9d;font-family:monospace;
  display:flex;align-items:center;justify-content:center;height:100vh;margin:0;font-size:18px;">
<div style="text-align:center">
  <div style="font-size:48px;margin-bottom:16px">&#10003;</div>
  <p>Login successful! You can close this window and return to GameVault.</p>
</div></body></html>""")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


class DiscordLoginDialog(QDialog):
    login_success = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sign in with Discord")
        self.setFixedSize(420, 380)
        self.setModal(True)
        self._server = None
        self._server_thread = None
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._check_code)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet("""
QDialog {
    background: #07070d;
    border: 1px solid #1a1a2e;
    border-radius: 16px;
}
""")
        root = QVBoxLayout(self)
        root.setContentsMargins(36, 36, 36, 36)
        root.setSpacing(0)

        logo_lbl = QLabel("🎮")
        logo_lbl.setAlignment(Qt.AlignCenter)
        logo_lbl.setStyleSheet("font-size: 52px; background: transparent;")
        root.addWidget(logo_lbl)
        root.addSpacing(10)

        title = QLabel("GameVault")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #00ff9d; "
            "letter-spacing: 3px; font-family: 'Consolas', monospace; background: transparent;")
        root.addWidget(title)
        root.addSpacing(6)

        sub = QLabel("Sign in with your Discord account\nto sync your profile across devices")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            "font-size: 11px; color: #6b6b80; font-family: 'Consolas', monospace; "
            "line-height: 1.5; background: transparent;")
        root.addWidget(sub)
        root.addSpacing(28)

        self._status_lbl = QLabel("Click below to open Discord in your browser")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            "font-size: 10px; color: #44445a; font-family: 'Consolas', monospace; background: transparent;")
        root.addWidget(self._status_lbl)
        root.addSpacing(16)

        self._login_btn = QPushButton("  Sign in with Discord")
        self._login_btn.setFixedHeight(46)
        self._login_btn.setCursor(Qt.PointingHandCursor)
        self._login_btn.setStyleSheet("""
QPushButton {
    background: #5865F2;
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
    font-family: 'Consolas', monospace;
    letter-spacing: 0.5px;
}
QPushButton:hover { background: #4752C4; }
QPushButton:disabled { background: #2a2d50; color: #44445a; }
""")
        self._login_btn.clicked.connect(self._start_login)
        root.addWidget(self._login_btn)
        root.addSpacing(10)

        skip_btn = QPushButton("Continue as Guest")
        skip_btn.setFixedHeight(34)
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.setStyleSheet("""
QPushButton {
    background: transparent;
    color: #44445a;
    border: 1px solid #1a1a2e;
    border-radius: 6px;
    font-size: 11px;
    font-family: 'Consolas', monospace;
}
QPushButton:hover { color: #6b6b80; border-color: #2e2e40; }
""")
        skip_btn.clicked.connect(self.reject)
        root.addWidget(skip_btn)

    def _start_login(self):
        if DISCORD_CLIENT_ID == "YOUR_DISCORD_CLIENT_ID":
            self._status_lbl.setText("⚠ Set your Discord app credentials in launcher.py first!")
            return
        DiscordOAuthHandler.auth_code = None
        self._start_local_server()
        webbrowser.open(DISCORD_AUTH_URL)
        self._login_btn.setText("⟳  Waiting for Discord...")
        self._login_btn.setEnabled(False)
        self._status_lbl.setText("Complete the login in your browser...")
        self._status_lbl.setStyleSheet(
            "font-size: 10px; color: #00ff9d; font-family: 'Consolas', monospace; background: transparent;")
        self._poll_timer.start()

    def _start_local_server(self):
        try:
            self._server = http.server.HTTPServer(("localhost", 7483), DiscordOAuthHandler)
            self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._server_thread.start()
        except Exception as e:
            self._status_lbl.setText(f"Server error: {e}")

    def _check_code(self):
        code = DiscordOAuthHandler.auth_code
        if not code:
            return
        self._poll_timer.stop()
        if self._server:
            self._server.shutdown()
        self._status_lbl.setText("Fetching your Discord profile...")
        threading.Thread(target=self._exchange_code, args=(code,), daemon=True).start()

    def _exchange_code(self, code):
        try:
            data = urllib.parse.urlencode({
                "client_id":     DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  DISCORD_REDIRECT_URI,
            }).encode()
            req = urllib.request.Request(
                "https://discord.com/api/oauth2/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read())
            access_token = token_data.get("access_token")
            if not access_token:
                raise ValueError("No access token in response")
            req2 = urllib.request.Request(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                user = json.loads(resp2.read())
            avatar_hash = user.get("avatar")
            uid = user.get("id", "")
            if avatar_hash:
                user["avatar_url"] = (
                    f"https://cdn.discordapp.com/avatars/{uid}/{avatar_hash}.png?size=128"
                )
            else:
                discriminator = int(user.get("discriminator", 0) or 0)
                user["avatar_url"] = (
                    f"https://cdn.discordapp.com/embed/avatars/{discriminator % 5}.png"
                )
            QTimer.singleShot(0, lambda u=user: self._on_discord_success(u))
        except Exception as e:
            QTimer.singleShot(0, lambda err=str(e): self._on_discord_error(err))

    def _on_discord_success(self, user):
        self.login_success.emit(user)
        self.accept()

    def _on_discord_error(self, err):
        self._login_btn.setText("  Sign in with Discord")
        self._login_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {err}")
        self._status_lbl.setStyleSheet(
            "font-size: 10px; color: #ff3860; font-family: 'Consolas', monospace; background: transparent;")

    def closeEvent(self, event):
        self._poll_timer.stop()
        if self._server:
            threading.Thread(target=self._server.shutdown, daemon=True).start()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════════════════
#  STEAM / EPIC / GAME LOADING
# ═══════════════════════════════════════════════════════════════════════════════
STEAM_PATHS = [
    os.path.expandvars(r"%ProgramFiles(x86)%\Steam"),
    os.path.expandvars(r"%ProgramFiles%\Steam"),
    os.path.expanduser("~/.steam/steam"),
    os.path.expanduser("~/.local/share/Steam"),
    "/Applications/Steam.app/Contents/MacOS",
    os.path.expanduser("~/Library/Application Support/Steam"),
]

STEAM_GENRE_MAP = {
    "730":    "Shooter", "570":    "RPG",     "440":    "Shooter",
    "578080": "Action",  "271590": "Action",  "1091500":"Action",
    "1245620":"RPG",     "489830": "RPG",     "374320": "Stealth",
}
STEAM_GENRE_KEYWORDS = {
    "battle royale": "Shooter", "fps": "Shooter", "shooter": "Shooter",
    "rpg": "RPG", "role": "RPG", "fantasy": "RPG",
    "strategy": "Strategy", "racing": "Racing",
    "stealth": "Stealth", "fighting": "Fighting",
    "rhythm": "Rhythm", "survival": "Survival", "action": "Action",
}


def _guess_genre(name, appid):
    if appid in STEAM_GENRE_MAP:
        return STEAM_GENRE_MAP[appid]
    lower = name.lower()
    for kw, genre in STEAM_GENRE_KEYWORDS.items():
        if kw in lower:
            return genre
    return "Action"


def _find_steam_root():
    for p in STEAM_PATHS:
        if os.path.isdir(p):
            return p
    return None


def _parse_acf(acf_path):
    data = {}
    try:
        with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                parts = re.findall(r'"([^"]*)"', line)
                if len(parts) == 2:
                    data[parts[0].lower()] = parts[1]
    except Exception:
        pass
    return data


def _get_library_folders(steam_root):
    vdf_paths = [
        os.path.join(steam_root, "steamapps", "libraryfolders.vdf"),
        os.path.join(steam_root, "config", "libraryfolders.vdf"),
    ]
    folders = [os.path.join(steam_root, "steamapps")]
    for vdf_path in vdf_paths:
        if not os.path.exists(vdf_path):
            continue
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for m in re.finditer(r'"path"\s+"([^"]+)"', content):
                path = m.group(1).replace("\\\\", "\\")
                sa = os.path.join(path, "steamapps")
                if os.path.isdir(sa) and sa not in folders:
                    folders.append(sa)
        except Exception:
            pass
    return folders


def _find_grid_image(userdata_dir, appid):
    if not os.path.isdir(userdata_dir):
        return ""
    extensions = [".jpg", ".png", ".jpeg"]
    suffixes = ["", "p", "_hero", "_logo"]
    try:
        for uid in os.listdir(userdata_dir):
            grid_dir = os.path.join(userdata_dir, uid, "config", "grid")
            if not os.path.isdir(grid_dir):
                continue
            for suf in suffixes:
                for ext in extensions:
                    candidate = os.path.join(grid_dir, f"{appid}{suf}{ext}")
                    if os.path.exists(candidate):
                        return candidate
    except Exception:
        pass
    return ""


def load_steam_games():
    steam_root = _find_steam_root()
    if not steam_root:
        return []
    library_folders = _get_library_folders(steam_root)
    seen_appids = set()
    result = []
    for steamapps_dir in library_folders:
        if not os.path.isdir(steamapps_dir):
            continue
        for fname in os.listdir(steamapps_dir):
            if not fname.startswith("appmanifest_") or not fname.endswith(".acf"):
                continue
            meta = _parse_acf(os.path.join(steamapps_dir, fname))
            appid = meta.get("appid", "")
            name = meta.get("name", "")
            if not appid or not name or appid in seen_appids:
                continue
            if any(kw in name.lower() for kw in [
                "redistributable","redist","steamworks","directx","vcredist",
                "common redist","steam linux runtime","proton","steam controller",
            ]):
                continue
            seen_appids.add(appid)
            genre = _guess_genre(name, appid)
            thumbnail = _find_grid_image(os.path.join(steam_root, "userdata"), appid)
            result.append({
                "name": name, "description": f"Steam • AppID {appid}",
                "thumbnail": thumbnail, "path": f"steam://rungameid/{appid}",
                "genre": genre, "appid": appid,
                "install_dir": meta.get("installdir", ""),
                "steamapps": steamapps_dir, "source": "steam",
            })
    result.sort(key=lambda g: g["name"].lower())
    return result


EPIC_PATHS = [
    os.path.expandvars(r"%ProgramData%\Epic\EpicGamesLauncher\Data\Manifests"),
    os.path.expanduser("~/Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests"),
    os.path.expanduser("~/.config/Epic/EpicGamesLauncher/Data/Manifests"),
]

EPIC_KNOWN_GENRES = {
    "Fortnite": "Shooter", "Rocket League": "Racing", "Fall Guys": "Action",
    "Borderlands 3": "Shooter", "Hades": "Action", "Satisfactory": "Survival",
}


def _epic_guess_genre(name):
    for known, genre in EPIC_KNOWN_GENRES.items():
        if known.lower() in name.lower():
            return genre
    return "Action"


def _find_epic_manifests_dir():
    for p in EPIC_PATHS:
        if os.path.isdir(p):
            return p
    return None


def _parse_epic_manifest(manifest_path):
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
    except Exception:
        return None
    if data.get("bIsIncompleteInstall", False):
        return None
    display_name    = data.get("DisplayName", "").strip()
    app_name        = data.get("AppName", "").strip()
    install_loc     = data.get("InstallLocation", "").strip()
    launch_exe      = data.get("LaunchExecutable", "").strip()
    catalog_item_id = data.get("CatalogItemId", "").strip()
    catalog_namespace = data.get("CatalogNamespace", "").strip()
    if not display_name or not app_name:
        return None
    skip_names = ["unreal engine", "epic games launcher", "directx", "vcredist"]
    if any(s in display_name.lower() for s in skip_names):
        return None
    if install_loc and launch_exe:
        launch_path = os.path.join(install_loc, launch_exe)
    else:
        launch_path = f"com.epicgames.launcher://apps/{app_name}?action=launch&silent=true"
    return {
        "name": display_name, "description": f"Epic Games • {display_name}",
        "thumbnail": "", "path": launch_path,
        "genre": _epic_guess_genre(display_name), "appid": app_name,
        "install_dir": os.path.basename(install_loc) if install_loc else app_name,
        "source": "epic",
        "catalog_namespace": catalog_namespace,
        "catalog_item_id": catalog_item_id,
    }


def load_epic_games():
    manifests_dir = _find_epic_manifests_dir()
    if not manifests_dir:
        return []
    result = []
    seen = set()
    try:
        for fname in os.listdir(manifests_dir):
            if not fname.endswith(".item"):
                continue
            game = _parse_epic_manifest(os.path.join(manifests_dir, fname))
            if game and game["name"] not in seen:
                seen.add(game["name"])
                result.append(game)
    except Exception as e:
        print(f"[GameVault] Epic scan error: {e}")
    result.sort(key=lambda g: g["name"].lower())
    return result


# ═══════════════════════════════════════════════════════════════════════════════
#  ASSET CACHING + FETCHING
# ═══════════════════════════════════════════════════════════════════════════════
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".game_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(appid, ext):
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', str(appid))
    return os.path.join(_CACHE_DIR, f"{safe}{ext}")


def _download_image(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return True
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status != 200:
                    continue
                data = resp.read()
            if len(data) < 1024:
                continue
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
    return False


_active_signals = []
_active_signals_lock = threading.Lock()


class _AssetSignal(QObject):
    done = Signal(str, str)


def _fetch_steam_cover(appid):
    urls_to_try = [
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900_2x.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/library_600x900_2x.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg",
        f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
        f"https://store.akamai.steamstatic.com/public/images/apps/{appid}/header.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_616x353.jpg",
        f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/capsule_467x181.jpg",
    ]
    dest_v = _cache_path(appid, "_cover_v.jpg")
    dest_h = _cache_path(appid, "_cover_h.jpg")
    for i, url in enumerate(urls_to_try):
        dest = dest_v if i < 2 else dest_h
        if _download_image(url, dest):
            return dest
    return ""


def _fetch_steam_assets(appid):
    meta_cache = _cache_path(appid, "_meta_v4.json")
    if os.path.exists(meta_cache):
        try:
            with open(meta_cache, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("img_path") and os.path.exists(cached["img_path"]):
                return cached
        except Exception:
            pass
    img_path = _fetch_steam_cover(appid)
    description = ""
    try:
        details_url = f"https://store.steampowered.com/api/appdetails?appids={appid}&filters=basic"
        req = urllib.request.Request(details_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        app = data.get(str(appid), {})
        d = app.get("data", {}) if app.get("success") else {}
        description = d.get("short_description", "")
    except Exception:
        pass
    result = {"description": description, "img_path": img_path}
    with open(meta_cache, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return result


def _fetch_epic_cover(game):
    appid     = game.get("appid", "")
    game_name = game.get("name", "")
    dest      = _cache_path(f"epic_{appid}", "_cover.jpg")
    if os.path.exists(dest) and os.path.getsize(dest) > 1024:
        return dest
    thumb = game.get("thumbnail", "")
    if thumb and os.path.exists(thumb) and os.path.getsize(thumb) > 1024:
        return thumb
    catalog_ns = game.get("catalog_namespace", "")
    catalog_id = game.get("catalog_item_id", "")
    epic_templates = []
    if catalog_ns and catalog_id:
        epic_templates = [
            f"https://cdn1.epicgames.com/offer/images/{catalog_ns}/{catalog_id}/offer/wide-1920x1080-{catalog_id}.jpg",
            f"https://cdn1.epicgames.com/{catalog_ns}/offer/wide-1920x1080-{catalog_id}.jpg",
            f"https://cdn2.epicgames.com/{catalog_ns}/offer/wide-1920x1080-{catalog_id}.jpg",
        ]
    for url in epic_templates:
        if _download_image(url, dest):
            return dest
    try:
        encoded = urllib.parse.quote(game_name)
        search_url = f"https://store.steampowered.com/api/storesearch/?term={encoded}&l=english&cc=US"
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            steam_data = json.loads(resp.read().decode("utf-8"))
        items = steam_data.get("items", [])
        for item in items[:3]:
            item_name = item.get("name", "").lower()
            if _fuzzy_name_match(game_name, item_name):
                steam_appid = str(item.get("id", ""))
                cover_url = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{steam_appid}/library_600x900_2x.jpg"
                if _download_image(cover_url, dest):
                    return dest
                header_url = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{steam_appid}/header.jpg"
                if _download_image(header_url, dest):
                    return dest
    except Exception as e:
        print(f"[GameVault] Epic Steam fallback failed for {game_name}: {e}")
    return ""


def _fuzzy_name_match(name_a, name_b):
    def words(s):
        return set(re.sub(r"[^\w\s]", "", s.lower()).split())
    a = words(name_a)
    b = words(name_b)
    if not a or not b:
        return False
    overlap = len(a & b)
    return overlap >= max(1, min(len(a), len(b)) * 0.6)


def fetch_game_assets_async(game, on_done):
    appid  = game.get("appid", "")
    source = game.get("source", "")
    sig = _AssetSignal()
    sig.done.connect(on_done)
    with _active_signals_lock:
        _active_signals.append(sig)

    def _run():
        desc     = game.get("description", "")
        img_path = game.get("thumbnail", "")
        try:
            if source == "steam" and appid:
                result   = _fetch_steam_assets(appid)
                desc     = result.get("description", desc) or desc
                fetched  = result.get("img_path", "")
                if fetched and os.path.exists(fetched):
                    img_path = fetched
            elif source == "epic":
                fetched = _fetch_epic_cover(game)
                if fetched and os.path.exists(fetched):
                    img_path = fetched
        except Exception as e:
            print(f"[GameVault] Asset error for {game.get('name','?')}: {e}")
        sig.done.emit(desc, img_path)
        with _active_signals_lock:
            try:
                _active_signals.remove(sig)
            except ValueError:
                pass

    threading.Thread(target=_run, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#  RUNNING GAME DETECTION
# ═══════════════════════════════════════════════════════════════════════════════
def _find_running_game_pid(game):
    install_dir = game.get("install_dir", "").lower()
    game_name   = game.get("name", "").lower()
    if not install_dir and not game_name:
        return None
    try:
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                exe   = (proc.info.get("exe") or "").replace("\\", "/").lower()
                pname = (proc.info.get("name") or "").lower()
                if install_dir and install_dir in exe:
                    return proc.info["pid"]
                words = [w for w in re.split(r"\W+", game_name) if len(w) >= 3]
                if words and any(w in pname for w in words):
                    return proc.info["pid"]
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass
    return None


def kill_game(pid):
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            psutil.Process(pid).kill()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
#  PERSISTENT DATA
# ═══════════════════════════════════════════════════════════════════════════════
USER_FILE = "user_data.json"
DEFAULTS = {
    "username": "Player One", "tag": "#0001", "status": "Online",
    "avatar": "🎮", "pfp_path": "", "discord_id": "",
    "discord_avatar_url": "", "discord_username": "",
    "play_counts": {},
    "friends": [
        {"name": "XenonKill",  "tag": "#4421", "avatar": "💀", "status": "Online",  "game": "Cyber Quest"},
        {"name": "NovaByte",   "tag": "#8832", "avatar": "🛸", "status": "Online",  "game": "Neon Drift"},
        {"name": "ShadowFox",  "tag": "#1107", "avatar": "🦊", "status": "Away",    "game": ""},
        {"name": "CryptoSlyr", "tag": "#2299", "avatar": "⚡", "status": "Offline", "game": ""},
    ],
    "messages": {},
    "live_bg": "",
    "live_bg_opacity": 60,
    "theme": {
        "accent": "#00ff9d", "bg_style": "pure_black",
        "font": "monospace", "density": "normal", "preset": "Neon Terminal",
    },
}


def load_user():
    try:
        with open(USER_FILE, "r") as f:
            d = json.load(f)
        for k, v in DEFAULTS.items():
            if k not in d:
                d[k] = v.copy() if isinstance(v, dict) else v
        return d
    except FileNotFoundError:
        return {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}


def save_user(data):
    with open(USER_FILE, "w") as f:
        json.dump(data, f, indent=2)


user_data = load_user()


# ═══════════════════════════════════════════════════════════════════════════════
#  THEME
# ═══════════════════════════════════════════════════════════════════════════════
THEME_PRESETS = {
    "Neon Terminal": {"accent": "#00ff9d", "bg_style": "pure_black", "font": "monospace"},
    "Cyber Blood":   {"accent": "#ff3860", "bg_style": "dark_navy",  "font": "monospace"},
    "Void Purple":   {"accent": "#bf5fff", "bg_style": "dark_purple","font": "monospace"},
    "Ice Core":      {"accent": "#00c8ff", "bg_style": "pure_black", "font": "sans"},
    "Solar Flare":   {"accent": "#ffd000", "bg_style": "dark_navy",  "font": "sans"},
}

BG_STYLES = {
    "pure_black":  {"base": "#070709", "panel": "#0d0d12", "card": "#111118", "card_h": "#181825", "input": "#0a0a10"},
    "dark_navy":   {"base": "#060810", "panel": "#0b0d18", "card": "#101422", "card_h": "#181e30", "input": "#080a14"},
    "dark_purple": {"base": "#08060e", "panel": "#0f0b18", "card": "#140f22", "card_h": "#1e1530", "input": "#0a0810"},
}

FONT_MAP = {
    "monospace": "'Consolas', 'Courier New', monospace",
    "sans":      "'Segoe UI', 'SF Pro Display', 'Helvetica Neue', sans-serif",
}


def _mix(hex_a, hex_b, t):
    a = QColor(hex_a); b = QColor(hex_b)
    r  = int(a.red()   * t + b.red()   * (1 - t))
    g  = int(a.green() * t + b.green() * (1 - t))
    bl = int(a.blue()  * t + b.blue()  * (1 - t))
    return QColor(r, g, bl).name()


class Theme:
    def reload(self):
        t = user_data.get("theme", DEFAULTS["theme"])
        self.accent   = t.get("accent",   "#00ff9d")
        self.bg_style = t.get("bg_style", "pure_black")
        self.font     = t.get("font",     "monospace")
        bg = BG_STYLES.get(self.bg_style, BG_STYLES["pure_black"])
        self.bg_base   = bg["base"]
        self.bg_panel  = bg["panel"]
        self.bg_card   = bg["card"]
        self.bg_card_h = bg["card_h"]
        self.bg_input  = bg["input"]
        self.border    = _mix(self.accent, bg["base"], 0.12)
        self.border_h  = _mix(self.accent, bg["base"], 0.28)
        self.text_pri  = "#e8e8f0"
        self.text_sec  = "#6b6b80"
        self.text_dim  = "#2e2e40"
        self.muted     = "#44445a"
        self.font_fam  = FONT_MAP.get(self.font, FONT_MAP["monospace"])
        self.accent_dim   = _mix(self.accent, bg["base"], 0.22)
        self.accent_faint = _mix(self.accent, bg["base"], 0.10)
        self.neon_r = "#ff3860"; self.neon_y = "#ffd000"
        self.neon_b = "#00c8ff"; self.neon_p = "#bf5fff"

    def qss(self):
        return f"""
QWidget {{ background-color: transparent; color: {self.text_pri}; font-family: {self.font_fam}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: {self.bg_card}; width: 4px; border-radius: 2px; }}
QScrollBar::handle:vertical {{ background: {self.accent}; border-radius: 2px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: {self.bg_input}; color: {self.text_pri};
    border: 1px solid {self.border_h}; border-radius: 6px;
    padding: 6px 10px; font-family: {self.font_fam}; font-size: 13px;
}}
QLineEdit:focus {{ border: 1px solid {self.accent}; }}
"""


TH = Theme()
TH.reload()


# ═══════════════════════════════════════════════════════════════════════════════
#  CIRCULAR AVATAR WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class ClickableAvatar(QLabel):
    clicked = Signal()

    def __init__(self, size=80, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self._size = size
        self._pfp_path = ""
        self._default_emoji = user_data.get("avatar", "🎮")
        self._movie = None
        self._static_pixmap = None
        self._load_from_user_data()

    def _load_from_user_data(self):
        self._pfp_path = user_data.get("pfp_path", "")
        self._default_emoji = user_data.get("avatar", "🎮")
        if not self._pfp_path:
            discord_cache = _cache_path("discord_avatar", ".jpg")
            if os.path.exists(discord_cache):
                self._pfp_path = discord_cache
        self._setup_media(self._pfp_path)

    def _setup_media(self, path):
        if self._movie:
            self._movie.stop()
            self._movie.frameChanged.disconnect()
            self._movie = None
        self._static_pixmap = None
        if not path or not os.path.exists(path):
            self.update()
            return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".gif":
            self._movie = QMovie(path)
            self._movie.setCacheMode(QMovie.CacheAll)
            self._movie.frameChanged.connect(lambda _: self.update())
            self._movie.start()
        else:
            px = QPixmap(path)
            if not px.isNull():
                self._static_pixmap = px
        self.update()

    def update_avatar(self):
        self._pfp_path = user_data.get("pfp_path", "")
        self._default_emoji = user_data.get("avatar", "🎮")
        if not self._pfp_path:
            discord_cache = _cache_path("discord_avatar", ".jpg")
            if os.path.exists(discord_cache):
                self._pfp_path = discord_cache
        self._setup_media(self._pfp_path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        s = self._size
        rect_f = QRectF(0, 0, s, s)
        clip_path = QPainterPath()
        clip_path.addEllipse(rect_f)
        painter.setClipPath(clip_path)
        drawn = False
        if self._movie and self._movie.state() != QMovie.NotRunning:
            frame_px = self._movie.currentPixmap()
            if not frame_px.isNull():
                scaled = frame_px.scaled(QSize(s, s), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                ox = (scaled.width() - s) // 2
                oy = (scaled.height() - s) // 2
                painter.drawPixmap(-ox, -oy, scaled)
                drawn = True
        elif self._static_pixmap and not self._static_pixmap.isNull():
            scaled = self._static_pixmap.scaled(QSize(s, s), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            ox = (scaled.width() - s) // 2
            oy = (scaled.height() - s) // 2
            painter.drawPixmap(-ox, -oy, scaled)
            drawn = True
        if not drawn:
            painter.fillRect(self.rect(), QColor(TH.bg_card))
            painter.setPen(QColor(TH.text_pri))
            font = QFont()
            font.setPointSize(s // 3)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, self._default_emoji)
        painter.setClipping(False)
        pen = QPen(QColor(TH.accent), 2)
        painter.setPen(pen)
        painter.drawEllipse(rect_f.adjusted(1, 1, -1, -1))
        painter.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  GAMES DATA
# ═══════════════════════════════════════════════════════════════════════════════
DEMO_GAMES = [
    {"name": "Cyber Quest",   "description": "Epic sci-fi RPG.", "thumbnail": "", "path": "", "genre": "RPG",      "appid": "", "source": "demo"},
    {"name": "Shadow Runner", "description": "Fast platformer.",  "thumbnail": "", "path": "", "genre": "Action",  "appid": "", "source": "demo"},
    {"name": "Neon Drift",    "description": "Anti-gravity racing.", "thumbnail": "", "path": "", "genre": "Racing","appid": "", "source": "demo"},
    {"name": "Star Siege",    "description": "4X space strategy.", "thumbnail": "", "path": "", "genre": "Strategy","appid": "", "source": "demo"},
    {"name": "Void Protocol", "description": "Tactical stealth.", "thumbnail": "", "path": "", "genre": "Stealth", "appid": "", "source": "demo"},
    {"name": "Iron Fist",     "description": "Fighting tournament.", "thumbnail": "","path": "", "genre": "Fighting","appid": "","source": "demo"},
    {"name": "Dungeon Lords",  "description": "Classic crawler.",  "thumbnail": "", "path": "", "genre": "RPG",    "appid": "", "source": "demo"},
    {"name": "Ember Throne",  "description": "Kingdom builder.",  "thumbnail": "", "path": "", "genre": "Strategy","appid": "", "source": "demo"},
    {"name": "Pulse Wave",    "description": "Rhythm-shooter.",   "thumbnail": "", "path": "", "genre": "Rhythm",  "appid": "", "source": "demo"},
    {"name": "Wasteland X",   "description": "Open world survival.", "thumbnail": "","path": "","genre": "Survival","appid": "","source": "demo"},
    {"name": "Zero Hour",     "description": "Tactical shooter.", "thumbnail": "", "path": "", "genre": "Shooter", "appid": "", "source": "demo"},
    {"name": "Arcane Blade",  "description": "Soulslike RPG.",    "thumbnail": "", "path": "", "genre": "RPG",    "appid": "", "source": "demo"},
]

GAMES_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "games.json")

_steam_games = load_steam_games()
_epic_games  = load_epic_games()

try:
    with open(GAMES_JSON_PATH, "r", encoding="utf-8") as f:
        _json_games = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    _json_games = []

_seen_names = set()
games = []


def _add_games(source_list):
    for g in source_list:
        if g["name"] not in _seen_names:
            _seen_names.add(g["name"])
            games.append(g)


_add_games(_steam_games)
_add_games(_epic_games)
_add_games(_json_games)
if not games:
    _add_games(DEMO_GAMES)

games.sort(key=lambda g: g["name"].lower())

GENRE_ICON   = {"RPG": "⚔", "Action": "💥", "Racing": "🏎", "Strategy": "♟",
                "Fighting": "🥊", "Stealth": "🗡", "Rhythm": "🎵", "Shooter": "🔫",
                "Survival": "🪓"}
GENRE_COLORS = {
    "RPG":      ("#bf5fff", "#1a0d2e"), "Action":   ("#ff3860", "#2e0d12"),
    "Racing":   ("#00c8ff", "#0d1a2e"), "Strategy": ("#ffd000", "#2e280d"),
    "Fighting": ("#ff3860", "#2e0d12"), "Stealth":  ("#00ff9d", "#0d2e1a"),
    "Rhythm":   ("#bf5fff", "#1a0d2e"), "Shooter":  ("#00c8ff", "#0d1a2e"),
    "Survival": ("#ffd000", "#2e1a0d"),
}
STATUS_COLOR = {
    "Online": "#00ff9d", "Away": "#ffd000",
    "Offline": "#44445a", "Do Not Disturb": "#ff3860",
}
SOURCE_COLORS = {"steam": "#1a9fff", "epic": "#a855f7", "demo": "#6b6b80", "": "#6b6b80"}


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def glass_card_style(alpha=40, accent=None, border_alpha=None):
    ba = border_alpha or 60
    a = accent or TH.accent
    return f"""QFrame {{
    background: rgba(10,10,18,{alpha});
    border: 1px solid rgba(255,255,255,{ba // 4});
    border-radius: 12px;
    backdrop-filter: blur(20px);
}}"""


def sidebar_btn_base():
    return f"""QPushButton {{
    background: transparent; color: {TH.text_sec};
    border: none; border-left: 3px solid transparent;
    text-align: left; padding: 8px 16px 8px 12px;
    font-size: 11px; font-family: {TH.font_fam}; font-weight: 600; letter-spacing: 0.5px;
}}
QPushButton:hover {{ background: rgba(255,255,255,6); color: {TH.text_pri}; border-left: 3px solid {TH.muted}; }}"""


def sidebar_btn_active():
    return f"""QPushButton {{
    background: rgba(255,255,255,8); color: {TH.accent};
    border: none; border-left: 3px solid {TH.accent};
    text-align: left; padding: 8px 16px 8px 12px;
    font-size: 11px; font-family: {TH.font_fam}; font-weight: 700; letter-spacing: 0.5px;
}}"""


def tab_active_style():
    return f"""QPushButton {{
    background: rgba(255, 255, 255, 0.1); color: {TH.text_pri};
    border: none; border-bottom: 2px solid {TH.accent};
    padding: 8px 20px; font-size: 11px; font-weight: 700;
    font-family: {TH.font_fam}; letter-spacing: 1px;
}}"""


def tab_inactive_style():
    return f"""QPushButton {{
    background: transparent; color: {TH.text_sec};
    border: none; border-bottom: 2px solid transparent;
    padding: 8px 20px; font-size: 11px; font-weight: 600;
    font-family: {TH.font_fam}; letter-spacing: 1px;
}}
QPushButton:hover {{ color: {TH.text_pri}; border-bottom: 2px solid {TH.muted}; }}"""


def ghost_btn(color=None):
    c = color or TH.accent
    return f"""QPushButton {{
    background: transparent; color: {c}; border: 1px solid {c}60; border-radius: 5px;
    padding: 5px 12px; font-family: {TH.font_fam}; font-size: 10px; font-weight: 700;
}}
QPushButton:hover {{ border: 1px solid {c}; background: {c}15; }}"""


def action_btn(color=None):
    c = color or TH.accent
    return f"""QPushButton {{
    background: {c}; color: #050508; border: none; border-radius: 5px;
    padding: 6px 16px; font-family: {TH.font_fam}; font-size: 10px; font-weight: 700;
}}
QPushButton:hover {{ background: {_mix(c, '#ffffff', 0.85)}; }}"""


def clear_layout(layout):
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())


# ═══════════════════════════════════════════════════════════════════════════════
#  LIVE BACKGROUND WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class LiveBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(False)
        self._mode = "none"
        self._pixmap = None
        self._movie = None
        self._opacity = user_data.get("live_bg_opacity", 60) / 100.0
        self._player = None
        self._video_widget = None
        self.lower()
        path = user_data.get("live_bg", "")
        if path and os.path.exists(path):
            self.load(path)

    def set_opacity(self, value):
        self._opacity = value / 100.0
        user_data["live_bg_opacity"] = value
        save_user(user_data)
        self.update()
        if self._video_widget:
            eff = QGraphicsOpacityEffect(self._video_widget)
            eff.setOpacity(self._opacity)
            self._video_widget.setGraphicsEffect(eff)

    def load(self, path):
        self._cleanup()
        if not path or not os.path.exists(path):
            self._mode = "none"; self.update(); return
        ext = os.path.splitext(path)[1].lower()
        if ext == ".gif":
            self._mode = "gif"
            self._movie = QMovie(path)
            self._movie.frameChanged.connect(lambda _: self.update())
            self._movie.start()
        elif ext in (".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv") and _HAS_MULTIMEDIA:
            self._mode = "video"
            self._video_widget = QVideoWidget(self)
            self._video_widget.setGeometry(self.rect())
            eff = QGraphicsOpacityEffect(self._video_widget)
            eff.setOpacity(self._opacity)
            self._video_widget.setGraphicsEffect(eff)
            self._video_widget.lower()
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._audio.setVolume(0)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video_widget)
            from PySide6.QtCore import QUrl
            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.setLoops(-1)
            self._player.play()
            self._video_widget.show()
            self._video_widget.lower()
        else:
            self._mode = "image"
            self._pixmap = QPixmap(path)
        self.update()

    def _cleanup(self):
        if self._movie:
            self._movie.stop(); self._movie = None
        if self._player:
            self._player.stop(); self._player = None
        if self._video_widget:
            self._video_widget.hide(); self._video_widget.deleteLater(); self._video_widget = None
        self._pixmap = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._video_widget:
            self._video_widget.setGeometry(self.rect())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if self._mode == "image" and self._pixmap and not self._pixmap.isNull():
            p.setOpacity(self._opacity)
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            p.drawPixmap(-x, -y, scaled)
            p.setOpacity(1.0)
        elif self._mode == "gif" and self._movie:
            p.setOpacity(self._opacity)
            frame = self._movie.currentPixmap()
            if not frame.isNull():
                scaled = frame.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                x = (scaled.width() - self.width()) // 2
                y = (scaled.height() - self.height()) // 2
                p.drawPixmap(-x, -y, scaled)
            p.setOpacity(1.0)
        else:
            grad = QLinearGradient(0, 0, self.width(), self.height())
            grad.setColorAt(0,   QColor("#07070d"))
            grad.setColorAt(0.5, QColor("#0a0a16"))
            grad.setColorAt(1,   QColor("#070710"))
            p.fillRect(self.rect(), QBrush(grad))
        overlay_alpha = max(40, int(255 * (1.0 - self._opacity * 0.5)))
        p.fillRect(self.rect(), QColor(5, 5, 14, overlay_alpha))
        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND SETTINGS PANEL
# ═══════════════════════════════════════════════════════════════════════════════
class BgSettingsPanel(QFrame):
    bg_changed = Signal()

    def __init__(self, bg_widget, parent=None):
        super().__init__(parent)
        self._bg = bg_widget
        self.setObjectName("BgPanel")
        self.setStyleSheet(f"""QFrame#BgPanel {{
    background: rgba(8,8,16,220); border: 1px solid {TH.border_h}; border-radius: 14px;
}}""")
        self.setFixedWidth(340)
        self._build()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(18, 18, 18, 18); v.setSpacing(12)
        title = QLabel("LIVE BACKGROUND")
        title.setStyleSheet(f"font-size:10px; font-weight:700; color:{TH.accent}; letter-spacing:2px; font-family:{TH.font_fam}; background:transparent;")
        v.addWidget(title)
        cur_path = user_data.get("live_bg", "")
        if cur_path and os.path.exists(cur_path):
            name = os.path.basename(cur_path)
            info = QLabel(f"Current: {name[:36]}")
            info.setStyleSheet(f"font-size:9px; color:{TH.text_sec}; font-family:{TH.font_fam}; background:transparent;")
            v.addWidget(info)
        hint = QLabel("Supports images (.jpg .png), animated GIFs, and\nvideos (.mp4 .webm) — loops automatically.")
        hint.setStyleSheet(f"font-size:9px; color:{TH.text_dim}; font-family:{TH.font_fam}; background:transparent;")
        hint.setWordWrap(True)
        v.addWidget(hint)
        choose_btn = QPushButton("⊕  BROWSE FILE")
        choose_btn.setStyleSheet(action_btn(TH.accent))
        choose_btn.setCursor(Qt.PointingHandCursor)
        choose_btn.clicked.connect(self._choose_file)
        v.addWidget(choose_btn)
        remove_btn = QPushButton("✕  REMOVE BACKGROUND")
        remove_btn.setStyleSheet(ghost_btn(TH.text_sec))
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(self._remove_bg)
        v.addWidget(remove_btn)
        v.addWidget(self._sep())
        opacity_lbl = QLabel("BRIGHTNESS  //  how visible the background is")
        opacity_lbl.setStyleSheet(f"font-size:9px; color:{TH.text_sec}; letter-spacing:1px; font-family:{TH.font_fam}; background:transparent;")
        v.addWidget(opacity_lbl)
        sl_row = QHBoxLayout(); sl_row.setSpacing(8)
        self._opac_slider = QSlider(Qt.Horizontal)
        self._opac_slider.setRange(10, 100)
        self._opac_slider.setValue(user_data.get("live_bg_opacity", 60))
        self._opac_slider.setStyleSheet(f"""
QSlider::groove:horizontal{{ background: {TH.bg_card}; height:4px; border-radius:2px;}}
QSlider::handle:horizontal{{ background:{TH.accent}; width:12px; height:12px; margin:-4px 0; border-radius:6px;}}
QSlider::sub-page:horizontal{{ background:{TH.accent}; height:4px; border-radius:2px;}}""")
        self._opac_val = QLabel(f"{self._opac_slider.value()}%")
        self._opac_val.setFixedWidth(36)
        self._opac_val.setStyleSheet(f"font-size:10px; color:{TH.text_pri}; font-family:{TH.font_fam}; background:transparent;")
        self._opac_slider.valueChanged.connect(self._set_opacity)
        sl_row.addWidget(self._opac_slider, stretch=1)
        sl_row.addWidget(self._opac_val)
        v.addLayout(sl_row)

    def _sep(self):
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"QFrame{{ color:{TH.border}; background:{TH.border}; max-height:1px; }}")
        return f

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Live Background", "", "Media (*.jpg *.jpeg *.png *.gif *.mp4 *.webm *.mkv *.avi *.mov)")
        if path:
            user_data["live_bg"] = path; save_user(user_data)
            self._bg.load(path); self.bg_changed.emit(); self._rebuild()

    def _remove_bg(self):
        user_data["live_bg"] = ""; save_user(user_data)
        self._bg.load(""); self.bg_changed.emit(); self._rebuild()

    def _set_opacity(self, val):
        self._opac_val.setText(f"{val}%"); self._bg.set_opacity(val)

    def _rebuild(self):
        clear_layout(self.layout()); temp = QWidget(); temp.setLayout(self.layout()); self._build()


# ═══════════════════════════════════════════════════════════════════════════════
#  ANIMATED OPACITY WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class FadeWrapper(QWidget):
    def __init__(self, child, delay_ms=0, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, self._start_fade_in)
        else:
            self._start_fade_in()

    def _start_fade_in(self):
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def fade_out(self, on_done=None):
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        if on_done:
            self._anim.finished.connect(on_done)
        self._anim.start()


# ═══════════════════════════════════════════════════════════════════════════════
#  GOG-STYLE GAME CARD
# ═══════════════════════════════════════════════════════════════════════════════
CARD_W = 210
CARD_H = 480


class GogGameCard(QFrame):
    def __init__(self, game, on_launch=None):
        super().__init__()
        self._game = game
        self._on_launch = on_launch
        self._running_pid = None
        self._destroyed = False
        self._is_running = False

        genre = game.get("genre", "")
        self._g_accent, gbg = GENRE_COLORS.get(genre, (TH.accent, TH.bg_card_h))

        self.setObjectName("GogCard")
        self._update_style(hovered=False)
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20); shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        cover_h = int(CARD_H * 0.68)
        self._cover_container = QFrame()
        self._cover_container.setFixedSize(CARD_W, cover_h)
        self._cover_container.setObjectName("CoverContainer")
        self._cover_container.setStyleSheet(
            f"QFrame#CoverContainer {{ background: {gbg}; border-radius: 10px 10px 0 0; border: none; }}"
        )

        self._emoji_lbl = QLabel(GENRE_ICON.get(genre, "🎮"), self._cover_container)
        self._emoji_lbl.setAlignment(Qt.AlignCenter)
        self._emoji_lbl.setGeometry(0, 0, CARD_W, cover_h)
        self._emoji_lbl.setStyleSheet("background: transparent; font-size: 42px; border: none;")

        self._art_lbl = QLabel(self._cover_container)
        self._art_lbl.setGeometry(0, 0, CARD_W, cover_h)
        self._art_lbl.setAlignment(Qt.AlignCenter)
        self._art_lbl.setStyleSheet("background: transparent; border: none;")
        self._art_lbl.hide()

        self._outer.addWidget(self._cover_container)

        info_h = CARD_H - cover_h
        info = QWidget()
        info.setStyleSheet("background: transparent; border: none;")
        info.setFixedSize(CARD_W, info_h)
        iv = QVBoxLayout(info); iv.setContentsMargins(8, 6, 8, 6); iv.setSpacing(2)

        name_lbl = QLabel(game["name"])
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(f"font-size: 10px; font-weight: 700; color: {TH.text_pri}; font-family: {TH.font_fam}; background: transparent; border: none;")
        iv.addWidget(name_lbl)

        badge_row = QHBoxLayout(); badge_row.setSpacing(3)
        if genre:
            badge = QLabel(f" {genre.upper()} ")
            badge.setStyleSheet(
                f"background: {gbg}; color: {self._g_accent}; border-radius: 3px; padding: 1px 3px; "
                f"font-size: 7px; font-weight: 700; letter-spacing: 1px; font-family: {TH.font_fam}; border: 1px solid {self._g_accent}40;")
            badge_row.addWidget(badge, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        source = game.get("source", "")
        if source in ("steam", "epic"):
            sc = SOURCE_COLORS.get(source, TH.text_sec)
            sb = QLabel("S" if source == "steam" else "E")
            sb.setFixedSize(14, 14); sb.setAlignment(Qt.AlignCenter)
            sb.setStyleSheet(f"background: {sc}30; color: {sc}; border-radius: 2px; font-size: 7px; font-weight: 700; font-family: {TH.font_fam}; border: none;")
            badge_row.addWidget(sb, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        count = user_data["play_counts"].get(game["name"], 0)
        if count > 0:
            cl = QLabel(f"▶{count}")
            cl.setStyleSheet(f"color: {TH.neon_y}; font-size: 8px; font-weight: 700; font-family: {TH.font_fam}; background: transparent; border: none;")
            badge_row.addWidget(cl, alignment=Qt.AlignLeft | Qt.AlignVCenter)
        badge_row.addStretch()
        iv.addLayout(badge_row)

        self._launch_hint = QLabel("▶  CLICK TO LAUNCH")
        self._launch_hint.setAlignment(Qt.AlignCenter)
        self._launch_hint.setStyleSheet(
            f"font-size: 8px; font-weight: 700; color: {self._g_accent}; "
            f"font-family: {TH.font_fam}; background: transparent; border: none; letter-spacing: 1px;")
        self._launch_hint.hide()
        iv.addWidget(self._launch_hint)
        iv.addStretch()
        self._outer.addWidget(info)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(4000)
        self._poll_timer.timeout.connect(self._check_running)
        self._poll_timer.start()

        self._run_dot = QLabel("● RUNNING", self)
        self._run_dot.setGeometry(6, 6, 90, 18)
        self._run_dot.setAlignment(Qt.AlignCenter)
        self._run_dot.setStyleSheet(
            f"background: {TH.accent}dd; color: #050508; border-radius: 9px; "
            f"font-size: 7px; font-weight: 700; font-family: {TH.font_fam}; border: none;")
        self._run_dot.hide()

        self._stop_hint = QLabel("⏹  CLICK TO STOP", self)
        self._stop_hint.setGeometry(6, 6, 120, 18)
        self._stop_hint.setAlignment(Qt.AlignCenter)
        self._stop_hint.setStyleSheet(
            f"background: #ff386080; color: #fff; border-radius: 9px; "
            f"font-size: 7px; font-weight: 700; font-family: {TH.font_fam}; border: none;")
        self._stop_hint.hide()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(800)
        self._pulse_timer.timeout.connect(self._pulse_run_dot)
        self._pulse_phase = 0

        self._loading_lbl = QLabel("⟳", self._cover_container)
        self._loading_lbl.setAlignment(Qt.AlignCenter)
        self._loading_lbl.setGeometry(CARD_W - 22, 6, 16, 16)
        self._loading_lbl.setStyleSheet(f"color: {TH.accent}80; font-size: 10px; background: transparent; border: none;")

        thumb = game.get("thumbnail", "")
        if thumb and os.path.exists(thumb) and os.path.getsize(thumb) > 1024:
            QTimer.singleShot(0, lambda p=thumb: self._on_assets("", p))
        else:
            fetch_game_assets_async(game, self._on_assets)

    def _update_style(self, hovered=False, running=False):
        border_color = "#ff3860" if running else (f"{self._g_accent}cc" if hovered else "rgba(255,255,255,12)")
        bg = "rgba(24,24,40,250)" if hovered else "rgba(10,10,20,200)"
        self.setStyleSheet(f"""QFrame#GogCard {{
    background: {bg}; border: 1px solid {border_color}; border-radius: 10px;
}}""")

    def _pulse_run_dot(self):
        self._pulse_phase = (self._pulse_phase + 1) % 2
        if not self._is_running or self._destroyed:
            return
        try:
            if self._pulse_phase == 0:
                self._run_dot.setStyleSheet(
                    f"background: {TH.accent}ff; color: #050508; border-radius: 9px; "
                    f"font-size: 7px; font-weight: 700; font-family: {TH.font_fam}; border: none;")
            else:
                self._run_dot.setStyleSheet(
                    f"background: {TH.accent}88; color: #050508; border-radius: 9px; "
                    f"font-size: 7px; font-weight: 700; font-family: {TH.font_fam}; border: none;")
        except RuntimeError:
            pass

    def _set_running_state(self, running):
        self._is_running = running
        try:
            if running:
                self._run_dot.show()
                self._pulse_timer.start()
                self._update_style(running=True)
            else:
                self._run_dot.hide()
                self._stop_hint.hide()
                self._pulse_timer.stop()
                self._update_style(running=False)
        except RuntimeError:
            pass

    def _on_game_killed(self):
        self._running_pid = None
        self._set_running_state(False)
        _resume_launcher_processes()

    def enterEvent(self, event):
        if not self._destroyed:
            self._update_style(hovered=True, running=self._is_running)
            if self._is_running:
                self._stop_hint.show()
                self._run_dot.hide()
            else:
                self._launch_hint.show()

    def leaveEvent(self, event):
        if not self._destroyed:
            self._update_style(hovered=False, running=self._is_running)
            self._launch_hint.hide()
            if self._is_running:
                self._stop_hint.hide()
                self._run_dot.show()

    def _on_assets(self, desc, thumb_path):
        if self._destroyed:
            return
        try:
            self._loading_lbl.hide()
        except RuntimeError:
            return
        try:
            if not thumb_path or not os.path.exists(thumb_path):
                return
            raw = QPixmap(thumb_path)
            if raw.isNull():
                return
            cover_h = int(CARD_H * 0.68)
            w, h = CARD_W, cover_h
            scaled = raw.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x_off = max(0, (scaled.width() - w) // 2)
            y_off = max(0, (scaled.height() - h) // 2)
            cropped = scaled.copy(QRect(x_off, y_off, w, h))
            result = QPixmap(w, h)
            result.fill(Qt.transparent)
            p = QPainter(result)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(0, 0, w, h + 12), 10, 10)
            p.setClipPath(clip)
            p.drawPixmap(0, 0, cropped)
            p.end()
            self._art_lbl.setPixmap(result)
            self._art_lbl.raise_()
            self._art_lbl.show()
            self._emoji_lbl.hide()
            self._cover_container.setStyleSheet(
                "QFrame#CoverContainer { background: #080810; border-radius: 10px 10px 0 0; border: none; }"
            )
        except Exception as e:
            print(f"[GameVault] cover render error for {self._game.get('name','?')}: {e}")

    def _check_running(self):
        if self._destroyed:
            return
        pid = _find_running_game_pid(self._game)
        was_running = self._running_pid is not None
        self._running_pid = pid
        is_now_running = pid is not None
        if is_now_running != was_running:
            self._set_running_state(is_now_running)
            with _running_lock:
                if is_now_running:
                    _currently_running_game["pid"]  = pid
                    _currently_running_game["name"] = self._game["name"]
                    _currently_running_game["card"] = self
                elif _currently_running_game.get("name") == self._game["name"]:
                    _currently_running_game["pid"]  = None
                    _currently_running_game["name"] = None
                    _currently_running_game["card"] = None
                    _resume_launcher_processes()
        try:
            self._run_dot.setVisible(is_now_running)
        except RuntimeError:
            pass

    def closeEvent(self, event):
        self._destroyed = True
        if self._poll_timer:
            self._poll_timer.stop()
        if self._pulse_timer:
            self._pulse_timer.stop()
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                eff = self.graphicsEffect()
                if isinstance(eff, QGraphicsDropShadowEffect):
                    eff.setBlurRadius(8); eff.setOffset(0, 2)
            except Exception:
                pass
            self._handle_click()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            try:
                eff = self.graphicsEffect()
                if isinstance(eff, QGraphicsDropShadowEffect):
                    eff.setBlurRadius(20); eff.setOffset(0, 4)
            except Exception:
                pass

    def _handle_click(self):
        if self._is_running and self._running_pid:
            pid = self._running_pid
            self._running_pid = None
            self._set_running_state(False)
            with _running_lock:
                if _currently_running_game.get("name") == self._game["name"]:
                    _currently_running_game["pid"]  = None
                    _currently_running_game["name"] = None
                    _currently_running_game["card"] = None
            threading.Thread(target=lambda: (kill_game(pid), _resume_launcher_processes()), daemon=True).start()
        else:
            self._launch()

    def _launch(self):
        path = self._game.get("path", "")
        name = self._game.get("name", "")
        source = self._game.get("source", "")

        if not path:
            return

        # Record the play count
        user_data["play_counts"][name] = user_data["play_counts"].get(name, 0) + 1
        save_user(user_data)

        def _do_launch():
            try:
                # ── FIX #2: Correct launch logic for all game types ───────────
                if path.startswith("steam://") or path.startswith("com.epicgames.launcher://"):
                    # Steam & Epic protocol URLs — use ShellExecute on Windows,
                    # webbrowser module on all platforms (most reliable)
                    import sys
                    if sys.platform == "win32":
                        os.startfile(path)
                    else:
                        webbrowser.open(path)

                elif os.path.isfile(path):
                    # Direct executable — launch without shell=True so the
                    # path is passed correctly even if it contains spaces
                    subprocess.Popen(
                        [path],
                        cwd=os.path.dirname(path),
                        creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
                    )

                else:
                    # Fallback: let the OS handle whatever string we have
                    import sys
                    if sys.platform == "win32":
                        os.startfile(path)
                    else:
                        subprocess.Popen(path, shell=True)

            except Exception as e:
                print(f"[GameVault] Launch error for '{name}': {e}")

        threading.Thread(target=_do_launch, daemon=True).start()

    def mouseDoubleClickEvent(self, event):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  ANIMATED CARD WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════
class AnimatedCard(QWidget):
    def __init__(self, card, delay_ms=0, parent=None):
        super().__init__(parent)
        self._card = card
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(card)
        self.setFixedSize(card.size())
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)
        QTimer.singleShot(delay_ms, self._animate_in)

    def _animate_in(self):
        if self._card._destroyed:
            return
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(320)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QAbstractAnimation.DeleteWhenStopped)

    def animate_out(self, on_done=None):
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(self._opacity_effect.opacity())
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        if on_done:
            anim.finished.connect(on_done)
        anim.start(QAbstractAnimation.DeleteWhenStopped)


# ═══════════════════════════════════════════════════════════════════════════════
#  RESPONSIVE FLOW GRID
# ═══════════════════════════════════════════════════════════════════════════════
class FlowGridWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._cards     = []
        self._raw_cards = []
        self._layout    = QGridLayout(self)
        self._layout.setSpacing(14)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._last_cols = -1

    def set_cards(self, game_list, on_launch=None, animate=True):
        while self._layout.count():
            self._layout.takeAt(0)
        for wrapper in self._cards:
            try:
                wrapper.deleteLater()
            except Exception:
                pass
        self._cards     = []
        self._raw_cards = []
        for i, game in enumerate(game_list):
            card    = GogGameCard(game, on_launch)
            delay   = min(i * 35, 600) if animate else 0
            wrapper = AnimatedCard(card, delay_ms=delay)
            self._cards.append(wrapper)
            self._raw_cards.append(card)
        self._reflow(force=True)

    def filter_cards(self, game_list, on_launch=None):
        self._fade_rebuild(game_list, on_launch)

    def _fade_rebuild(self, game_list, on_launch=None):
        if not self._cards:
            self.set_cards(game_list, on_launch, animate=True)
            return
        remaining = [len(self._cards)]

        def _check_done():
            remaining[0] -= 1
            if remaining[0] <= 0:
                while self._layout.count():
                    self._layout.takeAt(0)
                for wrapper in self._cards:
                    try:
                        wrapper.deleteLater()
                    except Exception:
                        pass
                self._cards     = []
                self._raw_cards = []
                self._last_cols = -1
                for i, game in enumerate(game_list):
                    card    = GogGameCard(game, on_launch)
                    delay   = min(i * 28, 400)
                    wrapper = AnimatedCard(card, delay_ms=delay)
                    self._cards.append(wrapper)
                    self._raw_cards.append(card)
                self._reflow(force=True)

        if not self._cards:
            _check_done()
            return
        for wrapper in self._cards:
            wrapper.animate_out(_check_done)

    def _cols_for_width(self, w):
        available = w - 40
        return max(1, available // (CARD_W + 14))

    def _reflow(self, force=False):
        w    = self.width() if self.width() > 0 else 900
        cols = self._cols_for_width(w)
        if not force and cols == self._last_cols and self._layout.count() == len(self._cards):
            return
        self._last_cols = cols
        while self._layout.count():
            self._layout.takeAt(0)
        if not self._cards:
            empty = QLabel("No games found")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"font-size:14px; color:{TH.text_dim}; font-family:{TH.font_fam}; padding:40px;")
            self._layout.addWidget(empty, 0, 0)
            return
        for i, wrapper in enumerate(self._cards):
            r, c = divmod(i, cols)
            self._layout.addWidget(wrapper, r, c)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_cols = self._cols_for_width(event.size().width())
        if new_cols != self._last_cols:
            self._reflow()


# ═══════════════════════════════════════════════════════════════════════════════
#  LIBRARY PAGE
# ═══════════════════════════════════════════════════════════════════════════════
class LibraryPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._tab           = "all"
        self._filter_source = "all"
        self._search_text   = ""
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(180)
        self._search_debounce.timeout.connect(self._do_search_filter)
        self._initial_load = True
        self._build()

    def _build(self):
        old = self.layout()
        if old:
            clear_layout(old); temp = QWidget(); temp.setLayout(old)

        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        topbar = QWidget()
        topbar.setStyleSheet("background: rgba(8,8,16,160); border-bottom: 1px solid rgba(255,255,255,8);")
        topbar.setFixedHeight(52)
        tb = QHBoxLayout(topbar); tb.setContentsMargins(18, 0, 18, 0); tb.setSpacing(0)

        self._tab_btns = {}
        for key, label in [("all", "ALL GAMES"), ("recent", "RECENTLY PLAYED"), ("favorites", "FAVORITES")]:
            btn = QPushButton(label)
            btn.setFixedHeight(52); btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(tab_active_style() if key == self._tab else tab_inactive_style())
            btn.clicked.connect(lambda _, k=key: self._set_tab(k))
            self._tab_btns[key] = btn
            tb.addWidget(btn)

        tb.addSpacing(16)
        for src, label, color in [("all", "All", TH.accent), ("steam", "Steam", "#1a9fff"), ("epic", "Epic", "#a855f7")]:
            has = any(g.get("source") == src for g in games) or src == "all"
            if not has:
                continue
            chip = QPushButton(label)
            chip.setCheckable(True); chip.setChecked(src == self._filter_source)
            chip.setCursor(Qt.PointingHandCursor)
            c = color
            chip.setStyleSheet(
                f"QPushButton{{ background: {c}25; color: {c}; border: 1px solid {c}60; "
                f"border-radius: 12px; padding: 3px 12px; font-size: 9px; font-weight: 700; font-family: {TH.font_fam}; }}"
                f"QPushButton:checked{{ background: {c}; color: #050508; }}"
                f"QPushButton:hover{{ background: {c}40; }}"
            )
            chip.clicked.connect(lambda _, s=src: self._set_source(s))
            tb.addWidget(chip); tb.addSpacing(4)

        tb.addStretch()
        total = len(games)
        plays = sum(user_data["play_counts"].values())
        for txt, val, color in [("GAMES", str(total), TH.accent), ("PLAYS", str(plays), TH.neon_b)]:
            vw = QWidget(); vh = QHBoxLayout(vw); vh.setContentsMargins(0, 0, 0, 0); vh.setSpacing(4)
            vl = QLabel(txt); vl.setStyleSheet(f"font-size:8px; color:{TH.text_dim}; letter-spacing:1.5px; font-family:{TH.font_fam}; background:transparent;")
            vv = QLabel(val); vv.setStyleSheet(f"font-size:15px; font-weight:700; color:{color}; font-family:{TH.font_fam}; background:transparent;")
            vh.addWidget(vv); vh.addWidget(vl)
            tb.addWidget(vw); tb.addSpacing(12)
        root.addWidget(topbar)

        search_bar = QWidget()
        search_bar.setStyleSheet("background: rgba(6,6,12,140); border-bottom: 1px solid rgba(255,255,255,5);")
        search_bar.setFixedHeight(44)
        sb_layout = QHBoxLayout(search_bar); sb_layout.setContentsMargins(18, 6, 18, 6); sb_layout.setSpacing(10)

        self._search_icon = QLabel("🔍")
        self._search_icon.setStyleSheet("background: transparent; font-size: 13px;")
        sb_layout.addWidget(self._search_icon)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search games...")
        self._search_input.setText(self._search_text)
        self._search_input.setFixedHeight(30)
        self._search_input.setStyleSheet(f"""
QLineEdit {{ background: rgba(255,255,255,5); color: {TH.text_pri}; border: 1px solid rgba(255,255,255,10);
    border-radius: 6px; padding: 4px 10px; font-family: {TH.font_fam}; font-size: 12px; }}
QLineEdit:focus {{ border: 1px solid {TH.accent}80; background: rgba(255,255,255,8); }}""")
        self._search_input.textChanged.connect(self._on_search)
        sb_layout.addWidget(self._search_input, stretch=1)

        self._clear_btn = QPushButton("✕")
        self._clear_btn.setFixedSize(24, 24)
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setStyleSheet(f"QPushButton{{background:transparent; color:{TH.text_sec}; border:none; font-size:10px;}} QPushButton:hover{{color:{TH.text_pri};}}")
        self._clear_btn.clicked.connect(self._clear_search)
        self._clear_btn.setVisible(bool(self._search_text))
        sb_layout.addWidget(self._clear_btn)

        self._result_lbl = QLabel("")
        self._result_lbl.setStyleSheet(f"font-size:9px; color:{TH.text_sec}; font-family:{TH.font_fam}; background:transparent;")
        self._result_lbl.setMinimumWidth(80)
        sb_layout.addWidget(self._result_lbl)

        self._searching_lbl = QLabel("filtering...")
        self._searching_lbl.setStyleSheet(f"font-size:9px; color:{TH.accent}80; font-family:{TH.font_fam}; background:transparent;")
        self._searching_lbl.hide()
        sb_layout.addWidget(self._searching_lbl)

        root.addWidget(search_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._flow_grid = FlowGridWidget()
        scroll.setWidget(self._flow_grid)
        root.addWidget(scroll)

        game_list = self._get_game_list()
        self._flow_grid.set_cards(game_list, animate=self._initial_load)
        self._initial_load = False
        self._result_lbl.setText(f"{len(game_list)} games")

    def _get_game_list(self):
        if self._tab == "recent":
            played = [(n, c) for n, c in user_data["play_counts"].items() if c > 0]
            played.sort(key=lambda x: -x[1])
            names = [n for n, _ in played[:24]]
            game_list = [g for g in games if g["name"] in names]
        elif self._tab == "favorites":
            favs = user_data.get("favorites", [])
            game_list = [g for g in games if g["name"] in favs]
            if not game_list:
                played = sorted(user_data["play_counts"].items(), key=lambda x: -x[1])[:12]
                names = {n for n, _ in played}
                game_list = [g for g in games if g["name"] in names]
        else:
            game_list = games[:]
        if self._filter_source != "all":
            game_list = [g for g in game_list if g.get("source") == self._filter_source]
        if self._search_text:
            q = self._search_text.lower()
            game_list = [g for g in game_list if q in g["name"].lower() or q in g.get("genre", "").lower() or q in g.get("description", "").lower()]
        return game_list

    def _populate(self, animated=False):
        game_list = self._get_game_list()
        if animated:
            self._flow_grid.filter_cards(game_list)
        else:
            self._flow_grid.set_cards(game_list, animate=True)
        count = len(game_list)
        self._result_lbl.setText(f"{count} result{'s' if count != 1 else ''}" if self._search_text else f"{count} games")

    def _on_search(self, text):
        self._search_text = text
        self._clear_btn.setVisible(bool(text))
        self._searching_lbl.show()
        self._search_icon.setText("⟳")
        self._search_debounce.stop()
        self._search_debounce.start()

    def _do_search_filter(self):
        self._searching_lbl.hide()
        self._search_icon.setText("🔍")
        self._populate(animated=True)

    def _clear_search(self):
        self._search_input.clear()
        self._search_text = ""
        self._clear_btn.setVisible(False)
        self._searching_lbl.hide()
        self._search_icon.setText("🔍")
        self._search_debounce.stop()
        self._populate(animated=True)

    def _set_tab(self, key):
        self._tab = key
        for k, btn in self._tab_btns.items():
            btn.setStyleSheet(tab_active_style() if k == key else tab_inactive_style())
        self._populate(animated=True)

    def _set_source(self, src):
        self._filter_source = src
        self._build()

    def refresh(self):
        self._build()


# ═══════════════════════════════════════════════════════════════════════════════
#  FRIENDS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
FAKE_REPLIES = [
    "gg no re lmao", "bro get good 💀", "i'll be on in 5", "what server?",
    "nah i'm hardstuck rn", "let's run a duo", "my ping is trash",
    "one more round?", "yo wtf was that play", "hold on eating",
]


class FriendsPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._sel = None
        self._build()

    def _build(self):
        old = self.layout()
        if old:
            clear_layout(old); temp = QWidget(); temp.setLayout(old)

        root = QHBoxLayout(self); root.setContentsMargins(20, 20, 20, 20); root.setSpacing(16)
        left = QFrame(); left.setFixedWidth(260)
        left.setStyleSheet("QFrame{background:rgba(8,8,20,200); border:1px solid rgba(255,255,255,12); border-radius:12px;}")
        lv = QVBoxLayout(left); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet("background:transparent; border-bottom:1px solid rgba(255,255,255,8);")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(14, 0, 14, 0)
        title = QLabel("FRIENDS"); title.setStyleSheet(f"font-size:12px; font-weight:700; color:{TH.accent}; letter-spacing:3px; font-family:{TH.font_fam};")
        add_btn = QPushButton("+ ADD"); add_btn.setStyleSheet(ghost_btn(TH.accent)); add_btn.setCursor(Qt.PointingHandCursor); add_btn.setFixedHeight(24)
        hh.addWidget(title); hh.addStretch(); hh.addWidget(add_btn)
        lv.addWidget(hdr)
        friends = user_data.get("friends", [])
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        lw = QWidget(); lw.setStyleSheet("background:transparent;")
        lv2 = QVBoxLayout(lw); lv2.setContentsMargins(8, 8, 8, 8); lv2.setSpacing(3)
        online  = [f for f in friends if f.get("status") == "Online"]
        away    = [f for f in friends if f.get("status") == "Away"]
        offline = [f for f in friends if f.get("status") == "Offline"]
        for sec_name, sec_friends, col in [(f"ONLINE — {len(online)}", online, "#00ff9d"), (f"AWAY — {len(away)}", away, "#ffd000"), (f"OFFLINE — {len(offline)}", offline, "#44445a")]:
            if sec_friends:
                hdr2 = QLabel(f"// {sec_name}")
                hdr2.setStyleSheet(f"font-size:8px; font-weight:700; color:{col}; letter-spacing:1.5px; font-family:{TH.font_fam}; padding:4px 2px 2px 2px;")
                lv2.addWidget(hdr2)
                for f in sec_friends:
                    sel = self._sel and self._sel["name"] == f["name"]
                    row = self._friend_row(f, sel)
                    lv2.addWidget(row)
        lv2.addStretch()
        scroll.setWidget(lw); lv.addWidget(scroll)
        root.addWidget(left)
        right = QFrame()
        right.setStyleSheet("QFrame{background:rgba(8,8,20,200); border:1px solid rgba(255,255,255,12); border-radius:12px;}")
        self._rv = QVBoxLayout(right); self._rv.setContentsMargins(0, 0, 0, 0); self._rv.setSpacing(0)
        if self._sel:
            self._build_chat(self._sel, right)
        else:
            empty = QLabel("Select a friend to chat"); empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"font-size:13px; color:{TH.text_dim}; font-family:{TH.font_fam};")
            self._rv.addWidget(empty)
        root.addWidget(right, stretch=1)

    def _friend_row(self, friend, selected):
        sc  = STATUS_COLOR.get(friend.get("status", "Offline"), TH.muted)
        bg  = "rgba(255,255,255,8)" if selected else "transparent"
        row = QFrame()
        row.setStyleSheet(f"QFrame{{background:{bg};border-radius:8px;}} QFrame:hover{{background:rgba(255,255,255,6);}}")
        row.setCursor(Qt.PointingHandCursor)
        h = QHBoxLayout(row); h.setContentsMargins(8, 6, 8, 6); h.setSpacing(8)
        av = QLabel(friend.get("avatar", "👤")); av.setFixedSize(32, 32); av.setAlignment(Qt.AlignCenter)
        av.setStyleSheet("font-size:14px; background:rgba(255,255,255,6); border-radius:5px; border:1px solid rgba(255,255,255,12);")
        h.addWidget(av)
        nv = QVBoxLayout(); nv.setSpacing(1)
        n = QLabel(friend["name"]); n.setStyleSheet(f"font-size:11px; font-weight:700; color:{TH.text_pri}; font-family:{TH.font_fam}; background:transparent;")
        game = friend.get("game", "")
        if game and friend.get("status") == "Online":
            s = QLabel(f"▶ {game}"); s.setStyleSheet(f"font-size:8px; color:{TH.accent}; font-family:{TH.font_fam}; background:transparent;")
        else:
            s = QLabel(f"● {friend.get('status', '')}"); s.setStyleSheet(f"font-size:8px; color:{sc}; font-family:{TH.font_fam}; background:transparent;")
        nv.addWidget(n); nv.addWidget(s); h.addLayout(nv)
        row.mousePressEvent = lambda e, f=friend: self._select(f) if e.button() == Qt.LeftButton else None
        return row

    def _select(self, friend):
        self._sel = friend; self._build()

    def _build_chat(self, friend, container):
        sc = STATUS_COLOR.get(friend.get("status", "Offline"), TH.muted)
        ch_hdr = QWidget(); ch_hdr.setFixedHeight(52)
        ch_hdr.setStyleSheet("background:transparent; border-bottom:1px solid rgba(255,255,255,8);")
        chh = QHBoxLayout(ch_hdr); chh.setContentsMargins(16, 0, 16, 0); chh.setSpacing(10)
        av = QLabel(friend.get("avatar", "👤"))
        av.setStyleSheet("font-size:18px; background:rgba(255,255,255,8); border:1px solid rgba(255,255,255,12); border-radius:5px; padding:2px 4px;")
        nl = QLabel(friend["name"]); nl.setStyleSheet(f"font-size:13px; font-weight:700; color:{TH.text_pri}; font-family:{TH.font_fam};")
        sl = QLabel(f"● {friend.get('status', '')}"); sl.setStyleSheet(f"font-size:9px; color:{sc}; font-family:{TH.font_fam};")
        nv = QVBoxLayout(); nv.setSpacing(1); nv.addWidget(nl); nv.addWidget(sl)
        chh.addWidget(av); chh.addLayout(nv); chh.addStretch()
        self._rv.addWidget(ch_hdr)
        self._msg_scroll = QScrollArea(); self._msg_scroll.setWidgetResizable(True)
        self._msg_scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._msg_w = QWidget(); self._msg_w.setStyleSheet("background:transparent;")
        self._msg_l = QVBoxLayout(self._msg_w); self._msg_l.setContentsMargins(12, 12, 12, 12); self._msg_l.setSpacing(4)
        self._msg_l.addStretch()
        for m in user_data.get("messages", {}).get(friend["name"], []):
            self._add_bubble(m["text"], m["sender"] == "me", m.get("time", ""))
        self._msg_scroll.setWidget(self._msg_w)
        self._rv.addWidget(self._msg_scroll, stretch=1)
        ib = QWidget(); ib.setFixedHeight(52)
        ib.setStyleSheet("background:transparent; border-top:1px solid rgba(255,255,255,8);")
        ibl = QHBoxLayout(ib); ibl.setContentsMargins(12, 10, 12, 10); ibl.setSpacing(8)
        self._inp = QLineEdit(); self._inp.setPlaceholderText(f"Message {friend['name']}...")
        self._inp.returnPressed.connect(lambda: self._send(friend))
        send = QPushButton("SEND"); send.setStyleSheet(action_btn(TH.accent)); send.setFixedWidth(66); send.setCursor(Qt.PointingHandCursor)
        send.clicked.connect(lambda: self._send(friend))
        ibl.addWidget(self._inp); ibl.addWidget(send)
        self._rv.addWidget(ib)
        self._scroll_bottom()

    def _add_bubble(self, text, is_me, time_str=""):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        h = QHBoxLayout(w); h.setContentsMargins(4, 2, 4, 2)
        bubble = QFrame()
        if is_me:
            bubble.setStyleSheet(f"QFrame{{background:{TH.accent}25; border:1px solid {TH.accent}40; border-radius:10px;}}")
        else:
            bubble.setStyleSheet("QFrame{background:rgba(255,255,255,8); border:1px solid rgba(255,255,255,12); border-radius:10px;}")
        bv = QVBoxLayout(bubble); bv.setContentsMargins(10, 6, 10, 6); bv.setSpacing(2)
        ml = QLabel(text); ml.setWordWrap(True); ml.setMaximumWidth(280)
        ml.setStyleSheet(f"font-size:12px; color:{TH.text_pri}; font-family:{TH.font_fam}; background:transparent; border:none;")
        tl = QLabel(time_str); tl.setStyleSheet(f"font-size:8px; color:{TH.text_sec}; font-family:{TH.font_fam}; background:transparent; border:none;")
        bv.addWidget(ml); bv.addWidget(tl)
        if is_me:
            h.addStretch(); h.addWidget(bubble)
        else:
            h.addWidget(bubble); h.addStretch()
        self._msg_l.addWidget(w)

    def _send(self, friend):
        text = self._inp.text().strip()
        if not text:
            return
        now = datetime.now().strftime("%H:%M")
        user_data.setdefault("messages", {}).setdefault(friend["name"], []).append({"sender": "me", "text": text, "time": now, "read": True})
        save_user(user_data)
        self._add_bubble(text, True, now); self._inp.clear(); self._scroll_bottom()
        if friend.get("status") in ("Online", "Away"):
            QTimer.singleShot(random.randint(1500, 4000), lambda: self._fake_reply(friend))

    def _fake_reply(self, friend):
        reply = random.choice(FAKE_REPLIES)
        now = datetime.now().strftime("%H:%M")
        user_data.setdefault("messages", {}).setdefault(friend["name"], []).append({"sender": friend["name"], "text": reply, "time": now, "read": True})
        save_user(user_data)
        self._add_bubble(reply, False, now); self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(50, lambda: self._msg_scroll.verticalScrollBar().setValue(self._msg_scroll.verticalScrollBar().maximum()))

    def refresh(self):
        self._build()


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS PAGE
# ═══════════════════════════════════════════════════════════════════════════════
class SettingsPage(QWidget):
    theme_changed = Signal()

    def __init__(self, bg_widget):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._bg      = bg_widget
        self._pending = user_data.get("theme", {}).copy()
        self._build()

    def _build(self):
        old = self.layout()
        if old:
            clear_layout(old); temp = QWidget(); temp.setLayout(old)

        root = QVBoxLayout(self); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(14)
        title = QLabel("SETTINGS"); title.setStyleSheet(f"font-size:22px; font-weight:700; color:{TH.accent}; letter-spacing:4px; font-family:{TH.font_fam};")
        root.addWidget(title)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        content = QWidget(); content.setStyleSheet("background:transparent;")
        cv = QVBoxLayout(content); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(20)

        cv.addWidget(self._section_label("DISCORD ACCOUNT"))
        discord_frame = QFrame()
        discord_frame.setStyleSheet("QFrame{background:rgba(88,101,242,15); border:1px solid rgba(88,101,242,40); border-radius:10px;}")
        df = QHBoxLayout(discord_frame); df.setContentsMargins(14, 12, 14, 12); df.setSpacing(12)
        discord_id = user_data.get("discord_id", "")
        if discord_id:
            av_cache = _cache_path("discord_avatar", ".jpg")
            if os.path.exists(av_cache):
                av_lbl = QLabel()
                av_lbl.setFixedSize(40, 40)
                px = QPixmap(av_cache).scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                av_lbl.setPixmap(px)
                av_lbl.setStyleSheet("border-radius: 20px; border: 2px solid #5865F2;")
                df.addWidget(av_lbl)
            dname = QLabel(f"{user_data.get('discord_username', 'Unknown')}")
            dname.setStyleSheet(f"font-size:13px; font-weight:700; color:{TH.text_pri}; font-family:{TH.font_fam};")
            dtag = QLabel(f"Discord ID: {discord_id}")
            dtag.setStyleSheet(f"font-size:9px; color:{TH.text_sec}; font-family:{TH.font_fam};")
            dv = QVBoxLayout(); dv.setSpacing(2); dv.addWidget(dname); dv.addWidget(dtag)
            df.addLayout(dv); df.addStretch()
            logout_btn = QPushButton("DISCONNECT")
            logout_btn.setStyleSheet(ghost_btn("#ff3860")); logout_btn.setCursor(Qt.PointingHandCursor)
            logout_btn.clicked.connect(self._discord_logout)
            df.addWidget(logout_btn)
        else:
            disc_lbl = QLabel("Not connected to Discord")
            disc_lbl.setStyleSheet(f"font-size:11px; color:{TH.text_sec}; font-family:{TH.font_fam};")
            df.addWidget(disc_lbl); df.addStretch()
            login_btn = QPushButton("  CONNECT DISCORD")
            login_btn.setStyleSheet(f"""QPushButton{{
    background: #5865F2; color: white; border: none; border-radius: 5px;
    padding: 6px 14px; font-family: {TH.font_fam}; font-size: 10px; font-weight: 700;
}}
QPushButton:hover{{ background: #4752C4; }}""")
            login_btn.setCursor(Qt.PointingHandCursor)
            login_btn.clicked.connect(self._open_discord_login)
            df.addWidget(login_btn)
        cv.addWidget(discord_frame)

        cv.addWidget(self._section_label("LIVE BACKGROUND"))
        bg_panel = BgSettingsPanel(self._bg)
        cv.addWidget(bg_panel)

        cv.addWidget(self._section_label("ACCENT COLOR"))
        ar = QHBoxLayout(); ar.setSpacing(10)
        cur_accent = self._pending.get("accent", "#00ff9d")
        for color, lbl in [("#00ff9d","Green"), ("#00c8ff","Blue"), ("#ff3860","Red"), ("#bf5fff","Purple"), ("#ffd000","Gold"), ("#ff8c00","Orange"), ("#00ffc8","Aqua"), ("#ff00aa","Pink"), ("#888899","Ghost")]:
            w = QWidget(); w.setCursor(Qt.PointingHandCursor)
            wv = QVBoxLayout(w); wv.setContentsMargins(0, 0, 0, 0); wv.setSpacing(3)
            box = QFrame(); box.setFixedSize(40, 40)
            sel = color.lower() == cur_accent.lower()
            border = "3px solid #fff" if sel else "2px solid rgba(255,255,255,15)"
            box.setStyleSheet(f"QFrame{{background:{color}; border-radius:8px; border:{border};}}")
            bl2 = QLabel(lbl); bl2.setAlignment(Qt.AlignCenter)
            bl2.setStyleSheet(f"font-size:7px; color:{TH.text_sec}; font-family:{TH.font_fam};")
            wv.addWidget(box, alignment=Qt.AlignCenter); wv.addWidget(bl2)
            w.mousePressEvent = lambda e, c=color: self._set_accent(c)
            ar.addWidget(w)
        ar.addStretch(); cv.addLayout(ar)

        cv.addWidget(self._section_label("THEME PRESET"))
        pr = QHBoxLayout(); pr.setSpacing(10)
        cur_preset = self._pending.get("preset", "")
        for pname, pvals in THEME_PRESETS.items():
            bg2 = BG_STYLES.get(pvals["bg_style"], BG_STYLES["pure_black"])["card"]
            sel = pname == cur_preset
            btn = QFrame(); btn.setFixedSize(120, 72); btn.setCursor(Qt.PointingHandCursor)
            border = f"2px solid {pvals['accent']}" if sel else "1px solid rgba(255,255,255,12)"
            btn.setStyleSheet(f"QFrame{{background:{bg2}; border:{border}; border-radius:10px;}}")
            bv = QVBoxLayout(btn); bv.setContentsMargins(10, 10, 10, 10); bv.setSpacing(3)
            dot = QLabel("◉"); dot.setStyleSheet(f"color:{pvals['accent']}; font-size:10px;")
            nl = QLabel(pname); nl.setStyleSheet(f"font-size:9px; font-weight:700; color:{pvals['accent']}; font-family:{TH.font_fam};")
            bv.addWidget(dot, alignment=Qt.AlignRight); bv.addStretch(); bv.addWidget(nl)
            btn.mousePressEvent = lambda e, p=pname, v=pvals: self._apply_preset(p, v)
            pr.addWidget(btn)
        pr.addStretch(); cv.addLayout(pr)

        cv.addSpacing(8)
        apply_btn = QPushButton("◈  APPLY THEME"); apply_btn.setStyleSheet(action_btn(TH.accent))
        apply_btn.setCursor(Qt.PointingHandCursor); apply_btn.setFixedHeight(40)
        apply_btn.clicked.connect(self._apply)
        ar2 = QHBoxLayout(); ar2.addStretch(); ar2.addWidget(apply_btn); ar2.addStretch()
        cv.addLayout(ar2); cv.addStretch()
        scroll.setWidget(content); root.addWidget(scroll)

    def _open_discord_login(self):
        dlg = DiscordLoginDialog(self)
        dlg.login_success.connect(self._on_discord_login)
        dlg.exec()

    def _on_discord_login(self, discord_user):
        user_data["discord_id"]         = discord_user.get("id", "")
        user_data["discord_username"]   = discord_user.get("username", "")
        user_data["discord_avatar_url"] = discord_user.get("avatar_url", "")
        global_name = discord_user.get("global_name") or discord_user.get("username", "")
        if global_name:
            user_data["username"] = global_name
        save_user(user_data)
        avatar_url = discord_user.get("avatar_url", "")
        if avatar_url:
            def _dl_avatar():
                dest = _cache_path("discord_avatar", ".jpg")
                _download_image(avatar_url, dest)
                QTimer.singleShot(0, self._rebuild_after_login)
            threading.Thread(target=_dl_avatar, daemon=True).start()
        else:
            self._rebuild_after_login()

    def _rebuild_after_login(self):
        self._build()
        self.theme_changed.emit()

    def _discord_logout(self):
        user_data["discord_id"]         = ""
        user_data["discord_username"]   = ""
        user_data["discord_avatar_url"] = ""
        av_cache = _cache_path("discord_avatar", ".jpg")
        if os.path.exists(av_cache):
            try:
                os.remove(av_cache)
            except Exception:
                pass
        save_user(user_data)
        self._build()
        self.theme_changed.emit()

    def _section_label(self, text):
        lbl = QLabel(f"// {text}")
        lbl.setStyleSheet(f"font-size:9px; font-weight:700; color:{TH.accent}; letter-spacing:2px; font-family:{TH.font_fam}; padding:4px 0 2px 0;")
        return lbl

    def _set_accent(self, c):
        self._pending["accent"] = c; self._pending["preset"] = "Custom"; self._build()

    def _apply_preset(self, name, vals):
        self._pending = {**vals, "preset": name}; self._build()

    def _apply(self):
        user_data["theme"] = self._pending.copy()
        save_user(user_data); TH.reload()
        self.theme_changed.emit()

    def refresh(self):
        self._pending = user_data.get("theme", {}).copy(); self._build()


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
NAV_ITEMS = [
    ("library",   "◈",  "Library"),
    ("downloads", "↓",  "Downloads"),
    ("friends",   "👥", "Friends"),
    ("settings",  "⚙",  "Settings"),
]
NAV_BOTTOM = [
    ("news", "📰", "News"),
]


class GOGSidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, on_profile_edit=None):
        super().__init__()
        self.setFixedWidth(200)
        self._active = "library"
        self._on_profile_edit = on_profile_edit
        self._buttons = {}
        self._build()

    def _build(self):
        old = self.layout()
        if old:
            clear_layout(old); temp = QWidget(); temp.setLayout(old)

        self.setStyleSheet("QWidget{ background: rgba(6,6,14,210); } QWidget{ border-right: 1px solid rgba(255,255,255,8); }")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        logo_w = QWidget(); logo_w.setFixedHeight(62)
        logo_w.setStyleSheet("background: transparent; border-bottom: 1px solid rgba(255,255,255,8);")
        ll = QHBoxLayout(logo_w); ll.setContentsMargins(16, 0, 14, 0)
        logo = QLabel("GAME\nVAULT"); logo.setStyleSheet(f"font-size:13px; font-weight:700; color:{TH.accent}; letter-spacing:2px; line-height:1.3; font-family:{TH.font_fam};")
        dot  = QLabel("●"); dot.setStyleSheet(f"color:{TH.accent}; font-size:8px;")
        ll.addWidget(logo); ll.addStretch(); ll.addWidget(dot, alignment=Qt.AlignVCenter)
        root.addWidget(logo_w)
        root.addSpacing(8)

        for key, icon, label in NAV_ITEMS:
            btn = self._nav_btn(key, icon, label)
            self._buttons[key] = btn; root.addWidget(btn)

        root.addStretch()

        for key, icon, label in NAV_BOTTOM:
            btn = self._nav_btn(key, icon, label)
            self._buttons[key] = btn; root.addWidget(btn)

        root.addSpacing(4)
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("QFrame{ background: rgba(255,255,255,8); max-height:1px; }")
        root.addWidget(sep)

        profile = QWidget(); profile.setFixedHeight(74)
        profile.setStyleSheet("background: transparent; cursor: pointer;")
        pl = QHBoxLayout(profile); pl.setContentsMargins(12, 10, 12, 10); pl.setSpacing(10)

        self._avatar_widget = ClickableAvatar(size=40)
        self._avatar_widget.clicked.connect(self._pick_pfp)
        pl.addWidget(self._avatar_widget)

        nv = QVBoxLayout(); nv.setSpacing(1)
        name_lbl = QLabel(user_data.get("username", "Player One"))
        name_lbl.setStyleSheet(f"font-size:11px; font-weight:700; color:{TH.text_pri}; font-family:{TH.font_fam};")
        status     = user_data.get("status", "Online")
        sc         = STATUS_COLOR.get(status, TH.accent)
        discord_id = user_data.get("discord_id", "")
        if discord_id:
            st_lbl = QLabel("🎮 Discord")
            st_lbl.setStyleSheet("font-size:8px; color:#5865F2; font-family:" + TH.font_fam + ";")
        else:
            st_lbl = QLabel(f"● {status}")
            st_lbl.setStyleSheet(f"font-size:8px; color:{sc}; font-family:{TH.font_fam};")
        nv.addWidget(name_lbl); nv.addWidget(st_lbl)
        pl.addLayout(nv); pl.addStretch()

        edit = QPushButton("✎"); edit.setFixedSize(24, 24); edit.setCursor(Qt.PointingHandCursor)
        edit.setStyleSheet(f"QPushButton{{background:transparent; color:{TH.text_sec}; border:none; font-size:12px;}} QPushButton:hover{{color:{TH.accent};}}")
        if self._on_profile_edit:
            edit.clicked.connect(self._on_profile_edit)
        pl.addWidget(edit)
        root.addWidget(profile)
        self._set_active(self._active)

    def _pick_pfp(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Profile Picture", "", "Images & GIFs (*.png *.jpg *.jpeg *.webp *.gif)")
        if path:
            user_data["pfp_path"] = path; save_user(user_data)
            if hasattr(self, "_avatar_widget"):
                self._avatar_widget.update_avatar()

    def _nav_btn(self, key, icon, label):
        btn = QPushButton(f"  {icon}   {label}"); btn.setFixedHeight(38); btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, k=key: self._click(k))
        return btn

    def _click(self, key):
        self._active = key; self._set_active(key); self.navigate.emit(key)

    def _set_active(self, key):
        self._active = key
        for k, btn in self._buttons.items():
            btn.setStyleSheet(sidebar_btn_active() if k == key else sidebar_btn_base())

    def set_active(self, key):
        self._set_active(key)

    def refresh(self):
        self._build()


# ═══════════════════════════════════════════════════════════════════════════════
#  PLACEHOLDER PAGE
# ═══════════════════════════════════════════════════════════════════════════════
class PlaceholderPage(QWidget):
    def __init__(self, icon, name, accent=None):
        super().__init__()
        self.setAttribute(Qt.WA_TranslucentBackground)
        c = accent or TH.accent
        v = QVBoxLayout(self); v.setAlignment(Qt.AlignCenter); v.setSpacing(8)
        for t, s in [(icon, "font-size:44px;"), (name, f"font-size:20px; font-weight:700; color:{c}; letter-spacing:4px; font-family:{TH.font_fam};"), ("// COMING SOON", f"font-size:10px; color:{TH.text_sec}; letter-spacing:2.5px; font-family:{TH.font_fam};")]:
            l = QLabel(t); l.setStyleSheet(s); l.setAlignment(Qt.AlignCenter); v.addWidget(l)

    def refresh(self):
        pass


# ═══════════════════════════════════════════════════════════════════════════════
#  PROFILE DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
AVATARS     = ["🎮", "🕹️", "👾", "🦾", "🧠", "🐉", "💀", "⚡", "🔥", "🛸", "🦊", "🌙", "⚔", "🏆", "🎯"]
STATUS_OPTS = ["Online", "Away", "Do Not Disturb", "Invisible"]


class ProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Profile"); self.setFixedSize(400, 480)
        self.setStyleSheet(f"QDialog{{background:{TH.bg_panel};}}")
        root = QVBoxLayout(self); root.setContentsMargins(22, 22, 22, 22); root.setSpacing(10)
        t = QLabel("// EDIT PROFILE")
        t.setStyleSheet(f"font-size:10px; font-weight:700; color:{TH.accent}; letter-spacing:2px; font-family:{TH.font_fam};")
        root.addWidget(t)

        discord_id = user_data.get("discord_id", "")
        if discord_id:
            disc_info = QLabel(f"🎮 Signed in via Discord as {user_data.get('discord_username', '')}")
            disc_info.setStyleSheet(f"font-size:9px; color:#5865F2; font-family:{TH.font_fam}; background: rgba(88,101,242,15); border: 1px solid rgba(88,101,242,40); border-radius:6px; padding:6px 10px;")
            root.addWidget(disc_info)

        pfp_row = QHBoxLayout(); pfp_row.setSpacing(14)
        self._dlg_avatar = ClickableAvatar(size=60)
        self._dlg_avatar.clicked.connect(self._pick_pfp_dialog)
        pfp_hint = QLabel("Click avatar to\nchange picture\n(PNG, JPG, GIF)")
        pfp_hint.setStyleSheet(f"font-size:8px; color:{TH.text_sec}; font-family:{TH.font_fam};")
        pfp_row.addWidget(self._dlg_avatar); pfp_row.addWidget(pfp_hint); pfp_row.addStretch()
        root.addLayout(pfp_row)

        av_lbl = QLabel("EMOJI AVATAR  (used when no picture is set)")
        av_lbl.setStyleSheet(f"font-size:8px; color:{TH.text_sec}; letter-spacing:1px; font-family:{TH.font_fam};")
        root.addWidget(av_lbl)
        self._sel_av = user_data.get("avatar", "🎮")
        self._av_btns = []
        row = QHBoxLayout(); row.setSpacing(5)
        for av in AVATARS[:10]:
            btn = QPushButton(av); btn.setFixedSize(30, 30); btn.setCheckable(True); btn.setChecked(av == self._sel_av)
            btn.setStyleSheet(f"QPushButton{{background:{TH.bg_card}; border:1px solid {TH.border}; border-radius:5px; font-size:14px;}} QPushButton:checked{{border:2px solid {TH.accent}; background:{TH.bg_card_h};}}")
            btn.clicked.connect(lambda _, b=btn, a=av: self._pick_av(b, a))
            self._av_btns.append((btn, av)); row.addWidget(btn)
        row.addStretch(); root.addLayout(row)

        for lbl_txt, attr, val in [("USERNAME", "_username", user_data.get("username", "Player One")), ("PLAYER TAG", "_tag", user_data.get("tag", "#0001"))]:
            l = QLabel(lbl_txt); l.setStyleSheet(f"font-size:8px; color:{TH.text_sec}; letter-spacing:1px; font-family:{TH.font_fam};")
            root.addWidget(l); inp = QLineEdit(val); setattr(self, attr, inp); root.addWidget(inp)

        sl = QLabel("STATUS"); sl.setStyleSheet(f"font-size:8px; color:{TH.text_sec}; letter-spacing:1px; font-family:{TH.font_fam};")
        root.addWidget(sl)
        self._status = QComboBox(); self._status.addItems(STATUS_OPTS)
        cur_status = user_data.get("status", "Online")
        self._status.setCurrentIndex(STATUS_OPTS.index(cur_status) if cur_status in STATUS_OPTS else 0)
        root.addWidget(self._status); root.addStretch()

        btn_row = QHBoxLayout()
        cancel = QPushButton("CANCEL"); cancel.setStyleSheet(ghost_btn(TH.text_sec)); cancel.clicked.connect(self.reject)
        save   = QPushButton("SAVE");   save.setStyleSheet(action_btn(TH.accent));    save.clicked.connect(self._save)
        btn_row.addWidget(cancel); btn_row.addStretch(); btn_row.addWidget(save)
        root.addLayout(btn_row)

    def _pick_pfp_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Profile Picture", "", "Images & GIFs (*.png *.jpg *.jpeg *.webp *.gif)")
        if path:
            user_data["pfp_path"] = path; save_user(user_data); self._dlg_avatar.update_avatar()

    def _pick_av(self, clicked, avatar):
        self._sel_av = avatar
        for btn, av in self._av_btns:
            btn.setChecked(av == avatar)

    def _save(self):
        user_data["username"] = self._username.text().strip() or "Player One"
        user_data["tag"]      = self._tag.text().strip() or "#0001"
        user_data["status"]   = self._status.currentText()
        user_data["avatar"]   = self._sel_av
        save_user(user_data); self.accept()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class GameVaultWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Game Vault")
        self.setMinimumSize(800, 600)
        self._active_key = "library"
        self._loader = None
        self._bg = None
        self._main_ui_built = False

        # Show loader FIRST — cover entire window
        self._loader = LoadingScreen(self)
        self._loader.setGeometry(self.rect())
        self._loader.show()
        self._loader.raise_()

        # Allow the loader to paint before any heavy work starts
        QApplication.processEvents()

        # Kick off the loading sequence
        QTimer.singleShot(80, self._start_loading_sequence)

    def _start_loading_sequence(self):
        steps = [
            (300,  15,  "Scanning Steam library...",  350),
            (700,  35,  "Scanning Epic library...",    350),
            (1100, 55,  "Loading game assets...",      380),
            (1500, 72,  "Building your library...",    400),
            (1900, 88,  "Almost ready...",             350),
            (2300, 100, "Ready!",                      300),
        ]
        for delay, pct, status, dur in steps:
            QTimer.singleShot(delay, lambda p=pct, s=status, d=dur: self._loader.set_progress(p, s, d))

        QTimer.singleShot(1400, self._build_main_ui)
        QTimer.singleShot(2700, self._begin_loader_exit)

    def _begin_loader_exit(self):
        if self._loader:
            self._loader.finish_and_hide(on_done=self._on_loader_done)

    def _on_loader_done(self):
        if self._loader:
            self._loader.hide()
            self._loader.deleteLater()
            self._loader = None

    def _build_main_ui(self):
        if self._main_ui_built:
            return
        self._main_ui_built = True

        old = self.layout()
        if old:
            clear_layout(old)
            temp = QWidget(); temp.setLayout(old)

        if not self._bg:
            self._bg = LiveBackground(self)
            self._bg.setGeometry(self.rect())
            self._bg.lower()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._library_page  = LibraryPage()
        self._friends_page  = FriendsPage()
        self._settings_page = SettingsPage(self._bg)
        self._settings_page.theme_changed.connect(self._on_theme_change)

        self.pages = {
            "library":   self._library_page,
            "friends":   self._friends_page,
            "settings":  self._settings_page,
            "downloads": PlaceholderPage("↓", "DOWNLOADS", TH.neon_p),
            "news":      PlaceholderPage("📰", "NEWS",      TH.neon_b),
        }

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent;")
        for page in self.pages.values():
            self._stack.addWidget(page)
        self._stack.setCurrentWidget(self.pages[self._active_key])

        self._sidebar = GOGSidebar(on_profile_edit=self._edit_profile)
        self._sidebar.navigate.connect(self._navigate)
        self._sidebar.set_active(self._active_key)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setStyleSheet("QFrame{ background: rgba(255,255,255,8); }")

        root.addWidget(self._sidebar)
        root.addWidget(sep)
        root.addWidget(self._stack, stretch=1)

        if self._loader:
            self._loader.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._bg:
            self._bg.setGeometry(self.rect())
            self._bg.lower()
        if self._loader:
            self._loader.setGeometry(self.rect())
            self._loader.raise_()

    def _navigate(self, key):
        self._active_key = key
        if key in self.pages:
            self._stack.setCurrentWidget(self.pages[key])
        self._sidebar.set_active(key)

    def _edit_profile(self):
        dlg = ProfileDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self._sidebar.refresh()

    def _on_theme_change(self):
        self._main_ui_built = False
        self._build_main_ui()
        self._sidebar.set_active(self._active_key)
        self._navigate(self._active_key)


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
app = QApplication([])
app.setStyle("Fusion")

from PySide6.QtGui import QPalette
palette = QPalette()
palette.setColor(QPalette.Window,          QColor(7, 7, 9))
palette.setColor(QPalette.WindowText,      QColor(232, 232, 240))
palette.setColor(QPalette.Base,            QColor(10, 10, 16))
palette.setColor(QPalette.AlternateBase,   QColor(13, 13, 18))
palette.setColor(QPalette.Text,            QColor(232, 232, 240))
palette.setColor(QPalette.Button,          QColor(13, 13, 18))
palette.setColor(QPalette.ButtonText,      QColor(232, 232, 240))
app.setPalette(palette)

window = GameVaultWindow()
window.show()
app.exec()
