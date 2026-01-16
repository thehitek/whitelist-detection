import sys
import os
import subprocess
import threading
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
    QSplitter,
    QCheckBox,
)
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QFont


class PingWorker(QThread):
    progress = Signal(int)
    result = Signal(str, bool)  # address, is_alive
    finished = Signal()

    def __init__(self, addresses, check_all_subnet_ips=False):
        super().__init__()
        self.addresses = addresses
        self.total = len(addresses)
        self.processed = 0
        self.running = True
        self.check_all_subnet_ips = check_all_subnet_ips

    def stop(self):
        self.running = False

    def run(self):
        for address in self.addresses:
            if not self.running:
                break

            is_alive = self.ping_address(address)
            self.result.emit(address, is_alive)

            self.processed += 1
            progress = int((self.processed / self.total) * 100)
            self.progress.emit(progress)

        self.finished.emit()

    def ping_address(self, address):
        try:
            # Проверяем, является ли это подсетью
            if "/" in address and not self.check_all_subnet_ips:
                # Пингуем только сетевой адрес
                network = ipaddress.ip_network(address, strict=False)
                test_ip = str(network.network_address)
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", test_ip],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                return result.returncode == 0
            elif "/" in address and self.check_all_subnet_ips:
                # Пингуем все IP в подсети
                network = ipaddress.ip_network(address, strict=False)
                for ip in network.hosts():
                    if not self.running:
                        return False
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "2", str(ip)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    if result.returncode == 0:
                        return True
                return False
            else:
                # Пингуем单个 адрес
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "2", address],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                return result.returncode == 0
        except Exception as e:
            print(f"Ошибка при пинге {address}: {e}")
            return False


