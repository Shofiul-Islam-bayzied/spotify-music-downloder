import sys
import os
import subprocess
import re
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QTextEdit,
    QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

class DownloadThread(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    log = pyqtSignal(str)  # Signal to emit log messages
    total_songs_signal = pyqtSignal(int)  # Signal to emit total songs count
    downloaded_songs_signal = pyqtSignal(int)  # Signal to emit downloaded songs count

    def __init__(self, url, output_dir, concurrent_downloads=5):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.concurrent_downloads = concurrent_downloads
        self.process = None
        self._is_running = True

    def run(self):
        try:
            # Build the spotdl command with correct concurrency argument
            command = [
                "spotdl",
                self.url,
                "--output", self.output_dir,
                "--format", "mp3",               # Specify desired format
                "--threads", str(self.concurrent_downloads)  # Set concurrency level
            ]

            # Start the subprocess
            self.process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            total_songs = 0
            downloaded_songs = 0
            total_songs_set = False  # Flag to ensure total_songs is set only once

            # Regular expressions for parsing spotdl output
            found_songs_pattern = re.compile(r"Found\s+(\d+)\s+songs in .*")
            downloaded_pattern = re.compile(r'Downloaded\s+"[^"]+":')

            for line in self.process.stdout:
                if not self._is_running:
                    break  # Exit if thread is stopped

                clean_line = line.strip()
                self.log.emit(clean_line)  # Emit log lines to the GUI

                # Parsing logic based on spotdl's output
                # 1. Detect "Found X songs in ..."
                if not total_songs_set:
                    found_songs_match = found_songs_pattern.search(clean_line)
                    if found_songs_match:
                        total_songs = int(found_songs_match.group(1))
                        self.total_songs_signal.emit(total_songs)
                        total_songs_set = True
                        self.log.emit(f"Total songs found: {total_songs}")
                        continue  # Move to next line

                # 2. Detect "Downloaded "Song Name":"
                if downloaded_pattern.search(clean_line):
                    downloaded_songs += 1
                    self.downloaded_songs_signal.emit(downloaded_songs)
                    if total_songs > 0:
                        progress_percentage = int((downloaded_songs / total_songs) * 100)
                        status = f"Downloading {downloaded_songs}/{total_songs}"
                        self.progress.emit(progress_percentage, status)

            self.process.wait()

            if self._is_running:
                if self.process.returncode == 0:
                    self.finished.emit()
                else:
                    self.error.emit("An error occurred during the download process. Please check the log for details.")
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.kill()
            self.process = None
            self.finished.emit()

class SpotifyDownloaderGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.download_thread = None

    def initUI(self):
        self.setWindowTitle('Spotify Playlist Downloader')
        self.setGeometry(300, 300, 800, 600)  # Increased width and height for better layout

        layout = QVBoxLayout()

        # URL Input
        url_layout = QHBoxLayout()
        url_label = QLabel('Spotify Playlist URL:')
        self.url_entry = QLineEdit()
        self.url_entry.setPlaceholderText("Enter Spotify playlist URL here")
        self.url_entry.setToolTip("Enter the URL of the Spotify playlist you wish to download.")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_entry)
        layout.addLayout(url_layout)

        # Output Directory
        output_layout = QHBoxLayout()
        output_label = QLabel('Output Directory:')
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("Select output directory")
        self.output_entry.setToolTip("Select the directory where downloaded songs will be saved.")
        self.browse_button = QPushButton('Browse')
        self.browse_button.setToolTip("Browse to select the output directory.")
        self.browse_button.clicked.connect(self.browse_directory)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_entry)
        output_layout.addWidget(self.browse_button)
        layout.addLayout(output_layout)

        # Download Button
        self.download_button = QPushButton('Download Playlist')
        self.download_button.setToolTip("Click to start downloading the playlist.")
        self.download_button.clicked.connect(self.start_download)
        layout.addWidget(self.download_button)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setToolTip("Shows the download progress.")
        layout.addWidget(self.progress_bar)

        # Status Label
        self.status_label = QLabel('')
        self.status_label.setToolTip("Displays the current status of the download.")
        layout.addWidget(self.status_label)

        # Song Count Indicators
        song_count_layout = QHBoxLayout()
        self.total_songs_label = QLabel('Total Songs: 0')
        self.total_songs_label.setToolTip("Total number of songs in the playlist.")
        self.downloaded_songs_label = QLabel('Downloaded Songs: 0')
        self.downloaded_songs_label.setToolTip("Number of songs downloaded so far.")
        song_count_layout.addWidget(self.total_songs_label)
        song_count_layout.addWidget(self.downloaded_songs_label)
        layout.addLayout(song_count_layout)

        # Cancel Button
        self.cancel_button = QPushButton('Cancel')
        self.cancel_button.setToolTip("Click to cancel the ongoing download.")
        self.cancel_button.clicked.connect(self.cancel_download)
        self.cancel_button.setEnabled(False)
        layout.addWidget(self.cancel_button)

        # Live Log View
        log_label = QLabel('Download Log:')
        layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.NoWrap)
        self.log_view.setStyleSheet("background-color: #f0f0f0;")
        self.log_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.log_view.setToolTip("Displays real-time logs of the download process.")
        layout.addWidget(self.log_view)

        self.setLayout(layout)

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_entry.setText(directory)

    def is_spotdl_installed(self):
        try:
            result = subprocess.run(["spotdl", "--version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            version = result.stdout.decode().strip()
            self.log_view.append(f"spotdl is installed: {version}")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def start_download(self):
        url = self.url_entry.text().strip()
        output_dir = self.output_entry.text().strip()

        if not url:
            QMessageBox.warning(self, "Input Error", "Please enter a Spotify playlist URL.")
            return

        if not output_dir:
            QMessageBox.warning(self, "Input Error", "Please select an output directory.")
            return

        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "Directory Error", "The selected output directory does not exist.")
            return

        # Verify spotdl is installed
        if not self.is_spotdl_installed():
            QMessageBox.critical(self, "Error", "spotdl is not installed or not found in PATH.")
            self.log_view.append("Error: spotdl is not installed or not found in PATH.")
            return

        self.download_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting download...")
        self.log_view.clear()
        self.total_songs_label.setText('Total Songs: 0')
        self.downloaded_songs_label.setText('Downloaded Songs: 0')

        # Initialize DownloadThread with desired concurrency
        concurrent_downloads = 5  # You can adjust this value or make it user-configurable
        self.download_thread = DownloadThread(url, output_dir, concurrent_downloads)
        self.download_thread.progress.connect(self.update_progress)
        self.download_thread.finished.connect(self.download_complete)
        self.download_thread.error.connect(self.download_error)
        self.download_thread.log.connect(self.append_log)  # Connect log signal
        self.download_thread.total_songs_signal.connect(self.update_total_songs)  # Connect total songs signal
        self.download_thread.downloaded_songs_signal.connect(self.update_downloaded_songs)  # Connect downloaded songs signal
        self.download_thread.start()

    def update_progress(self, value, status):
        self.progress_bar.setValue(value)
        self.status_label.setText(status)

    def update_total_songs(self, total):
        self.total_songs_label.setText(f'Total Songs: {total}')

    def update_downloaded_songs(self, downloaded):
        self.downloaded_songs_label.setText(f'Downloaded Songs: {downloaded}')

    def download_complete(self):
        self.status_label.setText("Download complete!")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        QMessageBox.information(self, "Success", "Playlist downloaded successfully!")

    def download_error(self, error_message):
        self.status_label.setText("Download failed.")
        self.download_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.log_view.append(f"Error: {error_message}")
        QMessageBox.critical(self, "Error", f"An error occurred: {error_message}")

    def append_log(self, message):
        """
        Append log messages to the log view.
        """
        self.log_view.append(message)
        # Auto-scroll to the bottom
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def cancel_download(self):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                'Cancel Download',
                "Are you sure you want to cancel the download?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.download_thread.stop()
                self.status_label.setText("Download cancelled.")
                self.download_button.setEnabled(True)
                self.cancel_button.setEnabled(False)
                self.log_view.append("Download has been cancelled.")
                QMessageBox.information(self, "Cancelled", "Download has been cancelled.")

    def closeEvent(self, event):
        if self.download_thread and self.download_thread.isRunning():
            reply = QMessageBox.question(
                self,
                'Exit',
                "A download is in progress. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.download_thread.stop()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = SpotifyDownloaderGUI()
    ex.show()
    sys.exit(app.exec())
