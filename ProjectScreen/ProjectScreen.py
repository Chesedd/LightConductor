import os.path
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QPushButton,
                            QFileDialog, QHBoxLayout,
                            QLabel, QDialog, QLineEdit)
from PyQt6.QtCore import pyqtSignal, Qt, QUrl
from PyQt6.QtGui import QAction, QKeySequence
import librosa
from ProjectScreen.SlaveBox import SlaveBox
from ProjectScreen.MasterBox import MasterBox
from ProjectScreen.WaveWidget import WaveWidget
from ProjectScreen.TagManager import TagManager
from ProjectScreen.ProjectManager import ProjectManager
from AssistanceTools.ChooseBox import  TagTypeChooseBox
import socket
import json
import time
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from datetime import datetime

class newMasterDialog(QDialog):
    masterCreated = pyqtSignal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.uiCreate()

    def uiCreate(self):
        masterNameText = QLabel("Master's name")
        self.masterNameBar = QLineEdit()
        masterNameLayout = QHBoxLayout()
        masterNameLayout.addWidget(masterNameText)
        masterNameLayout.addWidget(self.masterNameBar)

        okButton = QPushButton("Ok")
        okButton.clicked.connect(self.onOkClicked)
        cancelButton = QPushButton("Cancel")
        cancelButton.clicked.connect(self.reject)
        buttonLayout = QHBoxLayout()
        buttonLayout.addWidget(okButton)
        buttonLayout.addWidget(cancelButton)

        self.mainScreen = QWidget()
        self.mainLayout = QVBoxLayout(self.mainScreen)
        self.mainLayout.addLayout(masterNameLayout)
        self.mainLayout.addLayout(buttonLayout)

        self.setLayout(self.mainLayout)

    def onOkClicked(self):
        masterTitle = self.masterNameBar.text()
        self.masterCreated.emit(masterTitle)
        self.accept()



