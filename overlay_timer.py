import os
import sys
import json
import threading

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal  # Importar pyqtSignal
import keyboard  # para hotkeys globales


class OverlayTimer(QtWidgets.QWidget):
    # --- 1) Definición de señales ---
    sig_start = pyqtSignal()
    sig_pause = pyqtSignal()
    sig_reset = pyqtSignal()

    def __init__(self, config_path="config.json"):
        super().__init__()

        # Cargar configuración
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # Parámetros extraídos de config.json
        self.blink_times = set(self.config.get("blink_times", []))
        font_conf     = self.config.get("font", {})
        colors_conf   = self.config.get("colors", {})
        pos_conf      = self.config.get("position", {})
        self.opacity  = float(self.config.get("opacity", 1.0))

        # Colores (hex string)
        self.text_color_normal      = colors_conf.get("text", "#FFFFFF")
        self.bg_color_normal        = colors_conf.get("background", "#000000")
        self.text_color_blink       = colors_conf.get("blink_text", "#000000")
        self.bg_color_blink         = colors_conf.get("blink_background", "#FFFFFF")

        # Fuente
        family = font_conf.get("family", "Arial")
        size   = int(font_conf.get("size", 36))

        # Estado interno del cronómetro
        self.elapsed_seconds = 0
        self.is_running = False
        self.blinking = False

        # --- 2) Conectar señales a métodos ---
        # Cuando se emita sig_start, se invoca start_timer() en el hilo de Qt
        self.sig_start.connect(self.start_timer)
        self.sig_pause.connect(self.pause_timer)
        self.sig_reset.connect(self.reset_timer)

        # --- Configurar la ventana overlay ---
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        # Etiqueta que mostrará el tiempo
        self.label = QtWidgets.QLabel(self)
        font = QtGui.QFont(family, size, QtGui.QFont.Bold)
        self.label.setFont(font)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet(f"color: {self.text_color_normal};")

        # Fondo semitransparente
        self.bg_widget = QtWidgets.QWidget(self)
        self.bg_widget.setStyleSheet(f"background-color: {self.bg_color_normal};")
        self.bg_widget.setWindowOpacity(self.opacity)

        # Layout (bg_widget detrás del label)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.bg_widget)
        layout.addWidget(self.label, alignment=QtCore.Qt.AlignCenter)

        # Tamaño inicial aproximado
        self.resize(300, 100)
        self._move_to_position(pos_conf)

        # Timer principal de 1 s (cronómetro)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_time)

        # Timer secundario de parpadeo 0.5 s
        self.blink_timer = QtCore.QTimer()
        self.blink_timer.setInterval(500)
        self.blink_timer.timeout.connect(self._do_blink)
        self.blink_counter = 0

        # Mostrar inicialmente 00:00
        self._refresh_display()

    def _move_to_position(self, pos_conf):
        """Coloca la ventana según configuración: center u otra coordenada."""
        screen = QtWidgets.QApplication.primaryScreen()
        geom   = screen.availableGeometry()
        win_w  = self.width()
        win_h  = self.height()

        y = int(pos_conf.get("vertical", 0))
        horiz = pos_conf.get("horizontal", "center")
        if isinstance(horiz, (int, float)) or str(horiz).isdigit():
            x = int(horiz)
        else:
            x = geom.x() + (geom.width() - win_w) // 2

        self.move(x, y)

    def _refresh_display(self):
        """Formatea elapsed_seconds a mm:ss y actualiza el QLabel."""
        mins = self.elapsed_seconds // 60
        secs = self.elapsed_seconds % 60
        text = f"{mins:02d}:{secs:02d}"
        self.label.setText(text)

        # Ajustar tamaño de ventana en función del QLabel
        self.label.adjustSize()
        w = max(self.label.width() + 20, 200)
        h = max(self.label.height() + 20, 80)
        self.resize(w, h)
        self.bg_widget.resize(w, h)
        self._move_to_position(self.config.get("position", {}))

    def _update_time(self):
        """Llamado cada segundo si is_running=True."""
        if not self.is_running:
            return

        self.elapsed_seconds += 1
        self._refresh_display()

        # Si coincide con un tiempo de parpadeo y no está ya parpadeando
        if self.elapsed_seconds in self.blink_times and not self.blinking:
            self._start_blink()

    def _start_blink(self):
        """Inicia 5 s de parpadeo (10 alternancias de 0.5 s)."""
        self.blinking = True
        self.blink_counter = 0
        self.blink_timer.start()

    def _do_blink(self):
        """Cada 500 ms alterna colores; tras 10 ciclos, detiene el parpadeo."""
        if self.blink_counter >= 10:
            # Terminar parpadeo: colores normales
            self.blink_timer.stop()
            self._set_normal_style()
            self.blinking = False
            return

        if self.blink_counter % 2 == 0:
            self._set_blink_style()
        else:
            self._set_normal_style()

        self.blink_counter += 1

    def _set_normal_style(self):
        self.bg_widget.setStyleSheet(f"background-color: {self.bg_color_normal};")
        self.label.setStyleSheet(f"color: {self.text_color_normal};")

    def _set_blink_style(self):
        self.bg_widget.setStyleSheet(f"background-color: {self.bg_color_blink};")
        self.label.setStyleSheet(f"color: {self.text_color_blink};")

    # ------ Métodos de control del cronómetro ------
    def start_timer(self):
        if not self.is_running:
            self.is_running = True
            self.timer.start()

    def pause_timer(self):
        if self.is_running:
            self.is_running = False
            # Podríamos hacer también self.timer.stop(), pero el flag is_running=False basta

    def reset_timer(self):
        # Detener cronómetro y parpadeo
        self.is_running = False
        self.timer.stop()
        if self.blinking:
            self.blink_timer.stop()
            self.blinking = False
            self._set_normal_style()
        # Reiniciar a 0
        self.elapsed_seconds = 0
        self._refresh_display()

    def closeEvent(self, event):
        """Al cerrar la ventana, desregistrar hotkeys y parar timers."""
        self.timer.stop()
        self.blink_timer.stop()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        event.accept()


def register_hotkeys(window: OverlayTimer):
    """
    Registra hotkeys globales con 'keyboard'. Al presionar,
    emite la señal correspondiente (ejecutada en el hilo de Qt).
    """
    # Ctrl + Shift + U  → Iniciar / Reanudar
    keyboard.add_hotkey('ctrl+shift+u', lambda: window.sig_start.emit())
    # Ctrl + Shift + I  → Pausar
    keyboard.add_hotkey('ctrl+shift+i', lambda: window.sig_pause.emit())
    # Ctrl + Shift + O  → Reiniciar
    keyboard.add_hotkey('ctrl+shift+o', lambda: window.sig_reset.emit())
    
    # Ctrl + Shift + C → Cerrar _y_ terminar el proceso
    # Llamamos primero a window.close() para que dispare closeEvent,
    # y acto seguido a os._exit(0) para matar todo el intérprete.
    keyboard.add_hotkey(
        'ctrl+shift+c',
        lambda: (window.close(), os._exit(0))
    )

    # Mantener este hilo vivo mientras la app esté abierta
    keyboard.wait()


def main():
    app = QtWidgets.QApplication(sys.argv)

    # Crear overlay y mostrarlo
    overlay = OverlayTimer(config_path="config.json")
    overlay.show()

    # Lanzar hilo de hotkeys (daemon=True para que termine al cerrar la app)
    hotkey_thread = threading.Thread(
        target=register_hotkeys,
        args=(overlay,),
        daemon=True
    )
    hotkey_thread.start()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
