import os, sys, re, json, subprocess, socket, psutil
import urllib.request
from PyQt6 import QtWidgets, QtGui, QtCore, QtNetwork
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest

def load_config():
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {"servers_dir": os.path.abspath("servers")}

def save_config(config):
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def list_servers():
    global SERVERS_DIR
    if not SERVERS_DIR or not os.path.exists(SERVERS_DIR):
        os.makedirs(SERVERS_DIR, exist_ok=True)
        return []
    servers = []
    for name in os.listdir(SERVERS_DIR):
        server_dir = os.path.join(SERVERS_DIR, name)
        if not os.path.isdir(server_dir):
            continue
        # Ищем jar-файл сервера или bedrock_server.exe
        has_jar = any(
            f.endswith(".jar") and not f.endswith("installer.jar")
            for f in os.listdir(server_dir)
        )
        has_bedrock = "bedrock_server.exe" in os.listdir(server_dir)
        if has_jar or has_bedrock:
            servers.append(name)
    return servers

def get_latest_bedrock_url():
    url = "https://www.minecraft.net/en-us/download/server/bedrock"
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8")
    # Универсальный паттерн для поиска .zip
    match = re.search(
        r'https://[^\s"\']*bedrock-server-[\d\.]+\.zip', html
    )
    if match:
        return match.group(0)
    raise Exception("Не удалось найти актуальную ссылку на Bedrock Dedicated Server")

# Защита при запуске из exe
def resource_path(relative_path):
    """Возвращает абсолютный путь к ресурсу, работает и для PyInstaller, и для обычного запуска."""
    if hasattr(sys, '_MEIPASS'):
        # Если запущено из exe
        base_path = os.path.dirname(sys.executable)
    else:
        # Если запущено из исходников
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