class SubnetWorker(QThread):
    finished = Signal(list)  # minimal_subnets
    error = Signal(str)

    def __init__(self, alive_addresses):
        super().__init__()
        self.alive_addresses = alive_addresses

    def run(self):
        try:
            ip_addresses = []

            for address in self.alive_addresses:
                if "/" in address:
                    # Это подсеть, добавляем все IP из неё
                    try:
                        network = ipaddress.ip_network(address, strict=False)
                        ip_addresses.extend([str(ip) for ip in network.hosts()])
                    except:
                        pass
                else:
                    # Проверяем, является ли это IP-адресом
                    try:
                        ipaddress.ip_address(address)
                        ip_addresses.append(address)
                    except ValueError:
                        # Это домен, преобразуем в IP-адреса
                        try:
                            result = subprocess.run(
                                ["nslookup", address],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True
                            )
                            lines = result.stdout.split('\n')
                            for line in lines:
                                if 'Address:' in line and not line.strip().endswith('#53'):
                                    ip = line.split('Address:')[-1].strip()
                                    if ip:
                                        ip_addresses.append(ip)
                        except Exception as e:
                            print(f"Ошибка при преобразовании домена {address} в IP: {e}")

            # Формируем минимальные подсети из IP-адресов
            if ip_addresses:
                ip_set = IPSet(ip_addresses)
                ip_networks = list(ip_set.iter_cidrs())
                minimal_subnets = cidr_merge(ip_networks)
                self.finished.emit(list(minimal_subnets))
            else:
                self.finished.emit([])
        except Exception as e:
            self.error.emit(str(e))



            is_alive = self.ping_address(address)
            self.result.emit(address, is_alive)
            self.processed += 1
            if self.total > 0:
                self.progress.emit(int(self.processed / self.total * 100))

        self.finished.emit()

    def ping_address(self, address):
        try:
            # Проверяем тип адреса
            if "/" in address:
                # Это подсеть
                network = ipaddress.ip_network(address, strict=False)

                # Проверяем режим проверки
                if hasattr(self, 'check_all_subnet_ips') and self.check_all_subnet_ips:
                    # Проверяем все IP в подсети
                    for ip in network.hosts():
                        result = subprocess.run(
                            ["ping", "-c", "1", "-W", "1", str(ip)],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        if result.returncode == 0:
                            return True
                    return False
                else:
                    # Проверяем только первый и последний IP для скорости
                    first_ip = str(network[0])
                    last_ip = str(network[-1])
                    test_ips = (
                        [first_ip, last_ip] if network.num_addresses > 1 else [first_ip]
                    )
                    for ip in test_ips:
                        result = subprocess.run(
                            ["ping", "-c", "1", "-W", "1", ip],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                        )
                        if result.returncode == 0:
                            return True
                    return False
            else:
                # Проверяем, является ли это IP-адресом или доменом
                try:
                    ipaddress.ip_address(address)
                    # Это IP-адрес - уменьшаем таймаут до 1 секунды
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "1", address],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    return result.returncode == 0
                except ValueError:
                    # Это домен - уменьшаем таймаут до 1 секунды
                    result = subprocess.run(
                        ["ping", "-c", "1", "-W", "1", address],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                    return result.returncode == 0
        except Exception as e:
            print(f"Ошибка при пинге {address}: {e}")
            return False

    def stop(self):
        self.running = False


class WhitelistChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Проверка Whitelist - Russia Mobile Internet")
        self.setGeometry(100, 100, 1200, 800)

        self.addresses = []
        self.alive_addresses = []
        self.minimal_subnets = []
        self.check_all_subnet_ips = False  # По умолчанию проверяем только первый и последний IP

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # Верхняя панель с кнопками
        button_layout = QHBoxLayout()

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

        self.check_all_checkbox = QCheckBox("Проверять все IP в подсетях")
        self.check_all_checkbox.setChecked(False)
        self.check_all_checkbox.stateChanged.connect(self.toggle_check_mode)

        button_layout.addWidget(self.load_button)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.check_all_checkbox)

        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # Статус
        self.status_label = QLabel("Готов к работе")

        # Табы для отображения результатов
        self.tab_widget = QTabWidget()

        # Таб с результатами пинга
        self.ping_results = QTextEdit()
        self.ping_results.setReadOnly(True)
        self.ping_results.setFont(QFont("Courier New", 9))

        # Таб с минимальными подсетями
        self.subnet_results = QTextEdit()
        self.subnet_results.setReadOnly(True)
        self.subnet_results.setFont(QFont("Courier New", 9))

        self.tab_widget.addTab(self.ping_results, "Результаты пинга")
        self.tab_widget.addTab(self.subnet_results, "Минимальные подсети")

        # Добавляем все в основной layout
        main_layout.addLayout(button_layout)
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.tab_widget)

        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

    def toggle_check_mode(self, state):
        self.check_all_subnet_ips = (state == Qt.Checked.value)

    def load_from_repo(self):
        self.status_label.setText("Загрузка данных...")

        # Проверяем, существует ли локальная копия репозитория
        repo_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "russia-mobile-internet-whitelist",
        )

        if not os.path.exists(repo_path):
            # Клонируем репозиторий
            try:
                subprocess.run(
                    [
                        "git",
                        "clone",
                        "https://github.com/hxehex/russia-mobile-internet-whitelist.git",
                        repo_path,
                    ],
                    check=True,
                )
            except Exception as e:
                self.status_label.setText(f"Ошибка при клонировании репозитория: {e}")
                return

        # Загружаем адреса из файлов
        self.addresses = []

        # Загружаем IP-адреса и объединяем их в подсети
        ip_file = os.path.join(repo_path, "ipwhitelist.txt")
        if os.path.exists(ip_file):
            ip_addresses = []
            with open(ip_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ip_addresses.append(line)

            # Объединяем последовательные IP-адреса в подсети
            if ip_addresses:
                try:
                    ip_networks = [IPNetwork(ip) for ip in ip_addresses]
                    merged_subnets = cidr_merge(ip_networks)
                    for subnet in merged_subnets:
                        self.addresses.append(str(subnet))
                except Exception as e:
                    print(f"Ошибка при объединении IP в подсети: {e}")
                    # Если не удалось объединить, добавляем как есть
                    self.addresses.extend(ip_addresses)

        # Загружаем подсети
        subnet_file = os.path.join(repo_path, "cidrwhitelist.txt")
        if os.path.exists(subnet_file):
            with open(subnet_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.addresses.append(line)

        # Загружаем домены
        domain_file = os.path.join(repo_path, "whitelist.txt")
        if os.path.exists(domain_file):
            with open(domain_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.addresses.append(line)

        self.status_label.setText(f"Загружено {len(self.addresses)} адресов")
        self.start_button.setEnabled(True)

    def start_check(self):
        if not self.addresses:
            self.status_label.setText(
                "Нет адресов для проверки. Сначала загрузите данные."
            )
            return

        self.alive_addresses = []
        self.ping_results.clear()
        self.subnet_results.clear()
        self.progress_bar.setValue(0)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("Проверка адресов...")

        self.ping_worker = PingWorker(self.addresses, self.check_all_subnet_ips)
        self.ping_worker.progress.connect(self.update_progress)
        self.ping_worker.result.connect(self.handle_ping_result)
        self.ping_worker.finished.connect(self.check_finished)
        self.ping_worker.start()

    def stop_check(self):
        if hasattr(self, "ping_worker"):
            self.ping_worker.stop()
        self.status_label.setText("Проверка остановлена")

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def handle_ping_result(self, address, is_alive):
        if is_alive:
            self.alive_addresses.append(address)
            # Проверяем, является ли это доменом
            try:
                ipaddress.ip_address(address)
                # Это IP-адрес
                self.ping_results.append(f"✓ {address} - доступен")
            except ValueError:
                # Это домен, получаем его IP-адреса
                try:
                    result = subprocess.run(
                        ["nslookup", address],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    lines = result.stdout.split('\n')
                    ips = []
                    for line in lines:
                        if 'Address:' in line and not line.strip().endswith('#53'):
                            ip = line.split('Address:')[-1].strip()
                            if ip:
                                ips.append(ip)
                    if ips:
                        self.ping_results.append(f"✓ {address} ({', '.join(ips)}) - доступен")
                    else:
                        self.ping_results.append(f"✓ {address} - доступен")
                except Exception as e:
                    self.ping_results.append(f"✓ {address} - доступен")
        else:
            self.ping_results.append(f"✗ {address} - недоступен")

    def check_finished(self):
        self.stop_button.setEnabled(False)
        self.status_label.setText("Вычисление минимальных подсетей...")

        # Запускаем вычисление подсетей в отдельном потоке
        self.subnet_worker = SubnetWorker(self.alive_addresses)
        self.subnet_worker.finished.connect(self.on_subnets_calculated)
        self.subnet_worker.error.connect(self.on_subnet_error)
        self.subnet_worker.start()

    def on_subnets_calculated(self, minimal_subnets):
        # Обновляем результаты подсетей
        self.subnet_results.clear()
        if minimal_subnets:
            self.subnet_results.append("Минимальные подсети:")
            for subnet in minimal_subnets:
                self.subnet_results.append(f"  {subnet}")
        else:
            self.subnet_results.append("Нет доступных подсетей")

        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.export_button.setEnabled(True)

        self.status_label.setText(
            f"Проверка завершена. Доступно {len(self.alive_addresses)} из {len(self.addresses)} адресов"
        )

    def on_subnet_error(self, error_message):
        self.subnet_results.clear()
        self.subnet_results.append(f"Ошибка при вычислении подсетей: {error_message}")

        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(True)
        self.export_button.setEnabled(True)

        self.status_label.setText(
            f"Проверка завершена с ошибками. Доступно {len(self.alive_addresses)} из {len(self.addresses)} адресов"
        )

    def export_results(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить результаты",
            "",
            "Text Files (*.txt);;All Files (*)",
            options=options,
        )

        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("=== Результаты пинга ===\n")
                    f.write(self.ping_results.toPlainText())
                    f.write("\n\n=== Минимальные подсети ===\n")
                    f.write(self.subnet_results.toPlainText())

                self.status_label.setText(f"Результаты сохранены в {file_path}")
            except Exception as e:
                self.status_label.setText(f"Ошибка при сохранении: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WhitelistChecker()
    window.show()
    sys.exit(app.exec())
    setText("Проверка адресов...")

    self.ping_worker = PingWorker(self.addresses)
    self.ping_worker.progress.connect(self.update_progress)
    self.ping_worker.result.connect(self.handle_ping_result)
    self.ping_worker.finished.connect(self.check_finished)
    self.ping_worker.start()