class ProjectWindow(QMainWindow):
    def __init__(self, project_data):
        super().__init__()
        self.masters = {}

        saveAction = QAction("Save", self)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))
        saveAction.triggered.connect(self.saveData)
        self.addAction(saveAction)

        self.project_data = project_data
        self.audio = None
        self.sr = None
        self.boxCounter = 0
        self.projectManager = ProjectManager(self.project_data['project_name'])
        self.boxes = {}
        self.audioPath = None

        self.init_ui()
        self.initExistingData()
        self.initAudioPlayer()

    def initAudioPlayer(self):
        if self.audio is not None:
            self.audioPlayer = QMediaPlayer()
            self.audioPlayer.setSource(QUrl.fromLocalFile(self.audioPath))
            self.audioOutput = QAudioOutput()
            self.audioPlayer.setAudioOutput(self.audioOutput)

    def init_ui(self):
        self.setWindowTitle(self.project_data['project_name'])
        self.setGeometry(100, 100, 1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.layout = QVBoxLayout(central_widget)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        addButton = QPushButton("Add track")
        addButton.clicked.connect(self.addTrack)
        self.layout.addWidget(addButton)

        waveButton = QPushButton("Add master")
        waveButton.clicked.connect(self.showMasterDialog)
        self.layout.addWidget(waveButton)

        loadButton = QPushButton("Load data")
        loadButton.clicked.connect(self.loadData)
        self.layout.addWidget(loadButton)

        showButton = QPushButton("Start show")
        showButton.clicked.connect(self.startShow)
        self.layout.addWidget(showButton)

    def initExistingData(self):
        self.audio, self.sr, self.audioPath = self.projectManager.loadAudioData()
        masters = self.projectManager.returnAllBoxes()
        for masterID in masters:
            master = masters[masterID]
            slaves = master['slaves']
            self.addMaster(master["name"], master["id"])
            masterWidget = self.masters[master["id"]]
            for slaveID in slaves:
                slave = slaves[slaveID]
                slaveData = {}
                slaveData["name"] = slave["name"]
                slaveData["pin"] = slave["pin"]
                tagTypes = slave['tagTypes']
                masterWidget.addSlave(slaveData, slave["id"])
                manager = self.masters[master["id"]].slaves[slave["id"]].wave.manager
                for tagType in tagTypes:
                    params = tagTypes[tagType]
                    params['name'] = tagType
                    manager.addType(params)
                    type = manager.types[params['name']]
                    print(type.table)
                    tags = []
                    for tagID in params['tags']:
                        print(params['tags'][tagID])
                        tags.append(self.masters[master["id"]].slaves[slave["id"]].wave.addExistingTag(params['tags'][tagID], type))
                    type.addExistingTags(tags)

    def saveData(self):
        print("Save")
        self.projectManager.saveAudioData(self.audio, self.sr)
        self.projectManager.saveData(self.masters)

    def addTrack(self):
        filePath, _ = QFileDialog.getOpenFileName(
            self,
            "Choose audio",
            "",
            "Аудио файлы (*.mp3, *.wav, *.flac, *.ogg, *.m4a);;Все файлы (*)"
        )
        if not os.path.exists(filePath):
            print("File not exist")
            return
        try:
            self.audioPath = filePath
            self.audio, self.sr = librosa.load(filePath, sr=None, mono=True)
        except Exception as e:
            print(e)
            return

    def showMasterDialog(self):
        dialog = newMasterDialog(self)
        dialog.masterCreated.connect(self.addMaster)
        dialog.exec()

    def addMaster(self, masterName, boxID=None):
        if boxID is None:
            boxID = datetime.now().strftime("%Y%m%d%H%M%S%f")
        master = MasterBox(title=masterName, boxID=boxID, audio=self.audio, sr=self.sr, aydioPath=self.audioPath)
        self.masters[boxID] = master
        self.layout.addWidget(master)

    def loadData(self):
        pins, data = self.dataPack()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Преобразуем данные в JSON строку
        json_str = json.dumps(data)
        pins_str = json.dumps(pins)

        # Широковещательный адрес (255.255.255.255 или сетевой broadcast)
        # Лучше использовать сетевой broadcast адрес, например: 192.168.1.255
        broadcast_address = '192.168.0.129'  # Общий broadcast

        # Альтернативно, можно рассчитать broadcast адрес сети
        # broadcast_address = '192.168.1.255'  # Для сети 192.168.1.0/24

        try:
            # Отправляем данные
            sock.sendto("pins".encode('utf-8'), (broadcast_address, 12345))
            sock.sendto(pins_str.encode('utf-8'), (broadcast_address, 12345))
            sock.sendto("partiture".encode('utf-8'), (broadcast_address, 12345))
            for slave in data:
                json_str = json.dumps(data[slave])
                sock.sendto(slave.encode('utf-8'), (broadcast_address, 12345))
                sock.sendto(json_str.encode('utf-8'), (broadcast_address, 12345))
            sock.sendto("end".encode('utf-8'), (broadcast_address, 12345))
            print(f"Sent broadcast to {broadcast_address}:{12345}")
            print(f"Data: {json_str}")
        except Exception as e:
            print(f"Error sending broadcast: {e}")
        finally:
            sock.close()

    def dataPack(self):
        data = {}
        pins = {}
        for masterID in self.masters:
            master = self.masters[masterID]
            for slaveID in master.slaves:
                slave = master.slaves[slaveID]
                data[slave.slavePin] = {}
                pins[slave.slavePin] = {}
                types = slave.wave.manager.types
                for typeName in types:
                    type = types[typeName]
                    pins[slave.slavePin][type.pin] = type.table*type.row
                    for tag in type.tags:
                        time = round(tag.time * 1000)
                        if time not in data:
                            data[slave.slavePin][time] = {}
                        data[slave.slavePin][time][type.pin] = {}
                        data[slave.slavePin][time][type.pin]["action"] = tag.action
                        data[slave.slavePin][time][type.pin]["colors"] = tag.colors
        return pins, data

    def startShow(self):
        self.audioPlayer.setPosition(0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        broadcast_address = '192.168.0.129'  # Общий broadcast

        try:
            # Отправляем данные
            sock.sendto("start".encode('utf-8'), (broadcast_address, 12345))
            print(f"Sent broadcast to {broadcast_address}:{12345}")
        except Exception as e:
            print(f"Error sending broadcast: {e}")
        finally:
            sock.close()
        self.audioPlayer.play()