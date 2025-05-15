import json, os, sys
from PyQt6 import QtWidgets, QtCore, QtGui
import re
import zipfile
import shutil
import subprocess, requests
# config import SERVERS_DIR # Укажи путь к папке с серверами


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
SERVERS_DIR = None
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    # Значение по умолчанию
    return {"servers_dir": os.path.abspath("servers")}

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def list_servers():
    global SERVERS_DIR
    if not SERVERS_DIR or not os.path.exists(SERVERS_DIR):
        os.makedirs(SERVERS_DIR, exist_ok=True)
        return []
    return [
        name for name in os.listdir(SERVERS_DIR)
        if os.path.isdir(os.path.join(SERVERS_DIR, name))
        and os.path.isfile(os.path.join(SERVERS_DIR, name, 'eula.txt'))
    ]
class ServerManager(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft Server Manager")
        self.resize(1400, 800)
        # Установить иконку окна (замени путь на свой файл PNG/ICO)
        icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # Сначала загружаем конфиг!
        self.config = load_config()
        global SERVERS_DIR
        if not self.config.get("servers_dir") or not os.path.isdir(self.config.get("servers_dir")):
            self.choose_servers_dir_dialog()
        SERVERS_DIR = self.config.get("servers_dir", os.path.abspath("servers"))
        # Основной горизонтальный layout
        main_layout = QtWidgets.QHBoxLayout(self)

        # Левая панель (Список серверов, кнопки, список игроков)
        left_panel = QtWidgets.QVBoxLayout()

        # Список серверов
        left_panel.addWidget(QtWidgets.QLabel("Серверы:"))
        self.server_list_widget = QtWidgets.QWidget()
        self.server_list_layout = QtWidgets.QVBoxLayout(self.server_list_widget)
        self.server_list_layout.setContentsMargins(0, 0, 0, 0)
        self.server_list_layout.setSpacing(2)
        self.server_list_items = []

        # Кнопка "Создать сервер"
        self.create_server_button = QtWidgets.QPushButton("Создать сервер")
        self.create_server_button.clicked.connect(self.show_create_server_dialog)
        left_panel.addWidget(self.create_server_button)
        left_panel.addWidget(self.server_list_widget)

        # Кнопки старт/стоп
        btn_layout = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("Запустить")
        self.stop_button = QtWidgets.QPushButton("Стоп")
        self.stop_button.setEnabled(False)
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.stop_button)
        left_panel.addLayout(btn_layout)

        # Список игроков
        left_panel.addWidget(QtWidgets.QLabel("Игроки:"))
        self.players_list = QtWidgets.QListWidget()
        left_panel.addWidget(self.players_list)

        # Контекстное меню для игроков
        self.players_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.players_list.customContextMenuRequested.connect(self.show_player_menu)

        # Правая панель (Консоль и ввод команд)
        right_panel = QtWidgets.QVBoxLayout()

        # Кнопка "Настройки" (справа сверху)
        self.settings_button = QtWidgets.QPushButton("⚙ Настройки")
        self.settings_button.setFixedWidth(120)
        self.settings_button.clicked.connect(self.show_settings_dialog)

        # Обертка для выравнивания кнопки вправо
        settings_layout = QtWidgets.QHBoxLayout()
        settings_layout.addStretch(1)
        settings_layout.addWidget(self.settings_button)
        right_panel.addLayout(settings_layout)

        right_panel.addWidget(QtWidgets.QLabel("Консоль:"))
        self.log_output = QtWidgets.QTextEdit()
        self.log_output.setReadOnly(True)
        right_panel.addWidget(self.log_output, stretch=1)

        # Ввод команд
        cmd_layout = QtWidgets.QHBoxLayout()
        self.command_input = QtWidgets.QLineEdit()
        self.command_input.setPlaceholderText("Введите команду для сервера")
        self.send_command_button = QtWidgets.QPushButton("Отправить")
        self.send_command_button.setEnabled(False)
        cmd_layout.addWidget(self.command_input)
        cmd_layout.addWidget(self.send_command_button)
        right_panel.addLayout(cmd_layout)

        # Добавляем панели в основной layout
        main_layout.addLayout(left_panel, stretch=0)
        main_layout.addLayout(right_panel, stretch=1)
        self.setLayout(main_layout)

        # Сигналы
        self.command_input.returnPressed.connect(self.send_command)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.send_command_button.clicked.connect(self.send_command)
        self.process = None
        self.selected_server = None

        # Для статусов серверов
        self.server_status = {}  # server_name: "running"/"error"/"stopped"

        self.load_servers()
    

    def choose_servers_dir_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Выберите папку для серверов")
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel("Выберите, где будут храниться ваши сервера Minecraft:")
        layout.addWidget(label)

        btn_create = QtWidgets.QPushButton("Создать новую папку рядом с программой")
        btn_choose = QtWidgets.QPushButton("Выбрать существующую папку")
        layout.addWidget(btn_create)
        layout.addWidget(btn_choose)

        def create_new():
            new_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "servers"))
            os.makedirs(new_dir, exist_ok=True)
            self.config["servers_dir"] = new_dir
            save_config(self.config)
            dialog.accept()

        def choose_existing():
            folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Выберите папку для серверов")
            if folder:
                self.config["servers_dir"] = folder
                save_config(self.config)
                dialog.accept()

        btn_create.clicked.connect(create_new)
        btn_choose.clicked.connect(choose_existing)

        dialog.exec()

    def get_server_status(self, server_name):
        # Если сервер сейчас выбран и процесс запущен
        if hasattr(self, 'selected_server') and self.selected_server == server_name and self.process:
            if self.process.state() == QtCore.QProcess.ProcessState.Running:
                return "running"
            elif self.process.exitStatus() == QtCore.QProcess.ExitStatus.CrashExit:
                return "error"
            else:
                return "stopped"
        # Если есть сохранённый статус
        return self.server_status.get(server_name, "stopped")
    
    def show_settings_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Настройки")
        dialog.setFixedSize(500, 200)
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

        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(btn_box)

        def on_accept():
            new_dir = dir_edit.text().strip()
            if not new_dir or not os.path.isdir(new_dir):
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Укажите существующую папку.")
                return
            self.config["servers_dir"] = new_dir
            save_config(self.config)
            global SERVERS_DIR
            SERVERS_DIR = new_dir
            self.load_servers()
            dialog.accept()
        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dialog.reject)
        dialog.exec()

    def set_server_status(self, server_name, status):
        self.server_status[server_name] = status
        self.load_servers()

    def make_status_icon(self, status):
        # Возвращает QPixmap с кружком нужного цвета
        color = {
            "running": "#4caf50",   # Зеленый
            "error": "#f44336",     # Красный
            "stopped": "#bdbdbd"    # Серый
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
        # Очищаем старые элементы
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

            # Индикатор статуса
            status = self.get_server_status(server_name)
            icon_label = QtWidgets.QLabel()
            icon_label.setPixmap(self.make_status_icon(status).pixmap(16, 16))
            row_layout.addWidget(icon_label)

            # Текст сервера
            label = QtWidgets.QLabel(server_name)
            label.setMinimumHeight(20)
            label.setStyleSheet("padding-left: 4px;")
            label.mousePressEvent = lambda event, name=server_name: self.select_server_by_name(name)

            # Контекстное меню по ПКМ на строке сервера
            row_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            row_widget.customContextMenuRequested.connect(
                lambda pos, name=server_name, widget=row_widget: self.show_server_menu(pos, name, widget)
            )

            row_layout.addWidget(label)
            row_layout.addStretch(1)
            self.server_list_layout.addWidget(row_widget)
            self.server_list_items.append((server_name, row_widget, label, icon_label))

        self.players_list.clear()

    def start_server(self):
        server_name = self.get_selected_server()
        if not server_name:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите сервер для запуска.")
            return
        server_path = os.path.join(SERVERS_DIR, server_name)
        bat_file = os.path.join(server_path, 'start.bat')
        if not os.path.exists(bat_file):
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Файл start.bat не найден для сервера {server_name}")
            return

        if self.process:
            self.process.kill()
            self.process = None

        self.log_output.clear()
        self.process = QtCore.QProcess(self)
        self.process.setWorkingDirectory(server_path)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)
        self.process.start('cmd.exe', ['/c', bat_file])

        self.stop_button.setEnabled(True)
        self.send_command_button.setEnabled(True)

        # Установить статус "running"
        self.set_server_status(server_name)

    def stop_server(self):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            try:
                self.process.write(b"stop\n")
                self.process.waitForBytesWritten(1000)
            except Exception:
                pass
            self.process.kill()
            self.process = None
            self.stop_button.setEnabled(False)
            self.send_command_button.setEnabled(False)
            # Установить статус "stopped"
            if self.selected_server:
                self.set_server_status(self.selected_server, "stopped")

    def process_finished(self):
        self.log_output.append("\nСервер завершил работу.")
        self.stop_button.setEnabled(False)
        self.send_command_button.setEnabled(False)
        # Проверяем exitCode

        if self.process and self.process.exitStatus() == QtCore.QProcess.ExitStatus.CrashExit:
            self.set_server_status(self.selected_server, "error")
            self.log_output.append("\nСервер завершил работу с ошибкой (краш).")
            QtWidgets.QMessageBox.critical(self, "Краш сервера", "Сервер завершился с ошибкой (краш). Проверьте логи!")
        else:
            self.set_server_status(self.selected_server, "stopped")



    def show_player_menu(self, pos):
        item = self.players_list.itemAt(pos)
        if not item:
            return
        player_name = item.text()
        menu = QtWidgets.QMenu(self)
        kick_action = menu.addAction("Кикнуть")
        ban_action = menu.addAction("Забанить")

        # Проверяем, является ли игрок администратором (есть ли в ops.txt)
        server_name = self.get_selected_server()
        is_op = False
        if server_name:
            ops_path = os.path.join(SERVERS_DIR, server_name, "ops.json")
            if os.path.exists(ops_path):
                try:
                    with open(ops_path, encoding="utf-8") as f:
                        ops_content = f.read()
                        # Проверяем по имени (точное совпадение)
                        is_op = re.search(rf'"name"\s*:\s*"{re.escape(player_name)}"', ops_content) is not None
                except Exception:
                    pass

        if is_op:
            op_action = menu.addAction("Забрать права администратора")
        else:
            op_action = menu.addAction("Выдать права администратора")

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

        self.players_list.clear()    
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
            self.load_servers()  # Обновляем список серверов
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Не удалось заархивировать сервер {server_name}:\n{str(e)}")

    def select_server_by_name(self, name):
        self.selected_server = name
        # Подсветка выбранного
        for server_name, _, label, _ in self.server_list_items:
            if server_name == name:
                label.setStyleSheet("padding-left: 4px; background: #cceeff;")
            else:
                label.setStyleSheet("padding-left: 4px;")
        self.on_server_selected()

    def get_selected_server(self):
        return getattr(self, 'selected_server', None)

    def on_server_selected(self):
        self.players_list.clear()
        # Здесь можно добавить загрузку игроков для выбранного сервера, если нужно
        
    def show_server_info(self, server_name):
        server_path = os.path.join(SERVERS_DIR, server_name)
        loader_info = "Не удалось определить загрузчик"

        # Forge
        forge_lib_path = os.path.join(server_path, "libraries", "net", "minecraftforge", "forge")
        if os.path.isdir(forge_lib_path):
            versions = os.listdir(forge_lib_path)
            if versions:
                # Берём первую найденную версию (обычно одна)
                forge_version = versions[0]
                loader_info = f"Forge {forge_version}"

        # Fabric
        fabric_lib_path = os.path.join(server_path, "libraries", "net", "fabricmc", "fabric-loader")
        if os.path.isdir(fabric_lib_path):
            versions = os.listdir(fabric_lib_path)
            if versions:
                # Берём первую найденную версию (обычно одна)
                fabric_version = versions[0]
                # Ищем jar-файл
                jar_files = [f for f in os.listdir(os.path.join(fabric_lib_path, fabric_version)) if f.endswith(".jar")]
                if jar_files:
                    # Имя файла вида fabric-loader-0.16.9.jar
                    jar_name = jar_files[0]
                    # Извлекаем версию
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
        layout = QtWidgets.QFormLayout(dialog)

        # Название сервера
        name_edit = QtWidgets.QLineEdit()
        layout.addRow("Название сервера:", name_edit)

        # Выбор загрузчика
        loader_combo = QtWidgets.QComboBox()
        loader_combo.addItems(["Forge", "Fabric", "Paper"])
        layout.addRow("Загрузчик:", loader_combo)
        # Выбор версии сервера (ComboBox вместо LineEdit)

        version_combo = QtWidgets.QComboBox()
        version_combo.setEditable(True)
        version_combo.setPlaceholderText("например, 1.20.4")

        # Заполняем список популярных версий (можно расширить)
        common_versions = [
            "1.20.4", "1.20.1", "1.19.4", "1.18.2", "1.17.1", "1.16.5", "1.12.2", "1.8.9"
        ]
        version_combo.addItems(common_versions)
        layout.addRow("Версия Minecraft:", version_combo)

        # Кнопки
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        layout.addRow(btn_box)

        def on_accept():
            name = name_edit.text().strip()
            loader = loader_combo.currentText()
            version = version_combo.currentText().strip()
            if not name:
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Введите название сервера.")
                return
            if not version:
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Введите версию сервера.")
                return
            server_path = os.path.join(SERVERS_DIR, name)
            if os.path.exists(server_path):
                QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Сервер с таким именем уже существует.")
                return
            os.makedirs(server_path, exist_ok=True)

            # Скачиваем и устанавливаем сервер
            try:
                import urllib.request

                if loader == "Paper":
                    # Получаем билд PaperMC
                    api_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}"
                    with urllib.request.urlopen(api_url) as resp:
                        data = json.load(resp)
                    builds = data.get("builds", [])
                    if not builds:
                        raise Exception("Не найдены билды Paper для этой версии")
                    build = builds[-1]
                    jar_url = f"https://api.papermc.io/v2/projects/paper/versions/{version}/builds/{build}/downloads/paper-{version}-{build}.jar"
                    jar_path = os.path.join(server_path, "server.jar")
                    urllib.request.urlretrieve(jar_url, jar_path)
                    # Создаём start.bat
                    with open(os.path.join(server_path, "start.bat"), "w", encoding="utf-8") as f:
                        f.write('java -Xmx4G -jar server.jar nogui\npause\n')

                elif loader == "Fabric":
                    # Скачиваем fabric installer
                    fabric_installer_url = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.0/fabric-installer-1.0.0.jar"
                    installer_path = os.path.join(server_path, "fabric-installer.jar")
                    urllib.request.urlretrieve(fabric_installer_url, installer_path)
                    # Запускаем установщик
                    subprocess.check_call([
                        sys.executable, "-m", "pip", "install", "requests"
                    ])
                    subprocess.check_call([
                        "java", "-jar", installer_path, "server", "-mcversion", version, "-downloadMinecraft"
                    ], cwd=server_path)
                    # Создаём start.bat
                    with open(os.path.join(server_path, "start.bat"), "w", encoding="utf-8") as f:
                        f.write('java -Xmx4G -jar fabric-server-launch.jar nogui\npause\n')
                elif loader == "Forge":
                    # Получаем ссылку на Forge installer
                    forge_meta_url = f"https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
                    meta = requests.get(forge_meta_url).json()
                    key = f"{version}-recommended"
                    if key not in meta["promos"]:
                        QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Не найдена рекомендуемая версия Forge для этой версии Minecraft.")
                        shutil.rmtree(server_path)
                        return
                    forge_version = meta["promos"][key]
                    forge_installer_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{forge_version}/forge-{forge_version}-installer.jar"
                    installer_path = os.path.join(server_path, "forge-installer.jar")
                    urllib.request.urlretrieve(forge_installer_url, installer_path)
                    # Запускаем установщик
                    subprocess.check_call([
                        "java", "-jar", installer_path, "--installServer"
                    ], cwd=server_path)
                    # Находим forge-*-universal.jar
                    jars = [f for f in os.listdir(server_path) if f.startswith("forge-") and f.endswith(".jar") and "installer" not in f]
                    if jars:
                        jar_name = jars[0]
                        with open(os.path.join(server_path, "start.bat"), "w", encoding="utf-8") as f:
                            f.write(f'java -Xmx4G -jar {jar_name} nogui\npause\n')
                    else:
                        QtWidgets.QMessageBox.warning(dialog, "Ошибка", "Не удалось найти forge jar после установки.")
                        shutil.rmtree(server_path)
                        return
                # Создаём eula.txt
                with open(os.path.join(server_path, "eula.txt"), "w", encoding="utf-8") as f:
                    f.write("eula=true\n")
                QtWidgets.QMessageBox.information(dialog, "Успех", "Сервер успешно создан!")
            except Exception as e:
                QtWidgets.QMessageBox.critical(dialog, "Ошибка", f"Ошибка при создании сервера:\n{e}")
                shutil.rmtree(server_path)
                return

            self.load_servers()
            dialog.accept()
           

            self.load_servers()
            dialog.accept()

        btn_box.accepted.connect(on_accept)
        btn_box.rejected.connect(dialog.reject)
        dialog.exec()


    
    def start_server(self):
        server_name = self.get_selected_server()
        if not server_name:
            QtWidgets.QMessageBox.warning(self, "Ошибка", "Выберите сервер для запуска.")
            return
        server_path = os.path.join(SERVERS_DIR, server_name)
        bat_file = os.path.join(server_path, 'start.bat')
        if not os.path.exists(bat_file):
            QtWidgets.QMessageBox.critical(self, "Ошибка", f"Файл start.bat не найден для сервера {server_name}")
            return

        if self.process:
            self.process.kill()
            self.process = None

        self.log_output.clear()
        self.process = QtCore.QProcess(self)
        self.process.setWorkingDirectory(server_path)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)        
        self.process.start('cmd.exe', ['/c', bat_file])

        self.stop_button.setEnabled(True)
        self.send_command_button.setEnabled(True)
        
        # Установить статус "running"
        self.set_server_status(server_name, "running")

    def stop_server(self):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            try:
                self.process.write(b"stop\n")
                self.process.waitForBytesWritten(1000)
            except Exception:
                pass
            self.process.kill()
            self.process = None
            self.stop_button.setEnabled(False)
            self.send_command_button.setEnabled(False)
            # Установить статус "stopped"
            if self.selected_server:
                self.set_server_status(self.selected_server, "stopped")

    def send_command(self):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            cmd = self.command_input.text().strip()
            if cmd:
                try:
                    self.process.write((cmd + '\n').encode('utf-8'))
                    self.process.waitForBytesWritten(1000)
                except Exception:
                    QtWidgets.QMessageBox.warning(self, "Ошибка", "Не удалось отправить команду.")
                self.command_input.clear()



    def handle_stdout(self):
        if not self.process:
            return
        data = self.process.readAllStandardOutput().data().decode('cp866', errors='replace')
        self.log_output.append(data)
        self.update_players_list(data)



    def handle_stderr(self):
        data = self.process.readAllStandardError().data().decode('cp866', errors='replace')
        self.log_output.append(data)



    def process_finished(self):
        self.log_output.append("\nСервер завершил работу.")
        self.stop_button.setEnabled(False)
        self.send_command_button.setEnabled(False)



    def update_players_list(self, log_data):
        # Отслеживаем вход и выход игроков по сообщениям "* joined the game" и "* left the game"
        joined = re.findall(r'(\w+)\s+joined the game', log_data)
        left = re.findall(r'(\w+)\s+left the game', log_data)

        # Используем set для хранения текущих игроков
        if not hasattr(self, '_current_players'):
            self._current_players = set()

        for player in joined:
            self._current_players.add(player)
        for player in left:
            self._current_players.discard(player)

        self.players_list.clear()
        self.players_list.addItems(sorted(self._current_players))






    def closeEvent(self, event):
        if self.process:
            if self.process.state() == QtCore.QProcess.ProcessState.Running:
                try:
                    self.process.write(b"stop\n")
                    self.process.waitForBytesWritten(1000)
                except Exception:
                    pass
                self.process.kill()
            self.process = None
        event.accept()




def main():
    app = QtWidgets.QApplication(sys.argv)
    window = ServerManager()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()