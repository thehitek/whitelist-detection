import sys
import os
import subprocess
import ipaddress
from netaddr import IPSet, IPNetwork, cidr_merge

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QProgressBar,
    QLabel,
    QFileDialog,
    QTabWidget,
    QCheckBox,
    QLineEdit,
)
from PySide6.QtCore import QObject, QThread, Signal, Slot, Qt
from PySide6.QtGui import QFont


# ===================================
# Worker для пинга
# ===================================
class PingWorker(QObject):
    progress = Signal(int)
    result = Signal(str, bool)
    finished = Signal()

    def __init__(self, addresses, check_all_ips=False):
        super().__init__()
        self.addresses = addresses
        self.total = len(addresses)
        self.running = True
        self.check_all_ips = check_all_ips

    def stop(self):
        self.running = False

    @Slot()
    def run(self):
        processed = 0

        for address in self.addresses:
            if not self.running:
                break

            is_alive = self.ping_address(address)
            self.result.emit(address, is_alive)

            processed += 1
            progress = int((processed / self.total) * 100)
            self.progress.emit(progress)

        self.finished.emit()

    def ping_address(self, address):
        try:
            is_win = sys.platform.startswith("win")
            if "/" in address and not self.check_all_ips:
                network = ipaddress.ip_network(address, strict=False)
                test_ip = str(network.network_address)
                return self._ping_one(test_ip, is_win)
            elif "/" in address and self.check_all_ips:
                network = ipaddress.ip_network(address, strict=False)
                for ip in network.hosts():
                    if not self.running:
                        return False
                    if self._ping_one(str(ip), is_win):
                        return True
                return False
            else:
                return self._ping_one(address, is_win)
        except Exception:
            return False

    def _ping_one(self, ip, is_windows):
        if is_windows:
            cmd = ["ping", "-n", "2", "-w", "2000", ip]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return "TTL=" in result.stdout
        else:
            cmd = ["ping", "-c", "1", "-w", "2", ip]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.returncode == 0


# ===================================
# Worker для вычисления минимальных подсетей
# ===================================
class SubnetWorker(QObject):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, alive_addresses):
        super().__init__()
        self.alive_addresses = alive_addresses

    @Slot()
    def run(self):
        try:
            ip_list = []
            for addr in self.alive_addresses:
                if "/" in addr:
                    try:
                        net = ipaddress.ip_network(addr, strict=False)
                        hosts = list(net.hosts())
                        ip_list.extend([str(h) for h in hosts[:256]])
                    except Exception:
                        pass
                else:
                    try:
                        ipaddress.ip_address(addr)
                        ip_list.append(addr)
                    except ValueError:
                        try:
                            res = subprocess.run(
                                ["nslookup", addr],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                            )
                            for line in res.stdout.splitlines():
                                if "Address:" in line and not line.strip().endswith(
                                    "#53"
                                ):
                                    ip_list.append(line.split("Address:")[-1].strip())
                        except Exception:
                            pass

            if ip_list:
                ip_set = IPSet(ip_list)
                nets = list(ip_set.iter_cidrs())
                minimal = cidr_merge(nets)
                self.finished.emit([str(n) for n in minimal])
            else:
                self.finished.emit([])
        except Exception as e:
            self.error.emit(str(e))