config_path = resource_path("config.json")
SERVERS_DIR = None
class ServerManager(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft Server Manager")
        self.resize(1400, 800)
        
        # --- Защита от идиота 2 (от меня походу) ---
        self._ip_visible = False
        self._ip_always_visible = False

        # --- Иконка окна ---
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # --- Основной layout ---
        main_layout = QtWidgets.QHBoxLayout(self)

        # --- Левая панель ---
        left_panel = QtWidgets.QVBoxLayout()
        left_panel.setSpacing(10)

        # --- Список серверов ---
        server_group = QtWidgets.QGroupBox("Серверы")
        server_group_layout = QtWidgets.QVBoxLayout(server_group)
        
        self.server_list_widget = QtWidgets.QWidget()
        self.server_list_layout = QtWidgets.QVBoxLayout(self.server_list_widget)
        self.server_list_layout.setContentsMargins(0, 0, 0, 0)
        self.server_list_layout.setSpacing(2)
        self.server_list_items = []

        # --- Кнопка создания сервера ---
        self.create_server_button = QtWidgets.QPushButton("Создать сервер")
        self.create_server_button.clicked.connect(self.show_create_server_dialog)
        server_group_layout.addWidget(self.create_server_button)
        server_group_layout.addWidget(self.server_list_widget)
        
        left_panel.addWidget(server_group, stretch=1)

        # --- Список игроков ---
        players_group = QtWidgets.QGroupBox("Игроки")
        players_group_layout = QtWidgets.QVBoxLayout(players_group)
        self.players_list = QtWidgets.QListWidget()
        players_group_layout.addWidget(self.players_list)
        self.players_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.players_list.customContextMenuRequested.connect(self.show_player_menu)
        
        left_panel.addWidget(players_group, stretch=1)

        # --- Правая панель ---
        right_panel = QtWidgets.QVBoxLayout()
        right_panel.setSpacing(10)

        # --- Панель информации о сервере ---
        server_info_panel = QtWidgets.QVBoxLayout()
        server_info_panel.setSpacing(5)
        
        # --- Верхняя строка с названием и IP ---
        top_server_panel = QtWidgets.QHBoxLayout()
        self.text_label = QtWidgets.QLabel("Выбранный сервер:")
        top_server_panel.addWidget(self.text_label)
        top_server_panel.addStretch(1)
        top_server_panel.addWidget(QtWidgets.QLabel("ip:"))

        # --- Метка IP ---
        self.ip_label = QtWidgets.QLabel()
        self.ip_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.ip_label.setStyleSheet("""color: white;font-weight: bold;border: 1px solid #444;padding: 2px 8px;background-color: #222;border-radius: 4px;""")
        self.ip_label.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.ip_label.mousePressEvent = self.show_ip_temporarily
        self.ip_label.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ip_label.customContextMenuRequested.connect(self.show_ip_context_menu)
        self._ip_timer = QtCore.QTimer(self)
        self._ip_timer.setSingleShot(True)
        self._ip_timer.timeout.connect(self.hide_ip)
        top_server_panel.addWidget(self.ip_label)
        
        server_info_panel.addLayout(top_server_panel)

        # --- Надпись статуса сервера ---
        self.status_label = QtWidgets.QLabel("Статус: Не выбран")
        self.status_label.setStyleSheet("font-weight: bold; color: #ffffff; padding: 4px;")
        server_info_panel.addWidget(self.status_label)
        
        right_panel.addLayout(server_info_panel)

        # --- Кнопки управления сервером ---
        controls_panel = QtWidgets.QHBoxLayout()
        controls_panel.setSpacing(10)
        # --- Кнопка старт/стоп ---
        self.top_startstop_button = QtWidgets.QPushButton("Старт")
        self.top_startstop_button.setFixedWidth(100)
        self.top_startstop_button.clicked.connect(self.toggle_server)
        self.top_startstop_button.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold;")
        self.top_startstop_button.setEnabled(False)  # Серый до выбора сервера
        controls_panel.addWidget(self.top_startstop_button)

        # --- Кнопка быстрых действий ---
        self.quick_actions_button = QtWidgets.QPushButton("Быстрые действия")
        self.quick_actions_button.setMinimumWidth(150)
        self.quick_actions_button.setMaximumWidth(200)
        self.quick_actions_menu = QtWidgets.QMenu(self)
        self.action_whitelist = self.quick_actions_menu.addAction("Включить белый список")
        self.action_restart = self.quick_actions_menu.addAction("Перезапустить сервер")
        self.action_reload = self.quick_actions_menu.addAction("Команда reload")
        self.action_tickfreeze = self.quick_actions_menu.addAction("Заморозить время (tick freeze)")
        self.quick_actions_button.setMenu(self.quick_actions_menu)
        self.action_whitelist.triggered.connect(self.toggle_whitelist)
        self.action_restart.triggered.connect(self.restart_server)
        self.action_reload.triggered.connect(self.reload_server)
        self.action_tickfreeze.triggered.connect(self.tick_freeze)
        self.quick_actions_button.setEnabled(False)  # Серый до запуска сервера
        controls_panel.addWidget(self.quick_actions_button)

        # --- Кнопка конфигурации сервера ---
        self.config_button = QtWidgets.QPushButton("Конфиг")
        self.config_button.setFixedWidth(100)
        self.config_button.clicked.connect(self.show_server_config_dialog)
        self.config_button.setEnabled(False)  # Серый до выбора сервера
        controls_panel.addWidget(self.config_button)

        controls_panel.addStretch(1)  # Добавляем растяжку перед кнопкой настроек

        # --- Кнопка настроек (теперь справа) ---
        self.settings_button = QtWidgets.QPushButton("⚙ Настройки")
        self.settings_button.setFixedWidth(120)
        self.settings_button.clicked.connect(self.show_settings_dialog)
        controls_panel.addWidget(self.settings_button)

        right_panel.addLayout(controls_panel)

        # --- Лог консоли ---
        console_group = QtWidgets.QGroupBox("Консоль")
        console_layout = QtWidgets.QVBoxLayout(console_group)
        self.log_output = QtWidgets.QTextEdit()
        self.log_output.setReadOnly(True)
        console_layout.addWidget(self.log_output)
        right_panel.addWidget(console_group, stretch=1)

        # --- Ввод команды и кнопка отправки ---
        cmd_group = QtWidgets.QGroupBox()
        cmd_group.setFlat(True)
        cmd_layout = QtWidgets.QHBoxLayout(cmd_group)
        self.command_input = QtWidgets.QLineEdit()
        self.command_input.setPlaceholderText("Введите команду для сервера")
        self.send_command_button = QtWidgets.QPushButton("Отправить")
        self.send_command_button.setEnabled(False)
        cmd_layout.addWidget(self.command_input)
        cmd_layout.addWidget(self.send_command_button)
        right_panel.addWidget(cmd_group)

        # --- Добавление панелей в основной layout ---
        main_layout.addLayout(left_panel, stretch=1)
        main_layout.addLayout(right_panel, stretch=2)

        # --- Привязка событий ---
        self.command_input.returnPressed.connect(self.send_command)
        self.start_button = QtWidgets.QPushButton("Запустить")
        self.stop_button = QtWidgets.QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.send_command_button.clicked.connect(self.send_command)

        # --- Загрузка конфигурации и установка папки серверов ---
        global SERVERS_DIR
        if not os.path.exists(config_path):
            self.config = load_config()
            self.first_config()
        else:
            self.config = load_config()
        SERVERS_DIR = self.config.get("servers_dir", os.path.abspath("servers"))

        # --- Переменные состояния ---
        self.process = None
        self.selected_server = None
        self.server_status = {}
        self.online_players = set()
        # --- Инициализация интерфейса ---
        self.load_servers()
        self.update_top_buttons()
        self.update_ip_label()
        self.update_selected_server_label()

    def update_top_buttons(self):
        status = self.get_server_status(self.get_selected_server())
        server_selected = self.get_selected_server() is not None
        if status == "running":
            self.top_startstop_button.setText("Стоп")
            self.top_startstop_button.setStyleSheet("background-color: #f44336; color: white; font-weight: bold;")
            self.quick_actions_button.setEnabled(True)
        else:
            self.top_startstop_button.setText("Старт")
            self.top_startstop_button.setStyleSheet("background-color: #4caf50; color: white; font-weight: bold;")
            self.quick_actions_button.setEnabled(False)

        self.top_startstop_button.setEnabled(server_selected)
        self.config_button.setEnabled(server_selected)

    def update_selected_server_label(self):
        """Обновляет текст метки выбранного сервера."""
        server = self.get_selected_server()
        if server:
            self.text_label.setText(f"Выбранный сервер: {server}")
        else:
            self.text_label.setText("Выбранный сервер:")

    def first_config(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Первичная настройка")
        dialog.setFixedSize(700, 350)
        layout = QtWidgets.QFormLayout(dialog)

        # --- Директория по умолчанию ---
        default_dir = resource_path("servers")
        dir_edit = QtWidgets.QLineEdit(default_dir)
        browse_btn = QtWidgets.QPushButton("Обзор...")

        def browse():
            directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Выберите папку для серверов", dir_edit.text())
            if directory:
                dir_edit.setText(directory)

        browse_btn.clicked.connect(browse)
        dir_layout = QtWidgets.QHBoxLayout()
        dir_layout.addWidget(dir_edit)
        dir_layout.addWidget(browse_btn)
        layout.addRow("Папка серверов:", dir_layout)

        # --- Список сетей ---
        net_combo = QtWidgets.QComboBox()
        networks = []
        net_map = {}
        for iface, addrs in psutil.net_if_addrs().items():
            ip_list = [addr.address for addr in addrs if addr.family == socket.AF_INET and not addr.address.startswith("127.")]
            if ip_list:
                networks.append(iface)
                net_map[iface] = ip_list
        if not networks:
            networks = ["localhost"]
            net_map["localhost"] = ["127.0.0.1"]

        net_combo.addItems(networks)
        layout.addRow("Сеть для отображения:", net_combo)

        # --- Расширенные параметры ---
        advanced_group = QtWidgets.QGroupBox("Расширенные параметры")
        advanced_group.setCheckable(True)
        advanced_group.setChecked(False)
        adv_layout = QtWidgets.QFormLayout(advanced_group)

        # --- Java path ---
        java_path_edit = QtWidgets.QLineEdit(self.config.get("java_path", "java"))
        java_browse_btn = QtWidgets.QPushButton("Обзор...")

        def browse_java():
            file_dialog = QtWidgets.QFileDialog(self, "Укажите путь к java", java_path_edit.text())
            file_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
            if file_dialog.exec():
                files = file_dialog.selectedFiles()
                if files:
                    java_path_edit.setText(files[0])

        java_browse_btn.clicked.connect(browse_java)
        java_layout = QtWidgets.QHBoxLayout()
        java_layout.addWidget(java_path_edit)
        java_layout.addWidget(java_browse_btn)
        adv_layout.addRow("Путь к java:", java_layout)

        # --- Ползунок выбора максимальной оперативки ---
        total_gb = max(1, int(psutil.virtual_memory().total // (1024 ** 3)))
        ram_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        ram_slider.setMinimum(1)
        ram_slider.setMaximum(total_gb)
        ram_slider.setValue(min(5, total_gb))
        ram_slider.setTickInterval(1)
        ram_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        ram_label = QtWidgets.QLabel(f"{ram_slider.value()} ГБ")
        ram_warning = QtWidgets.QLabel("")
        ram_warning.setStyleSheet("color: orange; font-size: 11px;")
        ram_warning.setWordWrap(True)
        def update_ram_label(val):
            ram_label.setText(f"{val} ГБ")
            percent = val / total_gb
            if percent > 0.6:
                ram_warning.setText("Внимание: выделено больше 60% всей оперативной памяти. Сервер может не запуститься или система станет нестабильной.")
            elif total_gb > 8 and val < 2:
                ram_warning.setText("Внимание: выделено мало оперативной памяти. Сервер может работать нестабильно при таком объёме ОЗУ.")
            else:
                ram_warning.setText("")

        ram_slider.valueChanged.connect(update_ram_label)
        update_ram_label(ram_slider.value())

        ram_layout = QtWidgets.QHBoxLayout()
        ram_layout.addWidget(ram_slider)
        ram_layout.addWidget(ram_label)
        adv_layout.addRow("Выделено ОЗУ:", ram_layout)
        adv_layout.addRow("", ram_warning)

        layout.addRow(advanced_group)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        layout.addRow(btn_box)

        def on_accept():
            new_dir = dir_edit.text().strip()
            if not new_dir:
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Укажите папку для серверов.")
                return
            if not os.path.isdir(new_dir):
                try:
                    os.makedirs(new_dir, exist_ok=True)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(dialog, "Ошибка", f"Не удалось создать папку:\n{e}")
                    return
            self.config["servers_dir"] = new_dir
            self.config["selected_network"] = net_combo.currentText()
            iface = net_combo.currentText()
            ip_list = net_map.get(iface, [])
            self.config["selected_ip"] = ip_list[0] if ip_list else "127.0.0.1"
            if advanced_group.isChecked():
                self.config["java_path"] = java_path_edit.text().strip() or "java"
                self.config["max_ram_gb"] = ram_slider.value()
                self.config["advanced_option"] = True
            else:
                self.config["java_path"] = "java"
                self.config["max_ram_gb"] = 5
                self.config["advanced_option"] = False
            save_config(self.config)
            global SERVERS_DIR
            SERVERS_DIR = new_dir
            self.update_ip_label()
            self.load_servers()
            dialog.accept()

        btn_box.accepted.connect(on_accept)
        dialog.exec()

    def get_server_status(self, server_name):
        if hasattr(self, 'selected_server') and self.selected_server == server_name and self.process:
            if self.process.state() == QtCore.QProcess.ProcessState.Running:
                return "running"
            elif self.process.exitStatus() == QtCore.QProcess.ExitStatus.CrashExit:
                return "error"
            else:
                return "stopped"
        return self.server_status.get(server_name, "stopped")

    def show_settings_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Настройки")
        dialog.setFixedSize(500, 350)
        layout = QtWidgets.QFormLayout(dialog)
        dir_edit = QtWidgets.QLineEdit(self.config.get("servers_dir", ""))
        browse_btn = QtWidgets.QPushButton("Выбрать...")

        def browse():
            directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Выберите папку для серверов", dir_edit.text())
            if directory:
                dir_edit.setText(directory)

        browse_btn.clicked.connect(browse)
        dir_layout = QtWidgets.QHBoxLayout()
        dir_layout.addWidget(dir_edit)
        dir_layout.addWidget(browse_btn)
        layout.addRow("Папка серверов:", dir_layout)

        # --- Список сетей ---
        net_combo = QtWidgets.QComboBox()
        networks = []
        net_map = {}  # network name -> list of IPs
        for iface, addrs in psutil.net_if_addrs().items():
            ip_list = [addr.address for addr in addrs if addr.family == socket.AF_INET and not addr.address.startswith("127.")]
            if ip_list:
                networks.append(iface)
                net_map[iface] = ip_list
        if not networks:
            networks = ["localhost"]
            net_map["localhost"] = ["127.0.0.1"]

        net_combo.addItems(networks)
        selected_net = self.config.get("selected_network")
        if selected_net in networks:
            net_combo.setCurrentText(selected_net)
        else:
            net_combo.setCurrentIndex(0)
        layout.addRow("Сеть для отображения:", net_combo)

        # --- Расширенные параметры ---
        advanced_group = QtWidgets.QGroupBox("Расширенные параметры")
        advanced_group.setCheckable(True)
        # Загружаем состояние advanced_group из конфига, по умолчанию False
        advanced_group.setChecked(self.config.get("advanced_option", False))
        adv_layout = QtWidgets.QFormLayout(advanced_group)

        # --- Java path ---
        java_path_edit = QtWidgets.QLineEdit(self.config.get("java_path", "java"))
        java_browse_btn = QtWidgets.QPushButton("Выбрать...")

        def browse_java():
            file_dialog = QtWidgets.QFileDialog(self, "Укажите путь к java", java_path_edit.text())
            file_dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)
            if file_dialog.exec():
                files = file_dialog.selectedFiles()
                if files:
                    java_path_edit.setText(files[0])

        java_browse_btn.clicked.connect(browse_java)
        java_layout = QtWidgets.QHBoxLayout()
        java_layout.addWidget(java_path_edit)
        java_layout.addWidget(java_browse_btn)
        adv_layout.addRow("Путь к java:", java_layout)

        # --- Ползунок выбора максимальной оперативки ---
        total_gb = max(1, int(psutil.virtual_memory().total // (1024 ** 3)))
        max_ram_gb = self.config.get("max_ram_gb", min(5, total_gb))
        ram_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        ram_slider.setMinimum(1)
        ram_slider.setMaximum(total_gb)
        ram_slider.setValue(max_ram_gb)
        ram_slider.setTickInterval(1)
        ram_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        ram_label = QtWidgets.QLabel(f"{ram_slider.value()} ГБ")
        ram_warning = QtWidgets.QLabel("")
        ram_warning.setStyleSheet("color: orange; font-size: 11px;")
        ram_warning.setWordWrap(True)
        def update_ram_label(val):
            ram_label.setText(f"{val} ГБ")
            percent = val / total_gb
            if percent > 0.6:
                ram_warning.setText("Внимание: выделено больше 60% всей оперативной памяти. Сервер может не запуститься или система станет нестабильной.")
            elif total_gb > 8 and val < 2:
                ram_warning.setText("Внимание: выделено мало оперативной памяти. Сервер может работать нестабильно при таком объёме ОЗУ.")
            else:
                ram_warning.setText("")

        ram_slider.valueChanged.connect(update_ram_label)
        update_ram_label(ram_slider.value())

        ram_layout = QtWidgets.QHBoxLayout()
        ram_layout.addWidget(ram_slider)
        ram_layout.addWidget(ram_label)
        adv_layout.addRow("Выделено ОЗУ:", ram_layout)
        adv_layout.addRow("", ram_warning)

        layout.addRow(advanced_group)

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(btn_box)

        def on_accept():
            new_dir = dir_edit.text().strip()
            if not new_dir or not os.path.isdir(new_dir):
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Укажите существующую папку.")
                return
            self.config["servers_dir"] = new_dir
            self.config["selected_network"] = net_combo.currentText()
            # Выбираем первый IP из выбранной сети
            iface = net_combo.currentText()
            ip_list = net_map.get(iface, [])
            self.config["selected_ip"] = ip_list[0] if ip_list else "127.0.0.1"
            java_path = None
            if advanced_group.isChecked():
                java_path = java_path_edit.text().strip()
                if not java_path:
                    java_path = "java"
                self.config["java_path"] = java_path
                self.config["max_ram_gb"] = ram_slider.value()
                self.config["advanced_option"] = advanced_group.isChecked()
            else:
                self.config["java_path"] = "java"
                self.config["max_ram_gb"] = 5
            save_config(self.config)
            global SERVERS_DIR
            SERVERS_DIR = new_dir
            self.update_ip_label()
            self.load_servers()
            dialog.accept()

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dialog.reject)
        dialog.exec()

    def set_server_status(self, server_name, status):
        self.server_status[server_name] = status
        self.load_servers()

    def make_status_icon(self, status):

        color = {
            "running": "#4caf50",
            "error": "#f44336",
            "stopped": "#bdbdbd"
        }.get(status, "#bdbdbd")

        pixmap = QtGui.QPixmap(16, 16)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 12, 12)
        painter.end()

        return QtGui.QIcon(pixmap)
    

    def load_servers(self):
        for i in reversed(range(self.server_list_layout.count())):
            item = self.server_list_layout.takeAt(i)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.server_list_items.clear()
        servers = list_servers()

        for server_name in servers:
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            
            row_layout.setContentsMargins(2, 0, 2, 0)
            row_layout.setSpacing(4)
            status = self.get_server_status(server_name)
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(self.make_status_icon(status).pixmap(16, 16))
            row_layout.addWidget(icon_label)
            label = QtWidgets.QLabel(server_name)
            label.setMinimumHeight(20)
            label.setStyleSheet("padding-left: 4px;")
            label.mousePressEvent = lambda event, name=server_name: self.select_server_by_name(name)
            row_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

            row_widget.customContextMenuRequested.connect(
                lambda pos, name=server_name, widget=row_widget: self.show_server_menu(pos, name, widget)
            )

            row_layout.addWidget(label)
            row_layout.addStretch(1)
            self.server_list_layout.addWidget(row_widget)
            self.server_list_items.append((server_name, row_widget, label, icon_label))

        self.players_list.clear()
        
    def update_ip_label(self):
        server_name = self.get_selected_server()
        ip = None
        port = "*****"
        if server_name:
            props_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
            if os.path.exists(props_path):
                try:
                    with open(props_path, encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("server-port="):
                                port = line.strip().split("=", 1)[1] or "*****"
                except Exception:
                    pass

        # Получаем список всех IP-адресов пользователя
        ip_list = []
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    ip_list.append(addr.address)
        if not ip_list:
            ip_list = ["127.0.0.1"]
        # Сохраняем выбранный IP в настройках, если есть
        selected_ip = self.config.get("selected_ip")
        if selected_ip not in ip_list:
            selected_ip = ip_list[0]
            self.config["selected_ip"] = selected_ip
            save_config(self.config)
        ip = selected_ip

        self._real_ip = f"{ip}:{port}"
        if self._ip_visible or self._ip_always_visible:
            self.ip_label.setText(self._real_ip)
        else:
            self.ip_label.setText("*" * len(ip) + ":" + "*" * len(port))

    def show_ip_temporarily(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if not self._ip_always_visible:
                self._ip_visible = True
                self.update_ip_label()
                self._ip_timer.start(5000)

    def hide_ip(self):
        self._ip_visible = False
        self.update_ip_label()

    def show_ip_context_menu(self, pos):
        menu = QtWidgets.QMenu(self)
        show_always = menu.addAction("Показать всегда")
        copy_action = menu.addAction("Скопировать")
        action = menu.exec(self.ip_label.mapToGlobal(pos))
        if action == show_always:
            self._ip_always_visible = True
            self.update_ip_label()
        elif action == copy_action:
            QtWidgets.QApplication.clipboard().setText(self._real_ip)
            
    def show_server_config_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Настройки сервера") 
        dialog.setFixedSize(300, 400)
        layout = QtWidgets.QFormLayout(dialog)

        server_name = self.get_selected_server()
        if not server_name:
            return
            
        properties_path = os.path.join(SERVERS_DIR, server_name, "server.properties")
        properties = {}
        
        # Read server.properties
        if os.path.exists(properties_path):
            with open(properties_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        try:
                            key, value = line.split('=', 1)
                            properties[key.strip()] = value.strip()
                        except:
                            continue

        # Helper function to create clickable label with tooltip
        def create_labeled_field(param_name, tooltip):
            label = QtWidgets.QLabel(param_name)
            label.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
            label.setStyleSheet("color: white;") 
            label.setToolTip(tooltip)
            return label

        # MOTD field
        motd_label = create_labeled_field("MOTD:", "Это описание сервера, которое видят игроки в списке серверов")
        motd_input = QtWidgets.QLineEdit(properties.get('motd', ''))
        layout.addRow(motd_label, motd_input)

        # Server port field
        port_label = create_labeled_field("Порт сервера:", "Порт, на котором будет работать сервер")
        port_input = QtWidgets.QSpinBox()
        port_input.setRange(1, 65535)
        port_input.setValue(int(properties.get('server-port', '25565')))
        layout.addRow(port_label, port_input)

        # View distance slider
        view_label = create_labeled_field("Дальность прорисовки:", "Дальность прорисовки в чанках (8-48)")
        view_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        view_slider.setRange(8, 48)
        view_slider.setValue(int(properties.get('view-distance', '10')))
        view_value = QtWidgets.QLabel(str(view_slider.value()))
        view_slider.valueChanged.connect(lambda v: view_value.setText(str(v)))
        view_layout = QtWidgets.QHBoxLayout()
        view_layout.addWidget(view_slider)
        view_layout.addWidget(view_value)
        layout.addRow(view_label, view_layout)

        # Online mode checkbox
        online_mode = QtWidgets.QCheckBox()
        online_label = create_labeled_field("Онлайн режим", "Если включено - на сервер могут зайти только лицензионные аккаунты\nЕсли выключено - смогут зайти и пиратские клиенты")
        online_mode.setChecked(properties.get('online-mode', 'true').lower() == 'true')
        layout.addRow(online_label, online_mode)

        # Hide online players checkbox
        hide_players = QtWidgets.QCheckBox()
        hide_label = create_labeled_field("Скрыть список игроков", "Если включено - список игроков не будет виден в меню паузы")
        hide_players.setChecked(properties.get('hide-online-players', 'false').lower() == 'true')
        layout.addRow(hide_label, hide_players)

        # PvP checkbox 
        pvp = QtWidgets.QCheckBox()
        pvp_label = create_labeled_field("PVP", "Разрешает или запрещает PvP между игроками")
        pvp.setChecked(properties.get('pvp', 'true').lower() == 'true')
        layout.addRow(pvp_label, pvp)

        # Difficulty dropdown
        difficulty = QtWidgets.QComboBox()
        difficulty.addItems(['peaceful', 'easy', 'normal', 'hard'])
        difficulty.setCurrentText(properties.get('difficulty', 'easy'))
        diff_label = create_labeled_field("Сложность:", "Уровень сложности игры:\npeaceful - монстры не появляются\neasy - легкая сложность\nnormal - средняя сложность\nhard - сложная игра")
        layout.addRow(diff_label, difficulty)

        # Gamemode dropdown 
        gamemode = QtWidgets.QComboBox()
        gamemode.addItems(['survival', 'creative', 'adventure', 'spectator'])
        gamemode.setCurrentText(properties.get('gamemode', 'survival'))
        mode_label = create_labeled_field("Режим игры:", "Режим игры по умолчанию:\nsurvival - выживание\ncreative - творческий режим\nadventure - приключение\nspectator - наблюдатель") 
        layout.addRow(mode_label, gamemode)

        # Save button
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save | 
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )

        def save_properties():
            properties['motd'] = motd_input.text()
            properties['server-port'] = str(port_input.value())
            properties['view-distance'] = str(view_slider.value())
            properties['online-mode'] = str(online_mode.isChecked()).lower()
            properties['hide-online-players'] = str(hide_players.isChecked()).lower()
            properties['pvp'] = str(pvp.isChecked()).lower()
            properties['difficulty'] = difficulty.currentText()
            properties['gamemode'] = gamemode.currentText()

            try:
                with open(properties_path, 'w', encoding='utf-8') as f:
                    for key, value in properties.items():
                        f.write(f"{key}={value}\n")
                dialog.accept()
            except Exception as e:
                QtWidgets.QMessageBox.critical(dialog, "Ошибка", f"Не удалось сохранить настройки:\n{str(e)}")

        btn_box.accepted.connect(save_properties)
        btn_box.rejected.connect(dialog.reject)
        layout.addRow(btn_box)

        dialog.exec()

    def toggle_whitelist(self):
        self.command_input.setText("whitelist on")
        self.send_command()

    def restart_server(self):
        self.stop_server()
        QtCore.QTimer.singleShot(1500, self.start_server)

    def reload_server(self):
        self.command_input.setText("reload")
        self.send_command()

    def tick_freeze(self):
        self.command_input.setText("tick freeze")
        self.send_command()

    def select_server_by_name(self, name):
        self.selected_server = name
        self.update_top_buttons()
        self.update_ip_label()
        self.update_selected_server_label()  # <--- добавлено
        for server_name, _, label, _ in self.server_list_items:
            if server_name == name:
                label.setStyleSheet("padding-left: 4px; background: #cceeff;")
            else:
                label.setStyleSheet("padding-left: 4px;")
        self.on_server_selected()

    def get_selected_server(self):
        return getattr(self, 'selected_server', None)

    def on_server_selected(self):
        self.update_players_list()
        # Здесь можно добавить загрузку игроков для выбранного сервера, если нужно
    
    def show_player_menu(self, pos):
        item = self.players_list.itemAt(pos)
        if not item:
            return
        player_name = item.text()
        menu = QtWidgets.QMenu(self)
        kick_action = menu.addAction("Кикнуть")
        ban_action = menu.addAction("Забанить")
        server_name = self.get_selected_server()
        is_op = False
        is_whitelisted = False

        if server_name:
            ops_path = os.path.join(SERVERS_DIR, server_name, "ops.json")
            whitelist_path = os.path.join(SERVERS_DIR, server_name, "whitelist.json")
            # Проверка OP
            if os.path.exists(ops_path):
                try:
                    with open(ops_path, encoding="utf-8") as f:
                        ops_content = f.read()
                        is_op = re.search(rf'"name"\s*:\s*"{re.escape(player_name)}"', ops_content) is not None
                except Exception:
                    pass
            # Проверка whitelist
            if os.path.exists(whitelist_path):
                try:
                    with open(whitelist_path, encoding="utf-8") as f:
                        whitelist = json.load(f)
                        is_whitelisted = any(entry.get("name") == player_name for entry in whitelist)
                except Exception:
                    pass

        if is_op:
            op_action = menu.addAction("Забрать права администратора")
        else:
            op_action = menu.addAction("Выдать права администратора")

        if is_whitelisted:
            whitelist_action = menu.addAction("Убрать из белого списка")
        else:
            whitelist_action = menu.addAction("Добавить в белый список")

        action = menu.exec(self.players_list.mapToGlobal(pos))

        if action == kick_action:
            self.command_input.setText(f"kick {player_name}")
            self.send_command()

        elif action == ban_action:
            self.command_input.setText(f"ban {player_name}")
            self.send_command()

        elif action == op_action:
            if is_op:
                self.command_input.setText(f"deop {player_name}")
            else:
                self.command_input.setText(f"op {player_name}")
            self.send_command()

        elif action == whitelist_action:
            if is_whitelisted:
                self.command_input.setText(f"whitelist remove {player_name}")
            else:
                self.command_input.setText(f"whitelist add {player_name}")
            self.send_command()

    def show_server_menu(self, pos, server_name, widget):
        menu = QtWidgets.QMenu(self)
        info_action = menu.addAction("Информация о сервере")
        folder_action = menu.addAction("Открыть папку сервера")
        archive_action = menu.addAction("Заархивировать сервер")
        action = menu.exec(widget.mapToGlobal(pos))
        if action == info_action:
            self.show_server_info(server_name)
        elif action == folder_action:
            self.open_server_folder(server_name)
        elif action == archive_action:
            self.archive_server(server_name)

    def archive_server(self, server_name):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Нельзя архивировать запущенный сервер. Сначала остановите его.")
            return
        archive_dir = os.path.join(SERVERS_DIR, "Архив")
        if not os.path.exists(archive_dir):
            os.makedirs(archive_dir)
        server_path = os.path.join(SERVERS_DIR, server_name)
        archive_path = os.path.join(archive_dir, server_name)
        if os.path.exists(archive_path):
            QtWidgets.QMessageBox.warning(self, "Ошибка", f"Сервер {server_name} уже существует в архиве.")
            return
        try:
            os.rename(server_path, archive_path)
            QtWidgets.QMessageBox.information(self, "Успех", f"Сервер {server_name} успешно перемещен в архив.")
            self.load_servers()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось заархивировать сервер {server_name}:\n{str(e)}")

    def show_server_info(self, server_name):
        server_path = os.path.join(SERVERS_DIR, server_name)
        loader_info = "Не удалось определить загрузчик"
        forge_lib_path = os.path.join(server_path, "libraries", "net", "minecraftforge", "forge")
        if os.path.isdir(forge_lib_path):
            versions = os.listdir(forge_lib_path)
            if versions:
                forge_version = versions[0]
                loader_info = f"Forge {forge_version}"
        fabric_lib_path = os.path.join(server_path, "libraries", "net", "fabricmc", "fabric-loader")
        if os.path.isdir(fabric_lib_path):
            versions = os.listdir(fabric_lib_path)
            if versions:
                fabric_version = versions[0]
                jar_files = [f for f in os.listdir(os.path.join(fabric_lib_path, fabric_version)) if f.endswith(".jar")]
                if jar_files:
                    jar_name = jar_files[0]
                    match = re.search(r'fabric-loader-([\d\.]+)\.jar', jar_name)
                    if match:
                        fabric_version_str = match.group(1)
                        loader_info = f"Fabric {fabric_version_str}"
                    else:
                        loader_info = f"Fabric {fabric_version}"
        QtWidgets.QMessageBox.information(
            self,
            "Информация о сервере",
            f"Название сборки: {server_name}\nЗагрузчик: {loader_info}"
        )

    def open_server_folder(self, server_name):
        server_path = os.path.join(SERVERS_DIR, server_name)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(server_path))

    def show_create_server_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Создать сервер")
        layout = QtWidgets.QVBoxLayout(dialog)

        # Create tab widget
        tab_widget = QtWidgets.QTabWidget()
        java_tab = QtWidgets.QWidget()
        bedrock_tab = QtWidgets.QWidget()
        
        # Java tab layout
        java_layout = QtWidgets.QFormLayout(java_tab)
        java_name_edit = QtWidgets.QLineEdit()
        java_layout.addRow("Название сервера:", java_name_edit)
        
        java_loader_combo = QtWidgets.QComboBox()
        java_loader_combo.addItems(["Forge", "Fabric", "Paper"])
        java_layout.addRow("Загрузчик:", java_loader_combo)
        
        java_version_combo = QtWidgets.QComboBox()
        java_version_combo.setEditable(True)
        java_version_combo.setPlaceholderText("например, 1.20.4")
        java_versions = ["1.20.4", "1.20.1", "1.19.4", "1.18.2", "1.17.1", "1.16.5", "1.12.2", "1.8.9"]
        java_version_combo.addItems(java_versions)
        java_layout.addRow("Версия Minecraft:", java_version_combo)

        # Bedrock tab layout
        bedrock_layout = QtWidgets.QFormLayout(bedrock_tab)
        bedrock_name_edit = QtWidgets.QLineEdit()
        bedrock_layout.addRow("Название сервера:", bedrock_name_edit)
        
        # Add tabs
        tab_widget.addTab(java_tab, "Java Edition")
        tab_widget.addTab(bedrock_tab, "Bedrock")
        layout.addWidget(tab_widget)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | 
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(btn_box)

        def write_start_bat(folder, jar_file):
            with open(os.path.join(folder, "start.bat"), "w", encoding="utf-8") as f:
                f.write(f'java -Xmx5G -jar {jar_file} nogui\npause\n')

        def on_accept():
            is_java = tab_widget.currentIndex() == 0
            
            if is_java:
                name = java_name_edit.text().strip()
                loader = java_loader_combo.currentText()
                version = java_version_combo.currentText().strip()
            else:
                name = bedrock_name_edit.text().strip()
                loader = "Bedrock"
                version = "latest"  # For Bedrock we'll always get latest

            if not name:
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Введите название сервера.")
                return

            if is_java and not version:
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Введите версию сервера.")
                return

            server_path = os.path.join(SERVERS_DIR, name)
            if os.path.exists(server_path):
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Сервер с таким именем уже существует.")
                return

            tmp_server_path = server_path + "_tmp"
            if os.path.exists(tmp_server_path):
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Временная папка для установки уже существует. Удалите её вручную.")
                return

            try:
                os.makedirs(tmp_server_path, exist_ok=False)
                jar_file = None

                if loader == "Paper":
                    api_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}"
                    with urllib.request.urlopen(api_url) as resp:
                        data = json.load(resp)
                    builds = data.get("builds", [])
                    if not builds:
                        raise Exception("Не найдены билды Paper для этой версии")
                    build = builds[-1]
                    jar_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{build}/downloads/paper-{version}-{build}.jar"
                    jar_file = "server.jar"
                    jar_path = os.path.join(tmp_server_path, jar_file)
                    urllib.request.urlretrieve(jar_url, jar_path)

                elif loader == "Fabric":
                    fabric_installer_url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/0.11.2/fabric-installer-0.11.2.jar"
                    installer_path = os.path.join(tmp_server_path, "fabric-installer.jar")
                    urllib.request.urlretrieve(fabric_installer_url, installer_path)
                    if not os.path.exists(installer_path):
                        raise Exception(f"Не удалось скачать fabric-installer.jar")
                    
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
                    result = subprocess.run([
                        "java", "-jar", installer_path, "server", "-mcversion", version, "-downloadMinecraft"
                    ], cwd=tmp_server_path, capture_output=True, text=True)

                    if result.returncode != 0:
                        raise Exception(f"Ошибка при установке Fabric:\n{result.stderr}\n{result.stdout}")
                    jar_file = "fabric-server-launch.jar"

                elif loader == "Forge":
                    forge_meta_url = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
                    installer_path = os.path.join(tmp_server_path, "forge-installer.jar")
                    req = urllib.request.Request(forge_meta_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req) as resp:
                        meta = json.load(resp)
                    
                    key = f"{version}-latest"
                    if key not in meta["promos"]:
                        raise Exception(f"Forge не найден для версии {version}")
                    
                    forge_version = meta["promos"][key]
                    full_version = f"{version}-{forge_version}"
                    installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{full_version}/forge-{full_version}-installer.jar"
                    
                    req = urllib.request.Request(installer_url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req) as resp, open(installer_path, "wb") as out_file:
                        out_file.write(resp.read())

                    subprocess.check_call(["java", "-jar", installer_path, "--installServer"], cwd=tmp_server_path)
                    
                    jar_candidates = [f for f in os.listdir(tmp_server_path) 
                                    if f.startswith("forge-") and f.endswith(".jar") 
                                    and "installer" not in f]
                    if jar_candidates:
                        jar_file = jar_candidates[0]
                    else:
                        print("Ошибка: не найден forge-jar после установки")
                        raise Exception("Не найден forge-jar после установки")

                elif loader == "Bedrock":
                    print("Создание Bedrock сервера...")
                    import zipfile
                    
                    # Create progress dialog
                    progress = QtWidgets.QProgressDialog("Скачивание Bedrock Server...", "Отмена", 0, 100, dialog)
                    progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
                    progress.setAutoClose(True)
                    
                    print("Скачивание Bedrock Server...")
                    bedrock_url = get_latest_bedrock_url()
                    zip_path = os.path.join(tmp_server_path, "bedrock-server.zip")
                    
                    # Create network manager for async download
                    manager = QNetworkAccessManager()
                    request = QNetworkRequest(QtCore.QUrl(bedrock_url))
                    
                    # Create file for writing
                    output_file = QtCore.QFile(zip_path)
                    output_file.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                    
                    def handle_finished():
                        output_file.close()
                        extract_files()
                        
                    def handle_progress(bytes_received, bytes_total):
                        if bytes_total > 0:
                            percent = int(bytes_received * 100 / bytes_total)
                            progress.setValue(percent)
                            
                    def handle_ready_read():
                        output_file.write(reply.readAll())
                        
                    def extract_files():
                        progress.setLabelText("Распаковка файлов сервера...")
                        progress.setValue(0)
                        QtWidgets.QApplication.processEvents()
                        
                        print("Распаковка файлов сервера...")
                        with zipfile.ZipFile(zip_path, "r") as zip_ref:
                            total_files = len(zip_ref.namelist())
                            for index, file in enumerate(zip_ref.namelist()):
                                if progress.wasCanceled():
                                    raise Exception("Распаковка отменена пользователем")
                                progress.setValue(int((index / total_files) * 100))
                                zip_ref.extract(file, tmp_server_path)
                                QtWidgets.QApplication.processEvents()
                                
                        print("Очистка временных файлов...")
                        os.remove(zip_path)
                        
                        progress.setValue(100)
                        finish_installation()
                        
                    def finish_installation():
                        os.rename(tmp_server_path, server_path)
                        dialog.accept()
                        self.load_servers()
                    
                    reply = manager.get(request)
                    reply.finished.connect(handle_finished)
                    reply.downloadProgress.connect(handle_progress) 
                    reply.readyRead.connect(handle_ready_read)
                    
                    # Keep reference to prevent garbage collection
                    dialog.reply = reply
                    dialog.manager = manager
                    
                    return # Return early, installation will finish asynchronously

                os.rename(tmp_server_path, server_path)
                dialog.accept()
                self.load_servers()

            except Exception as e:
                import shutil
                shutil.rmtree(tmp_server_path, ignore_errors=True)
                QtWidgets.QMessageBox.critical(dialog, "Ошибка", f"Ошибка при создании сервера: {str(e)}")
                return

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dialog.reject)
        dialog.exec()

   


   

    def toggle_server(self):
        status = self.get_server_status(self.get_selected_server())
        if status == "running":
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        server_name = self.get_selected_server()
        if not server_name:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите сервер для запуска.")
            return
        server_path = os.path.join(SERVERS_DIR, server_name)
        # Найти jar-файл сервера (исключая installer)
        jar_files = [
            f for f in os.listdir(server_path)
            if (f.endswith(".jar") and not f.endswith("installer.jar")) or f == "bedrock_server.exe"
        ]
        if not jar_files:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не найден файл сервера в папке {server_name}")
            return
        jar_file = jar_files[0]
        jar_path = os.path.join(server_path, jar_file)
        if self.process:
            self.process.kill()
            self.process = None

        self.log_output.clear()
        self.process = QtCore.QProcess(self)
        self.process.setWorkingDirectory(server_path)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        if jar_file == "bedrock_server.exe":
            self.process.start(jar_path)  # Используем полный путь!
        else:
            java_path = self.config.get("java_path", "java")
            max_ram_gb = self.config.get("max_ram_gb", 5)
            xms = f"-Xms{max_ram_gb}G"
            xmx = f"-Xmx{max_ram_gb}G"
            self.process.start(java_path, [xms, xmx, "-jar", jar_file, "nogui"])
        


        self.send_command_button.setEnabled(True)
        self.update_status_label("starting")
        self.set_server_status(server_name, "running")
        self.update_top_buttons()

    def stop_server(self):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            try:
                self.process.write(b"stop\n")
                self.process.waitForBytesWritten(1000)
            except Exception:
                pass
            self.process.kill()
            self.process = None
            self.send_command_button.setEnabled(False)
            if self.selected_server:
                self.set_server_status(self.selected_server, "stopped")
                self.update_status_label("stopped")
            self.update_top_buttons()

    def process_finished(self):
        self.log_output.append("\nСервер завершил работу.")
        self.send_command_button.setEnabled(False)
        if self.process and self.process.exitStatus() == QtCore.QProcess.ExitStatus.CrashExit:
            self.set_server_status(self.selected_server, "error")
            self.log_output.append("\nСервер завершил работу с ошибкой (краш).")
            self.update_status_label("stopped")
            QtWidgets.QMessageBox.critical(self, "Краш сервера", "Сервер завершился с ошибкой (краш). Проверьте логи!")
        else:
            self.set_server_status(self.selected_server, "stopped")
            self.update_status_label("stopped")
        self.update_top_buttons()

    def handle_stdout(self):
        if self.process:
            data = self.process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
            self.log_output.append(data)
            # Проверка на успешный запуск сервера
            if "Done (" in data or "For help, type \"help\"" in data:
                self.update_status_label("running")
                self.set_server_status(self.get_selected_server(), "running")
            # --- Новый код для подсчёта игроков ---
            for line in data.splitlines():
                # For Java Edition
                join_match = re.search(r": (\w+) joined the game", line)
                left_match = re.search(r": (\w+) left the game", line)
                # For Bedrock Edition
                bedrock_join = re.search(r"Player connected: (\w+)", line)
                bedrock_left = re.search(r"Player disconnected: (\w+)", line) 
                if join_match:
                    player = join_match.group(1)
                    self.online_players.add(player)
                    self.update_players_list()
                elif left_match:
                    player = left_match.group(1)
                    self.online_players.discard(player)
                    self.update_players_list()
                elif bedrock_join:
                    player = bedrock_join.group(1)
                    self.online_players.add(player)
                    self.update_players_list()
                elif bedrock_left:
                    player = bedrock_left.group(1)
                    self.online_players.discard(player)
                    self.update_players_list()

    
    def handle_stderr(self):
        if self.process:
            data = self.process.readAllStandardError().data().decode("utf-8", errors="ignore")
            self.log_output.append(data)
            # Проверка на ошибки запуска или краша
            if "Exception" in data or "Error" in data or "FAILED" in data or "Caused by" in data:
                self.update_status_label(self, "error")
                self.set_server_status(self.get_selected_server(), "error")

    def update_players_list(self):
        self.players_list.clear()
        for player in sorted(self.online_players):
            self.players_list.addItem(player)

    def update_status_label(self, status=None, message=None):
        if status is None:
            status = self.get_server_status(self.get_selected_server())
        if status == "running":
            self.status_label.setText("Статус: Работает")
            self.status_label.setStyleSheet("font-weight: bold; color: #4caf50; padding: 4px;")
        elif status == "error":
            self.status_label.setText(f"Статус: Ошибка запуска{f' ({message})' if message else ''}")
            self.status_label.setStyleSheet("font-weight: bold; color: #f44336; padding: 4px;")
        elif status == "stopped":
            self.status_label.setText("Статус: Остановлен")
            self.status_label.setStyleSheet("font-weight: bold; color: #888; padding: 4px;")
        elif status == "starting":
            self.status_label.setText("Статус: Запуск...")
            self.status_label.setStyleSheet("font-weight: bold; color: #5da130; padding: 4px;")
        elif status == "crashed":
            self.status_label.setText("Статус: Краш")
            self.status_label.setStyleSheet("font-weight: bold; color: #ff2400; padding: 4px;")
        else:
            self.status_label.setText(f"Статус: {status}")
            self.status_label.setStyleSheet("font-weight: bold; color: #888; padding: 4px;")

    # Вызовите update_status_label в нужных местах:
    # - после выбора сервера
    # - после запуска/остановки/краша
    def send_command(self):
        cmd = self.command_input.text().strip()
        if not cmd or not self.process or self.process.state() != QtCore.QProcess.ProcessState.Running:
            return
        self.process.write((cmd + "\n").encode("utf-8"))
        self.command_input.clear()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = ServerManager()
    window.show()
    sys.exit(app.exec())
