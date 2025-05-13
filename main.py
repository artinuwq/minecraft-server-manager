import os
from PyQt6 import QtWidgets, QtCore, QtGui
import sys
import re
from config import SERVERS_DIR # Укажи путь к папке с серверами

def list_servers():
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
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))

        # Основной горизонтальный layout
        main_layout = QtWidgets.QHBoxLayout(self)

        # Левая панель (Список серверов, кнопки, список игроков)
        left_panel = QtWidgets.QVBoxLayout()

        # Список серверов с кнопками "инфо" и "папка"
        left_panel.addWidget(QtWidgets.QLabel("Серверы:"))
        self.server_list_widget = QtWidgets.QWidget()
        self.server_list_layout = QtWidgets.QVBoxLayout(self.server_list_widget)
        self.server_list_layout.setContentsMargins(0, 0, 0, 0)
        self.server_list_layout.setSpacing(2)
        self.server_list_items = []

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
        right_panel.addWidget(QtWidgets.QLabel("Консоль:"))
        self.log_output = QtWidgets.QTextEdit()
        self.log_output.setReadOnly(True)
        right_panel.addWidget(self.log_output, stretch=1)

        # Удаляем лишние пустые строки между сообщениями в консоли
        def append_log(text):
            # Удаляем двойные пустые строки
            cleaned = re.sub(r'\n{3,}', '\n\n', text)
            self.log_output.moveCursor(QtGui.QTextCursor.End)
            self.log_output.insertPlainText(cleaned)
            self.log_output.moveCursor(QtGui.QTextCursor.End)

        self.append_log = append_log

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

        # Сигналы
        self.command_input.returnPressed.connect(self.send_command)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.send_command_button.clicked.connect(self.send_command)
        self.process = None

        self.selected_server = None
        self.load_servers()
    
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

            # Кнопка инфо
            info_btn = QtWidgets.QToolButton()
            info_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation))
            info_btn.setFixedSize(20, 20)
            info_btn.setToolTip("Информация о сервере")
            info_btn.clicked.connect(lambda _, name=server_name: self.show_server_info(name))

            # Кнопка папка
            folder_btn = QtWidgets.QToolButton()
            folder_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DirOpenIcon))
            folder_btn.setFixedSize(20, 20)
            folder_btn.setToolTip("Открыть папку сервера")
            folder_btn.clicked.connect(lambda _, name=server_name: self.open_server_folder(name))

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

            row_layout.addWidget(info_btn)
            row_layout.addWidget(folder_btn)
            row_layout.addWidget(label)
            row_layout.addStretch(1)
            self.server_list_layout.addWidget(row_widget)
            self.server_list_items.append((server_name, row_widget, label))

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
        for server_name, _, label in self.server_list_items:
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

    def stop_server(self):
        if self.process and self.process.state() == QtCore.QProcess.ProcessState.Running:
            try:
                self.process.write(b"stop\n")
                self.process.waitForBytesWritten(1000)
            except Exception:
                pass
            self.process.kill()
            self.process = None
            self.log_output.append("\nСервер остановлен.")
            self.stop_button.setEnabled(False)
            self.send_command_button.setEnabled(False)

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