# ===================================
# Главное окно
# ===================================
class WhitelistChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Проверка Whitelist — Russia Mobile Internet")
        self.setGeometry(100, 100, 1200, 800)

        self.addresses = []
        self.alive = []
        self.check_all_ips = False
        self.minimal_subnets = []

        self.init_ui()
        self.load_minimal_subnets()

    def init_ui(self):
        main = QWidget()
        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.load_button = QPushButton("Загрузить данные из репозитория")
        self.load_button.clicked.connect(self.load_from_repo)

        self.start_button = QPushButton("Начать проверку")
        self.start_button.clicked.connect(self.start_check)
        self.start_button.setEnabled(False)

        self.stop_button = QPushButton("Остановить")
        self.stop_button.clicked.connect(self.stop_check)
        self.stop_button.setEnabled(False)

        self.export_button = QPushButton("Экспорт результатов")
        self.export_button.clicked.connect(self.export_results)
        self.export_button.setEnabled(False)

        self.check_cb = QCheckBox("Проверять все IP в подсетях")
        self.check_cb.stateChanged.connect(self.toggle_mode)

        btn_layout.addWidget(self.load_button)
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.stop_button)
        btn_layout.addWidget(self.export_button)
        btn_layout.addWidget(self.check_cb)

        self.progress_bar = QProgressBar()
        self.status_label = QLabel("Готов к работе")

        self.tabs = QTabWidget()
        self.ping_txt = QTextEdit()
        self.ping_txt.setReadOnly(True)
        self.ping_txt.setFont(QFont("Courier New", 9))

        self.subnet_txt = QTextEdit()
        self.subnet_txt.setReadOnly(True)
        self.subnet_txt.setFont(QFont("Courier New", 9))

        self.ip_input = QLineEdit()
        self.ip_check_btn = QPushButton("Проверить")
        self.ip_check_btn.clicked.connect(self.check_ip)

        self.ip_result = QTextEdit()
        self.ip_result.setReadOnly(True)
        self.ip_result.setMaximumHeight(200)

        ip_layout = QHBoxLayout()
        ip_layout.addWidget(QLabel("IP-адрес:"))
        ip_layout.addWidget(self.ip_input)
        ip_layout.addWidget(self.ip_check_btn)

        ip_widget = QWidget()
        v = QVBoxLayout()
        v.addLayout(ip_layout)
        v.addWidget(QLabel("Результат:"))
        v.addWidget(self.ip_result)
        ip_widget.setLayout(v)

        self.tabs.addTab(self.ping_txt, "Результаты пинга")
        self.tabs.addTab(self.subnet_txt, "Минимальные подсети")
        self.tabs.addTab(ip_widget, "Проверка IP")

        layout.addLayout(btn_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.tabs)

        main.setLayout(layout)
        self.setCentralWidget(main)

    def toggle_mode(self, state):
        self.check_all_ips = state == Qt.Checked

    def load_minimal_subnets(self):
        path = os.path.join(os.path.dirname(__file__), "minimal_subnets.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.minimal_subnets = [
                    l.strip() for l in f if l.strip() and not l.startswith("#")
                ]

    def check_ip(self):
        ip = self.ip_input.text().strip()
        if not ip:
            self.ip_result.setText("Введите IP-адрес")
            return
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            self.ip_result.setText("Неверный IP-адрес")
            return

        matches = [
            s
            for s in self.minimal_subnets
            if addr in ipaddress.ip_network(s, strict=False)
        ]
        if matches:
            self.ip_result.setText("\n".join(f"✓ {m}" for m in matches))
        else:
            self.ip_result.setText("Не принадлежит подсетям")

    def load_from_repo(self):
        self.status_label.setText("Загрузка данных...")
        repo_dir = os.path.join(
            os.path.dirname(__file__), "russia-mobile-internet-whitelist"
        )
        if not os.path.exists(repo_dir):
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "https://github.com/hxehex/russia-mobile-internet-whitelist.git",
                        repo_dir,
                    ],
                    check=True,
                )
            except Exception as e:
                self.status_label.setText(f"Ошибка: {e}")
                return

        self.addresses = []
        ip_file = os.path.join(repo_dir, "ipwhitelist.txt")
        if os.path.exists(ip_file):
            with open(ip_file, "r", encoding="utf-8") as f:
                ips = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            try:
                nets = cidr_merge([IPNetwork(i) for i in ips])
                self.addresses.extend(str(n) for n in nets)
            except Exception:
                self.addresses.extend(ips)

        domain_file = os.path.join(repo_dir, "whitelist.txt")
        if os.path.exists(domain_file):
            with open(domain_file, "r", encoding="utf-8") as f:
                self.addresses.extend(
                    l.strip() for l in f if l.strip() and not l.startswith("#")
                )

        self.status_label.setText(f"Загружено {len(self.addresses)} адресов")
        self.start_button.setEnabled(True)

    def start_check(self):
        if not self.addresses:
            self.status_label.setText("Сначала загрузите данные")
            return

        self.alive = []
        self.ping_txt.clear()
        self.subnet_txt.clear()
        self.progress_bar.setValue(0)

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.ping_thread = QThread()
        self.ping_worker = PingWorker(self.addresses, self.check_all_ips)
        self.ping_worker.moveToThread(self.ping_thread)

        self.ping_thread.started.connect(self.ping_worker.run)
        self.ping_worker.progress.connect(self.progress_bar.setValue)
        self.ping_worker.result.connect(self.on_ping_result)
        self.ping_worker.finished.connect(self.on_ping_finished)

        self.ping_worker.finished.connect(self.ping_thread.quit)
        self.ping_worker.finished.connect(self.ping_worker.deleteLater)
        self.ping_thread.finished.connect(self.ping_thread.deleteLater)

        self.ping_thread.start()

    def stop_check(self):
        if hasattr(self, "ping_worker"):
            self.ping_worker.stop()

    def on_ping_result(self, addr, alive):
        if alive:
            self.alive.append(addr)
            self.ping_txt.append(f"✓ {addr}")
        else:
            self.ping_txt.append(f"✗ {addr}")

    def on_ping_finished(self):
        self.stop_button.setEnabled(False)
        self.export_button.setEnabled(True)
        self.status_label.setText(f"Проверка завершена — {len(self.alive)} доступно")
        self.start_button.setEnabled(True)

        self.calc_thread = QThread()
        self.calc_worker = SubnetWorker(self.alive)
        self.calc_worker.moveToThread(self.calc_thread)

        self.calc_thread.started.connect(self.calc_worker.run)
        self.calc_worker.finished.connect(self.on_subnets_ready)
        self.calc_worker.error.connect(self.on_subnets_error)

        self.calc_worker.finished.connect(self.calc_thread.quit)
        self.calc_worker.finished.connect(self.calc_worker.deleteLater)
        self.calc_thread.finished.connect(self.calc_thread.deleteLater)

        self.calc_thread.start()

    def on_subnets_ready(self, minimal):
        self.subnet_txt.clear()
        for net in minimal:
            self.subnet_txt.append(str(net))

        path = os.path.join(os.path.dirname(__file__), "minimal_subnets.txt")
        with open(path, "w", encoding="utf-8") as f:
            for net in minimal:
                f.write(net + "\n")
        self.load_minimal_subnets()

    def on_subnets_error(self, msg):
        self.subnet_txt.setText(f"Ошибка: {msg}")

    def export_results(self):
        file, _ = QFileDialog.getSaveFileName(
            self, "Сохранить результаты", "", "Text Files (*.txt)"
        )
        if not file:
            return
        with open(file, "w", encoding="utf-8") as f:
            f.write("=== Результаты пинга ===\n")
            f.write(self.ping_txt.toPlainText() + "\n")
            f.write("=== Минимальные подсети ===\n")
            f.write(self.subnet_txt.toPlainText() + "\n")


# ========================
# старт приложения
# ========================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    okno = WhitelistChecker()
    okno.show()
    sys.exit(app.exec())
